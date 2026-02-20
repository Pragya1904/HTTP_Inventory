"""Domain models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MetadataMessage:
    """Parsed message payload for a metadata fetch request."""

    url: str
    request_id: str


@dataclass(frozen=True)
class FetchResult:
    """Domain metadata from the URL response (value object)."""

    headers: dict[str, str]
    cookies: dict[str, str]
    page_source: str
    status_code: int
    final_url: str
    additional_details: dict[str, Any] = field(default_factory=dict)


EMPTY_METADATA: dict[str, Any] = {
    "headers": {},
    "cookies": {},
    "page_source": "",
    "status_code": 0,
    "final_url": "",
}


@dataclass(frozen=True)
class MetadataBlock:
    """Frozen-schema `metadata` block for Mongo persistence."""

    headers: dict[str, Any]
    cookies: dict[str, Any]
    page_source: str
    status_code: int
    final_url: str
    additional_details: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.headers, dict):
            raise TypeError("metadata.headers must be a dict")
        if not isinstance(self.cookies, dict):
            raise TypeError("metadata.cookies must be a dict")
        if not isinstance(self.page_source, str):
            raise TypeError("metadata.page_source must be a str")
        if not isinstance(self.status_code, int):
            raise TypeError("metadata.status_code must be an int")
        if not isinstance(self.final_url, str) or not self.final_url:
            raise TypeError("metadata.final_url must be a non-empty str")
        if self.additional_details is not None and not isinstance(self.additional_details, dict):
            raise TypeError("metadata.additional_details must be a dict or None")

    @staticmethod
    def from_fetch_result(result: FetchResult) -> "MetadataBlock":
        additional = dict(result.additional_details) if result.additional_details else None
        return MetadataBlock(
            headers=dict(result.headers),
            cookies=dict(result.cookies),
            page_source=result.page_source,
            status_code=int(result.status_code),
            final_url=str(result.final_url),
            additional_details=additional,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialisable dict for persistence. Transport-agnostic (used by repository adapters)."""
        payload: dict[str, Any] = {
            "headers": dict(self.headers),
            "cookies": dict(self.cookies),
            "page_source": self.page_source,
            "status_code": int(self.status_code),
            "final_url": str(self.final_url),
        }
        if self.additional_details is not None:
            payload["additional_details"] = dict(self.additional_details)
        return payload

