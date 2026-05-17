from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.interface import route_to_vendor


@tool
def list_akshare_endpoints(
    prefix: Annotated[str, "Function prefix filter; examples: macro_ or stock_"] = "macro_",
    include_stock: Annotated[bool, "Include stock_* endpoints in output"] = True,
    limit: Annotated[int, "Maximum endpoints to show"] = 200,
) -> str:
    """
    List available AKShare endpoints for dynamic macro/market querying.
    """
    return route_to_vendor("list_akshare_endpoints", prefix, include_stock, limit)


@tool
def get_macro_data(
    function_name: Annotated[str, "AKShare function name, for example macro_cnbs or stock_ebs_lg"],
    params_json: Annotated[str, "JSON object string of kwargs to pass, for example {\"symbol\":\"上证A股\"}"] = "{}",
    tail_rows: Annotated[int, "How many recent rows to include in the markdown output"] = 120,
) -> str:
    """
    Fetch a macro/market dataset by dynamically calling an AKShare endpoint.
    """
    return route_to_vendor("get_macro_data", function_name, params_json, tail_rows)
