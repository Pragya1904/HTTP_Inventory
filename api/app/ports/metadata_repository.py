"""Port: metadata read persistence (API reads; worker writes)."""
from __future__ import annotations

from typing import Any, Protocol


class MetadataRepository(Protocol):
    async def get_by_url(self, url: str) -> dict[str, Any] | None: ...

