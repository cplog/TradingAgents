"""Pydantic schemas for price alert rules and hits."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

ConditionOp = Literal[">", ">=", "<", "<=", "=", "!=", "between"]
ConditionType = Literal["price", "change_pct", "volume", "turnover", "volume_ratio"]


class AlertCondition(BaseModel):
    type: ConditionType
    op: ConditionOp
    value: float | list[float]


class ConditionGroup(BaseModel):
    op: Literal["and", "or"] = "and"
    items: list[AlertCondition] = Field(default_factory=list)


class PriceAlertRule(BaseModel):
    id: str = Field(default_factory=lambda: __import__("uuid").uuid4().hex[:12])
    name: str = Field(..., min_length=1, max_length=100)
    ticker: str = Field(..., min_length=1, max_length=20)
    market: str = "US"
    enabled: bool = True
    condition_group: ConditionGroup = Field(default_factory=ConditionGroup)
    cooldown_minutes: int = Field(default=15, ge=0)
    max_triggers_per_day: int = Field(default=10, ge=0)
    repeat_mode: Literal["once", "always"] = "always"
    market_hours_mode: Literal["any", "trading_only"] = "any"
    notify_channel_ids: list[str] = Field(default_factory=list)
    expire_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    updated_at: datetime = Field(default_factory=lambda: datetime.utcnow())


class PriceAlertHit(BaseModel):
    id: str = Field(default_factory=lambda: __import__("uuid").uuid4().hex[:12])
    rule_id: str
    ticker: str
    triggered_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    price: float | None = None
    change_pct: float | None = None
    snapshot: dict[str, Any] = Field(default_factory=dict)
    notified: bool = False
    notify_error: str | None = None


class PriceAlertRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    ticker: str = Field(..., min_length=1, max_length=20)
    market: str = "US"
    enabled: bool = True
    condition_group: ConditionGroup = Field(default_factory=ConditionGroup)
    cooldown_minutes: int = Field(default=15, ge=0)
    max_triggers_per_day: int = Field(default=10, ge=0)
    repeat_mode: Literal["once", "always"] = "always"
    market_hours_mode: Literal["any", "trading_only"] = "any"
    notify_channel_ids: list[str] = Field(default_factory=list)
    expire_at: Optional[datetime] = None


class PriceAlertRuleUpdate(BaseModel):
    name: Optional[str] = None
    enabled: Optional[bool] = None
    condition_group: Optional[ConditionGroup] = None
    cooldown_minutes: Optional[int] = None
    max_triggers_per_day: Optional[int] = None
    repeat_mode: Optional[Literal["once", "always"]] = None
    market_hours_mode: Optional[Literal["any", "trading_only"]] = None
    notify_channel_ids: Optional[list[str]] = None
    expire_at: Optional[datetime] = None
