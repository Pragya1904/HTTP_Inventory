from pydantic import BaseModel, HttpUrl


class MetadataPostRequest(BaseModel):
    url: HttpUrl


class MetadataPostResponse(BaseModel):
    status: str = "QUEUED"
    url: str
    request_id: str
