"""Company headlines via AKShare ``stock_news_em`` (Eastmoney).

Works for many symbols used in ``stock_news_em`` (A-share codes, HK listing codes
such as ``06060``, and US tickers like ``AAPL``). Optional package — same install
as other AKShare paths.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from .china_cn_symbol import akshare_hk_listing_code, akshare_symbol, akshare_us_ticker
from .config import get_config
from .vendor_errors import DataVendorUnavailable


def _symbol_for_em_news(ticker: str) -> str | None:
    hk = akshare_hk_listing_code(ticker)
    if hk:
        return hk
    cn = akshare_symbol(ticker)
    if cn:
        return cn
    us = akshare_us_ticker(ticker)
    if us:
        return us
    return None


def get_news_akshare_em(
    ticker: str,
    start_date: str,
    end_date: str,
) -> str:
    """Eastmoney 个股新闻 — filtered to ``[start_date, end_date]``."""
    sym = _symbol_for_em_news(ticker)
    if not sym:
        raise DataVendorUnavailable(
            "akshare news: ticker shape not supported (need A-share, *.HK, or US ticker)"
        )

    try:
        import akshare as ak  # type: ignore[import-untyped]
    except ImportError as exc:
        raise DataVendorUnavailable(
            "akshare news: package not installed (pip install akshare or tradingagents[china-data])"
        ) from exc

    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")
    lo = pd.Timestamp(start_date)
    hi = pd.Timestamp(end_date) + pd.Timedelta(days=1)

    try:
        df = ak.stock_news_em(symbol=sym)
    except Exception as exc:
        raise DataVendorUnavailable(f"akshare news: {exc}") from exc

    if df is None or df.empty:
        raise DataVendorUnavailable("akshare news: empty feed")

    limit = int(get_config().get("news_article_limit", 20))

    time_col = next(
        (c for c in df.columns if "时间" in str(c)),
        None,
    )
    if time_col is None:
        raise DataVendorUnavailable("akshare news: no time column")

    df["__ts"] = pd.to_datetime(df[time_col], errors="coerce")
    df = df.dropna(subset=["__ts"])
    df = df[(df["__ts"] >= lo) & (df["__ts"] < hi)]
    if df.empty:
        raise DataVendorUnavailable("akshare news: no rows in date window")

    title_col = next((c for c in df.columns if "标题" in str(c)), None)
    body_col = next((c for c in df.columns if "内容" in str(c)), None)
    src_col = next((c for c in df.columns if "来源" in str(c)), None)
    link_col = next((c for c in df.columns if "链接" in str(c)), None)

    parts: list[str] = []
    for _, row in df.head(limit * 2).iterrows():
        if len(parts) >= limit:
            break
        ts = row["__ts"]
        title = str(row[title_col]) if title_col else ""
        body = str(row[body_col])[:400] if body_col else ""
        src = str(row[src_col]) if src_col else ""
        link = str(row[link_col]) if link_col else ""
        line = f"### {title}\n_{ts.strftime('%Y-%m-%d %H:%M')}_ ({src})"
        if body:
            line += f"\n{body}"
        if link:
            line += f"\n{link}"
        parts.append(line)

    if not parts:
        raise DataVendorUnavailable("akshare news: nothing to render")

    return (
        f"## {ticker} News (AKShare / Eastmoney), {start_date} to {end_date}\n\n"
        + "\n\n".join(parts)
    )
