"""Pydantic models for the notification layer."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

NotificationChannelType = Literal[
    "webhook",
    "telegram",
    "slack",
    "email",
    "discord",
]


class NotificationChannel(BaseModel):
    """One outbound notification channel."""

    id: str = Field(..., description="Stable channel identifier (UUID).")
    type: NotificationChannelType
    name: str = Field(..., min_length=1, description="Human label, e.g. 'Telegram alerts'.")
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("config", mode="before")
    @classmethod
    def _ensure_dict(cls, v: Any) -> dict[str, Any]:
        if v is None:
            return {}
        if not isinstance(v, dict):
            raise ValueError("config must be a dict")
        return dict(v)


class NotificationConfig(BaseModel):
    """Root notification settings persisted in StateStore."""

    enabled: bool = False
    quiet_hours_start: Optional[str] = Field(
        default=None,
        pattern=r"^\d{2}:\d{2}$",
        description="Quiet hours start in HH:MM (24h).",
    )
    quiet_hours_end: Optional[str] = Field(
        default=None,
        pattern=r"^\d{2}:\d{2}$",
        description="Quiet hours end in HH:MM (24h).",
    )
    channels: list[NotificationChannel] = Field(default_factory=list)
    dedupe_minutes: int = Field(default=15, ge=0, le=1440)

    @field_validator("channels", mode="before")
    @classmethod
    def _ensure_channels(cls, v: Any) -> list[NotificationChannel]:
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError("channels must be a list")
        return [NotificationChannel.model_validate(x) if isinstance(x, dict) else x for x in v]


class NotificationTestRequest(BaseModel):
    channel_id: str = Field(..., min_length=1)
    message: str = Field(default="Test notification from TradingAgents")


class NotificationStatus(BaseModel):
    enabled: bool
    channel_count: int
    channel_types: list[str]
    quiet_hours: Optional[str]
    dedupe_minutes: int


class NotificationSendRequest(BaseModel):
    title: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    tags: Optional[list[str]] = None
    force: bool = False
