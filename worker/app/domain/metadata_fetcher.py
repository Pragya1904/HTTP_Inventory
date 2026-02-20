"""Metadata fetcher: orchestrates HTTP fetch; accepts all successful (2xx) responses.

Uses the HTTP port (AbstractHttpClient); client is built in the composition root.
Domain depends only on ports, not on infrastructure. Does not restrict by Content-Type;
downstream processing handles format and size.
"""
from __future__ import annotations

from loguru import logger

from worker.app.domain.models import FetchResult
from worker.app.ports.http_client import (
    AbstractHttpClient,
    HttpClientError,
    HttpClientTimeoutError,
    RequestTimeout,
)


class MetadataFetchError(Exception):
    """Base error for metadata fetching failures."""


class MetadataFetchTimeoutError(MetadataFetchError):
    """Raised when an HTTP request times out."""


class MetadataFetcher:
    """Fetches URL metadata using an injectable AbstractHttpClient.

    Response body is stored in page_source; HTTP errors are still raised via
    raise_for_status(); timeouts and client errors are mapped to domain exceptions.
    """

    def __init__(
        self,
        client: AbstractHttpClient,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        *,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self._client = client
        self._timeout = RequestTimeout(
            connect_seconds=connect_timeout_seconds,
            read_seconds=read_timeout_seconds,
        )
        self._default_headers = dict(default_headers) if default_headers else {}

    async def fetch(self, url: str) -> FetchResult:
        try:
            response = await self._client.get(
                url,
                timeout=self._timeout,
                follow_redirects=True,
                headers=self._default_headers or None,
            )
            response.raise_for_status()
        except HttpClientTimeoutError as exc:
            raise MetadataFetchTimeoutError(str(exc)) from exc
        except HttpClientError as exc:
            raise MetadataFetchError(str(exc)) from exc

        logger.debug(f"Response object: {response}, status code: {response.status_code}, headers: {dict(response.headers)}, cookies: {dict(response.cookies)}, final URL: {response.url}, text: {response.text}, elapsed time: {getattr(response, 'elapsed_seconds', 'N/A')}")
        

        return FetchResult(
            headers=dict(response.headers),
            cookies=dict(response.cookies),
            page_source=response.text,
            status_code=response.status_code,
            final_url=str(response.url),
            additional_details={},
        )
