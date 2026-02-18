from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@postgres:5432/inference_club"
    redis_url: str = "redis://redis:6379/0"
    media_dir: str = "/app/media"
    openai_api_key: str = ""
    invokeai_url: str = "http://192.168.5.173:9090"
    invokeai_board_id: str | None = None
    comfyui_url: str = "http://192.168.6.19:8188"
    cors_origins: list[str] = ["*"]
    debug: bool = False

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
