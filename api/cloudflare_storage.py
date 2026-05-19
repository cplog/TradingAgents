"""Cloudflare storage roles — one backend per concern, no cross-fallback.

| Backend | Env vars | Used for |
|---------|----------|----------|
| **D1** (SQL) | ``CLOUDFLARE_ACCOUNT_ID``, ``CLOUDFLARE_D1_DATABASE_ID``, ``CLOUDFLARE_API_TOKEN`` | Analysis history, sector/industry SQL, coverage aggregates, dimension peer universes, optional ``ta_news_items`` / ``ta_stock_bars`` data cache |
| **KV** (StateStore) | account/token + ``CLOUDFLARE_KV_NAMESPACE_ID`` | Admin secrets, service overrides, in-flight job snapshots only |
| **Local file** | ``TRADINGAGENTS_API_STATE_FILE`` | Same as KV when Workers KV is not configured |
| **Disk cache** | ``data_cache_dir`` | Peer facts JSON (when D1 off), Yahoo sector/industry catalog cache |

History uses **either** D1 **or** KV/local — never both. Configure D1 for production history and ``/sectors`` run counts.
"""
from __future__ import annotations

import os


def _cf_core_configured() -> bool:
    return bool(
        os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
        and os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    )


def cloudflare_kv_enabled() -> bool:
    """True when Workers KV is the StateStore primary."""
    return bool(
        _cf_core_configured()
        and os.getenv("CLOUDFLARE_KV_NAMESPACE_ID", "").strip()
    )


def cloudflare_d1_enabled() -> bool:
    """True when D1 SQL should back history and peer tables."""
    return bool(
        _cf_core_configured()
        and os.getenv("CLOUDFLARE_D1_DATABASE_ID", "").strip()
    )


__all__ = [
    "cloudflare_d1_enabled",
    "cloudflare_kv_enabled",
]
