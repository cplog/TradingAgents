import logging

from .akshare_macro import get_macro_akshare, list_akshare_endpoints
from .alpha_vantage import (
    get_balance_sheet as get_alpha_vantage_balance_sheet,
    get_cashflow as get_alpha_vantage_cashflow,
    get_fundamentals as get_alpha_vantage_fundamentals,
    get_global_news as get_alpha_vantage_global_news,
    get_income_statement as get_alpha_vantage_income_statement,
    get_indicator as get_alpha_vantage_indicator,
    get_insider_transactions as get_alpha_vantage_insider_transactions,
    get_news as get_alpha_vantage_news,
    get_stock as get_alpha_vantage_stock,
)
from .alpha_vantage_common import AlphaVantageRateLimitError
from .catalog import (
    TOOLS_CATEGORIES,
    VENDOR_LIST,
    VENDOR_TRY_ORDER,
    get_category_for_method,
)
from .china_akshare import get_stock_akshare
from .china_cn_symbol import (
    akshare_hk_listing_code,
    akshare_symbol,
    akshare_us_ticker,
)
from .config import get_config
from .errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
    VendorRateLimitError,
)
from .finnhub_data import (
    get_stock_finnhub,
    get_news_finnhub,
    get_global_news_finnhub,
)
from .fred import get_macro_data as get_fred_macro_data
from .polymarket import get_prediction_markets as get_polymarket_prediction_markets
from .rss_news import (
    get_news_google_rss,
    get_global_news_google_rss,
)
from .vendor_errors import DataVendorUnavailable
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

logger = logging.getLogger(__name__)

# Mapping of methods to their vendor-specific implementations
VENDOR_METHODS = {
    # core_stock_apis
    "get_stock_data": {
        "yfinance": get_YFin_data_online,
        "akshare": get_stock_akshare,
        "alpha_vantage": get_alpha_vantage_stock,
        "finnhub": get_stock_finnhub,
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
        "google_rss": get_news_google_rss,
        "finnhub": get_news_finnhub,
        "alpha_vantage": get_alpha_vantage_news,
    },
    "get_global_news": {
        "yfinance": get_global_news_yfinance,
        "google_rss": get_global_news_google_rss,
        "finnhub": get_global_news_finnhub,
        "alpha_vantage": get_alpha_vantage_global_news,
    },
    "get_insider_transactions": {
        "alpha_vantage": get_alpha_vantage_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
    },
    # prediction_markets
    "get_prediction_markets": {
        "polymarket": get_polymarket_prediction_markets,
    },
    # macro_data via akshare
    "get_macro_data": {
        "fred": get_fred_macro_data,
        "akshare": get_macro_akshare,
    },
    "list_akshare_endpoints": {
        "akshare": list_akshare_endpoints,
    },
}


def get_vendor(category: str, method: str = None) -> str:
    """Get the configured vendor for a data category or specific tool method."""
    config = get_config()
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]
    return config.get("data_vendors", {}).get(category, "default")


def _build_vendor_fallback_chain(method: str, primary_vendors: list[str]) -> list[str]:
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


def _is_yfinance_style_no_data(result: object) -> bool:
    """Detect yfinance's plain-text empty-series message so we try the next vendor."""
    if not isinstance(result, str):
        return False
    s = result.lstrip()
    return s.startswith("No data found for symbol")


_METHOD_STRING_ERROR_PREFIXES: dict[str, tuple[str, ...]] = {
    "get_stock_data": ("No data found for symbol",),
    "get_news": ("No news found for ", "Error fetching news for "),
    "get_global_news": ("No global news found for ", "Error fetching global news"),
}


def _vendor_should_skip(method: str, result: object) -> bool:
    if not isinstance(result, str):
        return False
    prefixes = _METHOD_STRING_ERROR_PREFIXES.get(method)
    if prefixes is None:
        return False
    s = result.lstrip()
    return any(s.startswith(p) for p in prefixes)


def _akshare_auto_fallback_eligible(method: str, symbol: object) -> bool:
    """AKShare auto-fallback is for CN/HK symbols; US has yfinance + Stooq."""
    if method != "get_stock_data" or not isinstance(symbol, str):
        return True
    sym = symbol.strip().upper()
    if akshare_symbol(sym) or akshare_hk_listing_code(sym):
        return True
    if akshare_us_ticker(sym):
        return False
    return True


def _filter_auto_akshare_fallback(
    method: str,
    primary_vendors: list[str],
    fallback_vendors: list[str],
    *args: object,
) -> list[str]:
    """Skip AKShare in the automatic chain for US tickers unless explicitly configured."""
    if "akshare" not in fallback_vendors:
        return fallback_vendors
    if "akshare" in primary_vendors:
        return fallback_vendors
    symbol = args[0] if args else None
    if _akshare_auto_fallback_eligible(method, symbol):
        return fallback_vendors
    return [v for v in fallback_vendors if v != "akshare"]


def route_to_vendor(method: str, *args, **kwargs):
    """Route method calls to appropriate vendor implementation with fallback support."""
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    primary_vendors = [v.strip() for v in vendor_config.split(",") if v.strip()]

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    fallback_vendors = _build_vendor_fallback_chain(method, primary_vendors)
    fallback_vendors = _filter_auto_akshare_fallback(
        method, primary_vendors, fallback_vendors, *args
    )

    last_exc = None
    for vendor in fallback_vendors:
        if vendor not in VENDOR_METHODS[method]:
            continue

        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl

        try:
            out = impl_func(*args, **kwargs)
            if _vendor_should_skip(method, out):
                continue
            return out
        except (AlphaVantageRateLimitError, DataVendorUnavailable) as exc:
            last_exc = exc
            continue
        except (VendorRateLimitError, VendorNotConfiguredError, NoMarketDataError) as exc:
            logger.info("Vendor %s skipped for %s: %s", vendor, method, exc)
            last_exc = exc
            continue

    if last_exc is not None:
        if method in ("list_akshare_endpoints",):
            reason = str(last_exc)
            if "package not installed" in reason:
                hint = "Try: pip install akshare"
            else:
                hint = reason
            return (
                f"## {method} — not available\n\n"
                f"**{reason}**\n\n{hint}\n\n"
                f"> {method.title().replace('_', ' ')} requires the AKShare library. "
                f"See `tradingagents[china-data]` or `pip install akshare`."
            )
        raise RuntimeError(f"No available vendor for '{method}': {last_exc}") from last_exc
    raise RuntimeError(f"No available vendor for '{method}'")
