import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from loguru import logger

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

try:
    from config.settings import Settings
except ImportError:
    from api.config.settings import Settings

try:
    from publisher.rabbitmq_publisher import RabbitMQPublisher
except ImportError:
    from api.publisher.rabbitmq_publisher import RabbitMQPublisher

try:
    from infrastructure.database import get_database_connection
except ImportError:
    from api.infrastructure.database import get_database_connection

try:
    from routers.health import router as health_router
    from routers.metadata import metadata_router
except ImportError:
    from api.routers.health import router as health_router
    from api.routers.metadata import metadata_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.bind(service_name="api", event="api_starting").info("")
    settings = Settings()
    publisher = RabbitMQPublisher(settings)
    database = get_database_connection(settings)
    await publisher.connect()
    await database.connect()
    app.state.publisher = publisher
    app.state.database = database
    yield
    logger.bind(service_name="api", event="api_stopping").info("")
    await publisher.close()
    await database.close()


app = FastAPI(
    title="HTTP Metadata Inventory API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(metadata_router)
