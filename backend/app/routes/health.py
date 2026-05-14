import asyncio
from datetime import UTC, datetime
from functools import partial
from typing import Awaitable, Callable

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.client_factory import (
    build_comfyui_client,
    build_invokeai_client,
    build_qwen_vl_client,
    build_studio_voice_client,
)
from app.services.config_manager import ConfigManager

router = APIRouter(tags=["health"])


ServiceCheck = Callable[[], Awaitable[tuple[bool, str | None]]]


async def _check_client_health(
    check: Callable[[], Awaitable[bool]],
) -> tuple[bool, str | None]:
    try:
        is_healthy = await check()
        return is_healthy, None
    except Exception as exc:
        return False, str(exc)


async def _check_http_reachable(
    base_url: str,
    paths: tuple[str, ...],
) -> tuple[bool, str | None]:
    timeout = httpx.Timeout(timeout=5.0)
    base = base_url.rstrip("/")
    last_error: str | None = None

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            for path in paths:
                endpoint = f"{base}{path}"
                try:
                    response = await client.get(endpoint)
                    if response.status_code < 500:
                        return True, None
                    last_error = f"HTTP {response.status_code} from {endpoint}"
                except httpx.RequestError as exc:
                    last_error = str(exc)
    except Exception as exc:
        last_error = str(exc)

    return False, last_error


@router.get("/health")
def health_check():
    return {"status": "ok"}


@router.get("/services/health")
async def services_health_check(db: Session = Depends(get_db)):
    manager = ConfigManager(db)

    llm_cfg = manager.get_config("llm")
    dia_cfg = manager.get_config("dia")
    magpie_cfg = manager.get_config("magpie")
    stt_cfg = manager.get_config("stt")

    invokeai_client = build_invokeai_client(db)
    comfyui_client = build_comfyui_client(db)
    qwen_vl_client = build_qwen_vl_client(db)
    studio_voice_client = build_studio_voice_client(db)

    llm_base_url = llm_cfg.get("base_url", "")
    dia_url = dia_cfg.get("url", "")
    magpie_url = magpie_cfg.get("url", "")
    stt_url = stt_cfg.get("url", "")

    services: list[tuple[str, str, str, ServiceCheck]] = [
        (
            "llm",
            "LLM (OpenAI API)",
            llm_base_url,
            partial(
                _check_http_reachable,
                llm_base_url,
                ("/models", "/chat/completions", "/"),
            ),
        ),
        (
            "invokeai",
            "InvokeAI",
            invokeai_client.url,
            partial(_check_client_health, invokeai_client.check_health),
        ),
        (
            "comfyui",
            "ComfyUI",
            comfyui_client.url,
            partial(_check_client_health, comfyui_client.check_health),
        ),
        (
            "qwen_vl",
            "Qwen VL",
            qwen_vl_client.url,
            partial(_check_client_health, qwen_vl_client.check_health),
        ),
        (
            "dia",
            "Dia TTS",
            dia_url,
            partial(_check_http_reachable, dia_url, ("/gradio_api/info", "/")),
        ),
        (
            "magpie",
            "Magpie TTS",
            magpie_url,
            partial(
                _check_http_reachable,
                magpie_url,
                ("/v1/audio/list_voices", "/"),
            ),
        ),
        (
            "stt",
            "Speech-to-Text",
            stt_url,
            partial(
                _check_http_reachable,
                stt_url,
                ("/health", "/transcribe", "/"),
            ),
        ),
        (
            "studio_voice",
            "NVIDIA Studio Voice",
            studio_voice_client.url,
            partial(
                _check_http_reachable,
                studio_voice_client.health_url,
                ("",),
            ),
        ),
    ]

    check_results = await asyncio.gather(
        *(check() for _, _, _, check in services),
        return_exceptions=True,
    )

    checked_at = datetime.now(UTC).isoformat()
    service_statuses: list[dict[str, str | bool | None]] = []
    healthy_services = 0

    for (key, name, url, _), result in zip(services, check_results):
        if isinstance(result, Exception):
            is_healthy = False
            error = str(result)
        else:
            is_healthy, error = result

        if is_healthy:
            healthy_services += 1

        service_statuses.append(
            {
                "key": key,
                "name": name,
                "url": url,
                "healthy": is_healthy,
                "error": error,
            }
        )

    total_services = len(services)
    overall_status = "ok" if healthy_services == total_services else "degraded"

    return {
        "status": overall_status,
        "checked_at": checked_at,
        "healthy_services": healthy_services,
        "total_services": total_services,
        "services": service_statuses,
    }
