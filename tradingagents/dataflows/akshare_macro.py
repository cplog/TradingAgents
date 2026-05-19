"""Generic AKShare macro/stock dataset bridge for analyst tools.

This module intentionally exposes a dynamic function surface so analysts can
query the broader AKShare catalog (for example ``macro_*`` and ``stock_*``)
without adding one wrapper per endpoint.
"""

from __future__ import annotations

import difflib
import json
import re
from typing import Any

import pandas as pd

from .vendor_errors import DataVendorUnavailable

_FN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ALLOWED_PREFIXES = ("macro_", "stock_")
_INTEREST_RATE_EXTRA = frozenset({"macro_china_lpr"})

# Common LLM / doc typos vs actual AKShare symbol names (verified against akfamily/akshare).
_FN_ALIASES: dict[str, str] = {
    "macro_usa_bank_interest_rate": "macro_bank_usa_interest_rate",
    "macro_usa_interest_rate": "macro_bank_usa_interest_rate",
    "macro_usa_irate": "macro_bank_usa_interest_rate",
    "macro_usa_fed_rate": "macro_bank_usa_interest_rate",
    "macro_usa_bank_rate": "macro_bank_usa_interest_rate",
}


def _import_akshare():
    try:
        import akshare as ak  # type: ignore[import-untyped]
        return ak
    except ImportError as exc:
        raise DataVendorUnavailable(
            "akshare macro: package not installed (pip install akshare or tradingagents[china-data])"
        ) from exc


def _normalize_obj_to_df(obj: Any) -> pd.DataFrame:
    if isinstance(obj, pd.DataFrame):
        return obj.copy()
    if isinstance(obj, dict):
        return pd.DataFrame([obj])
    if isinstance(obj, (list, tuple)):
        try:
            return pd.DataFrame(obj)
        except Exception as exc:  # pragma: no cover - defensive
            raise DataVendorUnavailable(f"akshare macro: unsupported list payload ({exc})") from exc
    raise DataVendorUnavailable(f"akshare macro: unsupported payload type {type(obj).__name__}")


def _trim_frame(df: pd.DataFrame, tail_rows: int) -> pd.DataFrame:
    if df.empty:
        return df
    n = max(1, min(int(tail_rows), 500))
    # Prefer most-recent rows by common date-like columns.
    for col in ("date", "日期", "时间", "年份"):
        if col in df.columns:
            work = df.copy()
            parsed = pd.to_datetime(work[col], errors="coerce")
            if parsed.notna().any():
                work["__sort_key"] = parsed
                work = work.sort_values("__sort_key").drop(columns="__sort_key")
                return work.tail(n)
    return df.tail(n)


def _is_interest_rate_endpoint(name: str) -> bool:
    """Central-bank / policy rate endpoints (AKShare 利率数据 + macro_*_bank_rate)."""
    if name in _INTEREST_RATE_EXTRA:
        return True
    if name.startswith("macro_bank_") and name.endswith("_interest_rate"):
        return True
    return name.startswith("macro_") and name.endswith("_bank_rate")


def _callable_api_names(ak: Any, prefix: str) -> list[str]:
    return sorted(
        name
        for name in dir(ak)
        if isinstance(name, str)
        and name.startswith(prefix)
        and _FN_RE.match(name)
        and callable(getattr(ak, name, None))
    )


def _resolve_fn_alias(ak: Any, fn: str) -> tuple[str, bool]:
    """Map hallucinated / deprecated names to current AKShare symbols when known."""
    alt = _FN_ALIASES.get(fn)
    if alt and callable(getattr(ak, alt, None)):
        return alt, True

    low = fn.lower()
    if low.startswith("macro_usa_") and any(
        token in low for token in ("irate", "interest", "fed_rate", "bank_rate", "fed_funds")
    ):
        candidate = "macro_bank_usa_interest_rate"
        if callable(getattr(ak, candidate, None)):
            return candidate, True

    return fn, False


def _format_not_found(fn: str, suggestions: list[str]) -> str:
    lines = [
        f"## AKShare `{fn}` — not found",
        "",
        f"`{fn}` is not a callable AKShare endpoint in this environment.",
        "Call `list_akshare_endpoints` first (use category=\"interest_rate\" for central-bank/LPR rates) "
        "and use an exact name from that list.",
    ]
    if suggestions:
        lines.append("")
        lines.append("Closest matches in your AKShare build:")
        lines.extend(f"- `{name}`" for name in suggestions)
    return "\n".join(lines)


def _format_call_error(resolved: str, exc: Exception) -> str:
    return (
        f"## AKShare `{resolved}` — call failed\n\n"
        f"The endpoint exists but raised an error: `{exc}`\n\n"
        "Try different `params_json` kwargs or pick another endpoint via `list_akshare_endpoints`."
    )


def _suggest_fn_names(ak: Any, fn: str, *, limit: int = 5) -> list[str]:
    if fn.startswith("macro_"):
        pool = _callable_api_names(ak, "macro_")
    elif fn.startswith("stock_"):
        pool = _callable_api_names(ak, "stock_")
    else:
        return []
    return difflib.get_close_matches(fn, pool, n=limit, cutoff=0.55)


def list_akshare_endpoints(
    prefix: str = "macro_",
    include_stock: bool = True,
    limit: int = 300,
    category: str = "",
) -> str:
    """List callable AKShare endpoint names usable by the generic bridge."""
    ak = _import_akshare()
    lim = max(1, min(int(limit), 2000))
    cat = category.strip().lower().replace("-", "_")

    if cat == "interest_rate":
        names = sorted(
            name
            for name in dir(ak)
            if _FN_RE.match(name)
            and callable(getattr(ak, name, None))
            and _is_interest_rate_endpoint(name)
        )
        if not names:
            raise DataVendorUnavailable(
                "akshare macro: no callable interest-rate endpoints in this AKShare build"
            )
        sample = names[:lim]
        lines = [
            f"# AKShare central-bank / LPR endpoints (matched={len(names)}, shown={len(sample)})",
            "",
            "US Fed rate is `macro_bank_usa_interest_rate` (not `macro_usa_*`). "
            "Use exact names below with get_macro_data.",
            "",
        ]
        lines.extend(f"- `{name}`" for name in sample)
        return "\n".join(lines)

    if cat not in ("", "macro"):
        raise DataVendorUnavailable(
            f"akshare macro: unknown category '{category}' "
            "(supported: interest_rate, or leave empty for prefix browse)"
        )

    prefix = prefix.strip()
    if prefix and not _FN_RE.match(prefix):
        raise DataVendorUnavailable("akshare macro: invalid prefix")
    names = sorted(
        name
        for name in dir(ak)
        if _FN_RE.match(name)
        and callable(getattr(ak, name, None))
        and (name.startswith(prefix) if prefix else True)
        and (
            name.startswith("macro_")
            or (include_stock and name.startswith("stock_"))
        )
    )
    if not names:
        raise DataVendorUnavailable(
            f"akshare macro: no callable endpoints matched prefix '{prefix}'"
        )
    sample = names[:lim]
    lines = [
        f"# AKShare endpoints (matched={len(names)}, shown={len(sample)})",
        "",
        "For central-bank/LPR rates, call list_akshare_endpoints(category=\"interest_rate\").",
        "",
    ]
    lines.extend(f"- `{name}`" for name in sample)
    return "\n".join(lines)


def get_macro_akshare(function_name: str, params_json: str = "{}", tail_rows: int = 120) -> str:
    """Call any allowed AKShare function and return a compact markdown table."""
    ak = _import_akshare()
    fn = function_name.strip()
    if not _FN_RE.match(fn):
        raise DataVendorUnavailable("akshare macro: invalid function_name")
    if not any(fn.startswith(p) for p in _ALLOWED_PREFIXES):
        raise DataVendorUnavailable(
            "akshare macro: function_name must start with 'macro_' or 'stock_'"
        )
    resolved, used_alias = _resolve_fn_alias(ak, fn)
    func = getattr(ak, resolved, None)
    if not callable(func):
        suggestions = _suggest_fn_names(ak, fn)
        return _format_not_found(fn, suggestions)

    alias_line = ""
    if used_alias and resolved != fn:
        alias_line = f"\n- resolved_from_alias: `{fn}` → `{resolved}`\n"

    try:
        params = json.loads(params_json or "{}")
    except json.JSONDecodeError as exc:
        raise DataVendorUnavailable(f"akshare macro: params_json is not valid JSON ({exc})") from exc
    if not isinstance(params, dict):
        raise DataVendorUnavailable("akshare macro: params_json must decode to a JSON object")

    try:
        raw = func(**params)
    except Exception as exc:
        return _format_call_error(resolved, exc)

    try:
        df = _normalize_obj_to_df(raw)
    except DataVendorUnavailable as exc:
        return _format_call_error(resolved, exc)

    if df.empty:
        return (
            f"## AKShare `{resolved}` — empty result\n\n"
            f"No rows returned for params `{json.dumps(params, ensure_ascii=False)}`."
        )
    trimmed = _trim_frame(df, tail_rows=tail_rows)
    table = trimmed.to_markdown(index=False)

    return (
        f"## AKShare `{resolved}`\n"
        f"{alias_line}"
        f"\n"
        f"- params: `{json.dumps(params, ensure_ascii=False)}`\n"
        f"- total_rows: `{len(df)}`\n"
        f"- shown_rows: `{len(trimmed)}` (tail)\n\n"
        f"{table}"
    )
