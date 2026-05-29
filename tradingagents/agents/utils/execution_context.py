"""Live quote fetch + trading-plan level comparison for practical execution guidance."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

PlanStatus = Literal[
    "quote_unavailable",
    "no_levels",
    "below_stop",
    "above_target",
    "below_entry",
    "in_entry_zone",
    "above_entry",
    "neutral",
]

_FINAL_PROPOSAL_RE = re.compile(r"\s*FINAL TRANSACTION PROPOSAL:[\s\S]*", re.IGNORECASE)


def _escape_label(label: str) -> str:
    return re.escape(label)


def clean_md_field_value(raw: str) -> str:
    without = _FINAL_PROPOSAL_RE.split(raw, maxsplit=1)[0]
    return re.sub(r"\*\*", "", without).strip()


def parse_md_field(text: str, *labels: str) -> Optional[str]:
    if not (text or "").strip():
        return None
    for label in labels:
        pattern = (
            rf"\*\*{_escape_label(label)}\*\*:\s*"
            rf"([\s\S]*?)(?=\n\*\*[A-Za-z][^*]*\*\*:|\nFINAL TRANSACTION PROPOSAL:|$)"
        )
        m = re.search(pattern, text, re.IGNORECASE)
        if not m or not m.group(1):
            continue
        value = clean_md_field_value(m.group(1))
        if value:
            return value
    return None


def _parse_price(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    cleaned = value.replace(",", "").strip()
    try:
        n = float(cleaned)
    except ValueError:
        m = re.search(r"(\d+(?:\.\d+)?)", cleaned)
        if not m:
            return None
        try:
            n = float(m.group(1))
        except ValueError:
            return None
    return n if n > 0 else None


def _plausible_level_price(value: float, reference: Optional[float]) -> bool:
    if value <= 0 or value > 1_000_000:
        return False
    if reference is not None and reference > 0:
        ratio = value / reference
        if ratio < 0.15 or ratio > 6.0:
            return False
    return True


def _pick_narrative_price(
    matches: list[float],
    reference: Optional[float],
) -> Optional[float]:
    candidates = [m for m in matches if _plausible_level_price(m, reference)]
    if not candidates:
        return None
    if reference is not None and reference > 0:
        return min(candidates, key=lambda x: abs(x - reference))
    return candidates[0]


def _infer_levels_from_narrative(
    text: str,
    *,
    reference: Optional[float] = None,
) -> Dict[str, Optional[float]]:
    """Best-effort extraction when structured **Label**: fields are missing."""
    if not (text or "").strip():
        return {"entry": None, "stop_loss": None, "price_target": None}

    entry_matches: list[float] = []
    stop_matches: list[float] = []
    target_matches: list[float] = []

    entry_patterns = [
        r"(?i)(?:entry|buy(?:\s+zone)?|add(?:\s+near)?|accumulate(?:\s+(?:at|near|around))?)"
        r"\s*(?:at|near|around|@|:)?\s*\$?\s*(\d+(?:\.\d+)?)",
        r"(?i)\bentry\s*:\s*\$?\s*(\d+(?:\.\d+)?)",
        r"(?i)pull-?back(?:\s+to)?\s*\$?\s*(\d+(?:\.\d+)?)",
    ]
    stop_patterns = [
        r"(?i)(?:stop(?:\s*-?\s*loss)?|risk(?:\s+level)?)\s*(?:at|below|under|:)?\s*\$?\s*(\d+(?:\.\d+)?)",
        r"(?i)\bstop\s*:\s*\$?\s*(\d+(?:\.\d+)?)",
    ]
    target_patterns = [
        r"(?i)(?:price\s+target|target\s+price|upside\s+target|pt)\s*(?:at|of|to|:)?\s*\$?\s*(\d+(?:\.\d+)?)",
        r"(?i)\btarget\s*:\s*\$?\s*(\d+(?:\.\d+)?)",
    ]

    for pat in entry_patterns:
        entry_matches.extend(float(m.group(1)) for m in re.finditer(pat, text))
    for pat in stop_patterns:
        stop_matches.extend(float(m.group(1)) for m in re.finditer(pat, text))
    for pat in target_patterns:
        target_matches.extend(float(m.group(1)) for m in re.finditer(pat, text))

    # entry/stop/target triplet in one sentence
    triplet = re.search(
        r"(?i)entry[^$\d]{0,40}\$?\s*(\d+(?:\.\d+)?)[^$\d]{0,40}"
        r"stop[^$\d]{0,40}\$?\s*(\d+(?:\.\d+)?)[^$\d]{0,40}"
        r"target[^$\d]{0,40}\$?\s*(\d+(?:\.\d+)?)",
        text,
    )
    if triplet:
        entry_matches.append(float(triplet.group(1)))
        stop_matches.append(float(triplet.group(2)))
        target_matches.append(float(triplet.group(3)))

    # Buy zone range: use midpoint as entry
    zone = re.search(
        r"(?i)(?:between|range|zone)\s+\$?\s*(\d+(?:\.\d+)?)\s*(?:and|to|–|-)\s*\$?\s*(\d+(?:\.\d+)?)",
        text,
    )
    if zone:
        lo = float(zone.group(1))
        hi = float(zone.group(2))
        entry_matches.append((lo + hi) / 2.0)

    return {
        "entry": _pick_narrative_price(entry_matches, reference),
        "stop_loss": _pick_narrative_price(stop_matches, reference),
        "price_target": _pick_narrative_price(target_matches, reference),
    }


def _levels_from_structured(structured: Optional[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    if not isinstance(structured, dict):
        return {"entry": None, "stop_loss": None, "price_target": None}

    def _from_obj(obj: Any) -> Dict[str, Optional[float]]:
        if not isinstance(obj, dict):
            return {"entry": None, "stop_loss": None, "price_target": None}
        entry = obj.get("entry_price") if obj.get("entry_price") is not None else obj.get("entry")
        stop = obj.get("stop_loss")
        if stop is None:
            stop = obj.get("stop_loss_price")
        target = obj.get("price_target") if obj.get("price_target") is not None else obj.get("target")
        return {
            "entry": _parse_price(str(entry)) if entry is not None else None,
            "stop_loss": _parse_price(str(stop)) if stop is not None else None,
            "price_target": _parse_price(str(target)) if target is not None else None,
        }

    trader = _from_obj(structured.get("trader_proposal"))
    pm = _from_obj(structured.get("portfolio_manager_decision"))
    return {
        "entry": trader["entry"] or pm["entry"],
        "stop_loss": trader["stop_loss"] or pm["stop_loss"],
        "price_target": pm["price_target"] or trader["price_target"],
    }


def _merge_levels(
    *parts: Dict[str, Optional[float]],
) -> Dict[str, Optional[float]]:
    out: Dict[str, Optional[float]] = {
        "entry": None,
        "stop_loss": None,
        "price_target": None,
    }
    for part in parts:
        for key in out:
            if out[key] is None and part.get(key) is not None:
                out[key] = part[key]
    return out


def derive_plan_levels(
    reports: Optional[Dict[str, str]],
    *,
    structured: Optional[Dict[str, Any]] = None,
    plan_levels: Optional[Dict[str, Any]] = None,
    reference_price: Optional[float] = None,
) -> Dict[str, Optional[float]]:
    """Entry/stop/target from labeled fields, then structured JSON, narrative, stored snapshot."""
    if isinstance(plan_levels, dict):
        snap = {
            "entry": _parse_price(str(plan_levels.get("entry")))
            if plan_levels.get("entry") is not None
            else None,
            "stop_loss": _parse_price(str(plan_levels.get("stop_loss")))
            if plan_levels.get("stop_loss") is not None
            else None,
            "price_target": _parse_price(str(plan_levels.get("price_target")))
            if plan_levels.get("price_target") is not None
            else None,
        }
        if any(snap.values()):
            return snap

    reports = reports or {}
    pm = reports.get("portfolio_decision") or ""
    trader = reports.get("trader_plan") or ""
    research = reports.get("research_plan") or ""

    labeled = {
        "entry": _parse_price(
            parse_md_field(trader, "Entry Price")
            or parse_md_field(pm, "Entry Price", "Entry")
        ),
        "stop_loss": _parse_price(
            parse_md_field(trader, "Stop Loss")
            or parse_md_field(pm, "Stop Loss")
        ),
        "price_target": _parse_price(
            parse_md_field(pm, "Price Target", "Target Price")
            or parse_md_field(trader, "Price Target", "Target Price")
        ),
    }

    structured_levels = _levels_from_structured(structured)

    strategic = parse_md_field(research, "Strategic Actions") or ""
    exec_summary = parse_md_field(pm, "Executive Summary") or ""
    narrative_sources = [trader, pm, strategic, exec_summary, research]
    narrative: Dict[str, Optional[float]] = {
        "entry": None,
        "stop_loss": None,
        "price_target": None,
    }
    for block in narrative_sources:
        if not block.strip():
            continue
        inferred = _infer_levels_from_narrative(block, reference=reference_price)
        narrative = _merge_levels(narrative, inferred)

    return _merge_levels(labeled, structured_levels, narrative)


def fetch_live_quote(ticker: str) -> Dict[str, Any]:
    """Return regularMarketPrice via yfinance (best-effort)."""
    out: Dict[str, Any] = {
        "ticker": ticker,
        "price": None,
        "currency": None,
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "yfinance_regularMarketPrice",
        "error": None,
    }
    try:
        from api.dimensions.facts import _yf_ticker

        info = _yf_ticker(ticker).info or {}
        raw = info.get("regularMarketPrice")
        if raw is None:
            raw = info.get("currentPrice")
        if raw is not None:
            out["price"] = float(raw)
        currency = info.get("currency")
        if isinstance(currency, str) and currency.strip():
            out["currency"] = currency.strip()
        if out["price"] is None:
            out["error"] = "No regularMarketPrice in quote response"
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def fetch_report_close(ticker: str, trade_date: str) -> Optional[float]:
    """Last daily close on or before trade_date (for as-of context)."""
    try:
        import pandas as pd
        from api.dimensions.facts import _yf_ticker

        df = _yf_ticker(ticker).history(start=trade_date, end=trade_date, interval="1d")
        if df is None or df.empty:
            end = (pd.Timestamp(trade_date) + pd.Timedelta(days=7)).strftime("%Y-%m-%d")
            df = _yf_ticker(ticker).history(start=trade_date, end=end, interval="1d")
        if df is None or df.empty:
            return None
        close = df["Close"].iloc[-1]
        return float(close)
    except Exception:
        return None


def _parse_iso_age_hours(iso_ts: Optional[str]) -> Optional[float]:
    if not iso_ts:
        return None
    try:
        normalized = iso_ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt.astimezone(timezone.utc)
        return max(0.0, delta.total_seconds() / 3600.0)
    except (TypeError, ValueError):
        return None


def _price_drift_pct(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b <= 0:
        return None
    return abs(a - b) / b * 100.0


def compare_live_vs_plan(
    live_price: Optional[float],
    levels: Dict[str, Optional[float]],
    *,
    entry_tolerance_pct: float = 0.02,
    run_time_price: Optional[float] = None,
    completed_at: Optional[str] = None,
    stale_hours: float = 24.0,
    drift_pct_threshold: float = 3.0,
) -> Dict[str, Any]:
    entry = levels.get("entry")
    stop = levels.get("stop_loss")
    target = levels.get("price_target")

    if live_price is None or live_price <= 0:
        return {
            "status": "quote_unavailable",
            "guidance": (
                "Live quote unavailable; treat entry/stop/target as historical only "
                "and re-run analysis before acting."
            ),
            "live_price": live_price,
            "entry": entry,
            "stop_loss": stop,
            "price_target": target,
            "delta_vs_entry_pct": None,
            "delta_vs_stop_pct": None,
            "delta_vs_target_pct": None,
            "run_time_price": run_time_price,
            "suggest_refresh": True,
        }

    if entry is None and stop is None and target is None:
        return {
            "status": "no_levels",
            "guidance": (
                "No entry/stop/target levels found in this report. "
                "Use the full narrative or re-run for actionable levels."
            ),
            "live_price": live_price,
            "entry": entry,
            "stop_loss": stop,
            "price_target": target,
            "delta_vs_entry_pct": None,
            "delta_vs_stop_pct": None,
            "delta_vs_target_pct": None,
            "run_time_price": run_time_price,
            "suggest_refresh": False,
        }

    age_hours = _parse_iso_age_hours(completed_at)
    stale = age_hours is not None and age_hours > stale_hours
    drift = _price_drift_pct(live_price, run_time_price)
    price_moved = drift is not None and drift >= drift_pct_threshold
    price_unchanged = drift is not None and drift < 1.0

    delta_entry = ((live_price - entry) / entry) if entry else None
    delta_stop = ((live_price - stop) / stop) if stop else None
    delta_target = ((live_price - target) / target) if target else None

    suggest_refresh = False

    if stop is not None and live_price < stop:
        status: PlanStatus = "below_stop"
        run_was_below = run_time_price is not None and run_time_price < stop
        if run_was_below and (price_unchanged or not stale):
            guidance = (
                f"At analysis time live was {run_time_price:.2f} — already below the stated stop "
                f"({stop:.2f}). Do not use these entry/stop levels; treat the rating as strategic "
                "only and wait for a new base. No refresh needed unless the thesis changes."
            )
            suggest_refresh = False
        elif price_moved and run_time_price is not None:
            guidance = (
                f"Live price ({live_price:.2f}) has moved materially since analysis "
                f"(was {run_time_price:.2f} at run time) and is now below stop ({stop:.2f}). "
                "Setup invalidated — refresh analysis before acting."
            )
            suggest_refresh = True
        else:
            guidance = (
                f"Live price ({live_price:.2f}) is below the report stop-loss ({stop:.2f}). "
                "The tactical setup from this run is invalidated. Do not enter using this plan; "
                "refresh analysis with today's date before acting."
            )
            suggest_refresh = True
    elif target is not None and live_price >= target:
        status = "above_target"
        guidance = (
            f"Live price ({live_price:.2f}) is at or above the report target ({target:.2f}). "
            "Much of the planned upside may already be realized; confirm before adding."
        )
        suggest_refresh = stale or price_moved
    elif entry is not None:
        tol = entry * entry_tolerance_pct
        if abs(live_price - entry) <= tol or (stop is not None and stop <= live_price <= entry):
            status = "in_entry_zone"
            guidance = (
                f"Live price ({live_price:.2f}) is near the planned entry ({entry:.2f}). "
                "The pull-back entry plan may be actionable if the thesis still holds."
            )
        elif live_price < entry:
            status = "below_entry"
            entry_far_above_run = (
                run_time_price is not None
                and entry > run_time_price * 1.05
                and (price_unchanged or not stale)
            )
            if entry_far_above_run:
                guidance = (
                    f"Live ({live_price:.2f}) is below entry ({entry:.2f}), but entry was set above "
                    f"the run-time quote ({run_time_price:.2f}). Wait for price to reach a realistic "
                    "zone anchored to market — do not chase the historical level."
                )
                suggest_refresh = False
            else:
                guidance = (
                    f"Live price ({live_price:.2f}) is below the planned entry ({entry:.2f}). "
                    "Wait for price to stabilize toward the entry zone or refresh before sizing in."
                )
                suggest_refresh = stale or price_moved
        else:
            status = "above_entry"
            guidance = (
                f"Live price ({live_price:.2f}) is above the planned entry ({entry:.2f}). "
                "Wait for a pull-back into the entry zone or a confirmed breakout per the plan."
            )
    else:
        status = "neutral"
        guidance = (
            f"Live price is {live_price:.2f}. Compare against the report narrative before acting."
        )

    return {
        "status": status,
        "guidance": guidance,
        "live_price": live_price,
        "entry": entry,
        "stop_loss": stop,
        "price_target": target,
        "delta_vs_entry_pct": round(delta_entry * 100, 2) if delta_entry is not None else None,
        "delta_vs_stop_pct": round(delta_stop * 100, 2) if delta_stop is not None else None,
        "delta_vs_target_pct": round(delta_target * 100, 2) if delta_target is not None else None,
        "run_time_price": run_time_price,
        "suggest_refresh": suggest_refresh,
    }


def build_run_execution_snapshot(
    ticker: str,
    trade_date: str,
    quote: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Fetch live quote once at graph start; reuse for prompts and persisted result."""
    quote = quote if quote is not None else fetch_live_quote(ticker)
    report_close = fetch_report_close(ticker, trade_date)
    return {
        "markdown": _format_run_execution_context_markdown(
            ticker, trade_date, quote, report_close
        ),
        "quote": quote,
        "report_close": report_close,
        "trade_date": trade_date,
    }


def _format_run_execution_context_markdown(
    ticker: str,
    trade_date: str,
    quote: Dict[str, Any],
    report_close: Optional[float],
) -> str:
    """Compact block injected into analyst/manager/trader prompts at run time."""
    price = quote.get("price")
    lines = [
        "## Execution context (live quote at run time)",
        f"- Ticker: {ticker}",
        f"- Report trade date: {trade_date}",
    ]
    if report_close is not None:
        lines.append(f"- Last close on/near trade date: {report_close:.2f}")
    if price is not None:
        lines.append(f"- Live quote (regularMarketPrice): {price:.2f}")
        if report_close is not None and report_close > 0:
            chg = (price - report_close) / report_close * 100
            lines.append(f"- Change vs report-date close: {chg:+.1f}%")
    else:
        err = quote.get("error") or "unavailable"
        lines.append(f"- Live quote: unavailable ({err})")
    lines.extend(
        [
            "",
            "**Mandatory desk rules (must follow):**",
            "- Entry Price must be within ~3% of the live quote above, OR you must explicitly "
            "label it a limit order above market with rationale.",
            "- Stop Loss for long setups must be **below** the live quote. If live is already "
            "below a technical level (e.g. 50-SMA), do **not** use that level as entry.",
            "- If live is materially below a typical pull-back entry (>5% below a cited support), "
            "tactical action should be Hold/wait — not Buy with entry at the old support.",
            "- State one sentence on what the desk should do **right now** given live vs stop/target.",
        ]
    )
    return "\n".join(lines)


def build_run_execution_context_block(
    ticker: str,
    trade_date: str,
    quote: Optional[Dict[str, Any]] = None,
) -> str:
    """Compact block injected into analyst/manager prompts at run time."""
    return build_run_execution_snapshot(ticker, trade_date, quote=quote)["markdown"]


def build_run_execution_annotation(
    reports: Optional[Dict[str, str]],
    run_snapshot: Optional[Dict[str, Any]],
    completed_at: str,
    *,
    structured: Optional[Dict[str, Any]] = None,
    plan_levels: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Post-run snapshot: how plan levels relate to the quote captured at graph start."""
    if not run_snapshot:
        return None
    quote = run_snapshot.get("quote") or {}
    run_price = quote.get("price")
    ref = float(run_price) if run_price is not None else None
    levels = derive_plan_levels(
        reports,
        structured=structured,
        plan_levels=plan_levels,
        reference_price=ref,
    )
    comparison_at_run = compare_live_vs_plan(
        run_price,
        levels,
        run_time_price=run_price,
        completed_at=completed_at,
    )
    entry = levels.get("entry")
    anchored = True
    if run_price and entry and entry > run_price * 1.05:
        anchored = False
    return {
        "quote": quote,
        "report_close": run_snapshot.get("report_close"),
        "trade_date": run_snapshot.get("trade_date"),
        "levels": levels,
        "comparison_at_run": comparison_at_run,
        "levels_anchored_to_live": anchored,
        "completed_at": completed_at,
    }


def parse_run_snapshot_json(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def build_live_context_payload(
    ticker: str,
    trade_date: str,
    reports: Optional[Dict[str, str]],
    *,
    quote: Optional[Dict[str, Any]] = None,
    run_snapshot: Optional[Dict[str, Any]] = None,
    completed_at: Optional[str] = None,
    structured: Optional[Dict[str, Any]] = None,
    plan_levels: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Full payload for API / UI live-vs-plan strip."""
    quote = quote if quote is not None else fetch_live_quote(ticker)
    ref = quote.get("price")
    ref_f = float(ref) if ref is not None else None
    levels = derive_plan_levels(
        reports,
        structured=structured,
        plan_levels=plan_levels,
        reference_price=ref_f,
    )
    run_time_price = None
    if run_snapshot:
        run_quote = run_snapshot.get("quote") or {}
        run_time_price = run_quote.get("price")
        if completed_at is None:
            completed_at = run_snapshot.get("completed_at")
    comparison = compare_live_vs_plan(
        quote.get("price"),
        levels,
        run_time_price=run_time_price,
        completed_at=completed_at,
    )
    report_close = fetch_report_close(ticker, trade_date)
    if run_snapshot and run_snapshot.get("report_close") is not None:
        report_close = run_snapshot.get("report_close")

    historical_note = (
        "Rating and levels below are from the completed run; live guidance reflects "
        "current market price."
    )
    if run_time_price is not None:
        historical_note = (
            f"Analysis used live quote {run_time_price:.2f} at run time. "
            "Rating is unchanged; guidance compares today's price to this run's levels."
        )

    return {
        "quote": quote,
        "report_close": report_close,
        "trade_date": trade_date,
        "levels": levels,
        "comparison": comparison,
        "run_time_quote": run_snapshot.get("quote") if run_snapshot else None,
        "levels_anchored_at_run": run_snapshot.get("levels_anchored_to_live") if run_snapshot else None,
        "historical_rating_note": historical_note,
    }
