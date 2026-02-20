"""Port: database connection for health and persistence. Implementations live in infrastructure."""
from __future__ import annotations

from typing import Protocol


class DatabaseConnection(Protocol):
    """Interface for DB connection lifecycle and ping."""

    @property
    def ready(self) -> bool: ...

    async def connect(self) -> None: ...

    async def ping(self) -> bool: ...

    async def close(self) -> None: ...
