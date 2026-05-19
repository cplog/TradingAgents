"""Minimal Cloudflare D1 HTTP executor (same contract as ``api.history._d1_query``).

Used by ``tradingagents`` dataflows so CLI/graph jobs can persist cache rows without
importing the FastAPI package. Requires ``requests`` (already a framework dependency).
"""

from __future__ import annotations

import os
from typing import Any, Optional

import requests


def cloudflare_d1_configured() -> bool:
    return bool(
        os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
        and os.getenv("CLOUDFLARE_D1_DATABASE_ID", "").strip()
        and os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    )


def d1_execute_sql(sql: str, params: Optional[list[Any]] = None) -> list[dict[str, Any]]:
    """Run a single D1 statement via Cloudflare API v4; return result rows dicts."""
    account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    db_id = os.getenv("CLOUDFLARE_D1_DATABASE_ID", "").strip()
    token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    if not (account and db_id and token):
        raise RuntimeError(
            "Cloudflare D1 is not configured (need CLOUDFLARE_ACCOUNT_ID, "
            "CLOUDFLARE_D1_DATABASE_ID, CLOUDFLARE_API_TOKEN)"
        )

    url = (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{account}/d1/database/{db_id}/query"
    )
    body: dict[str, Any] = {"sql": sql}
    if params:
        body["params"] = params
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    resp = requests.post(url, headers=headers, json=body, timeout=35)
    resp.raise_for_status()
    payload = resp.json()
    result_rows = payload.get("result") or []
    if not isinstance(result_rows, list) or not result_rows:
        return []
    first = result_rows[0] or {}
    if not first.get("success", False):
        raise RuntimeError(f"D1 query failed: {first}")
    rows = first.get("results") or []
    return rows if isinstance(rows, list) else []
