from fastapi import APIRouter, Request, Response
from loguru import logger

try:
    from api.publisher.constants import PublisherState
except ImportError:
    from publisher.constants import PublisherState

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(request: Request) -> Response:
    publisher = getattr(request.app.state, "publisher", None)
    database = getattr(request.app.state, "database", None)
    if publisher is None or database is None:
        logger.bind(service_name="api", event="readiness_failed", reason="components_not_initialized").warning("")
        return Response(status_code=503, content="Not ready")
    if publisher.state != PublisherState.READY:
        logger.bind(service_name="api", event="readiness_failed", reason="publisher_not_ready").warning("")
        return Response(status_code=503, content="Publisher not ready")
    if not await database.ping():
        logger.bind(service_name="api", event="readiness_failed", reason="db_not_ready").warning("")
        return Response(status_code=503, content="Database not ready")
    return Response(status_code=200, content="OK")
