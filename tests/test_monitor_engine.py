"""Monitor engine intersection and cooldown."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.monitor.engine import MonitorEngine


@pytest.mark.unit
@pytest.mark.asyncio
async def test_empty_watchlist_skips():
    worker = MagicMock()
    engine = MonitorEngine(worker, {}, state_store=None)
    engine.watchlist.set_tickers([])
    out = await engine.tick_once()
    assert out.get("message") == "empty watchlist"


@pytest.mark.unit
def test_cooldown_blocks_repeat():
    worker = MagicMock()
    engine = MonitorEngine(worker, {}, state_store=None)
    engine._cooldown["AAPL"] = datetime.now(timezone.utc)
    assert engine._in_cooldown("AAPL", 30) is True
    engine._cooldown["AAPL"] = datetime.now(timezone.utc) - timedelta(minutes=60)
    assert engine._in_cooldown("AAPL", 30) is False
