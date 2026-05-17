"""Compact text summary of a StockDimensions dict for LLM prompts (no api imports)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def _fmt_num(v: Any) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        return f"{v:.2f}" if isinstance(v, float) else str(v)
    return str(v)


def _flatten_pillar_scores(pillar_scores: Any) -> List[Tuple[str, int, str]]:
    """Return (path, score, rationale_snippet) for each sub-dimension."""
    out: List[Tuple[str, int, str]] = []
    if not isinstance(pillar_scores, dict):
        return out
    for pillar_name, group in pillar_scores.items():
        if not isinstance(group, dict):
            continue
        for sub_name, sub in group.items():
            if not isinstance(sub, dict):
                continue
            sc = sub.get("score")
            rationale = str(sub.get("rationale") or "")[:160]
            if isinstance(sc, int):
                out.append((f"{pillar_name}.{sub_name}", sc, rationale))
    return out


def render_compact_dimensions_summary(dimensions: Dict[str, Any]) -> str:
    """Build a short bullet summary for Portfolio Manager / Trader context."""
    ticker = str(dimensions.get("ticker") or "?")
    as_of = str(dimensions.get("as_of_date") or "?")
    version = str(dimensions.get("dimensions_version") or "?")
    source = str(dimensions.get("source") or "?")
    peer = dimensions.get("peer_universe_id")
    peer_scope = dimensions.get("peer_scope")
    slug_used = dimensions.get("peer_universe_resolved_slug")
    search_path = dimensions.get("peer_universe_search_path") or []
    flags = dimensions.get("data_quality_flags") or []
    if not isinstance(flags, list):
        flags = []

    lines: List[str] = [
        f"Ticker {ticker} as of {as_of} (dimensions {version}, source={source}).",
    ]
    if peer_scope:
        lines.append(f"Peer scope: {peer_scope}")
    if peer:
        lines.append(f"Peer universe label: {peer}")
    elif not peer_scope or peer_scope == "unavailable":
        lines.append("Peer universe: unavailable or cache miss — style factors rely on sentiment only.")

    if isinstance(search_path, list) and search_path:
        sampled = "; ".join(str(x) for x in search_path[:4])
        if len(search_path) > 4:
            sampled += " …"
        lines.append(f"Peer comparison search path (ordered): {sampled}")

    if slug_used:
        lines.append(f"Peer cache / D1 slug used: {slug_used}")

    fs = dimensions.get("factor_scores")
    if isinstance(fs, dict):
        lines.append("Factor scores (0–100, higher is stronger for that style except interpret low_risk as defensive quality):")
        for key in ("value", "growth", "quality", "momentum", "low_risk", "sentiment"):
            block = fs.get(key)
            score: Optional[float] = None
            if isinstance(block, dict):
                raw = block.get("score")
                if isinstance(raw, (int, float)):
                    score = float(raw)
            lines.append(f"- {key}: {_fmt_num(score)}")

    flat = _flatten_pillar_scores(dimensions.get("pillar_scores"))
    if flat:
        flat_sorted = sorted(flat, key=lambda x: x[1])
        lows = flat_sorted[:3]
        highs = sorted(flat, key=lambda x: -x[1])[:3]

        def _fmt_items(items: List[Tuple[str, int, str]], label: str) -> None:
            lines.append(f"{label}:")
            for path, sc, rationale in items:
                tail = f" — {rationale}" if rationale else ""
                lines.append(f"- {path}: {sc}/5{tail}")

        _fmt_items(lows, "Weakest pillar signals (1–5)")
        _fmt_items(highs, "Strongest pillar signals (1–5)")

    facts = dimensions.get("facts")
    if isinstance(facts, dict):
        price = facts.get("price")
        cap = facts.get("market_cap_usd")
        sector = facts.get("sector")
        industry = facts.get("industry")
        lines.append(
            "Facts snapshot: "
            f"price={_fmt_num(price)}, market_cap_usd={_fmt_num(cap)}, "
            f"sector={sector or 'n/a'}, industry={industry or 'n/a'}"
        )

    if flags:
        lines.append("Data quality flags: " + "; ".join(str(f) for f in flags))

    return "\n".join(lines)
