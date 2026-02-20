from fastapi import APIRouter, Request, Response
from loguru import logger

from api.app.constants import ProcessingStatus
from api.app.schemas.metadata import MetadataPostRequest, MetadataPostResponse
from api.app.services.enqueue_metadata import enqueue_metadata


metadata_router = APIRouter(prefix="/metadata", tags=["metadata"])


@metadata_router.post("")
async def post_metadata(request: Request, body: MetadataPostRequest) -> Response:
    publisher = getattr(request.app.state, "publisher", None)
    if publisher is None:
        logger.bind(service_name="api", event="publish_rejected", reason="publisher_not_ready").warning("")
        return Response(status_code=503, content="Publisher not available")

    url_str = str(body.url)
    outcome = await enqueue_metadata(url_str, publisher)

    if outcome.success:
        return Response(
            status_code=202,
            media_type="application/json",
            content=MetadataPostResponse(
                status=ProcessingStatus.QUEUED, url=outcome.url or url_str, request_id=outcome.request_id or ""
            ).model_dump_json(),
        )

    logger.bind(
        service_name="api",
        event="publish_failed",
        reason=outcome.error,
        url=outcome.url or url_str,
        request_id=outcome.request_id or "",
    ).warning("")
    content = "Queue rejected" if outcome.is_queue_rejected else (outcome.error or "Publish failed")
    return Response(status_code=503, content=content)


@metadata_router.get("")
async def get_metadata() -> Response:
    return Response(
        status_code=202,
        media_type="application/json",
        content='{"message": "Processing or retrieval not yet implemented"}',
    )
