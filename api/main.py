"""
FastAPI application entry point — HTTP Metadata Inventory API.
"""
from fastapi import FastAPI

from api.routers import metadata_router

app = FastAPI(
    title="HTTP Metadata Inventory API",
    description="Ingest and manage HTTP transaction metadata.",
    version="0.1.0",
)

app.include_router(metadata_router, prefix="/metadata", tags=["metadata"])
