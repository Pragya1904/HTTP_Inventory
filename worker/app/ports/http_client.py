"""HTTP client port: contract for performing GET requests.

Domain and application code depend on this port; infrastructure (e.g. httpx)
implements it. Keeps domain free of infrastructure imports.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, runtime_checkable


class HttpClientError(Exception):
    """Base for HTTP client failures (status, network, etc.)."""


class HttpClientTimeoutError(HttpClientError):
    """Raised when the request times out."""


@runtime_checkable
class HttpResponse(Protocol):
    """Minimal read-only view of an HTTP response."""

    @property
    def headers(self) -> Mapping[str, str]: ...

    @property
    def cookies(self) -> Mapping[str, str]: ...

    @property
    def text(self) -> str: ...

    @property
    def status_code(self) -> int: ...

    @property
    def url(self) -> str: ...

    @property
    def elapsed_seconds(self) -> float: ...

    def raise_for_status(self) -> None: ...


@dataclass(frozen=True)
class RequestTimeout:
    """Connect and read timeouts in seconds."""

    connect_seconds: float
    read_seconds: float


@runtime_checkable
class AbstractHttpClient(Protocol):
    """Port: perform GET requests. Implementations live in infrastructure."""

    async def get(
        self,
        url: str,
        *,
        timeout: RequestTimeout,
        follow_redirects: bool = True,
        headers: dict[str, str] | None = None,
    ) -> HttpResponse:
        """Perform GET; raise HttpClientTimeoutError or HttpClientError on failure."""
        ...

    async def close(self) -> None:
        """Release resources (e.g. connection pool). No-op allowed if nothing to close."""
        ...
