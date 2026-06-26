"""Price alert engine: rule evaluation, persistence, and background polling.

Adapted from PanWatch's price_alert_engine.py (MIT).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from api.price_alerts.models import (
    AlertCondition,
    ConditionGroup,
    PriceAlertHit,
    PriceAlertRule,
)

logger = logging.getLogger(__name__)

_engine: Optional["PriceAlertEngine"] = None

DATA_DIR = Path(os.environ.get("TRADINGAGENTS_DATA_DIR", "./data"))
RULES_FILE = DATA_DIR / "price_alert_rules.json"
HITS_FILE = DATA_DIR / "price_alert_hits.json"


def get_engine() -> "PriceAlertEngine":
    global _engine
    if _engine is None:
        _engine = PriceAlertEngine()
    return _engine


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _op_eval(left: float | None, op: str, value: Any) -> bool:
    if left is None:
        return False
    o = op.strip().lower()
    if o == "between":
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            return False
        lo = _safe_float(value[0])
        hi = _safe_float(value[1])
        if lo is None or hi is None:
            return False
        return lo <= left <= hi
    rv = _safe_float(value)
    if rv is None:
        return False
    if o == ">":
        return left > rv
    if o == ">=":
        return left >= rv
    if o == "<":
        return left < rv
    if o == "<=":
        return left <= rv
    if o in ("=", "=="):
        return left == rv
    if o in ("!=", "<>"):
        return left != rv
    return False


def _fetch_quote(ticker: str) -> dict[str, Any]:
    """Fetch current quote for a ticker via yfinance."""
    import yfinance as yf

    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}
        hist = tk.history(period="2d")
    except Exception as exc:
        logger.debug("yfinance quote failed for %s: %s", ticker, exc)
        return {}

    current_price = _safe_float(info.get("currentPrice") or info.get("regularMarketPrice"))
    prev_close = _safe_float(info.get("regularMarketPreviousClose") or info.get("previousClose"))
    change_pct = None
    if current_price is not None and prev_close is not None and prev_close != 0:
        change_pct = (current_price - prev_close) / prev_close * 100

    volume = _safe_float(info.get("volume") or info.get("regularMarketVolume"))
    turnover = None
    if current_price is not None and volume is not None:
        turnover = current_price * volume

    volume_ratio = None
    if hist is not None and not hist.empty and len(hist) >= 2:
        avg_vol = hist["Volume"].iloc[:-1].mean()
        if avg_vol > 0 and volume is not None:
            volume_ratio = volume / avg_vol

    return {
        "current_price": current_price,
        "change_pct": change_pct,
        "volume": volume,
        "volume_ratio": volume_ratio,
        "turnover": turnover,
        "prev_close": prev_close,
    }


def _eval_condition(cond: AlertCondition, quote: dict) -> tuple[bool, dict]:
    left: float | None = None
    if cond.type == "price":
        left = quote.get("current_price")
    elif cond.type == "change_pct":
        left = quote.get("change_pct")
    elif cond.type == "volume":
        left = quote.get("volume")
    elif cond.type == "turnover":
        left = quote.get("turnover")
    elif cond.type == "volume_ratio":
        left = quote.get("volume_ratio")

    ok = _op_eval(left, cond.op, cond.value)
    return ok, {
        "type": cond.type,
        "op": cond.op,
        "target": cond.value,
        "actual": left,
        "matched": ok,
    }


def _eval_condition_group(group: ConditionGroup, quote: dict) -> tuple[bool, list[dict]]:
    results: list[dict] = []
    bools: list[bool] = []
    for cond in group.items:
        ok, detail = _eval_condition(cond, quote)
        results.append(detail)
        bools.append(ok)

    if not bools:
        return False, results
    if group.op == "or":
        return any(bools), results
    return all(bools), results


class PriceAlertEngine:
    """Price alert engine: CRUD, evaluation, polling, notification."""

    def __init__(self):
        self._rules: dict[str, PriceAlertRule] = {}
        self._hits: list[PriceAlertHit] = []
        self._trigger_counts: dict[str, int] = {}  # rule_id -> count today
        self._trigger_date: str = ""
        self._task: Optional[asyncio.Task] = None
        self._last_tick: Optional[str] = None
        self._load()

    # ------------------------------------------------------------------ persistence

    def _rules_path(self) -> Path:
        return RULES_FILE

    def _hits_path(self) -> Path:
        return HITS_FILE

    def _load(self) -> None:
        self._rules = {}
        self._hits = []
        try:
            p = self._rules_path()
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                for d in data:
                    r = PriceAlertRule.model_validate(d)
                    self._rules[r.id] = r
        except Exception as exc:
            logger.warning("Failed to load price alert rules: %s", exc)

        try:
            p = self._hits_path()
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                self._hits = [PriceAlertHit.model_validate(d) for d in data]
        except Exception as exc:
            logger.warning("Failed to load price alert hits: %s", exc)

    def _save_rules(self) -> None:
        p = self._rules_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        data = [r.model_dump(mode="json") for r in self._rules.values()]
        p.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def _save_hits(self) -> None:
        p = self._hits_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        data = [h.model_dump(mode="json") for h in self._hits]
        p.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    # ------------------------------------------------------------------ CRUD

    def list_rules(self) -> list[PriceAlertRule]:
        return list(self._rules.values())

    def get_rule(self, rule_id: str) -> Optional[PriceAlertRule]:
        return self._rules.get(rule_id)

    def create_rule(self, rule: PriceAlertRule) -> PriceAlertRule:
        rule.created_at = _utc_now()
        rule.updated_at = _utc_now()
        self._rules[rule.id] = rule
        self._save_rules()
        return rule

    def update_rule(self, rule_id: str, updates: dict) -> Optional[PriceAlertRule]:
        rule = self._rules.get(rule_id)
        if rule is None:
            return None
        for key, val in updates.items():
            if val is not None and hasattr(rule, key):
                setattr(rule, key, val)
        rule.updated_at = _utc_now()
        self._save_rules()
        return rule

    def delete_rule(self, rule_id: str) -> bool:
        if rule_id not in self._rules:
            return False
        del self._rules[rule_id]
        self._save_rules()
        return True

    def list_hits(self, limit: int = 50) -> list[PriceAlertHit]:
        return sorted(self._hits, key=lambda h: h.triggered_at, reverse=True)[:limit]

    def clear_hits(self) -> None:
        self._hits.clear()
        self._save_hits()

    def status(self) -> dict[str, Any]:
        today = _utc_now().strftime("%Y-%m-%d")
        return {
            "enabled": self._task is not None and not self._task.done(),
            "rules_count": len(self._rules),
            "hits_count": len(self._hits),
            "last_tick": self._last_tick,
            "active_rules": sum(1 for r in self._rules.values() if r.enabled),
            "trigger_date": today,
        }

    # ------------------------------------------------------------------ evaluation

    def _can_trigger(self, rule: PriceAlertRule, now: datetime) -> tuple[bool, str]:
        if not rule.enabled:
            return False, "disabled"
        if rule.expire_at:
            exp = rule.expire_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if now > exp:
                return False, "expired"
        if rule.repeat_mode == "once" and rule.id in [h.rule_id for h in self._hits]:
            return False, "once_triggered"
        today = now.strftime("%Y-%m-%d")
        if today != self._trigger_date:
            self._trigger_date = today
            self._trigger_counts.clear()
        if rule.max_triggers_per_day > 0:
            count = self._trigger_counts.get(rule.id, 0)
            if count >= rule.max_triggers_per_day:
                return False, "daily_limit"
        return True, "ok"

    def tick(self) -> dict[str, Any]:
        """Evaluate all enabled rules against current quotes.

        Returns summary of triggered rules.
        """
        now = _utc_now()
        triggered: list[dict] = []
        errors: list[str] = []

        enabled_rules = [r for r in self._rules.values() if r.enabled]
        if not enabled_rules:
            self._last_tick = now.isoformat()
            return {"triggered": 0, "total": 0, "errors": errors}

        for rule in enabled_rules:
            can, reason = self._can_trigger(rule, now)
            if not can:
                continue

            quote = _fetch_quote(rule.ticker)
            if not quote.get("current_price"):
                logger.debug("No quote for %s, skipping rule %s", rule.ticker, rule.id)
                continue

            matched, details = _eval_condition_group(rule.condition_group, quote)
            if not matched:
                continue

            price = quote.get("current_price")
            chg = quote.get("change_pct")
            hit = PriceAlertHit(
                rule_id=rule.id,
                ticker=rule.ticker,
                price=price,
                change_pct=chg,
                snapshot={
                    "conditions": details,
                    "quote": {
                        "current_price": price,
                        "change_pct": chg,
                        "volume": quote.get("volume"),
                        "turnover": quote.get("turnover"),
                    },
                },
            )
            self._hits.append(hit)
            today_key = now.strftime("%Y-%m-%d")
            self._trigger_counts[rule.id] = self._trigger_counts.get(rule.id, 0) + 1

            try:
                import asyncio
                notify_ok, notify_err = asyncio.run(
                    _send_notification(rule, hit)
                )
                hit.notified = notify_ok
                hit.notify_error = notify_err
            except Exception as exc:
                hit.notified = False
                hit.notify_error = str(exc)

            triggered.append({
                "rule_id": rule.id,
                "rule_name": rule.name,
                "ticker": rule.ticker,
                "price": price,
                "change_pct": chg,
                "notified": hit.notified,
                "notify_error": hit.notify_error,
            })

        if triggered:
            self._save_hits()

        self._last_tick = now.isoformat()
        return {
            "triggered": len(triggered),
            "total": len(enabled_rules),
            "errors": errors,
            "items": triggered,
        }

    # ------------------------------------------------------------------ background loop

    async def start(self, interval_seconds: int = 300) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop(interval_seconds))

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self, interval: int) -> None:
        while True:
            try:
                self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Price alert loop error: %s", exc)
            await asyncio.sleep(interval)


async def _send_notification(rule: PriceAlertRule, hit: PriceAlertHit) -> tuple[bool, str]:
    """Send notification for a triggered alert."""
    from api.notifications import get_manager

    title = f"Price Alert: {rule.ticker} ({rule.name})"
    price_str = f"{hit.price:.2f}" if hit.price is not None else "--"
    chg_str = f"{hit.change_pct:+.2f}%" if hit.change_pct is not None else "--"
    body = (
        f"Rule: {rule.name}\n"
        f"Ticker: {rule.ticker}\n"
        f"Price: {price_str} ({chg_str})\n"
        f"Triggered: {hit.triggered_at.isoformat()}"
    )

    result = await get_manager().send(title=title, body=body, tags=["price_alert", rule.ticker])
    if result.get("sent"):
        return True, ""
    reason = result.get("reason") or str(result.get("errors", ""))
    return False, reason
