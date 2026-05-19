"""Markdown + JSON formatters for KronosForecastPayload.

Pure functions — no I/O, no LLM calls. Easy to test against fixtures.
"""
from __future__ import annotations

from typing import Optional

from api.kronos.schema import KronosForecastPayload


def forecast_to_markdown(payload: Optional[KronosForecastPayload]) -> str:
    if payload is None:
        return ""

    last_actual = payload.history_tail[-1].close if payload.history_tail else 0.0
    last_forecast = payload.forecast[-1].close if payload.forecast else 0.0
    drift_pct = (
        ((last_forecast - last_actual) / last_actual) * 100.0
        if last_actual
        else 0.0
    )

    high_max = max((r.high for r in payload.forecast), default=0.0)
    low_min = min((r.low for r in payload.forecast), default=0.0)
    total_vol = sum(r.volume for r in payload.forecast)

    header = (
        f"## Kronos forecast — {payload.ticker} on {payload.trade_date}\n\n"
        f"**Model:** {payload.model} · "
        f"**Device:** {payload.device} · "
        f"**History:** {payload.lookback}d · "
        f"**Horizon:** {payload.pred_len}d\n\n"
    )

    narrative = (
        f"Kronos forecasts the close drifting from {last_actual:,.2f} "
        f"(last actual) to {last_forecast:,.2f} on day {payload.pred_len}, "
        f"a {drift_pct:+.2f}% move. The forecast range spans "
        f"{low_min:,.2f}–{high_max:,.2f} and the total forecast volume is "
        f"{total_vol:,.0f}.\n\n"
    )

    table_header = (
        "| Day | Date       |   open |   high |    low |  close |    volume |\n"
        "|----:|------------|-------:|-------:|-------:|-------:|----------:|\n"
    )
    table_rows = []
    for i, r in enumerate(payload.forecast, start=1):
        table_rows.append(
            f"| {i:>3} | {r.date} | "
            f"{r.open:>6.2f} | {r.high:>6.2f} | {r.low:>6.2f} | "
            f"{r.close:>6.2f} | {r.volume:>9,.0f} |"
        )
    table = table_header + "\n".join(table_rows) + "\n\n"

    footer = (
        f"*Single-path forecast from the Kronos foundation model "
        f"(sample_count={payload.sample_count}). Probabilistic bands across "
        f"multiple sampled paths are coming in a follow-up PR. Not "
        f"investment advice.*\n"
    )

    return header + narrative + table + footer


def forecast_to_state(payload: Optional[KronosForecastPayload]) -> Optional[dict]:
    """JSON-serializable dict for embedding in final_state['kronos_forecast'].

    The frontend (follow-up PR) will read this shape to render a chart.
    """
    if payload is None:
        return None
    return payload.model_dump(mode="json")
