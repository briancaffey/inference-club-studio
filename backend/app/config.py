from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@postgres:5432/inference_club"
    redis_url: str = "redis://redis:6379/0"
    media_dir: str = "/app/media"
    openai_api_key: str = ""
    groq_api_key: str = ""
    openai_base_url: str = "http://192.168.6.19:8002/v1"
    openai_model: str = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16"
    invokeai_url: str = "http://192.168.5.173:9090"
    invokeai_board_id: str | None = None
    comfyui_url: str = "http://192.168.6.19:8188"
    qwen_vl_url: str = "http://192.168.5.253:8000"
    dia_url: str = "http://192.168.5.253:7860"
    magpie_url: str = "http://192.168.6.3:9000"
    stt_url: str = "http://192.168.5.96:8001"
    cors_origins: list[str] = ["*"]
    debug: bool = False

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
