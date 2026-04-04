from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@postgres:5432/inference_club"
    redis_url: str = "redis://redis:6379/0"
    media_dir: str = "/app/media"
    openai_api_key: str = ""
    groq_api_key: str = ""
    openai_base_url: str = "http://192.168.5.173:1234/v1"
    openai_model: str = "qwen3.5-27b"
    invokeai_url: str = "http://192.168.5.173:9090"
    invokeai_board_id: str | None = None
    comfyui_url: str = "http://192.168.6.19:8188"
    qwen_vl_url: str = "http://192.168.5.253:8000"
    dia_url: str = "http://192.168.5.253:7860"
    magpie_url: str = "http://192.168.6.3:9000"
    stt_url: str = "http://192.168.5.96:8001"
    studio_voice_url: str = "http://192.168.6.3:8000"
    studio_voice_health_url: str = "http://192.168.6.3:8000/v1/health/ready"
    studio_voice_grpc_target: str = "192.168.5.173:8001"
    studio_voice_enhance_path: str | None = None
    studio_voice_model_type: str = "48k-hq"
    studio_voice_input_sample_rate: int = 48000
    studio_voice_auto_clean: bool = True
    cors_origins: list[str] = ["*"]
    debug: bool = False

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
