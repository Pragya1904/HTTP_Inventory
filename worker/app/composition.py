"""Worker composition root: build and lifecycle-manage concrete dependencies.

Composition may: import concrete classes, call factories, store interface types,
manage high-level lifecycle.
"""
from __future__ import annotations

from typing import Any
from loguru import logger

from worker.app.application.processing_service import ProcessingService
from worker.app.config.settings import Settings
from worker.app.core import SERVICE_NAME
from worker.app.domain.metadata_fetcher import MetadataFetcher
from worker.app.ports.http_client import AbstractHttpClient
from worker.app.infrastructure.http.factory import create_http_client
from worker.app.infrastructure.messaging.factory import create_message_consumer
from worker.app.infrastructure.persistence.factory import create_metadata_repository
from worker.app.ports.message_consumer import MessageConsumer
from worker.app.ports.metadata_repository import MetadataRepository

def _log(event: str, **kwargs: Any) -> None:
    logger.bind(service_name=SERVICE_NAME, event=event, **kwargs).info("")


class WorkerDependencies:
    """Holds wired worker dependencies and their lifecycle."""

    def __init__(self, *, settings: Settings) -> None:
        self._settings = settings
        self._repository: MetadataRepository | None = None
        self._message_consumer: MessageConsumer | None = None
        self._http_client: AbstractHttpClient | None = None
        self._processing_service: ProcessingService | None = None
        self._connected = False

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def repository(self) -> MetadataRepository:
        if self._repository is None:
            raise RuntimeError("repository is not initialized")
        return self._repository

    @property
    def message_consumer(self) -> MessageConsumer:
        if self._message_consumer is None:
            raise RuntimeError("message_consumer is not initialized")
        return self._message_consumer

    @property
    def processing_service(self) -> ProcessingService:
        if self._processing_service is None:
            raise RuntimeError("processing_service is not initialized")
        return self._processing_service

    async def connect(self) -> None:
        self._repository = await create_metadata_repository(self._settings)

        self._message_consumer = create_message_consumer(self._settings)
        await self._message_consumer.connect()

        self._http_client = create_http_client(self._settings)
        default_headers: dict[str, str] | None = None
        if self._settings.fetch_user_agent:
            default_headers = {"User-Agent": self._settings.fetch_user_agent}

        fetcher = MetadataFetcher(
            self._http_client,
            connect_timeout_seconds=self._settings.fetch_connect_timeout_seconds,
            read_timeout_seconds=self._settings.fetch_read_timeout_seconds,
            default_headers=default_headers,
        )
        self._processing_service = ProcessingService(
            self.repository,
            fetcher,
            max_retries=self._settings.max_retries,
            max_page_source_length=self._settings.max_page_source_length,
        )
        self._connected = True

    async def close(self) -> None:
        if self._message_consumer is not None:
            try:
                await self._message_consumer.close()
            except Exception as exc:
                logger.warning("message consumer close failed: {}", exc)
            self._message_consumer = None

        if self._http_client is not None:
            try:
                await self._http_client.close()
            except Exception as exc:
                logger.warning("http client close failed: {}", exc)
            self._http_client = None

        if self._repository is not None:
            try:
                await self._repository.close()
            except Exception as exc:
                logger.warning("repository close failed: {}", exc)

        self._repository = None
        self._processing_service = None
        self._connected = False


def create_worker_dependencies(settings: Settings | None = None) -> WorkerDependencies:
    return WorkerDependencies(settings=settings or Settings())
