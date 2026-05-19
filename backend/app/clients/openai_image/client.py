"""Client for any server that implements the OpenAI Images API.

Talks to a base URL that already ends in ``/v1`` (e.g. a local Flux 2 Klein
server at ``http://192.168.5.96:8000/v1``). Uses the standard OpenAI endpoints:

  - POST {base_url}/images/generations  (text-to-image, JSON)
  - POST {base_url}/images/edits        (image edit / image-to-image, multipart)
  - GET  {base_url}/models              (health/readiness check)

Responses follow the OpenAI shape: ``{"data": [{"b64_json": "..."}]}``.

The server's model field is typically accepted but ignored for fixed-model
backends; we still send the configured model id so OpenAI proper works too.
``response_format="b64_json"`` is always requested. ``size`` is sent as
``"WxH"``. Seeds / step / cfg are not part of the spec and are omitted.
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


class OpenAIImageError(Exception):
    """Raised when an OpenAI-compatible image API call fails."""


@dataclass
class GeneratedImage:
    """Result returned by OpenAIImageClient generation methods.

    Mirrors the InvokeAI / Flux2Klein client's GeneratedImage so callers
    can be provider-agnostic.
    """

    image_name: str
    image_bytes: bytes
    width: int
    height: int
    seed: int


class OpenAIImageClient:
    def __init__(
        self,
        config: dict[str, Any] | None = None,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout: float = 300.0,
        width: int = 1024,
        height: int = 1024,
    ):
        if config is not None:
            self.base_url = (
                config.get("base_url") or settings.openai_image_base_url
            ).rstrip("/")
            self.model = config.get("model") or settings.openai_image_model
            self.api_key = (
                config.get("api_key") or settings.openai_image_api_key or "dummy"
            )
            self.timeout = float(config.get("timeout", timeout))
            self.default_width = int(config.get("width", width))
            self.default_height = int(config.get("height", height))
        else:
            self.base_url = (base_url or settings.openai_image_base_url).rstrip("/")
            self.model = model or settings.openai_image_model
            self.api_key = api_key or settings.openai_image_api_key or "dummy"
            self.timeout = timeout
            self.default_width = width
            self.default_height = height

    @property
    def url(self) -> str:
        """Base URL (used by health-check/registry display)."""
        return self.base_url

    def _headers(self, json: bool = True) -> dict[str, str]:
        headers: dict[str, str] = {}
        if json:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _decode_response(
        self, payload: dict, width: int, height: int, seed: int
    ) -> GeneratedImage:
        data = payload.get("data") or []
        if not data or not isinstance(data[0], dict):
            raise OpenAIImageError(
                f"OpenAI image response missing data: keys={list(payload.keys())}"
            )

        entry = data[0]
        b64 = entry.get("b64_json") or entry.get("base64")
        if not b64:
            raise OpenAIImageError(
                "OpenAI image response missing b64_json "
                "(response_format must be b64_json)"
            )

        try:
            image_bytes = base64.b64decode(b64)
        except (ValueError, TypeError) as exc:
            raise OpenAIImageError(f"Failed to decode base64 image: {exc}") from exc

        image_id = entry.get("id")
        return GeneratedImage(
            image_name=image_id or f"openai-image-{seed}",
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
        num_steps: Optional[int] = None,  # accepted for interface parity, ignored
        cfg_scale: Optional[float] = None,  # accepted for interface parity, ignored
        seed: int = 0,
    ) -> GeneratedImage:
        w = width or self.default_width
        h = height or self.default_height

        payload = {
            "model": self.model,
            "prompt": prompt,
            "n": 1,
            "size": f"{w}x{h}",
            "response_format": "b64_json",
        }

        endpoint = f"{self.base_url}/images/generations"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint, json=payload, headers=self._headers()
                )
        except httpx.RequestError as exc:
            raise OpenAIImageError(f"OpenAI image request failed: {exc}") from exc

        if response.status_code != 200:
            raise OpenAIImageError(
                f"OpenAI image HTTP {response.status_code}: {response.text[:500]}"
            )

        return self._decode_response(response.json(), w, h, seed)

    async def generate_with_reference_bytes(
        self,
        prompt: str,
        reference_bytes: bytes,
        reference_name: str = "reference.png",
        width: Optional[int] = None,
        height: Optional[int] = None,
        num_steps: Optional[int] = None,  # accepted for interface parity, ignored
        cfg_scale: Optional[float] = None,  # accepted for interface parity, ignored
        seed: int = 0,
    ) -> GeneratedImage:
        w = width or self.default_width
        h = height or self.default_height

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
        }

        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        endpoint = f"{self.base_url}/images/edits"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint, data=data, files=files, headers=headers
                )
        except httpx.RequestError as exc:
            raise OpenAIImageError(f"OpenAI image edit request failed: {exc}") from exc

        if response.status_code != 200:
            raise OpenAIImageError(
                f"OpenAI image edit HTTP {response.status_code}: {response.text[:500]}"
            )

        return self._decode_response(response.json(), w, h, seed)

    async def check_health(self) -> bool:
        """Probe a few endpoints; any < 500 response means the server is up.

        The spec only guarantees ``/images/generations`` and ``/images/edits``
        (POST). ``/models`` is common on OpenAI-compat servers but not required,
        so we accept 404s from these probes — we only care that *something*
        responds. POSTing without a body to ``/images/generations`` is the
        most reliable: it returns 4xx (validation) when the server is up.
        """
        timeout = httpx.Timeout(timeout=5.0)
        try:
            async with httpx.AsyncClient(
                timeout=timeout, follow_redirects=True
            ) as client:
                for method, path in (
                    ("GET", "/models"),
                    ("POST", "/images/generations"),
                    ("GET", "/"),
                ):
                    endpoint = f"{self.base_url}{path}"
                    try:
                        if method == "GET":
                            response = await client.get(
                                endpoint, headers=self._headers(json=False)
                            )
                        else:
                            response = await client.post(
                                endpoint, json={}, headers=self._headers()
                            )
                        if response.status_code < 500:
                            return True
                    except httpx.RequestError:
                        continue
        except Exception:
            return False
        return False
