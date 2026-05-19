from typing import Literal, Optional

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
    """Speech-to-text service configuration.

    Supports two backends:
      - ``nemotron``: NVIDIA Nemotron NIM — POST {base_url}/transcribe
      - ``openai``:   OpenAI-compatible — POST {base_url}/audio/transcriptions
                      (base_url may or may not include /v1; the client
                      normalizes it). Works with Qwen3-ASR served by vLLM,
                      OpenAI Whisper, vLLM-served Whisper, etc.
    """

    provider: Literal["nemotron", "openai"] = Field(
        default="openai",
        description="Active STT backend",
    )
    base_url: str = Field(default="", description="STT service base URL")
    model: str = Field(
        default="Qwen/Qwen3-ASR-1.7B",
        description="STT model name (provider=openai)",
    )
    api_key: Optional[str] = None
    language: Optional[str] = Field(
        default=None,
        description="ISO-639-1 hint for openai provider (e.g. 'en'). "
        "Leave blank for auto-detect.",
    )
    timeout: float = Field(default=120.0, ge=1.0)


class Flux2KleinConfig(BaseModel):
    """Flux 2 Klein NIM (OpenAI-compatible) image generation config."""

    url: str = Field(..., description="Flux 2 Klein NIM base URL")
    model: str = Field(
        default="black-forest-labs/flux.2-klein-4b",
        description="Model identifier for /v1/images/generations",
    )
    api_key: Optional[str] = None
    timeout: float = Field(default=300.0, ge=1.0)
    width: int = Field(default=1024, ge=512, le=2048)
    height: int = Field(default=1024, ge=512, le=2048)
    steps: int = Field(default=4, ge=1, le=4)
    cfg_scale: float = Field(default=0.0, ge=0.0)


class OpenAIImageConfig(BaseModel):
    """OpenAI-compatible image generation config.

    Use for any server that implements the OpenAI Images API
    (POST /images/generations + /images/edits). ``base_url`` should already
    include the ``/v1`` suffix.
    """

    base_url: str = Field(
        ...,
        description="OpenAI-compatible image API base URL (ends in /v1)",
    )
    model: str = Field(
        default="flux-2-klein-4b",
        description="Model identifier sent in the request (may be ignored by server)",
    )
    api_key: Optional[str] = None
    timeout: float = Field(default=300.0, ge=1.0)
    width: int = Field(default=1024, ge=64, le=2048)
    height: int = Field(default=1024, ge=64, le=2048)


class ImageGenerationConfig(BaseModel):
    """Provider switch for image generation (narration image series)."""

    provider: Literal["invokeai", "flux2_klein", "openai_image"] = Field(
        default="invokeai",
        description="Active image-generation backend",
    )


SERVICE_CONFIG_SCHEMAS: dict[str, type[BaseModel]] = {
    "invokeai": InvokeAIConfig,
    "comfyui": ComfyUIConfig,
    "studio_voice": StudioVoiceConfig,
    "llm": LLMConfig,
    "dia": DIAConfig,
    "magpie": MagpieConfig,
    "stt": STTConfig,
    "flux2_klein": Flux2KleinConfig,
    "openai_image": OpenAIImageConfig,
    "image_generation": ImageGenerationConfig,
}
