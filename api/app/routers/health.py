import asyncio

from typing import Any
from fastapi import APIRouter, Request, Response
from loguru import logger

from api.app.routers.utils import readiness_ping_timeout_seconds
from api.app.core import SERVICE_NAME

health_router = APIRouter(tags=["Health"])

def _log(event: str, **kwargs: Any) -> None:
    logger.bind(service_name=SERVICE_NAME, event=event, **kwargs).info("")

@health_router.get(
    "/health/live",
    summary="Liveness probe",
    description="Returns 200 if the API process is running. Used to confirm the service is running.",
    responses={200: {"description": "Service is alive."}},
)
async def live() -> dict:
    return {"status": "ok"}


@health_router.get(
    "/health/ready",
    summary="Readiness probe",
    description="Returns 200 only when the publisher (RabbitMQ) and database (MongoDB) are connected and ready. Used to confirm the service is ready to accept requests.",
    responses={
        200: {"description": "Publisher and database are ready."},
        503: {"description": "Publisher or database not ready."},
    },
)
async def ready(request: Request) -> Response:
    publisher = getattr(request.app.state, "publisher", None)
    database = getattr(request.app.state, "database", None)
    if publisher is None or database is None:
        _log("components_not_initialized")
        return Response(status_code=503, content="Not ready")
    if not publisher.ready:
        _log("publisher_not_ready")
        return Response(status_code=503, content="Publisher not ready")

    timeout_s = readiness_ping_timeout_seconds(request)
    try:
        ping_ok = await asyncio.wait_for(database.ping(), timeout=timeout_s)
    except asyncio.TimeoutError:
        _log("db_ping_timeout")
        return Response(status_code=503, content="Database not ready")
    if not ping_ok:
        _log("db_not_ready")
        return Response(status_code=503, content="Database not ready")
    return Response(status_code=200, content="OK")
