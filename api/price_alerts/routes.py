"""FastAPI router for price alert CRUD and management."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from api.price_alerts.engine import get_engine
from api.price_alerts.models import (
    PriceAlertHit,
    PriceAlertRule,
    PriceAlertRuleCreate,
    PriceAlertRuleUpdate,
)

router = APIRouter(prefix="/api/price-alerts", tags=["price_alerts"])


@router.get("/rules")
async def list_rules() -> list[PriceAlertRule]:
    return get_engine().list_rules()


@router.get("/rules/{rule_id}")
async def get_rule(rule_id: str) -> PriceAlertRule:
    rule = get_engine().get_rule(rule_id)
    if rule is None:
        raise HTTPException(404, "Rule not found")
    return rule


@router.post("/rules", status_code=201)
async def create_rule(body: PriceAlertRuleCreate) -> PriceAlertRule:
    rule = PriceAlertRule(
        name=body.name,
        ticker=body.ticker.upper(),
        market=body.market,
        enabled=body.enabled,
        condition_group=body.condition_group,
        cooldown_minutes=body.cooldown_minutes,
        max_triggers_per_day=body.max_triggers_per_day,
        repeat_mode=body.repeat_mode,
        market_hours_mode=body.market_hours_mode,
        notify_channel_ids=body.notify_channel_ids,
        expire_at=body.expire_at,
    )
    return get_engine().create_rule(rule)


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: str, body: PriceAlertRuleUpdate) -> PriceAlertRule:
    updates = body.model_dump(exclude_none=True)
    rule = get_engine().update_rule(rule_id, updates)
    if rule is None:
        raise HTTPException(404, "Rule not found")
    return rule


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str) -> dict[str, bool]:
    ok = get_engine().delete_rule(rule_id)
    if not ok:
        raise HTTPException(404, "Rule not found")
    return {"ok": True}


@router.get("/hits")
async def list_hits(limit: int = 50) -> list[PriceAlertHit]:
    return get_engine().list_hits(limit)


@router.delete("/hits")
async def clear_hits() -> dict[str, bool]:
    get_engine().clear_hits()
    return {"ok": True}


@router.post("/tick")
async def tick_alerts() -> dict[str, Any]:
    """Manually trigger one evaluation pass."""
    return get_engine().tick()


@router.get("/status")
async def alert_status() -> dict[str, Any]:
    return get_engine().status()
