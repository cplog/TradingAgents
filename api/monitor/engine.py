"""Background monitor loop: AKShare scan ∩ watchlist → daily BTC → scan jobs."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from tradingagents.dataflows.akshare_monitor import scan_us_panic_candidates
from tradingagents.dataflows.config import get_config, set_config
from tradingagents.dataflows.daily_signals import compute_overnight_signal
from tradingagents.default_config import build_fresh_config

from .scheduler import monitor_should_poll, us_session_now
from .triggers import trigger_scan_job
from .watchlist import get_watchlist

logger = logging.getLogger(__name__)

_engine: Optional["MonitorEngine"] = None


def get_monitor_engine(worker=None, service_config=None, state_store=None) -> Optional[MonitorEngine]:
    global _engine
    if worker is not None and service_config is not None:
        _engine = MonitorEngine(worker, service_config, state_store)
    return _engine


class MonitorEngine:
    def __init__(self, worker, service_config: dict, state_store=None):
        self.worker = worker
        self.service_config = service_config
        self.watchlist = get_watchlist(state_store)
        self._cooldown: Dict[str, datetime] = {}
        self._task: Optional[asyncio.Task] = None
        self._last_tick: Optional[str] = None
        self._last_errors: List[str] = []
        self._last_candidates: List[str] = []

    def status(self) -> dict[str, Any]:
        cfg = build_fresh_config()
        return {
            "enabled": bool(cfg.get("monitor_enabled")),
            "session": us_session_now().value,
            "should_poll": monitor_should_poll(),
            "poll_seconds": int(cfg.get("monitor_poll_seconds", 900)),
            "threshold": int(cfg.get("monitor_signal_threshold", 75)),
            "watchlist": self.watchlist.list_tickers(),
            "last_tick": self._last_tick,
            "last_candidates": self._last_candidates,
            "last_errors": self._last_errors[-5:],
            "cooldown_tickers": list(self._cooldown.keys()),
        }

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def tick_once(self) -> dict[str, Any]:
        return await self._run_scan()

    async def _loop(self) -> None:
        cfg = build_fresh_config()
        interval = max(60, int(cfg.get("monitor_poll_seconds", 900)))
        consecutive_errors = 0
        while True:
            try:
                if bool(build_fresh_config().get("monitor_enabled")) and monitor_should_poll():
                    await self._run_scan()
                    consecutive_errors = 0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                consecutive_errors += 1
                # Only log every error for the first 3 failures, then throttle
                if consecutive_errors <= 3:
                    logger.exception("monitor loop error: %s", exc)
                elif consecutive_errors % 10 == 0:
                    logger.error(
                        "monitor loop still failing (%d consecutive errors): %s",
                        consecutive_errors,
                        exc,
                    )
                self._last_errors.append(str(exc))
            await asyncio.sleep(interval)

    async def _run_scan(self) -> dict[str, Any]:
        from api.notifications import get_manager

        self._last_tick = datetime.now(timezone.utc).isoformat()
        self._last_errors = []
        triggered: List[str] = []
        cfg = build_fresh_config()
        threshold = int(cfg.get("monitor_signal_threshold", 75))
        cooldown_min = int(cfg.get("monitor_cooldown_minutes", 30))
        min_drop = float(cfg.get("monitor_min_drop_pct", -10.0))
        watch = set(self.watchlist.list_tickers())
        if not watch:
            self._last_candidates = []
            return {"triggered": [], "message": "empty watchlist"}

        loop = asyncio.get_running_loop()
        try:
            candidates = await loop.run_in_executor(
                None, lambda: scan_us_panic_candidates(min_drop_pct=min_drop)
            )
        except Exception as exc:
            self._last_errors.append(f"akshare scan: {exc}")
            return {"triggered": [], "error": str(exc)}

        hits = [c for c in candidates if c.get("ticker") in watch]
        self._last_candidates = [h["ticker"] for h in hits]

        today = datetime.utcnow().strftime("%Y-%m-%d")
        for row in hits:
            ticker = str(row.get("ticker") or "")
            if not ticker or self._in_cooldown(ticker, cooldown_min):
                continue
            try:
                set_config(self.service_config)
                signal = await loop.run_in_executor(
                    None,
                    lambda t=ticker, spot=row: compute_overnight_signal(
                        t, trade_date=today, spot=spot
                    ),
                )
            except Exception as exc:
                self._last_errors.append(f"{ticker}: {exc}")
                continue
            if signal.score < threshold:
                continue
            job_id = await trigger_scan_job(
                self.worker,
                ticker=ticker,
                date=today,
                base_config=self.service_config,
                signal=signal,
            )
            self._cooldown[ticker] = datetime.now(timezone.utc)
            record = {
                "ticker": ticker,
                "score": signal.score,
                "job_id": job_id,
                "at": self._last_tick,
                "change_pct": signal.change_pct,
            }
            self.watchlist.append_signal(record)
            await get_manager().send(
                title=f"Monitor alert: {ticker}",
                body=(
                    f"Overnight panic signal detected for {ticker}.\n"
                    f"Score: {signal.score}, change: {signal.change_pct:.2f}%\n"
                    f"Job: {job_id}"
                ),
                tags=["monitor", ticker],
            )
            triggered.append(ticker)

        return {"triggered": triggered, "candidates": self._last_candidates}

    def _in_cooldown(self, ticker: str, minutes: int) -> bool:
        last = self._cooldown.get(ticker)
        if last is None:
            return False
        return datetime.now(timezone.utc) - last < timedelta(minutes=minutes)
