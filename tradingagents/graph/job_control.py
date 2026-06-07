"""Cooperative job control hooks for LangGraph streaming execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


class GraphJobCancelled(Exception):
    """Raised when a job cancellation flag is set between graph steps."""


class GraphJobTimeout(Exception):
    """Raised when a job exceeds its wall-clock timeout between graph steps."""

    def __init__(self, timeout_seconds: int) -> None:
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Job exceeded wall-clock timeout ({timeout_seconds}s) during LangGraph execution."
        )


@dataclass
class GraphStepHooks:
    """Optional callbacks checked after each LangGraph stream step."""

    should_cancel: Optional[Callable[[], bool]] = None
    should_timeout: Optional[Callable[[], bool]] = None
    on_step: Optional[Callable[[str], None]] = None
    timeout_seconds: Optional[int] = None

    def after_step(self, node_name: str) -> None:
        if self.on_step:
            self.on_step(node_name)
        if self.should_cancel and self.should_cancel():
            raise GraphJobCancelled()
        if self.should_timeout and self.should_timeout():
            limit = self.timeout_seconds or 0
            raise GraphJobTimeout(limit)
