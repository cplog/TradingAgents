from .catalog import (
    TOOLS_CATEGORIES,
    VENDOR_LIST,
    VENDOR_TRY_ORDER,
    get_category_for_method,
)
from .config import get_config
from .y_finance import (
    get_YFin_data_online,
    get_stock_stats_indicators_window,
    get_fundamentals as get_yfinance_fundamentals,
    get_balance_sheet as get_yfinance_balance_sheet,
    get_cashflow as get_yfinance_cashflow,
    get_income_statement as get_yfinance_income_statement,
    get_insider_transactions as get_yfinance_insider_transactions,
)
from .yfinance_news import get_news_yfinance, get_global_news_yfinance
from .alpha_vantage import (
    get_stock as get_alpha_vantage_stock,
    get_indicator as get_alpha_vantage_indicator,
    get_fundamentals as get_alpha_vantage_fundamentals,
    get_balance_sheet as get_alpha_vantage_balance_sheet,
    get_cashflow as get_alpha_vantage_cashflow,
    get_income_statement as get_alpha_vantage_income_statement,
    get_insider_transactions as get_alpha_vantage_insider_transactions,
    get_news as get_alpha_vantage_news,
    get_global_news as get_alpha_vantage_global_news,
)
from .alpha_vantage_common import AlphaVantageRateLimitError
from .vendor_errors import DataVendorUnavailable
from .finnhub_data import (
    get_stock_finnhub,
    get_news_finnhub,
    get_global_news_finnhub,
)
from .china_akshare import get_stock_akshare
from .china_baostock import get_stock_baostock
from .rss_news import get_global_news_google_rss, get_news_google_rss
from .akshare_news import get_news_akshare_em
from .akshare_macro import get_macro_akshare, list_akshare_endpoints

# Mapping of methods to their vendor-specific implementations
VENDOR_METHODS = {
    # core_stock_apis
    "get_stock_data": {
        "yfinance": get_YFin_data_online,
        "finnhub": get_stock_finnhub,
        "alpha_vantage": get_alpha_vantage_stock,
        "akshare": get_stock_akshare,
        "baostock": get_stock_baostock,
    },
    # technical_indicators
    "get_indicators": {
        "alpha_vantage": get_alpha_vantage_indicator,
        "yfinance": get_stock_stats_indicators_window,
    },
    # fundamental_data
    "get_fundamentals": {
        "alpha_vantage": get_alpha_vantage_fundamentals,
        "yfinance": get_yfinance_fundamentals,
    },
    "get_balance_sheet": {
        "alpha_vantage": get_alpha_vantage_balance_sheet,
        "yfinance": get_yfinance_balance_sheet,
    },
    "get_cashflow": {
        "alpha_vantage": get_alpha_vantage_cashflow,
        "yfinance": get_yfinance_cashflow,
    },
    "get_income_statement": {
        "alpha_vantage": get_alpha_vantage_income_statement,
        "yfinance": get_yfinance_income_statement,
    },
    # news_data
    "get_news": {
        "yfinance": get_news_yfinance,
        "finnhub": get_news_finnhub,
        "google_rss": get_news_google_rss,
        "akshare": get_news_akshare_em,
        "alpha_vantage": get_alpha_vantage_news,
    },
    "get_global_news": {
        "yfinance": get_global_news_yfinance,
        "finnhub": get_global_news_finnhub,
        "google_rss": get_global_news_google_rss,
        "alpha_vantage": get_alpha_vantage_global_news,
    },
    "get_insider_transactions": {
        "alpha_vantage": get_alpha_vantage_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
    },
    # macro_data
    "list_akshare_endpoints": {
        "akshare": list_akshare_endpoints,
    },
    "get_macro_data": {
        "akshare": get_macro_akshare,
    },
}


def get_vendor(category: str, method: str = None) -> str:
    """Get the configured vendor for a data category or specific tool method.
    Tool-level configuration takes precedence over category-level.
    """
    config = get_config()

    # Check tool-level configuration first (if method provided)
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]

    # Fall back to category-level configuration
    return config.get("data_vendors", {}).get(category, "default")


def _build_vendor_fallback_chain(method: str, primary_vendors: list[str]) -> list[str]:
    """Dedupe and order vendors for a tool. When ``prefer_free_data_vendors`` is true
    (default), yfinance is always tried before alpha_vantage so no-key / free paths
    run first; remaining configured primaries and unknown vendors follow.
    """
    cfg = get_config()
    prefer_free = cfg.get("prefer_free_data_vendors", True)
    available = VENDOR_METHODS[method]
    primaries = [v for v in (p.strip() for p in primary_vendors) if v and v in available]

    if prefer_free:
        seen: set[str] = set()
        ordered: list[str] = []
        for v in VENDOR_TRY_ORDER:
            if v in available and v not in seen:
                ordered.append(v)
                seen.add(v)
        for v in primaries:
            if v not in seen:
                ordered.append(v)
                seen.add(v)
        for v in available:
            if v not in seen:
                ordered.append(v)
                seen.add(v)
        return ordered

    seen = set()
    ordered: list[str] = []
    for v in primaries:
        if v not in seen:
            ordered.append(v)
            seen.add(v)
    for v in VENDOR_TRY_ORDER:
        if v in available and v not in seen:
            ordered.append(v)
            seen.add(v)
    for v in available:
        if v not in seen:
            ordered.append(v)
            seen.add(v)
    return ordered


def _is_yfinance_style_no_ohlcv(result: object) -> bool:
    """Detect yfinance's plain-text empty-series message so we try the next vendor."""
    if not isinstance(result, str):
        return False
    return result.lstrip().startswith("No data found for symbol")


def _is_yfinance_style_no_news(result: object) -> bool:
    if not isinstance(result, str):
        return False
    s = result.lstrip()
    return s.startswith("No news found for ") or s.startswith("Error fetching news for ")


def _is_yfinance_style_no_global_news(result: object) -> bool:
    if not isinstance(result, str):
        return False
    s = result.lstrip()
    return s.startswith("No global news found for ") or s.startswith("Error fetching global news")


_MACRO_SOFT_ERROR_METHODS = frozenset({"get_macro_data", "list_akshare_endpoints"})


def route_to_vendor(method: str, *args, **kwargs):
    """Route method calls to appropriate vendor implementation with fallback support."""
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    primary_vendors = [v.strip() for v in vendor_config.split(",") if v.strip()]

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    fallback_vendors = _build_vendor_fallback_chain(method, primary_vendors)

    last_exc = None
    for vendor in fallback_vendors:
        if vendor not in VENDOR_METHODS[method]:
            continue

        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl

        try:
            out = impl_func(*args, **kwargs)
            if method == "get_stock_data" and _is_yfinance_style_no_ohlcv(out):
                continue
            if method == "get_news" and _is_yfinance_style_no_news(out):
                continue
            if method == "get_global_news" and _is_yfinance_style_no_global_news(out):
                continue
            return out
        except (AlphaVantageRateLimitError, DataVendorUnavailable) as exc:
            last_exc = exc
            continue

    if last_exc is not None:
        if method in _MACRO_SOFT_ERROR_METHODS:
            return (
                f"## AKShare tool error\n\n"
                f"`{last_exc}`\n\n"
                "Call `list_akshare_endpoints` and pass an exact `macro_*` or `stock_*` name "
                "to `get_macro_data`."
            )
        raise RuntimeError(f"No available vendor for '{method}': {last_exc}") from last_exc
    raise RuntimeError(f"No available vendor for '{method}'")