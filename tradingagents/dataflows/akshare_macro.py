"""Generic AKShare macro/stock dataset bridge for analyst tools.

This module intentionally exposes a dynamic function surface so analysts can
query the broader AKShare catalog (for example ``macro_*`` and ``stock_*``)
without adding one wrapper per endpoint.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pandas as pd

from .vendor_errors import DataVendorUnavailable

_FN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ALLOWED_PREFIXES = ("macro_", "stock_")


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


def list_akshare_endpoints(prefix: str = "macro_", include_stock: bool = True, limit: int = 300) -> str:
    """List callable AKShare endpoint names usable by the generic bridge."""
    ak = _import_akshare()
    prefix = prefix.strip()
    if prefix and not _FN_RE.match(prefix):
        raise DataVendorUnavailable("akshare macro: invalid prefix")
    lim = max(1, min(int(limit), 2000))
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
    lines = [f"# AKShare endpoints (matched={len(names)}, shown={len(sample)})", ""]
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
    func = getattr(ak, fn, None)
    if not callable(func):
        raise DataVendorUnavailable(f"akshare macro: function not found: {fn}")

    try:
        params = json.loads(params_json or "{}")
    except json.JSONDecodeError as exc:
        raise DataVendorUnavailable(f"akshare macro: params_json is not valid JSON ({exc})") from exc
    if not isinstance(params, dict):
        raise DataVendorUnavailable("akshare macro: params_json must decode to a JSON object")

    try:
        raw = func(**params)
    except Exception as exc:
        raise DataVendorUnavailable(f"akshare macro: {fn} failed: {exc}") from exc

    df = _normalize_obj_to_df(raw)
    if df.empty:
        raise DataVendorUnavailable(f"akshare macro: {fn} returned no rows")
    trimmed = _trim_frame(df, tail_rows=tail_rows)
    table = trimmed.to_markdown(index=False)

    return (
        f"## AKShare `{fn}`\n\n"
        f"- params: `{json.dumps(params, ensure_ascii=False)}`\n"
        f"- total_rows: `{len(df)}`\n"
        f"- shown_rows: `{len(trimmed)}` (tail)\n\n"
        f"{table}"
    )
