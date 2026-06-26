"""Notification layer: multi-channel delivery via Apprise + custom HTTP.

Extended from PanWatch (MIT) to add DingTalk, Feishu/Lark, Pushover,
Bark, WeChat Work, ServerChan, and PushPlus channels.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, time, timezone
from typing import Any, Optional

import apprise
import httpx

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
                if channel.type in _CUSTOM_TYPES:
                    return await _send_custom(channel, title, body)
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

_APPRISE_TYPES = {"telegram", "bark", "dingtalk", "lark", "discord", "pushover"}
_CUSTOM_TYPES = {"wecom", "serverchan", "pushplus"}


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
    if t == "dingtalk":
        token = (cfg.get("token") or "").strip()
        secret = (cfg.get("secret") or "").strip()
        if not token:
            return None
        if secret:
            return f"dingtalk://{secret}@{token}/"
        return f"dingtalk://{token}/"
    if t == "lark":
        webhook_token = (cfg.get("webhook_token") or "").strip()
        if not webhook_token:
            return None
        return f"lark://{webhook_token}/"
    if t == "pushover":
        user_key = cfg.get("user_key")
        app_token = cfg.get("app_token")
        if not user_key or not app_token:
            return None
        return f"pover://{user_key}@{app_token}/"
    if t == "bark":
        device_key = cfg.get("device_key")
        server_url = cfg.get("server_url", "").strip("/")
        if not device_key:
            return None
        if server_url:
            host = server_url.replace("https://", "").replace("http://", "")
            return f"bark://{host}/{device_key}/"
        return f"bark://{device_key}/"
    return None


# ------------------------------------------------------------------ custom channel senders

async def _send_custom(channel: NotificationChannel, title: str, body: str) -> dict[str, Any]:
    t = channel.type
    cfg = channel.config or {}
    if t == "wecom":
        return await _send_wecom(cfg, title, body)
    if t == "serverchan":
        return await _send_serverchan(cfg, title, body)
    if t == "pushplus":
        return await _send_pushplus(cfg, title, body)
    return {"ok": False, "error": f"unsupported custom type: {t}"}


async def _send_wecom(config: dict, title: str, body: str) -> dict[str, Any]:
    """WeChat Work (企业微信) robot webhook."""
    key = (config.get("webhook_key") or "").strip()
    if not key:
        return {"ok": False, "error": "missing webhook_key"}

    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}"
    text = f"## {title}\n\n{body}" if title else body
    payload = {"msgtype": "markdown", "markdown": {"content": text}}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    if data.get("errcode") != 0:
        return {"ok": False, "error": data.get("errmsg", "unknown")}
    return {"ok": True}


async def _send_serverchan(config: dict, title: str, body: str) -> dict[str, Any]:
    """ServerChan push notification."""
    sendkey = (config.get("sendkey") or "").strip()
    if not sendkey:
        return {"ok": False, "error": "missing sendkey"}

    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    payload = {"title": title or "Notification", "desp": body}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    if data.get("code") != 0:
        return {"ok": False, "error": data.get("message", "unknown")}
    return {"ok": True}


async def _send_pushplus(config: dict, title: str, body: str) -> dict[str, Any]:
    """PushPlus push notification."""
    token = (config.get("token") or "").strip()
    if not token:
        return {"ok": False, "error": "missing token"}

    url = "https://www.pushplus.plus/send"
    payload = {
        "token": token,
        "title": title or "Notification",
        "content": body,
        "template": "markdown",
    }
    topic = (config.get("topic") or "").strip()
    if topic:
        payload["topic"] = topic

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    if data.get("code") != 200:
        return {"ok": False, "error": data.get("msg", "unknown")}
    return {"ok": True}
