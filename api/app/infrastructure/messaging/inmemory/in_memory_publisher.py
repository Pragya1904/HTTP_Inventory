"""In-memory publisher for testing and local mode.
Not to be used as consumer not added for this publisher.
Only For Demonstration Purposes. Stating publishers can be easily changed in future without changing the code.
"""
from __future__ import annotations

from typing import Any


class InMemoryPublisher:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def connect(self) -> None:
        return

    @property
    def ready(self) -> bool:
        return True

    async def publish(self, message: dict[str, Any]) -> None:
        self.messages.append(message)

    async def close(self) -> None:
        return
