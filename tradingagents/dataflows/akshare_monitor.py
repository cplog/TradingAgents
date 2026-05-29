"""AKShare helpers for daily overnight monitor: universe scan, HK regime."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from .china_akshare import _import_akshare
from .vendor_errors import DataVendorUnavailable


def normalize_akshare_us_code(raw: str) -> str:
    """Map Eastmoney code like ``105.AAPL`` to ``AAPL``."""
    s = str(raw).strip().upper()
    m = re.match(r"^\d+\.(.+)$", s)
    return m.group(1) if m else s


def scan_us_panic_candidates(min_drop_pct: float = -10.0) -> list[dict[str, Any]]:
    """Full-market US snapshot; return tickers with 涨跌幅 <= min_drop_pct."""
    ak = _import_akshare()
    df = None
    last_exc = None
    for attempt in range(3):
        try:
            df = ak.stock_us_spot_em()
            if df is not None and not df.empty:
                break
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                import time
                time.sleep(0.5 * (attempt + 1))
    if df is None or df.empty:
        raise DataVendorUnavailable(
            f"akshare stock_us_spot_em: {last_exc or 'empty after 3 attempts'}"
        ) from last_exc
    pct_col = next((c for c in df.columns if "涨跌幅" in str(c)), None)
    amp_col = next((c for c in df.columns if "振幅" in str(c)), None)
    code_col = next((c for c in df.columns if str(c) in ("代码", "code")), "代码")
    name_col = next((c for c in df.columns if str(c) in ("名称", "name")), "名称")
    price_col = next((c for c in df.columns if "最新价" in str(c) or str(c) == "最新"), None)
    if pct_col is None:
        raise DataVendorUnavailable("akshare stock_us_spot_em: missing 涨跌幅 column")
    work = df.copy()
    work[pct_col] = pd.to_numeric(work[pct_col], errors="coerce")
    hits = work[work[pct_col] <= min_drop_pct].sort_values(pct_col)
    out: list[dict[str, Any]] = []
    for _, row in hits.iterrows():
        raw_code = str(row.get(code_col, ""))
        amp = float(row[amp_col]) if amp_col and pd.notna(row.get(amp_col)) else None
        out.append(
            {
                "ticker": normalize_akshare_us_code(raw_code),
                "akshare_code": raw_code,
                "name": str(row.get(name_col, "")),
                "change_pct": float(row[pct_col]),
                "amplitude_pct": amp,
                "last_price": float(row[price_col]) if price_col and pd.notna(row.get(price_col)) else None,
            }
        )
    return out


def get_spot_for_ticker(ticker: str) -> dict[str, Any] | None:
    """Lookup one ticker in the latest US spot snapshot."""
    sym = ticker.strip().upper()
    ak = _import_akshare()
    try:
        df = ak.stock_us_spot_em()
    except Exception:
        return None
    if df is None or df.empty:
        return None
    code_col = next((c for c in df.columns if str(c) in ("代码", "code")), "代码")
    pct_col = next((c for c in df.columns if "涨跌幅" in str(c)), None)
    amp_col = next((c for c in df.columns if "振幅" in str(c)), None)
    for _, row in df.iterrows():
        if normalize_akshare_us_code(str(row.get(code_col, ""))) == sym:
            return {
                "ticker": sym,
                "change_pct": float(row[pct_col]) if pct_col and pd.notna(row.get(pct_col)) else None,
                "amplitude_pct": float(row[amp_col]) if amp_col and pd.notna(row.get(amp_col)) else None,
            }
    return None


def get_hk_regime_snapshot() -> dict[str, Any]:
    """Aggregate HK market snapshot for regime context."""
    ak = _import_akshare()
    try:
        df = ak.stock_hk_spot_em()
    except Exception as exc:
        raise DataVendorUnavailable(f"akshare stock_hk_spot_em: {exc}") from exc
    if df is None or df.empty:
        raise DataVendorUnavailable("akshare stock_hk_spot_em: empty")
    pct_col = next((c for c in df.columns if "涨跌幅" in str(c)), None)
    vol_col = next((c for c in df.columns if "成交量" in str(c)), None)
    if pct_col is None:
        raise DataVendorUnavailable("akshare stock_hk_spot_em: missing 涨跌幅")
    work = df.copy()
    work[pct_col] = pd.to_numeric(work[pct_col], errors="coerce")
    avg_change = float(work[pct_col].mean())
    decliners = int((work[pct_col] < 0).sum())
    advancers = int((work[pct_col] > 0).sum())
    total = len(work)
    decliner_ratio = decliners / total if total else 0.0
    avg_volume = float(pd.to_numeric(work[vol_col], errors="coerce").mean()) if vol_col else None
    return {
        "market": "HK",
        "avg_change_pct": round(avg_change, 3),
        "decliner_ratio": round(decliner_ratio, 3),
        "advancers": advancers,
        "decliners": decliners,
        "total_symbols": total,
        "avg_volume": avg_volume,
        "risk_off": avg_change <= -1.0 or decliner_ratio >= 0.65,
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }
