"""Concrete HTTP client implementation using httpx (injected where AbstractHttpClient is needed)."""
from __future__ import annotations

import httpx

from worker.app.ports.http_client import (
    AbstractHttpClient,
    HttpClientError,
    HttpClientTimeoutError,
    HttpResponse,
    RequestTimeout,
)


class _HttpxResponseAdapter:
    """Adapts httpx.Response to the HttpResponse protocol."""

    def __init__(self, response: httpx.Response) -> None:
        self._response = response

    @property
    def headers(self) -> dict[str, str]:
        return dict(self._response.headers)

    @property
    def cookies(self) -> dict[str, str]:
        return {c.name: c.value for c in self._response.cookies.jar}

    @property
    def text(self) -> str:
        return self._response.text

    @property
    def status_code(self) -> int:
        return self._response.status_code

    @property
    def url(self) -> str:
        return str(self._response.url)

    @property
    def elapsed_seconds(self) -> float:
        return self._response.elapsed.total_seconds()

    def raise_for_status(self) -> None:
        try:
            self._response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HttpClientError(
                f"http status {exc.response.status_code} for {exc.request.url}"
            ) from exc


class HttpxHttpClient(AbstractHttpClient):
    """AbstractHttpClient implementation using httpx.AsyncClient."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def get(
        self,
        url: str,
        *,
        timeout: RequestTimeout,
        follow_redirects: bool = True,
        headers: dict[str, str] | None = None,
    ) -> HttpResponse:
        httpx_timeout = httpx.Timeout(
            connect=timeout.connect_seconds,
            read=timeout.read_seconds,
            write=timeout.read_seconds,
            pool=timeout.connect_seconds,
        )
        try:
            response = await self._client.get(
                url,
                timeout=httpx_timeout,
                follow_redirects=follow_redirects,
                headers=headers or {},
            )
            return _HttpxResponseAdapter(response)
        except httpx.TimeoutException as exc:
            raise HttpClientTimeoutError(f"timeout while fetching {url}") from exc
        except httpx.HTTPError as exc:
            raise HttpClientError(f"http fetch failed for {url}: {exc}") from exc

    async def close(self) -> None:
        await self._client.aclose()
