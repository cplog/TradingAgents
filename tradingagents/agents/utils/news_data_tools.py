from langchain_core.tools import tool
from typing import Annotated, Optional

from tradingagents.dataflows.cache.repository import (
    cache_status_message,
    search_cached_news as repo_search_cached_news,
    upsert_news_items,
)
from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.hot_board import (
    fetch_hot_board_items,
    fetch_polymarket_markets,
    format_hot_board_markdown,
    normalize_hot_board_rows,
)
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_news(
    ticker: Annotated[str, "Ticker symbol"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve news data for a given ticker symbol.
    Uses the configured news_data vendor.
    Args:
        ticker (str): Ticker symbol
        start_date (str): Start date in yyyy-mm-dd format
        end_date (str): End date in yyyy-mm-dd format
    Returns:
        str: A formatted string containing news data
    """
    return route_to_vendor("get_news", ticker, start_date, end_date)

@tool
def get_global_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[Optional[int], "Days to look back; omit to use the configured default"] = None,
    limit: Annotated[Optional[int], "Max articles to return; omit to use the configured default"] = None,
) -> str:
    """
    Retrieve global news data.
    Uses the configured news_data vendor. Defaults for look_back_days and
    limit come from DEFAULT_CONFIG (global_news_lookback_days,
    global_news_article_limit); pass explicit values to override.

    Args:
        curr_date (str): Current date in yyyy-mm-dd format
        look_back_days (int): Number of days to look back; omit to inherit config
        limit (int): Maximum number of articles to return; omit to inherit config

    Returns:
        str: A formatted string containing global news data
    """
    return route_to_vendor("get_global_news", curr_date, look_back_days, limit)

@tool
def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol"],
) -> str:
    """
    Retrieve insider transaction information about a company.
    Uses the configured news_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
    Returns:
        str: A report of insider transaction data
    """
    return route_to_vendor("get_insider_transactions", ticker)


@tool
def fetch_hot_news_board(
    source_id: Annotated[str, "Hot-board source key for the configured JSON feed"],
    count: Annotated[int, "Maximum headlines to retrieve"] = 15,
    persist_to_cache: Annotated[
        bool,
        "When True, upsert headlines into the data cache if backend is sqlite or d1",
    ] = True,
) -> str:
    """
    Fetch ranked headlines from an optional hot-board HTTP API.

    Set ``hot_news_feed_base_url`` in config to a NewsNow-compatible base
    (``GET {base}/api/s?id={source_id}``). When ``data_cache_backend`` is
    ``sqlite`` or ``d1``, rows can be persisted for ``search_data_cache_news``.
    """
    cfg = get_config()
    items = fetch_hot_board_items(source_id.strip(), int(count))
    md = format_hot_board_markdown(source_id.strip(), items)
    if persist_to_cache and items:
        try:
            n = upsert_news_items(cfg, normalize_hot_board_rows(source_id.strip(), items))
            md += f"\n\n_(cached {n} row(s); {cache_status_message(cfg)})_"
        except Exception as exc:
            md += f"\n\n_(cache persist failed: {exc})_"
    return md


@tool
def search_data_cache_news(
    query: Annotated[str, "Substring match against cached news title or body"],
    limit: Annotated[int, "Maximum rows to return"] = 10,
) -> str:
    """
    Search persisted headlines/snippets in the TradingAgents data cache.

    Requires ``data_cache_backend`` of ``sqlite`` (local file under
    ``data_cache_dir``) or ``d1`` (same Cloudflare credentials as API history).
    """
    cfg = get_config()
    rows = repo_search_cached_news(cfg, query.strip(), int(limit))
    if not rows:
        return f"{cache_status_message(cfg)}\nNo matching cached rows for {query!r}."
    lines = ["### Cached news matches", ""]
    for r in rows:
        title = r.get("title") or ""
        sid = r.get("source_id") or ""
        crawl = r.get("crawl_time") or ""
        url = r.get("url") or ""
        snippet = (r.get("content") or "")[:240]
        head = f"- **{title}** [{sid}] _{crawl}_"
        if url:
            head += f" — {url}"
        lines.append(head)
        if snippet.strip():
            lines.append(f"  _{snippet.strip()}…_" if len(snippet) == 240 else f"  _{snippet}_")
    lines.append("")
    lines.append(f"_({cache_status_message(cfg)})_")
    return "\n".join(lines)


@tool
def get_prediction_market_snapshot(
    limit: Annotated[int, "Max Polymarket markets to list"] = 15,
) -> str:
    """Active Polymarket markets (public gamma API, no key)."""
    return fetch_polymarket_markets(int(limit))
