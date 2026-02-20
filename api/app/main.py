from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from api.app.composition import create_app_dependencies
from api.app.routers.health import health_router
from api.app.routers.metadata import metadata_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.bind(service_name="api", event="api_starting").info("")
    deps = create_app_dependencies()
    try:
        await deps.connect()
        app.state.settings = deps.settings
        app.state.publisher = deps.publisher
        app.state.database = deps.database
        yield
    except Exception as e:
        logger.exception("startup failed: {}", e)
        raise
    finally:
        logger.bind(service_name="api", event="api_stopping").info("")
        await deps.close()


app = FastAPI(
    title="HTTP Metadata Inventory API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(metadata_router)
