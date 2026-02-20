"""
Accepts plain Python types and MessagePublisher abstraction; returns an outcome.
Router translates outcome to HTTP status codes and content.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from api.app.ports.message_publisher import MessagePublisher


@dataclass(frozen=True)
class EnqueueMetadataOutcome:
    """Result of enqueue_metadata.
    success=True => request_id and url set.
    success=False => error set; request_id and url may be set when failure occurred after building the message (e.g. publish raised).
    """
    success: bool
    request_id: str | None = None
    url: str | None = None
    error: str | None = None

    @property
    def is_queue_rejected(self) -> bool:
        """True if failure was due to queue reject/overflow (caller may map to specific 503 message)."""
        if not self.error:
            return False
        return "queue_rejected" in self.error or "queue_overflow" in self.error


async def enqueue_metadata(url: str, publisher: MessagePublisher) -> EnqueueMetadataOutcome:
    """
    Enqueue a URL for metadata processing.
    Returns outcome; router maps to 202/503 and logging.
    Caller must ensure publisher is not None (router returns 503 when missing).
    """
    if not publisher.ready:
        return EnqueueMetadataOutcome(success=False, error="publisher_not_ready")

    request_id = str(uuid.uuid4())
    message: dict[str, Any] = {
        "url": url,
        "requested_at": datetime.now(tz=timezone.utc).isoformat(),
        "request_id": request_id,
    }

    try:
        await publisher.publish(message)
        return EnqueueMetadataOutcome(success=True, request_id=request_id, url=url)
    except RuntimeError as e:
        return EnqueueMetadataOutcome(success=False, request_id=request_id, url=url, error=str(e))
    except Exception as e:
        return EnqueueMetadataOutcome(success=False, request_id=request_id, url=url, error=str(e))
