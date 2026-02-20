"""Domain value object for per-message processing context. Used by MetadataRepository port."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ProcessingContext:
    """Per-message processing context."""

    request_id: str
    started_at: datetime
    attempt_number: int = 0
