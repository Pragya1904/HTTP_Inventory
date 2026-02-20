"""API-level constants shared across modules."""
from __future__ import annotations

class ProcessingStatus:
    QUEUED = "QUEUED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED_PERMANENT = "FAILED_PERMANENT"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    UNKNOWN = "UNKNOWN"
    PENDING = "PENDING"
