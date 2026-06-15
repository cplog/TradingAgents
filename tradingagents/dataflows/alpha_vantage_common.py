import json
import os
from datetime import datetime
from io import StringIO

import pandas as pd
import requests

from .errors import VendorNotConfiguredError, VendorRateLimitError

API_BASE_URL = "https://www.alphavantage.co/query"

REQUEST_TIMEOUT = 30


class AlphaVantageNotConfiguredError(VendorNotConfiguredError):
    """Raised when Alpha Vantage is selected but no API key is configured."""


def get_api_key() -> str:
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        raise AlphaVantageNotConfiguredError(
            "ALPHA_VANTAGE_API_KEY environment variable is not set."
        )
    return api_key


def format_datetime_for_api(date_input) -> str:
    if isinstance(date_input, str):
        if len(date_input) == 13 and 'T' in date_input:
            return date_input
        try:
            dt = datetime.strptime(date_input, "%Y-%m-%d")
            return dt.strftime("%Y%m%dT0000")
        except ValueError:
            try:
                dt = datetime.strptime(date_input, "%Y-%m-%d %H:%M")
                return dt.strftime("%Y%m%dT%H%M")
            except ValueError:
                raise ValueError(f"Unsupported date format: {date_input}") from None
    elif isinstance(date_input, datetime):
        return date_input.strftime("%Y%m%dT%H%M")
    else:
        raise ValueError(f"Date must be string or datetime object, got {type(date_input)}")


class AlphaVantageRateLimitError(VendorRateLimitError):
    """Raised when the Alpha Vantage API rate limit is exceeded."""


def _make_api_request(function_name: str, params: dict) -> dict | str:
    api_params = params.copy()
    api_params.update({
        "function": function_name,
        "apikey": get_api_key(),
        "source": "trading_agents",
    })

    current_entitlement = globals().get('_current_entitlement')
    entitlement = api_params.get("entitlement") or current_entitlement
    if entitlement:
        api_params["entitlement"] = entitlement
    elif "entitlement" in api_params:
        api_params.pop("entitlement", None)

    response = requests.get(API_BASE_URL, params=api_params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    response_text = response.text

    try:
        response_json = json.loads(response_text)
    except json.JSONDecodeError:
        return response_text

    notice = response_json.get("Information") or response_json.get("Note")
    if notice:
        low = notice.lower()
        if any(m in low for m in ("rate limit", "requests per day", "call frequency", "premium")):
            raise AlphaVantageRateLimitError(f"Alpha Vantage rate limit exceeded: {notice}")
        if "api key" in low or "apikey" in low:
            raise AlphaVantageNotConfiguredError(f"Alpha Vantage API key invalid or missing: {notice}")

    return response_text


def _filter_csv_by_date_range(csv_data: str, start_date: str, end_date: str) -> str:
    if not csv_data or csv_data.strip() == "":
        return csv_data

    try:
        df = pd.read_csv(StringIO(csv_data))
        date_col = df.columns[0]
        df[date_col] = pd.to_datetime(df[date_col])
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        filtered_df = df[(df[date_col] >= start_dt) & (df[date_col] <= end_dt)]
        return filtered_df.to_csv(index=False)
    except Exception as e:
        print(f"Warning: Failed to filter CSV data by date range: {e}")
        return csv_data
