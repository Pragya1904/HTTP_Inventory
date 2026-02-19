from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    rabbitmq_host: str = Field(..., env="RABBITMQ_HOST")
    rabbitmq_port: int = Field(..., env="RABBITMQ_PORT")
    rabbitmq_user: str = Field(..., env="RABBITMQ_USER")
    rabbitmq_password: str = Field(..., env="RABBITMQ_PASSWORD")
    queue_name: str = Field(..., env="QUEUE_NAME")
    queue_max_length: int = Field(..., env="QUEUE_MAX_LENGTH")

    mongo_uri: str = Field(..., env="MONGO_URI")
    max_retries: int = Field(..., env="MAX_RETRIES")
    prefetch_count: int = Field(..., env="PREFETCH_COUNT")

    initial_backoff_seconds: float = Field(..., env="INITIAL_BACKOFF_SECONDS")
    max_backoff_seconds: float = Field(..., env="MAX_BACKOFF_SECONDS")
    max_connection_attempts: int = Field(..., env="MAX_CONNECTION_ATTEMPTS")

