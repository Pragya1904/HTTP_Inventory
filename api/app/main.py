import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from loguru import logger

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from api.config.settings import Settings
from api.infrastructure.database import get_database_connection
from api.publisher.rabbitmq_publisher import RabbitMQPublisher
from api.routers.health import router as health_router
from api.routers.metadata import metadata_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.bind(service_name="api", event="api_starting").info("")
    settings = Settings()
    publisher = RabbitMQPublisher(settings)
    database = get_database_connection(settings)
    publisher_connected = False
    database_connected = False
    try:
        await publisher.connect()
        publisher_connected = True
        try:
            await database.connect()
            database_connected = True
        except Exception as e:
            await publisher.close()
            logger.exception("database connect failed: {}", e)
            raise

        app.state.settings = settings
        app.state.publisher = publisher
        app.state.database = database
        yield
    finally:
        logger.bind(service_name="api", event="api_stopping").info("")
        if publisher_connected:
            await publisher.close()
        if database_connected:
            await database.close()


app = FastAPI(
    title="HTTP Metadata Inventory API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(metadata_router)
