"""HTTP client factory: builds AbstractHttpClient from settings (no provider logic in composition)."""
from __future__ import annotations

import httpx

from worker.app.config.settings import Settings
from worker.app.ports.http_client import AbstractHttpClient
from worker.app.infrastructure.http.httpx_client import HttpxHttpClient


def create_http_client(settings: Settings) -> AbstractHttpClient:
    """Build an HTTP client from settings. Timeouts are applied per-request by the adapter."""
    async_client = httpx.AsyncClient()
    return HttpxHttpClient(async_client)
