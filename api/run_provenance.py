"""Run provenance: LLM, data vendors, and analyst coverage for bias-aware history."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from api.llm_config_normalize import provenance_model_mismatch_warning

PILLAR_KEYS = (
    "core_stock_apis",
    "technical_indicators",
    "fundamental_data",
    "news_data",
)

PILLAR_LABELS = {
    "core_stock_apis": "OHLCV",
    "technical_indicators": "indicators",
    "fundamental_data": "fundamentals",
    "news_data": "news",
}


def merge_config_snapshot(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Non-sensitive config fields persisted on completed runs."""
    if not config:
        return {}
    out: Dict[str, Any] = {}
    for k in (
        "llm_provider",
        "deep_think_llm",
        "quick_think_llm",
        "max_debate_rounds",
        "max_risk_discuss_rounds",
        "output_language",
        "analysts",
        "data_vendors",
        "tool_vendors",
        "prefer_free_data_vendors",
        "dimensions_enabled",
        "dimensions_in_graph",
        "checkpoint_enabled",
    ):
        if k in config and config[k] is not None:
            out[k] = config[k]
    return out


def _first_vendor_token(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    return text.split(",")[0].strip().lower() or None


def format_data_routing(config: Dict[str, Any]) -> str:
    """Short description of market-data vendor routing."""
    dv_raw = config.get("data_vendors") or {}
    tv_raw = config.get("tool_vendors") or {}
    dv: Dict[str, Any] = dv_raw if isinstance(dv_raw, dict) else {}
    tv: Dict[str, Any] = tv_raw if isinstance(tv_raw, dict) else {}

    parts: List[str] = []
    for key in PILLAR_KEYS:
        if key in dv and dv[key] is not None and str(dv[key]).strip():
            parts.append(f"{PILLAR_LABELS[key]}→{dv[key]}")

    if not parts:
        base = "defaults"
    else:
        vals = {str(v).strip() for v in dv.values() if v is not None and str(v).strip()}
        if len(vals) == 1 and not tv:
            (single,) = vals
            base = f"all→{single}"
        else:
            base = ", ".join(parts)

    if tv:
        if len(tv) <= 2:
            overrides = ", ".join(f"{k}→{v}" for k, v in sorted(tv.items()))
            return f"{base}; overrides: {overrides}"
        return f"{base}; {len(tv)} tool overrides"
    return base


def build_run_provenance(
    config: Optional[Dict[str, Any]],
    analyst_coverage: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compact provenance dict for API list/detail responses."""
    cfg = config if isinstance(config, dict) else {}
    provider = str(cfg.get("llm_provider") or "").strip() or None
    deep = str(cfg.get("deep_think_llm") or "").strip() or None
    quick = str(cfg.get("quick_think_llm") or "").strip() or None

    analysts_raw = cfg.get("analysts")
    analysts: List[str] = []
    if isinstance(analysts_raw, list):
        analysts = [str(a).strip() for a in analysts_raw if str(a).strip()]

    vendors: set[str] = set()
    pillars = 0
    dv = cfg.get("data_vendors") if isinstance(cfg.get("data_vendors"), dict) else {}
    for key in PILLAR_KEYS:
        token = _first_vendor_token(dv.get(key) if isinstance(dv, dict) else None)
        if token:
            pillars += 1
            vendors.add(token)

    ok = empty = failed = 0
    cov = analyst_coverage if isinstance(analyst_coverage, dict) else {}
    if analysts and cov:
        for aid in analysts:
            meta = cov.get(aid) if isinstance(cov.get(aid), dict) else {}
            status = str(meta.get("status") or "").lower()
            if status == "ok":
                ok += 1
            elif status == "empty":
                empty += 1
            else:
                failed += 1
    elif cov:
        for _aid, meta in cov.items():
            if not isinstance(meta, dict):
                continue
            status = str(meta.get("status") or "").lower()
            if status == "ok":
                ok += 1
            elif status == "empty":
                empty += 1
            else:
                failed += 1
        analysts = sorted(str(k) for k in cov.keys())

    warnings: List[str] = []
    if not provider:
        warnings.append("LLM provider not recorded (legacy run)")
    if pillars < 4:
        warnings.append(f"Only {pillars}/4 data pillars configured")
    if pillars > 0 and len(vendors) == 1:
        warnings.append(f"Single data vendor ({next(iter(vendors))}) across pillars")
    if analysts and empty > 0:
        warnings.append(f"{empty} analyst section(s) empty — incomplete narrative")
    if analysts and ok < max(3, len(analysts) // 2):
        warnings.append("Few analyst sections succeeded — compare with coverage detail")
    mismatch = provenance_model_mismatch_warning(provider, deep, quick)
    if mismatch:
        warnings.append(mismatch)

    return {
        "llm_provider": provider,
        "llm_deep": deep,
        "llm_quick": quick,
        "data_routing": format_data_routing(cfg),
        "analysts_selected": analysts,
        "analysts_ok": ok,
        "analysts_empty": empty,
        "analysts_failed": failed,
        "analysts_total": len(analysts) if analysts else len(cov),
        "source_pillars": pillars,
        "vendor_count": len(vendors),
        "bias_warnings": warnings,
    }
