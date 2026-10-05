"""Keeps a replay buffer so a late page still sees every progress event."""

from __future__ import annotations

import asyncio
from typing import Any


class LiveRun:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.finished = asyncio.Event()
        self.choice = asyncio.Event()
        self.selected: str | None = None
        self.note: str = ""

    def publish(self, event: dict[str, Any]) -> None:
        self.events.append(event)
