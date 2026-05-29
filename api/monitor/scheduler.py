"""US extended-hours session detection (ET)."""

from __future__ import annotations

from datetime import datetime, time
from enum import Enum
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")


class SessionKind(str, Enum):
    closed = "closed"
    premarket = "premarket"
    regular = "regular"
    overnight = "overnight"


def us_session_now(when: datetime | None = None) -> SessionKind:
    """Return session kind for US equities at ``when`` (default: now UTC)."""
    dt = when or datetime.now(_ET)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_ET)
    else:
        dt = dt.astimezone(_ET)
    t = dt.time()
    # Pre-market 04:00–09:30 ET
    if time(4, 0) <= t < time(9, 30):
        return SessionKind.premarket
    # Regular 09:30–16:00 ET
    if time(9, 30) <= t < time(16, 0):
        return SessionKind.regular
    # Overnight / after-hours 20:00–04:00 ET (wraps midnight)
    if t >= time(20, 0) or t < time(4, 0):
        return SessionKind.overnight
    return SessionKind.closed


def monitor_should_poll(when: datetime | None = None) -> bool:
    """Poll during pre-market and overnight only (daily barbell focus)."""
    kind = us_session_now(when)
    return kind in (SessionKind.premarket, SessionKind.overnight)
