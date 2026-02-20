"""Repository factory: selects and assembles persistence adapters."""
from __future__ import annotations

from worker.app.config.settings import Settings
from worker.app.infrastructure.persistence.mongo.connection import create_mongo_client
from worker.app.infrastructure.persistence.mongo.mongo_repository import MongoRepository
from worker.app.ports.metadata_repository import MetadataRepository


async def create_metadata_repository(settings: Settings) -> MetadataRepository:
    """Select repository adapter from configuration and return port type."""
    backend = settings.repository_backend.strip().lower()

    if backend in ("mongo", ):
        mongo_client = await create_mongo_client(settings)
        repo = MongoRepository(
            mongo_client[settings.database_name][settings.database_collection],
            client=mongo_client,
        )
        await repo.ensure_indexes()
        return repo
    raise ValueError(f"Unsupported repository backend: {backend}")
