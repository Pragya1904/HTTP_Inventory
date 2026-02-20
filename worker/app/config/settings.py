from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_host: str = Field(..., validation_alias="DATABASE_HOST")
    database_port: int = Field(..., validation_alias="DATABASE_PORT")
    database_user: str = Field("", validation_alias="DATABASE_USER")
    database_password: str = Field("", validation_alias="DATABASE_PASSWORD")
    database_name: str = Field("metadata_inventory", validation_alias="DATABASE_NAME")
    database_collection: str = Field(
        "metadata_records",
        validation_alias="DATABASE_COLLECTION",
    )

    broker_host: str = Field(..., validation_alias="BROKER_HOST")
    broker_port: int = Field(..., validation_alias="BROKER_PORT")
    broker_user: str = Field(..., validation_alias="BROKER_USER")
    broker_password: str = Field(..., validation_alias="BROKER_PASSWORD")

    queue_name: str = Field(..., validation_alias="QUEUE_NAME")
    queue_max_length: int = Field(..., validation_alias="QUEUE_MAX_LENGTH")

    # Max fetch attempts (0, 1, ..., max_retries-1). After the last attempt fails we mark FAILED_PERMANENT.
    max_retries: int = Field(..., validation_alias="MAX_RETRIES")
    prefetch_count: int = Field(..., validation_alias="PREFETCH_COUNT")

    repository_backend: str = Field("mongo", validation_alias="REPOSITORY_BACKEND")
    consumer_backend: str = Field("rabbitmq", validation_alias="CONSUMER_BACKEND")
    
    initial_backoff_seconds: float = Field(..., validation_alias="INITIAL_BACKOFF_SECONDS")
    max_backoff_seconds: float = Field(..., validation_alias="MAX_BACKOFF_SECONDS")
    max_connection_attempts: int = Field(..., validation_alias="MAX_CONNECTION_ATTEMPTS")
    backoff_multiplier: float = Field(2.0, validation_alias="BACKOFF_MULTIPLIER")
    database_connection_timeout_ms: int = Field(5000, validation_alias="DATABASE_CONNECTION_TIMEOUT_MS")
    fetch_connect_timeout_seconds: float = Field(5.0, validation_alias="FETCH_CONNECT_TIMEOUT_SECONDS")
    fetch_read_timeout_seconds: float = Field(15.0, validation_alias="FETCH_READ_TIMEOUT_SECONDS")
    fetch_user_agent: str = Field("", validation_alias="FETCH_USER_AGENT")

    max_page_source_length: int = Field(1_000_000, validation_alias="MAX_PAGE_SOURCE_LENGTH")
