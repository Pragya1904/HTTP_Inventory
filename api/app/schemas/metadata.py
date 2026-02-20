from typing import Any

from pydantic import BaseModel, HttpUrl

from api.app.constants import ProcessingStatus


class MetadataPostRequest(BaseModel):
    url: HttpUrl


class MetadataPostResponse(BaseModel):
    status: str = ProcessingStatus.QUEUED
    url: str
    request_id: str


class MetadataPayload(BaseModel):
    headers: dict[str, Any]
    cookies: dict[str, Any]
    status_code: int
    page_source: str
    additional_details: dict[str, Any] | None = None


class MetadataGetSuccessResponse(BaseModel):
    status: str = ProcessingStatus.COMPLETED
    url: str
    metadata: MetadataPayload


class MetadataGetFailedResponse(BaseModel):
    status: str = ProcessingStatus.FAILED_PERMANENT
    url: str
    error_msg: str | None = None
    attempt_number: int | None = None
