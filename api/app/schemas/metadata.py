from pydantic import BaseModel, HttpUrl

from api.app.constants import ProcessingStatus


class MetadataPostRequest(BaseModel):
    url: HttpUrl


class MetadataPostResponse(BaseModel):
    status: str = ProcessingStatus.QUEUED
    url: str
    request_id: str
