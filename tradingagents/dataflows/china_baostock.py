"""Mainland A-share OHLCV via BaoStock (free library; optional dependency).

Install: ``pip install 'tradingagents[china-data]'`` or ``pip install baostock``.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from .vendor_errors import DataVendorUnavailable
from .china_cn_symbol import baostock_code


def get_stock_baostock(
    symbol: str,
    start_date: str,
    end_date: str,
) -> str:
    code = baostock_code(symbol)
    if not code:
        raise DataVendorUnavailable("baostock: not a mainland A-share symbol")

    try:
        import baostock as bs  # type: ignore[import-untyped]
    except ImportError as exc:
        raise DataVendorUnavailable(
            "baostock: package not installed (pip install baostock or tradingagents[china-data])"
        ) from exc

    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    fields = "date,open,high,low,close,volume"
    lg = bs.login()
    if lg.error_code != "0":
        raise DataVendorUnavailable(f"baostock login: {lg.error_msg}")
    try:
        rs = bs.query_history_k_data_plus(
            code,
            fields,
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="3",
        )
        if rs.error_code != "0":
            raise DataVendorUnavailable(f"baostock query: {rs.error_msg}")
        rows: list[list[str]] = []
        while rs.error_code == "0" and rs.next():
            rows.append(rs.get_row_data())
    finally:
        bs.logout()

    if not rows:
        raise DataVendorUnavailable("baostock stock: empty series")

    df = pd.DataFrame(rows, columns=fields.split(","))
    # dtypes
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    df = df.rename(
        columns={
            "date": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )
    df = df.dropna(subset=["Date", "Close"])
    if df.empty:
        raise DataVendorUnavailable("baostock stock: no valid rows")

    csv_string = df.to_csv(index=False)
    header = (
        f"# Stock data for {symbol.upper()} from {start_date} to {end_date} (BaoStock)\n"
        f"# Total records: {len(df)}\n\n"
    )
    return header + csv_string
