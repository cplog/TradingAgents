"""Submit scan-mode analysis jobs when overnight signal fires."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from tradingagents.dataflows.daily_signals import OvernightSignal

logger = logging.getLogger(__name__)

SCAN_ANALYSTS = ["market", "news", "fundamentals", "kronos"]


def build_scan_config(base_config: Dict[str, Any]) -> Dict[str, Any]:
    cfg = dict(base_config)
    cfg["max_debate_rounds"] = 1
    cfg["max_risk_discuss_rounds"] = 1
    return cfg


async def trigger_scan_job(
    worker,
    *,
    ticker: str,
    date: str,
    base_config: Dict[str, Any],
    signal: OvernightSignal,
) -> str:
    """Enqueue a scan-mode job with overnight signal metadata."""
    config = build_scan_config(base_config)
    job_id = await worker.submit(
        ticker=ticker,
        date=date,
        config=config,
        analysts=list(SCAN_ANALYSTS),
        trigger="overnight_monitor",
        signal_score=signal.score,
        overnight_signal=signal.to_dict(),
    )
    logger.info(
        "overnight monitor triggered scan job %s for %s score=%s",
        job_id,
        ticker,
        signal.score,
    )
    return job_id
