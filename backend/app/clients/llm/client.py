"""Generic OpenAI-compatible chat-completions client.

Backed by the ``llm`` service config (base_url already includes ``/v1``,
plus model + optional api_key). Supports text, image, and video content
blocks via the chat-completions multimodal message format.
"""

import base64
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Raised when an LLM API call fails."""


@dataclass
class ChatCompletionResult:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int


class LLMClient:
    """OpenAI-compatible chat completions client (text + multimodal)."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout: float = 120.0,
    ):
        if config is not None:
            self.base_url = (
                config.get("base_url") or settings.openai_base_url
            ).rstrip("/")
            self.model = config.get("model") or settings.openai_model
            self.api_key = (
                config.get("api_key") or settings.openai_api_key or None
            )
            self.timeout = float(config.get("timeout", timeout))
        else:
            self.base_url = (base_url or settings.openai_base_url).rstrip("/")
            self.model = model or settings.openai_model
            self.api_key = api_key or settings.openai_api_key or None
            self.timeout = timeout

    @property
    def url(self) -> str:
        """Base URL (used by health-check/registry display)."""
        return self.base_url

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def _request_completion(self, payload: dict) -> ChatCompletionResult:
        endpoint = f"{self.base_url}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint, json=payload, headers=self._headers()
                )
                response.raise_for_status()
        except httpx.TimeoutException:
            raise LLMError(f"Request timed out after {self.timeout}s.")
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:500] if exc.response else "no body"
            raise LLMError(
                f"LLM returned HTTP {exc.response.status_code}: {body}"
            )
        except httpx.RequestError as exc:
            raise LLMError(
                f"Failed to connect to LLM at {self.base_url}: {exc}"
            )

        data = response.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message", {}) or {}
        usage = data.get("usage") or {}

        content = message.get("content") or ""
        if not content:
            raise LLMError("Empty response from model")

        return ChatCompletionResult(
            content=content,
            model=data.get("model", self.model),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )

    async def analyze_video(
        self,
        video_path: str | Path,
        prompt: str = "Describe this video in detail.",
        max_tokens: int = 1024,
        temperature: float = 0.7,
        top_p: float = 0.8,
    ) -> ChatCompletionResult:
        video_path = Path(video_path)
        if not video_path.exists():
            raise LLMError(f"Video file not found: {video_path}")

        logger.info("Reading video file: %s", video_path)
        video_bytes = video_path.read_bytes()
        video_b64 = base64.b64encode(video_bytes).decode("utf-8")
        logger.info(
            "Video encoded: %.1f MB (%.1f MB base64)",
            len(video_bytes) / 1024 / 1024,
            len(video_b64) / 1024 / 1024,
        )

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "video_url",
                            "video_url": {
                                "url": f"data:video/mp4;base64,{video_b64}",
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }
        result = await self._request_completion(payload)
        logger.info(
            "Video analysis complete: %d tokens generated",
            result.completion_tokens,
        )
        return result

    async def analyze_image(
        self,
        image_path: str | Path,
        prompt: str = "Describe this image in detail.",
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.8,
    ) -> ChatCompletionResult:
        image_path = Path(image_path)
        if not image_path.exists():
            raise LLMError(f"Image file not found: {image_path}")

        suffix = image_path.suffix.lower().lstrip(".")
        mime_map = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}
        mime_subtype = mime_map.get(suffix, "png")

        image_bytes = image_path.read_bytes()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{mime_subtype};base64,{image_b64}",
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }
        logger.info("Sending image analysis request for %s", image_path)
        return await self._request_completion(payload)

    async def generate_text(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.4,
        top_p: float = 0.8,
    ) -> ChatCompletionResult:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }
        logger.info("Sending text generation request to %s", self.base_url)
        return await self._request_completion(payload)

    async def check_health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self.base_url}/models", headers=self._headers()
                )
                return response.status_code == 200
        except Exception as exc:
            logger.warning("LLM health check failed: %s", exc)
            return False
