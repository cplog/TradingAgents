"""Notification layer: multi-channel delivery via Apprise."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timezone
from typing import Any, Optional

import apprise

from api.models import (
    NotificationChannel,
    NotificationConfig,
    NotificationStatus,
)
from api.state_store import get_state_store

logger = logging.getLogger(__name__)

STATE_KEY_NOTIFICATIONS = "notifications_config"

_manager: Optional["NotificationManager"] = None


class NotificationManager:
    """Async notification dispatcher with quiet hours, dedupe, and Apprise backends."""

    def __init__(self, store=None) -> None:
        self._store = store or get_state_store()
        self._config = self._load_config()
        self._dedupe: dict[str, datetime] = {}
        self._lock = asyncio.Lock()
        self._sem = asyncio.Semaphore(5)

    # ------------------------------------------------------------------ config
    def _load_config(self) -> NotificationConfig:
        raw = self._store.get_json(STATE_KEY_NOTIFICATIONS)
        if not isinstance(raw, dict):
            return NotificationConfig()
        try:
            return NotificationConfig.model_validate(raw)
        except Exception as exc:
            logger.warning("Invalid notification config in state store: %s", exc)
            return NotificationConfig()

    def _save_config(self) -> None:
        self._store.put_json(STATE_KEY_NOTIFICATIONS, self._config.model_dump(mode="json"))

    def get_config(self) -> NotificationConfig:
        return self._config

    def put_config(self, config: NotificationConfig) -> None:
        self._config = config
        self._save_config()

    def status(self) -> NotificationStatus:
        return NotificationStatus(
            enabled=self._config.enabled and any(c.enabled for c in self._config.channels),
            channel_count=len(self._config.channels),
            channel_types=sorted({c.type for c in self._config.channels}),
            quiet_hours=_fmt_quiet_hours(self._config.quiet_hours_start, self._config.quiet_hours_end),
            dedupe_minutes=self._config.dedupe_minutes,
        )

    # ------------------------------------------------------------------ delivery
    async def send(
        self,
        title: str,
        body: str,
        tags: Optional[list[str]] = None,
        force: bool = False,
    ) -> dict[str, Any]:
        if not self._config.enabled:
            return {"sent": False, "reason": "disabled"}

        channels = [c for c in self._config.channels if c.enabled]
        if not channels:
            return {"sent": False, "reason": "no_enabled_channels"}

        if not force and _is_quiet_hours(self._config.quiet_hours_start, self._config.quiet_hours_end):
            return {"sent": False, "reason": "quiet_hours"}

        dedupe_key = _dedupe_key(title, body, tags)
        if not force and _is_dup(dedupe_key, self._dedupe, self._config.dedupe_minutes):
            return {"sent": False, "reason": "deduped"}

        self._dedupe[dedupe_key] = datetime.now(timezone.utc)
        self._prune_dedupe()

        results = await asyncio.gather(
            *[self._send_one_channel(c, title, body) for c in channels],
            return_exceptions=True,
        )

        ok = sum(1 for r in results if isinstance(r, dict) and r.get("ok"))
        errors = [
            {"channel": channels[i].id, "error": str(r)}
            for i, r in enumerate(results)
            if isinstance(r, Exception)
        ]
        return {"sent": ok > 0, "ok_count": ok, "total": len(channels), "errors": errors}

    async def _send_one_channel(
        self, channel: NotificationChannel, title: str, body: str
    ) -> dict[str, Any]:
        async with self._sem:
            try:
                return await asyncio.to_thread(_deliver_sync, channel, title, body)
            except Exception as exc:
                logger.exception("Failed to send notification to %s", channel.id)
                raise

    async def test_channel(self, channel_id: str, message: str) -> dict[str, Any]:
        channel = next((c for c in self._config.channels if c.id == channel_id), None)
        if channel is None:
            return {"ok": False, "error": "channel_not_found"}
        try:
            return await self._send_one_channel(channel, "TradingAgents test", message)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ------------------------------------------------------------------ cleanup
    def _prune_dedupe(self) -> None:
        now = datetime.now(timezone.utc)
        cutoff = now.timestamp() - 86400
        stale = [k for k, v in self._dedupe.items() if v.timestamp() < cutoff]
        for k in stale:
            self._dedupe.pop(k, None)


def get_manager() -> NotificationManager:
    global _manager
    if _manager is None:
        _manager = NotificationManager()
    return _manager


def reset_manager_for_tests() -> None:
    global _manager
    _manager = None


# ------------------------------------------------------------------ helpers

def _fmt_quiet_hours(start: Optional[str], end: Optional[str]) -> Optional[str]:
    if start and end:
        return f"{start}-{end}"
    return None


def _is_quiet_hours(start: Optional[str], end: Optional[str]) -> bool:
    if not start or not end:
        return False
    try:
        now = datetime.now(timezone.utc)
        t = now.time()
        s = time.fromisoformat(start)
        e = time.fromisoformat(end)
    except Exception:
        return False
    if s < e:
        return s <= t < e
    return t >= s or t < e


def _dedupe_key(title: str, body: str, tags: Optional[list[str]]) -> str:
    parts = [title.strip().lower(), body.strip().lower()]
    if tags:
        parts.extend(sorted(tags))
    return "|".join(parts)


def _is_dup(key: str, dedupe: dict[str, datetime], minutes: int) -> bool:
    if minutes <= 0:
        return False
    last = dedupe.get(key)
    if last is None:
        return False
    return (datetime.now(timezone.utc) - last).total_seconds() < minutes * 60


# ------------------------------------------------------------------ Apprise delivery

def _deliver_sync(channel: NotificationChannel, title: str, body: str) -> dict[str, Any]:
    apobj = apprise.Apprise()
    uri = _build_apprise_uri(channel)
    if not uri:
        return {"ok": False, "error": "invalid_channel_config"}
    apobj.add(uri)
    ok = apobj.notify(body=body, title=title)
    return {"ok": bool(ok)}


def _build_apprise_uri(channel: NotificationChannel) -> Optional[str]:
    cfg = channel.config or {}
    t = channel.type
    if t == "webhook":
        url = cfg.get("url")
        if not url:
            return None
        method = cfg.get("method", "POST")
        if method.upper() == "GET":
            return f"json://{url.lstrip('https://').lstrip('http://')}?method=GET"
        return f"json://{url.lstrip('https://').lstrip('http://')}"
    if t == "telegram":
        token = cfg.get("bot_token")
        chat_id = cfg.get("chat_id")
        if not token or not chat_id:
            return None
        return f"tgram://{token}/{chat_id}"
    if t == "slack":
        webhook = cfg.get("webhook_url")
        if webhook:
            return webhook
        token = cfg.get("token")
        channel_id = cfg.get("channel_id")
        if token and channel_id:
            return f"slack://{token}/#{channel_id}"
        return None
    if t == "email":
        user = cfg.get("smtp_user")
        password = cfg.get("smtp_password")
        host = cfg.get("smtp_host")
        port = cfg.get("smtp_port", 587)
        to = cfg.get("to")
        if not user or not host or not to:
            return None
        return f"mailto://{user}:{password}@{host}:{port}/?to={to}"
    if t == "discord":
        webhook = cfg.get("webhook_url")
        if not webhook:
            return None
        return webhook
    return None
