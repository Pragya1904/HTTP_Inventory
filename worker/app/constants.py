"""Worker-level constants shared across modules."""
from __future__ import annotations


class PROCESSING_STATUS:
    UNKNOWN = "UNKNOWN"
    QUEUED = "QUEUED"
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_PERMANENT = "FAILED_PERMANENT"
