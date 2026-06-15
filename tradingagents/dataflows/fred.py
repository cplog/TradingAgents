"""FRED (Federal Reserve Economic Data) macro vendor.

Fetches macroeconomic time series from the St. Louis Fed's free API.
"""

import logging
import os
from datetime import datetime, timedelta

import requests

from .errors import VendorNotConfiguredError

logger = logging.getLogger(__name__)

FRED_API_BASE = "https://api.stlouisfed.org/fred"
REQUEST_TIMEOUT = 30
DEFAULT_LOOKBACK_DAYS = 365
MAX_ROWS = 40

MACRO_SERIES = {
    "fed_funds_rate": "FEDFUNDS", "federal_funds_rate": "FEDFUNDS", "fed_funds": "FEDFUNDS",
    "2y_treasury": "DGS2", "10y_treasury": "DGS10", "30y_treasury": "DGS30",
    "10y_2y_spread": "T10Y2Y", "yield_curve": "T10Y2Y",
    "cpi": "CPIAUCSL", "core_cpi": "CPILFESL", "pce": "PCEPI", "core_pce": "PCEPILFE",
    "inflation_expectations": "T10YIE",
    "real_gdp": "GDPC1", "gdp": "GDP", "industrial_production": "INDPRO",
    "unemployment_rate": "UNRATE", "unemployment": "UNRATE",
    "nonfarm_payrolls": "PAYEMS", "payrolls": "PAYEMS", "initial_claims": "ICSA",
    "m2": "M2SL", "money_supply": "M2SL",
    "vix": "VIXCLS", "dollar_index": "DTWEXBGS",
    "consumer_sentiment": "UMCSENT", "housing_starts": "HOUST", "retail_sales": "RSAFS",
}


class FredNotConfiguredError(VendorNotConfiguredError):
    """Raised when FRED is selected but no API key is configured."""


def get_api_key() -> str:
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        raise FredNotConfiguredError(
            "FRED_API_KEY env var not set. Get a free key at "
            "https://fred.stlouisfed.org/docs/api/api_key.html"
        )
    return api_key


def _resolve_series_id(indicator: str) -> str:
    key = indicator.strip().lower().replace(" ", "_").replace("-", "_")
    return MACRO_SERIES.get(key, indicator.strip().upper())


def _request(path: str, params: dict) -> dict:
    api_params = {**params, "api_key": get_api_key(), "file_type": "json"}
    response = requests.get(
        f"{FRED_API_BASE}/{path}", params=api_params, timeout=REQUEST_TIMEOUT
    )
    if response.status_code == 400:
        try:
            message = response.json().get("error_message", response.text)
        except ValueError:
            message = response.text
        raise ValueError(f"FRED request failed: {message}")
    response.raise_for_status()
    return response.json()


def get_macro_data(
    indicator: str,
    curr_date: str,
    look_back_days: int | None = None,
) -> str:
    """Fetch a FRED macro series as a formatted markdown report."""
    if look_back_days is None:
        look_back_days = DEFAULT_LOOKBACK_DAYS

    end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_date = (end_dt - timedelta(days=look_back_days)).strftime("%Y-%m-%d")
    series_id = _resolve_series_id(indicator)

    meta = _request("series", {"series_id": series_id}).get("seriess") or []
    if not meta:
        raise ValueError(f"FRED series '{series_id}' not found.")
    info = meta[0]
    title = info.get("title", series_id)
    units = info.get("units_short") or info.get("units", "")
    frequency = info.get("frequency", "")
    seasonal = info.get("seasonal_adjustment_short", "")

    observations = _request(
        "series/observations",
        {"series_id": series_id, "observation_start": start_date, "observation_end": curr_date, "sort_order": "asc"},
    ).get("observations", [])

    points = [(o["date"], o["value"]) for o in observations if o.get("value") not in (".", None, "")]

    header = (
        f"## FRED: {title} ({series_id})\n"
        f"- Units: {units}\n- Frequency: {frequency}{f' ({seasonal})' if seasonal else ''}\n"
        f"- Window: {start_date} to {curr_date}\n"
    )

    if not points:
        return header + f"\nNo observations in this window."

    first_date, first_val = points[0]
    last_date, last_val = points[-1]
    try:
        delta = float(last_val) - float(first_val)
        base = float(first_val)
        pct = f" ({delta / base * 100:+.2f}%)" if base != 0 else ""
        summary = f"\n**Latest:** {last_val} ({last_date}) | **Change over window:** {delta:+.2f}{pct} from {first_val} ({first_date})\n"
    except ValueError:
        summary = f"\n**Latest:** {last_val} ({last_date})\n"

    shown = points
    note = ""
    if len(points) > MAX_ROWS:
        shown = points[-MAX_ROWS:]
        note = f"\n_(showing the most recent {MAX_ROWS} of {len(points)} observations)_\n"

    table = "\n| Date | Value |\n| --- | --- |\n" + "\n".join(f"| {d} | {v} |" for d, v in shown) + "\n"
    return header + summary + note + table
