"""Server-side monitor watchlist persisted via StateStore or local JSON."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional

from tradingagents.default_config import DEFAULT_CONFIG

logger = logging.getLogger(__name__)

_WATCHLIST_KEY = "monitor:watchlist"
_SIGNALS_KEY = "monitor:signals"


def _local_path() -> Path:
    base = Path(DEFAULT_CONFIG.get("data_cache_dir") or Path.home() / ".tradingagents" / "cache")
    base.mkdir(parents=True, exist_ok=True)
    return base / "monitor_watchlist.json"


class MonitorWatchlist:
    def __init__(self, state_store=None):
        self._store = state_store

    def list_tickers(self) -> List[str]:
        raw = self._load()
        tickers = raw.get("tickers") if isinstance(raw, dict) else None
        if not isinstance(tickers, list):
            return []
        return sorted({str(t).strip().upper() for t in tickers if str(t).strip()})

    def set_tickers(self, tickers: List[str]) -> List[str]:
        clean = sorted({t.strip().upper() for t in tickers if t and t.strip()})
        self._save({"tickers": clean})
        return clean

    def add(self, ticker: str) -> List[str]:
        sym = ticker.strip().upper()
        current = self.list_tickers()
        if sym and sym not in current:
            current.append(sym)
        return self.set_tickers(current)

    def remove(self, ticker: str) -> List[str]:
        sym = ticker.strip().upper()
        return self.set_tickers([t for t in self.list_tickers() if t != sym])

    def append_signal(self, record: dict, *, max_items: int = 200) -> None:
        raw = self._load()
        signals = raw.get("signals") if isinstance(raw, dict) else []
        if not isinstance(signals, list):
            signals = []
        signals.insert(0, record)
        raw = raw if isinstance(raw, dict) else {}
        raw["signals"] = signals[:max_items]
        if "tickers" not in raw:
            raw["tickers"] = self.list_tickers()
        self._save(raw)

    def list_signals(self, limit: int = 50) -> list:
        raw = self._load()
        signals = raw.get("signals") if isinstance(raw, dict) else []
        if not isinstance(signals, list):
            return []
        return signals[:limit]

    def _load(self) -> dict:
        if self._store is not None:
            try:
                data = self._store.get_json(_WATCHLIST_KEY)
                if isinstance(data, dict):
                    return data
            except Exception as exc:
                logger.warning("monitor watchlist state get failed: %s", exc)
        path = _local_path()
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {"tickers": [], "signals": []}
        return {"tickers": [], "signals": []}

    def _save(self, data: dict) -> None:
        if self._store is not None:
            try:
                self._store.put_json(_WATCHLIST_KEY, data)
            except Exception as exc:
                logger.warning("monitor watchlist state put failed: %s", exc)
        try:
            _local_path().write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("monitor watchlist file write failed: %s", exc)


_monitor_watchlist: Optional[MonitorWatchlist] = None


def get_watchlist(state_store=None) -> MonitorWatchlist:
    global _monitor_watchlist
    if _monitor_watchlist is None or state_store is not None:
        _monitor_watchlist = MonitorWatchlist(state_store=state_store)
    return _monitor_watchlist
