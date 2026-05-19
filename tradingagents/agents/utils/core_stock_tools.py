import logging

from langchain_core.tools import tool
from typing import Annotated

from tradingagents.dataflows.cache.repository import (
    cache_status_message,
    fetch_cached_stock_bars,
    maybe_autocache_stock_bars_from_payload,
)
from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.interface import route_to_vendor

logger = logging.getLogger(__name__)


@tool
def get_stock_data(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve stock price data (OHLCV) for a given ticker symbol.
    Uses the configured core_stock_apis vendor.
    Args:
        symbol (str): Ticker symbol of the company, e.g. AAPL, TSM
        start_date (str): Start date in yyyy-mm-dd format
        end_date (str): End date in yyyy-mm-dd format
    Returns:
        str: A formatted dataframe containing the stock price data for the specified ticker symbol in the specified date range.
    """
    out = route_to_vendor("get_stock_data", symbol, start_date, end_date)
    try:
        maybe_autocache_stock_bars_from_payload(
            get_config(), symbol, start_date, end_date, out
        )
    except Exception:
        logger.debug("ta_stock_bars autocache failed", exc_info=True)
    return out


@tool
def query_cached_ohlcv(
    symbol: Annotated[str, "Ticker symbol"],
    start_date: Annotated[str, "Start date yyyy-mm-dd (inclusive)"],
    end_date: Annotated[str, "End date yyyy-mm-dd (inclusive)"],
    max_rows: Annotated[int, "Maximum rows to show in the markdown table"] = 80,
) -> str:
    """
    Read OHLCV rows previously stored in the TradingAgents data cache (SQLite or D1).

    Rows are populated when ``data_cache_auto_stock_bars`` is True and agents call
    ``get_stock_data``, or by future explicit cache loaders.
    """
    cfg = get_config()
    cap = max(1, min(int(max_rows or 80), 500))
    rows = fetch_cached_stock_bars(cfg, symbol, start_date, end_date, limit=cap)
    if not rows:
        return (
            f"No cached OHLCV for `{symbol.upper().strip()}` in [{start_date}, {end_date}]. "
            f"{cache_status_message(cfg)} "
            "Enable `data_cache_backend` and `data_cache_auto_stock_bars`, then fetch prices once."
        )
    lines = [
        f"### Cached OHLCV `{symbol.upper().strip()}` ({start_date} → {end_date})",
        "",
        "| Date | Open | High | Low | Close | Volume | Δ% | Vendor |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            "| {bar_date} | {o} | {h} | {l} | {c} | {v} | {p} | {ven} |".format(
                bar_date=r.get("bar_date") or "",
                o=r.get("open") if r.get("open") is not None else "",
                h=r.get("high") if r.get("high") is not None else "",
                l=r.get("low") if r.get("low") is not None else "",
                c=r.get("close") if r.get("close") is not None else "",
                v=r.get("volume") if r.get("volume") is not None else "",
                p=r.get("change_pct") if r.get("change_pct") is not None else "",
                ven=r.get("vendor") or "",
            )
        )
    lines.append("")
    lines.append(f"_({cache_status_message(cfg)}; showing up to {cap} rows)_")
    return "\n".join(lines)
