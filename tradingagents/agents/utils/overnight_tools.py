from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.akshare_monitor import scan_us_panic_candidates
from tradingagents.dataflows.daily_signals import compute_overnight_signal


@tool
def compute_overnight_signal_tool(
    symbol: Annotated[str, "Ticker symbol, e.g. AAPL"],
) -> str:
    """
    Compute daily Barbell Trend Cloud overnight dip signal (score 0–100).
    Uses free daily OHLCV + optional AKShare spot for today's change/amplitude.
    """
    try:
        signal = compute_overnight_signal(symbol)
    except Exception as exc:
        return f"Overnight signal computation failed for {symbol}: {exc}"
    return signal.to_markdown() + "\n\n```json\n" + signal.to_json() + "\n```"


@tool
def scan_us_market_drops(
    min_drop_pct: Annotated[float, "Minimum drop percent, e.g. -10 for -10%"] = -10.0,
) -> str:
    """
    Scan all US equities via AKShare for names down at least min_drop_pct today.
    Free data; useful before refining with compute_overnight_signal on watchlist names.
    """
    try:
        hits = scan_us_panic_candidates(min_drop_pct=min_drop_pct)
    except Exception as exc:
        return (
            f"US market scan temporarily unavailable ({exc}). "
            f"Use `compute_overnight_signal` for individual tickers instead."
        )
    if not hits:
        return f"No US tickers at or below {min_drop_pct}% today."
    lines = [f"# US panic candidates (≤ {min_drop_pct}%)", "", f"Count: {len(hits)}", ""]
    for row in hits[:40]:
        lines.append(
            f"- **{row['ticker']}** {row.get('change_pct', '?'):.2f}% "
            f"amp={row.get('amplitude_pct', 'n/a')} {row.get('name', '')}"
        )
    if len(hits) > 40:
        lines.append(f"\n… and {len(hits) - 40} more")
    return "\n".join(lines)
