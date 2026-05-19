"""Client for the Flux 2 Klein NVIDIA NIM image generation service.

Uses the NIM's OpenAI-compatible endpoints:
  - POST /v1/images/generations  (text-to-image)
  - POST /v1/images/edits        (image editing / image-to-image)
  - GET  /v1/health/ready        (readiness check)

Images are returned as base64 in ``data[0].b64_json``.
"""

from __future__ import annotations

import base64
import logging
import mimetypes
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class Flux2KleinError(Exception):
    """Raised when a Flux 2 Klein NIM call fails."""


@dataclass
class GeneratedImage:
    """Result returned by Flux2KleinClient generation methods.

    Mirrors the InvokeAI client's GeneratedImage so callers can be provider-agnostic.
    """

    image_name: str
    image_bytes: bytes
    width: int
    height: int
    seed: int


class Flux2KleinClient:
    def __init__(
        self,
        config: dict[str, Any] | None = None,
        url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout: float = 300.0,
        width: int = 1024,
        height: int = 1024,
        steps: int = 4,
        cfg_scale: float = 0.0,
    ):
        if config is not None:
            self.url = (config.get("url") or settings.flux2_klein_url).rstrip("/")
            self.model = config.get("model", settings.flux2_klein_model)
            self.api_key = config.get("api_key") or settings.flux2_klein_api_key or None
            self.timeout = config.get("timeout", timeout)
            self.default_width = int(config.get("width", width))
            self.default_height = int(config.get("height", height))
            self.default_steps = int(config.get("steps", steps))
            self.default_cfg_scale = float(config.get("cfg_scale", cfg_scale))
        else:
            self.url = (url or settings.flux2_klein_url).rstrip("/")
            self.model = model or settings.flux2_klein_model
            self.api_key = api_key or settings.flux2_klein_api_key or None
            self.timeout = timeout
            self.default_width = width
            self.default_height = height
            self.default_steps = steps
            self.default_cfg_scale = cfg_scale

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _decode_response(
        self, payload: dict, width: int, height: int, seed: int
    ) -> GeneratedImage:
        data = payload.get("data") or []
        if not data:
            artifacts = payload.get("artifacts") or []
            if artifacts and isinstance(artifacts[0], dict):
                b64 = artifacts[0].get("base64") or artifacts[0].get("b64_json")
            else:
                b64 = None
        else:
            entry = data[0] if isinstance(data[0], dict) else {}
            b64 = entry.get("b64_json") or entry.get("base64")

        if not b64:
            raise Flux2KleinError(
                f"Flux 2 Klein response missing image data: keys={list(payload.keys())}"
            )

        try:
            image_bytes = base64.b64decode(b64)
        except (ValueError, TypeError) as exc:
            raise Flux2KleinError(f"Failed to decode base64 image: {exc}") from exc

        image_id = (data[0] if data else {}).get("id") if data else None
        return GeneratedImage(
            image_name=image_id or f"flux2klein-{seed}",
            image_bytes=image_bytes,
            width=width,
            height=height,
            seed=seed,
        )

    async def generate_text_to_image(
        self,
        prompt: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        num_steps: Optional[int] = None,
        cfg_scale: Optional[float] = None,
        seed: int = 0,
    ) -> GeneratedImage:
        w = width or self.default_width
        h = height or self.default_height
        steps = num_steps if num_steps is not None else self.default_steps
        cfg = cfg_scale if cfg_scale is not None else self.default_cfg_scale

        payload = {
            "model": self.model,
            "prompt": prompt,
            "n": 1,
            "size": f"{w}x{h}",
            "response_format": "b64_json",
            "extra_body": {
                "steps": steps,
                "cfg_scale": cfg,
                "seed": seed,
            },
        }

        endpoint = f"{self.url}/v1/images/generations"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint, json=payload, headers=self._headers()
                )
        except httpx.RequestError as exc:
            raise Flux2KleinError(f"Flux 2 Klein request failed: {exc}") from exc

        if response.status_code != 200:
            raise Flux2KleinError(
                f"Flux 2 Klein HTTP {response.status_code}: {response.text[:500]}"
            )

        return self._decode_response(response.json(), w, h, seed)

    async def generate_with_reference_bytes(
        self,
        prompt: str,
        reference_bytes: bytes,
        reference_name: str = "reference.png",
        width: Optional[int] = None,
        height: Optional[int] = None,
        num_steps: Optional[int] = None,
        cfg_scale: Optional[float] = None,
        seed: int = 0,
    ) -> GeneratedImage:
        w = width or self.default_width
        h = height or self.default_height
        steps = num_steps if num_steps is not None else self.default_steps
        cfg = cfg_scale if cfg_scale is not None else self.default_cfg_scale

        mime, _ = mimetypes.guess_type(reference_name)
        if not mime:
            mime = "image/png"

        files = {
            "image": (reference_name, reference_bytes, mime),
        }
        data = {
            "model": self.model,
            "prompt": prompt,
            "n": "1",
            "size": f"{w}x{h}",
            "response_format": "b64_json",
            "steps": str(steps),
            "cfg_scale": str(cfg),
            "seed": str(seed),
        }

        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        endpoint = f"{self.url}/v1/images/edits"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint, data=data, files=files, headers=headers
                )
        except httpx.RequestError as exc:
            raise Flux2KleinError(f"Flux 2 Klein edit request failed: {exc}") from exc

        if response.status_code != 200:
            raise Flux2KleinError(
                f"Flux 2 Klein edit HTTP {response.status_code}: {response.text[:500]}"
            )

        return self._decode_response(response.json(), w, h, seed)

    async def check_health(self) -> bool:
        endpoint = f"{self.url}/v1/health/ready"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(endpoint)
            return response.status_code == 200
        except httpx.RequestError:
            return False
