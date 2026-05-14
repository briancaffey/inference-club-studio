from typing import Optional

from pydantic import BaseModel, Field


class InvokeAIConfig(BaseModel):
    """InvokeAI service configuration schema."""

    url: str = Field(..., description="InvokeAI base URL")
    board_id: Optional[str] = None
    poll_interval: float = Field(default=2.0, ge=0.1)
    timeout: float = Field(default=300.0, ge=1.0)
    max_retries: int = Field(default=3, ge=0)


class ComfyUIConfig(BaseModel):
    """ComfyUI service configuration schema."""

    url: str = Field(..., description="ComfyUI base URL")
    poll_interval: float = Field(default=5.0, ge=0.1)
    timeout: float = Field(default=600.0, ge=1.0)


class StudioVoiceConfig(BaseModel):
    """NVIDIA Studio Voice configuration schema."""

    url: str = Field(..., description="Studio Voice HTTP base URL")
    health_url: Optional[str] = None
    grpc_target: Optional[str] = None
    model_type: str = Field(default="48k-hq")
    input_sample_rate: int = Field(default=48000, ge=16000)
    auto_clean: bool = True
    enhance_path: Optional[str] = None


class LLMConfig(BaseModel):
    """LLM/OpenAI-compatible API configuration schema."""

    base_url: str = Field(..., description="OpenAI-compatible API base URL")
    model: str = Field(default="gpt-4", description="Default model name")
    api_key: Optional[str] = None


class TTSConfig(BaseModel):
    """Generic TTS service configuration."""

    url: str = Field(..., description="TTS service base URL")
    timeout: float = Field(default=60.0, ge=1.0)


class DIAConfig(TTSConfig):
    pass


class MagpieConfig(TTSConfig):
    voices: list[str] = []


class STTConfig(BaseModel):
    """Speech-to-text service configuration."""

    url: str = Field(..., description="STT service base URL")
    timeout: float = Field(default=120.0, ge=1.0)


class QwenVLConfig(BaseModel):
    """Qwen-VL vision language model configuration."""

    url: str = Field(..., description="Qwen-VL base URL")
    timeout: float = Field(default=60.0, ge=1.0)


SERVICE_CONFIG_SCHEMAS: dict[str, type[BaseModel]] = {
    "invokeai": InvokeAIConfig,
    "comfyui": ComfyUIConfig,
    "studio_voice": StudioVoiceConfig,
    "llm": LLMConfig,
    "dia": DIAConfig,
    "magpie": MagpieConfig,
    "stt": STTConfig,
    "qwen_vl": QwenVLConfig,
}
