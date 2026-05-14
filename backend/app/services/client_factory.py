"""Factories that build service clients from database-backed config.

Each helper reads the active config via :class:`ConfigManager` and passes it
through the client's ``config`` kwarg.  When no DB config exists the client
falls back to env vars internally, so these factories are always safe to call.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.clients.comfyui.client import ComfyUIClient
from app.clients.invokeai.client import InvokeAIClient
from app.clients.qwen_vl.client import QwenVLClient
from app.clients.studio_voice.client import StudioVoiceClient
from app.services.config_manager import ConfigManager


def _config(db: Session, service_key: str) -> dict:
    return ConfigManager(db).get_config(service_key)


def build_invokeai_client(db: Session) -> InvokeAIClient:
    return InvokeAIClient(config=_config(db, "invokeai"))


def build_comfyui_client(db: Session) -> ComfyUIClient:
    return ComfyUIClient(config=_config(db, "comfyui"))


def build_qwen_vl_client(db: Session) -> QwenVLClient:
    return QwenVLClient(config=_config(db, "qwen_vl"))


def build_studio_voice_client(db: Session) -> StudioVoiceClient:
    return StudioVoiceClient(config=_config(db, "studio_voice"))
