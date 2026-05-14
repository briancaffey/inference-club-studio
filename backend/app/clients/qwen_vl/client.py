"""Client for Qwen3-VL vision-language model served via vLLM."""

import base64
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class QwenVLError(Exception):
    """Exception raised when Qwen VL operations fail."""

    pass


@dataclass
class VideoAnalysis:
    """Result from a chat completion request."""

    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int


class QwenVLClient:
    """Client for Qwen3-VL vision-language model via vLLM OpenAI-compatible API."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        url: str | None = None,
        model: str = "Qwen/Qwen3-VL-4B-Instruct",
        timeout: float = 120.0,
    ):
        if config is not None:
            self.url = (config.get("url") or settings.qwen_vl_url).rstrip("/")
            self.model = config.get("model", model)
            self.timeout = config.get("timeout", timeout)
        else:
            self.url = (url or settings.qwen_vl_url).rstrip("/")
            self.model = model
            self.timeout = timeout

    async def _request_completion(self, payload: dict) -> VideoAnalysis:
        endpoint = f"{self.url}/v1/chat/completions"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()

        except httpx.TimeoutException:
            raise QwenVLError(f"Request timed out after {self.timeout}s.")
        except httpx.HTTPStatusError as e:
            body = e.response.text[:500] if e.response else "no body"
            raise QwenVLError(f"vLLM returned HTTP {e.response.status_code}: {body}")
        except httpx.RequestError as e:
            raise QwenVLError(f"Failed to connect to vLLM at {self.url}: {e}")

        data = response.json()
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        usage = data.get("usage", {})

        content = message.get("content", "")
        if not content:
            raise QwenVLError("Empty response from model")

        return VideoAnalysis(
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
    ) -> VideoAnalysis:
        """Analyze a video file using Qwen3-VL.

        Sends the video as a base64 data URI to the vLLM OpenAI-compatible API.
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise QwenVLError(f"Video file not found: {video_path}")

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
                        {
                            "type": "text",
                            "text": prompt,
                        },
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
    ) -> VideoAnalysis:
        """Analyze an image file using Qwen3-VL."""
        image_path = Path(image_path)
        if not image_path.exists():
            raise QwenVLError(f"Image file not found: {image_path}")

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
                        {
                            "type": "text",
                            "text": prompt,
                        },
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
    ) -> VideoAnalysis:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }
        logger.info("Sending text generation request to %s", self.url)
        return await self._request_completion(payload)

    async def check_health(self) -> bool:
        """Check if the vLLM service is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.url}/v1/models")
                return response.status_code == 200
        except Exception as e:
            logger.warning("Qwen VL health check failed: %s", e)
            return False
