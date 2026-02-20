"""Abstract interface for metadata persistence (port)."""
from __future__ import annotations

from typing import Any, Protocol

from worker.app.domain.models import MetadataBlock
from worker.app.domain.processing_context import ProcessingContext


class MetadataRepository(Protocol):
    """Port: metadata record persistence. Implementations live in infrastructure."""

    async def ensure_indexes(self) -> None: ...

    async def ensure_record(self, url: str, ctx: ProcessingContext) -> None: ...

    async def mark_in_progress(self, url: str, ctx: ProcessingContext) -> None: ...

    async def mark_completed(self, url: str, ctx: ProcessingContext, metadata: MetadataBlock) -> None: ...

    async def mark_retryable_failure(self, url: str, ctx: ProcessingContext, error: str) -> int: ...

    async def mark_permanent_failure(self, url: str, ctx: ProcessingContext, error: str) -> None: ...

    async def get_by_url(self, url: str) -> dict[str, Any] | None: ...

    async def close(self) -> None:
        """Release resources (e.g. DB client). No-op allowed if nothing to close."""
        ...
