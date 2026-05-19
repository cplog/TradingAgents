from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.interface import route_to_vendor

AKSHARE_MACRO_DISCOVERY_HINT = (
    "Always call list_akshare_endpoints before get_macro_data. "
    'For central-bank/LPR rates use list_akshare_endpoints(category="interest_rate"); '
    "US Fed rate is macro_bank_usa_interest_rate, not macro_usa_*."
)


@tool
def list_akshare_endpoints(
    prefix: Annotated[str, "Function prefix filter; examples: macro_ or stock_"] = "macro_",
    include_stock: Annotated[bool, "Include stock_* endpoints in output"] = True,
    limit: Annotated[int, "Maximum endpoints to show"] = 200,
    category: Annotated[
        str,
        'Optional preset filter; use "interest_rate" for macro_bank_* and macro_*_bank_rate endpoints',
    ] = "",
) -> str:
    """
    List available AKShare endpoints for dynamic macro/market querying.
    Use category="interest_rate" for central-bank/LPR rates (macro_bank_usa_interest_rate, etc.).
    Always call this before get_macro_data and pass exact names from the output.
    """
    return route_to_vendor("list_akshare_endpoints", prefix, include_stock, limit, category)


@tool
def get_macro_data(
    function_name: Annotated[str, "AKShare function name, for example macro_cnbs or stock_ebs_lg"],
    params_json: Annotated[str, "JSON object string of kwargs to pass, for example {\"symbol\":\"上证A股\"}"] = "{}",
    tail_rows: Annotated[int, "How many recent rows to include in the markdown output"] = 120,
) -> str:
    """
    Fetch a macro/market dataset by dynamically calling an AKShare endpoint.
    Call list_akshare_endpoints first; for Fed/central-bank rates use category="interest_rate".
    """
    return route_to_vendor("get_macro_data", function_name, params_json, tail_rows)
