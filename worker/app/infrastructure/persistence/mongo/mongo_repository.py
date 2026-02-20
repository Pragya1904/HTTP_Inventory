"""MongoDB implementation of MetadataRepository."""
from __future__ import annotations

import inspect
from datetime import datetime, timezone
from typing import Any

from pymongo import ReturnDocument
from motor.motor_asyncio import AsyncIOMotorCollection

from worker.app.constants import PROCESSING_STATUS
from worker.app.domain.processing_context import ProcessingContext
from worker.app.domain.models import EMPTY_METADATA, MetadataBlock

class MongoRepository:
    """Concrete implementation of MetadataRepository using MongoDB."""

    def __init__(self, collection: AsyncIOMotorCollection, *, client: Any | None = None) -> None:
        self._collection = collection
        self._client = client

    async def ensure_indexes(self) -> None:
        """Infrastructure bootstrap: create indexes. Not part of the port."""
        await self._collection.create_index("url", unique=True, name="uq_metadata_url")
        await self._collection.create_index("created_at", name="idx_metadata_created_at")

    async def ensure_record(self, url: str, ctx: ProcessingContext) -> None:
        now = datetime.now(timezone.utc)
        await self._collection.update_one(
            {"url": url},
            {
                "$setOnInsert": {
                    "url": url,
                    "status": PROCESSING_STATUS.PENDING,
                    "metadata": dict(EMPTY_METADATA),
                    "processing": {
                        "attempt_number": int(ctx.attempt_number),
                        "error_msg": None,
                        "last_attempt_at": now,
                        "last_request_id": ctx.request_id,
                    },
                    "additional_details": None,
                    "created_at": now,
                },
                "$set": {"updated_at": now},
            },
            upsert=True,
        )

    async def mark_in_progress(self, url: str, ctx: ProcessingContext) -> None:
        now = datetime.now(timezone.utc)
        await self._collection.update_one(
            {"url": url},
            {
                "$set": {
                    "status": PROCESSING_STATUS.IN_PROGRESS,
                    "processing.attempt_number": int(ctx.attempt_number),
                    "processing.error_msg": None,
                    "processing.last_attempt_at": now,
                    "processing.last_request_id": ctx.request_id,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "url": url,
                    "metadata": dict(EMPTY_METADATA),
                    "additional_details": None,
                    "created_at": now,
                },
            },
            upsert=True,
        )

    async def mark_completed(self, url: str, ctx: ProcessingContext, metadata: MetadataBlock) -> None:
        now = datetime.now(timezone.utc)
        payload: dict[str, Any] = metadata.to_dict()
        await self._collection.update_one(
            {"url": url},
            {
                "$setOnInsert": {
                    "url": url,
                    "additional_details": None,
                    "created_at": now,
                },
                "$set": {
                    "status": PROCESSING_STATUS.COMPLETED,
                    "metadata": payload,
                    "processing.attempt_number": int(ctx.attempt_number),
                    "processing.error_msg": None,
                    "processing.last_attempt_at": now,
                    "processing.last_request_id": ctx.request_id,
                    "updated_at": now,
                },
            },
            upsert=True,
        )

    async def mark_retryable_failure(self, url: str, ctx: ProcessingContext, error: str) -> int:
        now = datetime.now(timezone.utc)
        doc = await self._collection.find_one_and_update(
            {"url": url},
            {
                "$setOnInsert": {
                    "url": url,
                    "metadata": dict(EMPTY_METADATA),
                    "additional_details": None,
                    "created_at": now,
                },
                "$set": {
                    "status": PROCESSING_STATUS.FAILED_RETRYABLE,
                    "processing.error_msg": error,
                    "processing.last_attempt_at": now,
                    "processing.last_request_id": ctx.request_id,
                    "processing.attempt_number": int(ctx.attempt_number),
                    "updated_at": now,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if not doc:
            return int(ctx.attempt_number)
        return int(doc.get("processing", {}).get("attempt_number", int(ctx.attempt_number)))

    async def mark_permanent_failure(self, url: str, ctx: ProcessingContext, error: str) -> None:
        now = datetime.now(timezone.utc)
        await self._collection.update_one(
            {"url": url},
            {
                "$setOnInsert": {
                    "url": url,
                    "metadata": dict(EMPTY_METADATA),
                    "additional_details": None,
                    "created_at": now,
                },
                "$set": {
                    "status": PROCESSING_STATUS.FAILED_PERMANENT,
                    "processing.error_msg": error,
                    "processing.last_attempt_at": now,
                    "processing.last_request_id": ctx.request_id,
                    "processing.attempt_number": int(ctx.attempt_number),
                    "updated_at": now,
                },
            },
            upsert=True,
        )

    async def get_by_url(self, url: str) -> dict[str, Any] | None:
        return await self._collection.find_one({"url": url})

    async def close(self) -> None:
        """Close underlying Mongo client when owned by this adapter."""
        if self._client is not None:
            res = self._client.close()
            if inspect.isawaitable(res):
                await res
