import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response
from loguru import logger

try:
    from api.schemas.metadata import MetadataPostRequest, MetadataPostResponse
except ImportError:
    from schemas.metadata import MetadataPostRequest, MetadataPostResponse

try:
    from api.publisher.constants import PublisherState
except ImportError:
    from publisher.constants import PublisherState

metadata_router = APIRouter(prefix="/metadata", tags=["metadata"])


@metadata_router.post("")
async def post_metadata(request: Request, body: MetadataPostRequest) -> Response:
    publisher = getattr(request.app.state, "publisher", None)
    if publisher is None:
        logger.bind(service_name="api", event="publish_rejected", reason="publisher_not_ready").warning("")
        return Response(status_code=503, content="Publisher not available")
    if publisher.state != PublisherState.READY:
        logger.bind(service_name="api", event="publish_rejected", reason="publisher_not_ready").warning("")
        return Response(status_code=503, content="Publisher not ready")
    url_str = str(body.url)
    request_id = str(uuid.uuid4())
    message = {
        "url": url_str,
        "requested_at": datetime.now(tz=timezone.utc).isoformat(),
        "request_id": request_id,
    }
    try:
        await publisher.publish(message)
    except RuntimeError as e:
        reason = str(e)
        logger.bind(service_name="api", event="publish_failed", request_id=request_id, url=url_str, reason=reason).warning("")
        if "queue_rejected" in reason or "queue_overflow" in reason:
            return Response(status_code=503, content="Queue rejected")
        return Response(status_code=503, content="Publish failed")
    except Exception as e:
        logger.bind(service_name="api", event="publish_failed", request_id=request_id, url=url_str, reason=str(e)).exception("")
        return Response(status_code=503, content="Publish failed")
    return Response(
        status_code=202,
        media_type="application/json",
        content=MetadataPostResponse(status="QUEUED", url=url_str, request_id=request_id).model_dump_json(),
    )


@metadata_router.get("")
async def get_metadata() -> Response:
    return Response(
        status_code=202,
        media_type="application/json",
        content='{"message": "Processing or retrieval not yet implemented"}',
    )
