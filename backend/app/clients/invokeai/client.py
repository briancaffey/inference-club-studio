"""Class-based InvokeAI client for image generation.

Adapted from reference.py — uses FLUX 2 Klein model graphs with
optional Kontext conditioning for reference-image-guided generation.
"""

import asyncio
import copy
import logging
import mimetypes
import random
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class InvokeAIError(Exception):
    """Exception raised when InvokeAI operations fail."""

    pass


@dataclass
class GeneratedImage:
    """Result from an image generation request."""

    image_name: str
    image_bytes: bytes
    width: int
    height: int
    seed: int


# ---------------------------------------------------------------------------
# Graph templates (FLUX 2 Klein) — copied from reference.py
# ---------------------------------------------------------------------------

_REF_PROMPT_NODE = "positive_prompt:DpqaYB9S7t"
_REF_SEED_NODE = "seed:RjnwO1De5E"
_REF_DENOISE_NODE = "flux2_denoise:j67JF7bzP8"
_REF_METADATA_NODE = "core_metadata:pxJjogXVaB"
_REF_OUTPUT_NODE = "canvas_output:G3dQL5ApwS"
_REF_KONTEXT_NODE = "flux_kontext:HYkcPvWDua"
_REF_KONTEXT_COLLECT_NODE = "flux2_kontext_collect:TvtAcjXEQY"

_REF_IMG_GRAPH = {
    "id": "flux_graph:0QoyFNDLOP",
    "nodes": {
        _REF_PROMPT_NODE: {
            "id": _REF_PROMPT_NODE,
            "is_intermediate": True,
            "use_cache": True,
            "value": "",
            "type": "string",
        },
        _REF_SEED_NODE: {
            "id": _REF_SEED_NODE,
            "is_intermediate": True,
            "use_cache": True,
            "value": 0,
            "type": "integer",
        },
        "flux2_klein_model_loader:mNbHzTdH2U": {
            "id": "flux2_klein_model_loader:mNbHzTdH2U",
            "is_intermediate": True,
            "use_cache": True,
            "model": {
                "key": "8b8bdeff-0671-424a-b3b5-2ce490438445",
                "hash": "blake3:c3ee838d71d99497db01fae6f304eafd9e734e935f3b783e968d50febb56be2c",  # noqa: E501
                "name": "FLUX.2 Klein 4B (GGUF Q4)",
                "base": "flux2",
                "type": "main",
                "submodel_type": None,
            },
            "vae_model": {
                "key": "574e7a50-b904-403f-90a7-c5868dd13124",
                "hash": "blake3:531855de70db993d0f6181f82cde27d15411d58b7ffa3b2fdce2b9434c0173c2",  # noqa: E501
                "name": "FLUX.2 VAE",
                "base": "flux2",
                "type": "vae",
                "submodel_type": None,
            },
            "qwen3_encoder_model": {
                "key": "4cbb7cfb-52d5-4b50-9791-a44d81ac30b8",
                "hash": "blake3:af5840e6770dc99f678e69867949c8b9264835915eb82a990e940fa6e4fa6c81",  # noqa: E501
                "name": "FLUX.2 Klein Qwen3 4B Encoder",
                "base": "any",
                "type": "qwen3_encoder",
                "submodel_type": None,
            },
            "qwen3_source_model": None,
            "max_seq_len": 512,
            "type": "flux2_klein_model_loader",
        },
        "flux2_klein_text_encoder:tFXaGTvC5p": {
            "id": "flux2_klein_text_encoder:tFXaGTvC5p",
            "is_intermediate": True,
            "use_cache": True,
            "prompt": None,
            "qwen3_encoder": None,
            "max_seq_len": 512,
            "mask": None,
            "type": "flux2_klein_text_encoder",
        },
        _REF_DENOISE_NODE: {
            "id": _REF_DENOISE_NODE,
            "is_intermediate": True,
            "use_cache": True,
            "latents": None,
            "denoise_mask": None,
            "denoising_start": 0,
            "denoising_end": 1,
            "add_noise": True,
            "transformer": None,
            "positive_text_conditioning": None,
            "negative_text_conditioning": None,
            "cfg_scale": 1,
            "width": 1024,
            "height": 1024,
            "num_steps": 16,
            "scheduler": "euler",
            "seed": 0,
            "vae": None,
            "kontext_conditioning": None,
            "type": "flux2_denoise",
        },
        _REF_METADATA_NODE: {
            "id": _REF_METADATA_NODE,
            "is_intermediate": True,
            "use_cache": True,
            "generation_mode": "flux2_txt2img",
            "positive_prompt": None,
            "negative_prompt": None,
            "width": 1024,
            "height": 1024,
            "seed": None,
            "rand_device": None,
            "cfg_scale": None,
            "cfg_rescale_multiplier": None,
            "steps": 16,
            "scheduler": None,
            "seamless_x": None,
            "seamless_y": None,
            "clip_skip": None,
            "model": {
                "key": "8b8bdeff-0671-424a-b3b5-2ce490438445",
                "hash": "blake3:c3ee838d71d99497db01fae6f304eafd9e734e935f3b783e968d50febb56be2c",  # noqa: E501
                "name": "FLUX.2 Klein 4B (GGUF Q4)",
                "base": "flux2",
                "type": "main",
                "submodel_type": None,
            },
            "controlnets": None,
            "ipAdapters": None,
            "t2iAdapters": None,
            "loras": None,
            "strength": None,
            "init_image": None,
            "vae": {
                "key": "574e7a50-b904-403f-90a7-c5868dd13124",
                "hash": "blake3:531855de70db993d0f6181f82cde27d15411d58b7ffa3b2fdce2b9434c0173c2",  # noqa: E501
                "name": "FLUX.2 VAE",
                "base": "flux2",
                "type": "vae",
                "submodel_type": None,
            },
            "qwen3_encoder": {
                "key": "4cbb7cfb-52d5-4b50-9791-a44d81ac30b8",
                "hash": "blake3:af5840e6770dc99f678e69867949c8b9264835915eb82a990e940fa6e4fa6c81",  # noqa: E501
                "name": "FLUX.2 Klein Qwen3 4B Encoder",
                "base": "any",
                "type": "qwen3_encoder",
                "submodel_type": None,
            },
            "hrf_enabled": None,
            "hrf_method": None,
            "hrf_strength": None,
            "positive_style_prompt": None,
            "negative_style_prompt": None,
            "refiner_model": None,
            "refiner_cfg_scale": None,
            "refiner_steps": None,
            "refiner_scheduler": None,
            "refiner_positive_aesthetic_score": None,
            "refiner_negative_aesthetic_score": None,
            "refiner_start": None,
            "type": "core_metadata",
            "ref_images": [],
        },
        _REF_KONTEXT_COLLECT_NODE: {
            "id": _REF_KONTEXT_COLLECT_NODE,
            "is_intermediate": True,
            "use_cache": True,
            "item": None,
            "collection": [],
            "type": "collect",
        },
        _REF_KONTEXT_NODE: {
            "id": _REF_KONTEXT_NODE,
            "is_intermediate": True,
            "use_cache": True,
            "image": {"image_name": ""},
            "type": "flux_kontext",
        },
        _REF_OUTPUT_NODE: {
            "metadata": None,
            "id": _REF_OUTPUT_NODE,
            "is_intermediate": False,
            "use_cache": False,
            "latents": None,
            "vae": None,
            "type": "flux2_vae_decode",
        },
    },
    "edges": [
        {
            "source": {
                "node_id": "flux2_klein_model_loader:mNbHzTdH2U",
                "field": "qwen3_encoder",
            },
            "destination": {
                "node_id": "flux2_klein_text_encoder:tFXaGTvC5p",
                "field": "qwen3_encoder",
            },
        },
        {
            "source": {
                "node_id": "flux2_klein_model_loader:mNbHzTdH2U",
                "field": "max_seq_len",
            },
            "destination": {
                "node_id": "flux2_klein_text_encoder:tFXaGTvC5p",
                "field": "max_seq_len",
            },
        },
        {
            "source": {
                "node_id": "flux2_klein_model_loader:mNbHzTdH2U",
                "field": "transformer",
            },
            "destination": {
                "node_id": _REF_DENOISE_NODE,
                "field": "transformer",
            },
        },
        {
            "source": {
                "node_id": "flux2_klein_model_loader:mNbHzTdH2U",
                "field": "vae",
            },
            "destination": {"node_id": _REF_DENOISE_NODE, "field": "vae"},
        },
        {
            "source": {
                "node_id": "flux2_klein_model_loader:mNbHzTdH2U",
                "field": "vae",
            },
            "destination": {"node_id": _REF_OUTPUT_NODE, "field": "vae"},
        },
        {
            "source": {"node_id": _REF_PROMPT_NODE, "field": "value"},
            "destination": {
                "node_id": "flux2_klein_text_encoder:tFXaGTvC5p",
                "field": "prompt",
            },
        },
        {
            "source": {
                "node_id": "flux2_klein_text_encoder:tFXaGTvC5p",
                "field": "conditioning",
            },
            "destination": {
                "node_id": _REF_DENOISE_NODE,
                "field": "positive_text_conditioning",
            },
        },
        {
            "source": {"node_id": _REF_SEED_NODE, "field": "value"},
            "destination": {"node_id": _REF_DENOISE_NODE, "field": "seed"},
        },
        {
            "source": {"node_id": _REF_DENOISE_NODE, "field": "latents"},
            "destination": {"node_id": _REF_OUTPUT_NODE, "field": "latents"},
        },
        {
            "source": {"node_id": _REF_SEED_NODE, "field": "value"},
            "destination": {"node_id": _REF_METADATA_NODE, "field": "seed"},
        },
        {
            "source": {"node_id": _REF_PROMPT_NODE, "field": "value"},
            "destination": {
                "node_id": _REF_METADATA_NODE,
                "field": "positive_prompt",
            },
        },
        {
            "source": {
                "node_id": _REF_KONTEXT_NODE,
                "field": "kontext_cond",
            },
            "destination": {
                "node_id": _REF_KONTEXT_COLLECT_NODE,
                "field": "item",
            },
        },
        {
            "source": {
                "node_id": _REF_KONTEXT_COLLECT_NODE,
                "field": "collection",
            },
            "destination": {
                "node_id": _REF_DENOISE_NODE,
                "field": "kontext_conditioning",
            },
        },
        {
            "source": {"node_id": _REF_METADATA_NODE, "field": "metadata"},
            "destination": {"node_id": _REF_OUTPUT_NODE, "field": "metadata"},
        },
    ],
}


class InvokeAIClient:
    """Client for InvokeAI image generation service."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        url: str | None = None,
        board_id: str | None = None,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
        max_retries: int = 3,
    ):
        if config is not None:
            self.url = config.get("url", settings.invokeai_url)
            self.board_id = config.get("board_id", settings.invokeai_board_id)
            self.poll_interval = config.get("poll_interval", poll_interval)
            self.timeout = config.get("timeout", timeout)
            self.max_retries = config.get("max_retries", max_retries)
        else:
            self.url = url or settings.invokeai_url
            self.board_id = (
                board_id if board_id is not None else settings.invokeai_board_id
            )
            self.poll_interval = poll_interval
            self.timeout = timeout
            self.max_retries = max_retries

    def _build_ref_img_batch(
        self,
        prompt: str,
        reference_image_name: str,
        width: int,
        height: int,
        num_steps: int,
        cfg_scale: float,
        seed: int,
    ) -> dict:
        """Build an enqueue_batch payload for reference-image generation."""
        graph = copy.deepcopy(_REF_IMG_GRAPH)

        graph["nodes"][_REF_PROMPT_NODE]["value"] = prompt
        graph["nodes"][_REF_SEED_NODE]["value"] = seed
        graph["nodes"][_REF_DENOISE_NODE]["width"] = width
        graph["nodes"][_REF_DENOISE_NODE]["height"] = height
        graph["nodes"][_REF_DENOISE_NODE]["num_steps"] = num_steps
        # FLUX 2 Klein requires negative conditioning when cfg_scale != 1.0,
        # which our graph doesn't include. Force to 1.0.
        if cfg_scale != 1.0:
            logger.warning(
                "cfg_scale=%.1f ignored — FLUX 2 Klein requires 1.0 "
                "without negative conditioning. Using 1.0.",
                cfg_scale,
            )
        graph["nodes"][_REF_DENOISE_NODE]["cfg_scale"] = 1.0
        graph["nodes"][_REF_METADATA_NODE]["width"] = width
        graph["nodes"][_REF_METADATA_NODE]["height"] = height
        graph["nodes"][_REF_METADATA_NODE]["steps"] = num_steps

        # Set the reference image for kontext conditioning
        graph["nodes"][_REF_KONTEXT_NODE]["image"]["image_name"] = reference_image_name
        graph["nodes"][_REF_METADATA_NODE]["ref_images"] = [
            {
                "id": "reference_image:waywo_ref",
                "isEnabled": True,
                "config": {
                    "type": "flux2_reference_image",
                    "image": {
                        "original": {
                            "image": {
                                "image_name": reference_image_name,
                                "width": width,
                                "height": height,
                            }
                        }
                    },
                    "model": None,
                    "beginEndStepPct": [0, 1],
                    "method": "full",
                    "clipVisionModel": "ViT-H",
                    "weight": 1,
                },
            }
        ]

        # Conditionally add board to output node
        if self.board_id:
            graph["nodes"][_REF_OUTPUT_NODE]["board"] = {"board_id": self.board_id}

        return {
            "queue_id": "default",
            "batch": {
                "data": [],
                "graph": graph,
                "runs": 1,
            },
            "priority": 0,
        }

    def _build_text_to_image_batch(
        self,
        prompt: str,
        width: int,
        height: int,
        num_steps: int,
        cfg_scale: float,
        seed: int,
    ) -> dict:
        """Build an enqueue_batch payload for pure text-to-image generation."""
        graph = copy.deepcopy(_REF_IMG_GRAPH)

        graph["nodes"][_REF_PROMPT_NODE]["value"] = prompt
        graph["nodes"][_REF_SEED_NODE]["value"] = seed
        graph["nodes"][_REF_DENOISE_NODE]["width"] = width
        graph["nodes"][_REF_DENOISE_NODE]["height"] = height
        graph["nodes"][_REF_DENOISE_NODE]["num_steps"] = num_steps
        if cfg_scale != 1.0:
            logger.warning(
                "cfg_scale=%.1f ignored — FLUX 2 Klein requires 1.0 "
                "without negative conditioning. Using 1.0.",
                cfg_scale,
            )
        graph["nodes"][_REF_DENOISE_NODE]["cfg_scale"] = 1.0
        graph["nodes"][_REF_METADATA_NODE]["width"] = width
        graph["nodes"][_REF_METADATA_NODE]["height"] = height
        graph["nodes"][_REF_METADATA_NODE]["steps"] = num_steps
        graph["nodes"][_REF_METADATA_NODE]["ref_images"] = []

        # Remove Kontext-specific nodes/edges for txt2img runs.
        graph["nodes"].pop(_REF_KONTEXT_NODE, None)
        graph["nodes"].pop(_REF_KONTEXT_COLLECT_NODE, None)
        graph["edges"] = [
            edge
            for edge in graph["edges"]
            if edge["source"]["node_id"]
            not in {_REF_KONTEXT_NODE, _REF_KONTEXT_COLLECT_NODE}
            and edge["destination"]["node_id"]
            not in {_REF_KONTEXT_NODE, _REF_KONTEXT_COLLECT_NODE}
            and not (
                edge["destination"]["node_id"] == _REF_DENOISE_NODE
                and edge["destination"]["field"] == "kontext_conditioning"
            )
        ]

        if self.board_id:
            graph["nodes"][_REF_OUTPUT_NODE]["board"] = {"board_id": self.board_id}

        return {
            "queue_id": "default",
            "batch": {
                "data": [],
                "graph": graph,
                "runs": 1,
            },
            "priority": 0,
        }

    async def upload_image(
        self, image_bytes: bytes, filename: str = "reference.png"
    ) -> str:
        """Upload an image to InvokeAI and return the image_name."""
        mime_type, _ = mimetypes.guess_type(filename)
        if mime_type is None:
            mime_type = "image/png"

        url = f"{self.url}/api/v1/images/upload"
        params = {
            "image_category": "user",
            "is_intermediate": "false",
        }
        if self.board_id:
            params["board_id"] = self.board_id

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    url,
                    params=params,
                    files={"file": (filename, image_bytes, mime_type)},
                    headers={"accept": "application/json"},
                )
                response.raise_for_status()
                data = response.json()
                image_name = data.get("image_name")
                if not image_name:
                    raise InvokeAIError(
                        "Upload succeeded but no image_name in response"
                    )
                logger.info("Uploaded image to InvokeAI: %s", image_name)
                return image_name

        except httpx.HTTPStatusError as e:
            raise InvokeAIError(f"Image upload failed: HTTP {e.response.status_code}")
        except httpx.RequestError as e:
            raise InvokeAIError(f"Image upload failed: {e}")

    async def generate_with_reference(
        self,
        prompt: str,
        ref_image_name: str,
        width: int = 1024,
        height: int = 1024,
        num_steps: int = 16,
        cfg_scale: float = 1.0,
        seed: int = -1,
    ) -> GeneratedImage:
        """Generate an image using a reference image with Kontext conditioning."""
        if seed < 0:
            seed = random.randint(0, 2**32 - 1)

        batch_payload = self._build_ref_img_batch(
            prompt, ref_image_name, width, height, num_steps, cfg_scale, seed
        )
        batch_info = await self._submit_batch(batch_payload)
        image_name = await self._poll_for_result(batch_info)
        image_bytes = await self._download_image(image_name)

        return GeneratedImage(
            image_name=image_name,
            image_bytes=image_bytes,
            width=width,
            height=height,
            seed=seed,
        )

    async def generate_text_to_image(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
        num_steps: int = 16,
        cfg_scale: float = 1.0,
        seed: int = -1,
    ) -> GeneratedImage:
        """Generate an image from text only (no reference image)."""
        if seed < 0:
            seed = random.randint(0, 2**32 - 1)

        batch_payload = self._build_text_to_image_batch(
            prompt=prompt,
            width=width,
            height=height,
            num_steps=num_steps,
            cfg_scale=cfg_scale,
            seed=seed,
        )
        batch_info = await self._submit_batch(batch_payload)
        image_name = await self._poll_for_result(batch_info)
        image_bytes = await self._download_image(image_name)

        return GeneratedImage(
            image_name=image_name,
            image_bytes=image_bytes,
            width=width,
            height=height,
            seed=seed,
        )

    async def check_health(self) -> bool:
        """Check if the InvokeAI service is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.url}/api/v1/queue/default/status")
                return response.status_code == 200
        except Exception as e:
            logger.warning("InvokeAI health check failed: %s", e)
            return False

    async def _submit_batch(self, batch_payload: dict) -> dict:
        """Submit a batch to the InvokeAI queue and return batch info."""
        endpoint = f"{self.url}/api/v1/queue/default/enqueue_batch"

        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    logger.info("Submitting batch to InvokeAI at %s", endpoint)
                    response = await client.post(endpoint, json=batch_payload)
                    response.raise_for_status()

                    data = response.json()
                    batch_info = {
                        "batch_id": data.get("batch", {}).get("batch_id"),
                        "item_ids": data.get("item_ids", []),
                        "queue_id": data.get("queue_id", "default"),
                    }

                    if not batch_info["batch_id"]:
                        raise InvokeAIError("No batch_id in enqueue response")

                    logger.info(
                        "Batch submitted: %s (items: %s)",
                        batch_info["batch_id"],
                        batch_info["item_ids"],
                    )
                    return batch_info

            except httpx.TimeoutException:
                logger.warning("InvokeAI submission timeout (attempt %d)", attempt + 1)
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2**attempt)
                else:
                    raise InvokeAIError("Batch submission timed out after all retries")

            except httpx.HTTPStatusError as e:
                raise InvokeAIError(
                    f"Batch submission failed: HTTP {e.response.status_code}"
                )

            except httpx.RequestError as e:
                logger.warning(
                    "InvokeAI connection error (attempt %d): %s",
                    attempt + 1,
                    e,
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2**attempt)
                else:
                    raise InvokeAIError(f"Failed to connect to InvokeAI: {e}")

        raise InvokeAIError("Batch submission failed after all retries")

    async def _poll_for_result(self, batch_info: dict) -> str:
        """Poll a batch until complete and return the generated image name."""
        queue_id = batch_info["queue_id"]
        batch_id = batch_info["batch_id"]
        item_ids = batch_info["item_ids"]

        elapsed = 0.0
        while elapsed < self.timeout:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    status_url = (
                        f"{self.url}/api/v1/queue/{queue_id}" f"/b/{batch_id}/status"
                    )
                    response = await client.get(status_url)

                    if response.status_code == 200:
                        status = response.json()
                        completed = status.get("completed", 0)
                        failed = status.get("failed", 0)
                        total = status.get("total", 0)

                        if failed > 0:
                            raise InvokeAIError(
                                f"Batch {batch_id} failed ({failed}/{total})"
                            )

                        if completed > 0 and completed >= total:
                            logger.info(
                                "Batch %s completed (%d/%d)",
                                batch_id,
                                completed,
                                total,
                            )
                            return await self._extract_image_name(queue_id, item_ids)

                        logger.info(
                            "Batch %s: %d/%d completed, waiting...",
                            batch_id,
                            completed,
                            total,
                        )

            except InvokeAIError:
                raise
            except Exception as e:
                logger.warning("Error polling batch status: %s", e)

            await asyncio.sleep(self.poll_interval)
            elapsed += self.poll_interval

        raise InvokeAIError(f"Batch {batch_id} timed out after {self.timeout}s")

    async def _extract_image_name(self, queue_id: str, item_ids: list) -> str:
        """Extract the generated image name from queue item results."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            for item_id in item_ids:
                item_url = f"{self.url}/api/v1/queue/{queue_id}/i/{item_id}"
                response = await client.get(item_url)

                if response.status_code != 200:
                    continue

                item_data = response.json()
                session = item_data.get("session", {})
                results = session.get("results", {})

                for _node_id, result in results.items():
                    if result.get("type") == "image_output":
                        image_name = result.get("image", {}).get("image_name")
                        if image_name:
                            logger.info("Generated image: %s", image_name)
                            return image_name

        raise InvokeAIError("No image found in batch results")

    async def _download_image(self, image_name: str) -> bytes:
        """Download a generated image by name."""
        url = f"{self.url}/api/v1/images/i/{image_name}/full"

        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(url)
                    if response.status_code == 200:
                        logger.info("Downloaded image: %s", image_name)
                        return response.content
                    else:
                        logger.warning(
                            "Download attempt %d/%d returned HTTP %d",
                            attempt + 1,
                            self.max_retries,
                            response.status_code,
                        )

            except Exception as e:
                logger.warning(
                    "Download attempt %d/%d failed: %s",
                    attempt + 1,
                    self.max_retries,
                    e,
                )

            if attempt < self.max_retries - 1:
                await asyncio.sleep(2**attempt)

        raise InvokeAIError(
            f"Failed to download image {image_name} "
            f"after {self.max_retries} attempts"
        )
