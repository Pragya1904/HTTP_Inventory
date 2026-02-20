from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from loguru import logger

from api.app.composition import create_app_dependencies
from api.app.routers.health import health_router
from api.app.routers.metadata import metadata_router
from api.app.core import SERVICE_NAME

def _log(event: str, **kwargs: Any) -> None:
    logger.bind(service_name=SERVICE_NAME, event=event, **kwargs).info("")

@asynccontextmanager
async def lifespan(app: FastAPI):
    _log("api_starting")
    deps = create_app_dependencies()
    try:
        await deps.connect()
        app.state.settings = deps.settings
        app.state.publisher = deps.publisher
        app.state.database = deps.database
        app.state.metadata_repository = deps.metadata_repository
        yield
    except Exception as e:
        logger.exception("startup failed: {}", e)
        raise
    finally:
        _log("api_stopping")
        await deps.close()


app = FastAPI(
    title="HTTP Metadata Inventory API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(metadata_router)
