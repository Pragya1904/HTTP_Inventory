from __future__ import annotations

import inspect
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from worker.app.domain.processing_context import ProcessingContext
from worker.app.config.settings import Settings
from worker.app.constants import PROCESSING_STATUS
from worker.app.domain.models import MetadataBlock
from worker.app.infrastructure.persistence.mongo.connection import create_mongo_client
from worker.app.infrastructure.persistence.mongo.mongo_repository import MongoRepository


def _build_worker_settings() -> Settings:
    return Settings(
        database_host=os.getenv("DATABASE_HOST", "mongo"),
        database_port=int(os.getenv("DATABASE_PORT", "27017")),
        database_user=os.getenv("DATABASE_USER", ""),
        database_password=os.getenv("DATABASE_PASSWORD", ""),
        database_name=os.getenv("DATABASE_NAME", "metadata_inventory"),
        database_collection=os.getenv("DATABASE_COLLECTION", "metadata_records"),
        broker_host=os.getenv("BROKER_HOST", "rabbitmq"),
        broker_port=int(os.getenv("BROKER_PORT", "5672")),
        broker_user=os.getenv("BROKER_USER", "guest"),
        broker_password=os.getenv("BROKER_PASSWORD", "guest"),
        queue_name=os.getenv("QUEUE_NAME", "metadata_queue"),
        queue_max_length=int(os.getenv("QUEUE_MAX_LENGTH", "1000")),
        max_retries=int(os.getenv("MAX_RETRIES", "3")),
        prefetch_count=int(os.getenv("PREFETCH_COUNT", "1")),
        repository_backend=os.getenv("REPOSITORY_BACKEND", "mongo"),
        consumer_backend=os.getenv("CONSUMER_BACKEND", "rabbitmq"),
        initial_backoff_seconds=float(os.getenv("INITIAL_BACKOFF_SECONDS", "1")),
        max_backoff_seconds=float(os.getenv("MAX_BACKOFF_SECONDS", "30")),
        max_connection_attempts=int(os.getenv("MAX_CONNECTION_ATTEMPTS", "10")),
        backoff_multiplier=float(os.getenv("BACKOFF_MULTIPLIER", "2")),
        database_connection_timeout_ms=int(os.getenv("DATABASE_CONNECTION_TIMEOUT_MS", "5000")),
    )


@pytest.mark.integration
def test_worker_mongo_connection_ping_is_live() -> None:
    async def _run() -> None:
        settings = _build_worker_settings()
        client = await create_mongo_client(settings)
        try:
            ping = await client.admin.command("ping")
            assert ping.get("ok") == 1
        finally:
            res = client.close()
            if inspect.isawaitable(res):
                await res

    asyncio.run(_run())


@pytest.mark.integration
def test_worker_mongo_collection_and_indexes_exist() -> None:
    async def _run() -> None:
        settings = _build_worker_settings()
        client = await create_mongo_client(settings)
        repo = MongoRepository(
            client[settings.database_name][settings.database_collection],
            client=client,
        )

        url = f"https://dummy.local/index-check/{uuid.uuid4()}"
        ctx = ProcessingContext(
            request_id=f"req-{uuid.uuid4()}",
            started_at=datetime.now(timezone.utc),
            attempt_number=0,
        )
        try:
            await repo.ensure_indexes()
            await repo.ensure_record(url, ctx)

            collection_names = await client[settings.database_name].list_collection_names()
            assert settings.database_collection in collection_names

            index_info = await client[settings.database_name][settings.database_collection].index_information()
            assert "uq_metadata_url" in index_info
            assert "idx_metadata_created_at" in index_info
        finally:
            await client[settings.database_name][settings.database_collection].delete_many({"url": url})
            await repo.close()

    asyncio.run(_run())


@pytest.mark.integration
def test_worker_mongo_dummy_write_and_read_roundtrip() -> None:
    async def _run() -> None:
        settings = _build_worker_settings()
        client = await create_mongo_client(settings)
        repo = MongoRepository(
            client[settings.database_name][settings.database_collection],
            client=client,
        )

        url = f"https://dummy.local/persistence-check/{uuid.uuid4()}"
        ctx = ProcessingContext(
            request_id=f"req-{uuid.uuid4()}",
            started_at=datetime.now(timezone.utc),
            attempt_number=0,
        )
        dummy_metadata = MetadataBlock(
            headers={"content-type": "text/plain"},
            cookies={"session": "dummy"},
            page_source="dummy page source",
            status_code=200,
            final_url=url,
            additional_details={"source": "integration-test"},
        )

        try:
            await repo.ensure_indexes()
            await repo.ensure_record(url, ctx)
            await repo.mark_in_progress(url, ctx)
            await repo.mark_completed(url, ctx, dummy_metadata)

            doc = await repo.get_by_url(url)
            assert doc is not None
            assert doc["url"] == url
            assert doc["status"] == PROCESSING_STATUS.COMPLETED
            assert isinstance(doc.get("metadata"), dict)
            assert doc["metadata"]["status_code"] == 200
            assert doc["metadata"]["final_url"] == url
            assert doc["metadata"]["additional_details"]["source"] == "integration-test"
            assert isinstance(doc.get("processing"), dict)
            assert doc["processing"]["error_msg"] is None
            assert doc["processing"]["attempt_number"] == ctx.attempt_number
            assert doc["processing"]["last_request_id"] == ctx.request_id
            assert doc.get("created_at") is not None
            assert doc.get("updated_at") is not None
        finally:
            await client[settings.database_name][settings.database_collection].delete_many({"url": url})
            await repo.close()

    asyncio.run(_run())


@pytest.mark.integration
def test_worker_mongo_fetch_records_created_in_past_24_hours() -> None:
    async def _run() -> None:
        settings = _build_worker_settings()
        client = await create_mongo_client(settings)
        repo = MongoRepository(
            client[settings.database_name][settings.database_collection],
            client=client,
        )

        url = f"https://dummy.local/past-24h/{uuid.uuid4()}"
        ctx = ProcessingContext(
            request_id=f"req-{uuid.uuid4()}",
            started_at=datetime.now(timezone.utc),
            attempt_number=0,
        )

        try:
            await repo.ensure_indexes()
            await repo.ensure_record(url, ctx)

            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            coll = client[settings.database_name][settings.database_collection]
            docs = await coll.find({"created_at": {"$gte": cutoff}}).to_list(length=1000)

            assert isinstance(docs, list)
            assert any(d.get("url") == url for d in docs)
        finally:
            await client[settings.database_name][settings.database_collection].delete_many({"url": url})
            await repo.close()

    asyncio.run(_run())
