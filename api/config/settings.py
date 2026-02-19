from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_host: str = Field(..., env="DATABASE_HOST")
    database_port: int = Field(..., env="DATABASE_PORT")
    database_user: str = Field("", env="DATABASE_USER")
    database_password: str = Field("", env="DATABASE_PASSWORD")

    broker_host: str = Field(..., env="BROKER_HOST")
    broker_port: int = Field(..., env="BROKER_PORT")
    broker_user: str = Field(..., env="BROKER_USER")
    broker_password: str = Field(..., env="BROKER_PASSWORD")

    queue_name: str = Field(..., env="QUEUE_NAME")
    queue_max_length: int = Field(..., env="QUEUE_MAX_LENGTH")

    max_retries: int = Field(..., env="MAX_RETRIES")
    prefetch_count: int = Field(..., env="PREFETCH_COUNT")

    initial_backoff_seconds: float = Field(..., env="INITIAL_BACKOFF_SECONDS")
    max_backoff_seconds: float = Field(..., env="MAX_BACKOFF_SECONDS")
    max_connection_attempts: int = Field(..., env="MAX_CONNECTION_ATTEMPTS")

    readiness_ping_timeout_seconds: float = Field(30.0, env="READINESS_PING_TIMEOUT_SECONDS")
