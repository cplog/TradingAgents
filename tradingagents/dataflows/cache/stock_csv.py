"""Parse OHLCV CSV payloads returned by ``get_stock_data`` tooling."""

from __future__ import annotations

import io
from typing import Any, Dict, List

import pandas as pd


def parse_stock_data_csv_payload(payload: str) -> List[Dict[str, Any]]:
    """Extract daily bars from a vendor CSV blob (skips ``#`` header lines).

    Expects columns including Date, Open, High, Low, Close, Volume (Adj Close optional).
    Returns rows with keys: bar_date, open, high, low, close, volume, change_pct.
    """
    if not payload or not isinstance(payload, str):
        return []
    stripped = payload.lstrip()
    if stripped.startswith("No data found") or stripped.startswith("Error"):
        return []

    buf = io.StringIO()
    for line in payload.splitlines():
        if line.startswith("#"):
            continue
        if line.strip():
            buf.write(line + "\n")
    buf.seek(0)
    try:
        df = pd.read_csv(buf)
    except Exception:
        return []
    if df.empty or len(df.columns) < 2:
        return []

    cols = {str(c).strip(): c for c in df.columns}

    def pick(*names: str):
        for n in names:
            key = next((k for k in cols if k.lower() == n.lower()), None)
            if key is not None:
                return cols[key]
        return None

    date_c = pick("Date")
    open_c = pick("Open")
    high_c = pick("High")
    low_c = pick("Low")
    close_c = pick("Close", "Adj Close")
    vol_c = pick("Volume")
    if not all([date_c, open_c, high_c, low_c, close_c]):
        return []

    sub = df[[date_c, open_c, high_c, low_c, close_c]].copy()
    if vol_c:
        sub["__vol"] = df[vol_c]
    else:
        sub["__vol"] = pd.NA

    sub.columns = ["dt", "open", "high", "low", "close", "volume"]
    sub["dt"] = pd.to_datetime(sub["dt"], errors="coerce")
    sub = sub.dropna(subset=["dt"])
    if sub.empty:
        return []

    sub = sub.sort_values("dt").reset_index(drop=True)
    closes = pd.to_numeric(sub["close"], errors="coerce")
    chg = closes.pct_change() * 100.0

    out: List[Dict[str, Any]] = []
    for i in range(len(sub)):
        r = sub.iloc[i]
        ts = pd.Timestamp(r["dt"])
        bar_date = ts.strftime("%Y-%m-%d")
        vol_raw = r["volume"]
        vol_f = float(vol_raw) if pd.notna(vol_raw) else None
        cp = float(chg.iloc[i]) if pd.notna(chg.iloc[i]) else None
        out.append(
            {
                "bar_date": bar_date,
                "open": float(pd.to_numeric(r["open"], errors="coerce")),
                "high": float(pd.to_numeric(r["high"], errors="coerce")),
                "low": float(pd.to_numeric(r["low"], errors="coerce")),
                "close": float(pd.to_numeric(r["close"], errors="coerce")),
                "volume": vol_f,
                "change_pct": cp,
            }
        )
    return out
