from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@postgres:5432/inference_club"
    redis_url: str = "redis://redis:6379/0"
    media_dir: str = "/app/media"
    openai_api_key: str = ""
    cors_origins: list[str] = ["*"]
    debug: bool = False

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
