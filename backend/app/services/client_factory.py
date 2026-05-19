"""Factories that build service clients from database-backed config.

Each helper reads the active config via :class:`ConfigManager` and passes it
through the client's ``config`` kwarg.  When no DB config exists the client
falls back to env vars internally, so these factories are always safe to call.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.clients.comfyui.client import ComfyUIClient
from app.clients.flux2_klein.client import Flux2KleinClient
from app.clients.invokeai.client import InvokeAIClient
from app.clients.llm.client import LLMClient
from app.clients.openai_image.client import OpenAIImageClient
from app.clients.studio_voice.client import StudioVoiceClient
from app.services.config_manager import ConfigManager


def _config(db: Session, service_key: str) -> dict:
    return ConfigManager(db).get_config(service_key)


def build_invokeai_client(db: Session) -> InvokeAIClient:
    return InvokeAIClient(config=_config(db, "invokeai"))


def build_flux2_klein_client(db: Session) -> Flux2KleinClient:
    return Flux2KleinClient(config=_config(db, "flux2_klein"))


def build_openai_image_client(db: Session) -> OpenAIImageClient:
    return OpenAIImageClient(config=_config(db, "openai_image"))


def build_comfyui_client(db: Session) -> ComfyUIClient:
    return ComfyUIClient(config=_config(db, "comfyui"))


def build_llm_client(db: Session) -> LLMClient:
    return LLMClient(config=_config(db, "llm"))


def build_studio_voice_client(db: Session) -> StudioVoiceClient:
    return StudioVoiceClient(config=_config(db, "studio_voice"))
