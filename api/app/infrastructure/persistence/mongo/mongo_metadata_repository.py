"""MongoDB implementation of API MetadataRepository (read-only)."""
from __future__ import annotations

from typing import Any

from api.app.infrastructure.persistence.mongo.mongo_connection import MongoConnection
from api.app.ports.metadata_repository import MetadataRepository


class MongoMetadataRepository(MetadataRepository):
    def __init__(self, database: MongoConnection) -> None:
        self._database = database

    async def get_by_url(self, url: str) -> dict[str, Any] | None:
        return await self._database.metadata_collection.find_one({"url": url})

