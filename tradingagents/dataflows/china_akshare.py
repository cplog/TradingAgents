"""OHLCV via AKShare (optional): mainland A-share, Hong Kong, and US equities.

Install: ``pip install 'tradingagents[china-data]'`` or ``pip install akshare``.

Uses ``stock_zh_a_hist``, ``stock_hk_hist``, and ``stock_us_daily`` as fallbacks
when other vendors are empty or unavailable. Data sources are third-party
(see `AKShare docs <https://akshare.akfamily.xyz/data/index.html>`_).
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from .china_cn_symbol import (
    akshare_hk_listing_code,
    akshare_symbol,
    akshare_us_ticker,
)
from .vendor_errors import DataVendorUnavailable


def _import_akshare():
    try:
        import akshare as ak  # type: ignore[import-untyped]
        return ak
    except ImportError as exc:
        raise DataVendorUnavailable(
            "akshare: package not installed (pip install akshare or tradingagents[china-data])"
        ) from exc


def _to_ohlcv_csv(
    *,
    symbol: str,
    start_date: str,
    end_date: str,
    out: pd.DataFrame,
    route_tag: str,
) -> str:
    out = out.dropna(subset=["Date"])
    if out.empty:
        raise DataVendorUnavailable(f"akshare {route_tag}: no rows after normalize")
    out = out[(out["Date"] >= start_date) & (out["Date"] <= end_date)]
    if out.empty:
        raise DataVendorUnavailable(f"akshare {route_tag}: empty after date filter")
    csv_string = out.to_csv(index=False)
    header = (
        f"# Stock data for {symbol.upper()} from {start_date} to {end_date} "
        f"(AKShare {route_tag})\n"
        f"# Total records: {len(out)}\n\n"
    )
    return header + csv_string


def _normalize_chinese_ohlcv_df(df: pd.DataFrame) -> pd.DataFrame:
    colmap = {c: str(c).strip() for c in df.columns}
    df = df.rename(columns={k: colmap[k] for k in df.columns})
    date_col = next(
        (c for c in df.columns if "日期" in c or c.lower() == "date"),
        None,
    )
    if date_col is None:
        raise DataVendorUnavailable("akshare: no date column")
    out = pd.DataFrame()
    out["Date"] = pd.to_datetime(df[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
    for src, dst in [
        ("开盘", "Open"),
        ("收盘", "Close"),
        ("最高", "High"),
        ("最低", "Low"),
        ("成交量", "Volume"),
    ]:
        if src in df.columns:
            out[dst] = df[src]
    return out


def _akshare_zh_a(
    ak,
    symbol: str,
    start_date: str,
    end_date: str,
) -> str:
    code = akshare_symbol(symbol)
    if not code:
        raise DataVendorUnavailable("akshare cn: not a mainland A-share symbol")
    start_s = start_date.replace("-", "")
    end_s = end_date.replace("-", "")
    try:
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start_s,
            end_date=end_s,
            adjust="",
        )
    except Exception as exc:
        raise DataVendorUnavailable(f"akshare cn: {exc}") from exc
    if df is None or df.empty:
        raise DataVendorUnavailable("akshare cn: empty series")
    out = _normalize_chinese_ohlcv_df(df)
    return _to_ohlcv_csv(symbol=symbol, start_date=start_date, end_date=end_date, out=out, route_tag="A-share")


def _akshare_hk(
    ak,
    symbol: str,
    start_date: str,
    end_date: str,
) -> str:
    code = akshare_hk_listing_code(symbol)
    if not code:
        raise DataVendorUnavailable("akshare hk: not an HK-listed symbol (*.HK)")
    start_s = start_date.replace("-", "")
    end_s = end_date.replace("-", "")
    try:
        df = ak.stock_hk_hist(
            symbol=code,
            period="daily",
            start_date=start_s,
            end_date=end_s,
            adjust="",
        )
    except Exception as exc:
        raise DataVendorUnavailable(f"akshare hk: {exc}") from exc
    if df is None or df.empty:
        raise DataVendorUnavailable("akshare hk: empty series")
    out = _normalize_chinese_ohlcv_df(df)
    return _to_ohlcv_csv(symbol=symbol, start_date=start_date, end_date=end_date, out=out, route_tag="HK")


def _akshare_us(
    ak,
    symbol: str,
    start_date: str,
    end_date: str,
) -> str:
    tick = akshare_us_ticker(symbol)
    if not tick:
        raise DataVendorUnavailable(
            "akshare us: ticker must look like US common stock (e.g. AAPL, BRK.B)"
        )
    try:
        df = ak.stock_us_daily(symbol=tick, adjust="")
    except Exception as exc:
        raise DataVendorUnavailable(f"akshare us: {exc}") from exc
    if df is None or df.empty:
        raise DataVendorUnavailable("akshare us: empty series")
    if "date" not in df.columns:
        raise DataVendorUnavailable("akshare us: unexpected columns")
    work = df.copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    lo = pd.Timestamp(start_date)
    hi = pd.Timestamp(end_date)
    work = work[(work["date"] >= lo) & (work["date"] <= hi)]
    if work.empty:
        raise DataVendorUnavailable("akshare us: empty after date filter")
    out = pd.DataFrame({
        "Date": work["date"].dt.strftime("%Y-%m-%d"),
        "Open": work["open"],
        "High": work["high"],
        "Low": work["low"],
        "Close": work["close"],
        "Volume": work["volume"],
    })
    return _to_ohlcv_csv(symbol=symbol, start_date=start_date, end_date=end_date, out=out, route_tag="US")


def get_stock_akshare(
    symbol: str,
    start_date: str,
    end_date: str,
) -> str:
    """Daily OHLCV: routes to A-share / HK / US implementation."""
    ak = _import_akshare()
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    if akshare_symbol(symbol):
        return _akshare_zh_a(ak, symbol, start_date, end_date)
    if akshare_hk_listing_code(symbol):
        return _akshare_hk(ak, symbol, start_date, end_date)
    if akshare_us_ticker(symbol):
        return _akshare_us(ak, symbol, start_date, end_date)

    raise DataVendorUnavailable(
        "akshare: symbol not supported (use A-share, *.HK, or US ticker such as AAPL)"
    )
