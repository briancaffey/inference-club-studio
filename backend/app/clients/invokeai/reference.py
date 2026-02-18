"""Client for InvokeAI image generation service.

Uses the InvokeAI API to generate images via FLUX 2 Klein model graphs.
Supports text-to-image and reference-image-guided generation.
"""

import asyncio
import copy
import logging
import random
from dataclasses import dataclass
from typing import Optional

import httpx
from src.settings import INVOKEAI_URL

logger = logging.getLogger(__name__)

DEFAULT_INVOKEAI_URL = INVOKEAI_URL
BOARD_ID = "d5f9e3ae-df06-451f-b538-4bb58a6cc43e"


class InvokeAIError(Exception):
    """Exception raised when image generation fails."""

    pass


@dataclass
class GeneratedImage:
    """Result from an image generation request."""

    image_name: str
    image_bytes: bytes
    width: int
    height: int


# ---------------------------------------------------------------------------
# Graph templates (FLUX 2 Klein)
# ---------------------------------------------------------------------------

# Node IDs for the text-to-image graph
_TXT2IMG_PROMPT_NODE = "positive_prompt:CjR0mYpz31"
_TXT2IMG_SEED_NODE = "seed:B3us1QPx5h"
_TXT2IMG_DENOISE_NODE = "flux2_denoise:oTqFW3KTNk"
_TXT2IMG_METADATA_NODE = "core_metadata:azr5jlV6MZ"
_TXT2IMG_OUTPUT_NODE = "canvas_output:rHGkBPcPOE"

_TXT2IMG_GRAPH = {
    "id": "flux_graph:scp50VxYZi",
    "nodes": {
        _TXT2IMG_PROMPT_NODE: {
            "id": _TXT2IMG_PROMPT_NODE,
            "is_intermediate": True,
            "use_cache": True,
            "value": "",
            "type": "string",
        },
        _TXT2IMG_SEED_NODE: {
            "id": _TXT2IMG_SEED_NODE,
            "is_intermediate": True,
            "use_cache": True,
            "value": 0,
            "type": "integer",
        },
        "flux2_klein_model_loader:vVjCkJJqjL": {
            "id": "flux2_klein_model_loader:vVjCkJJqjL",
            "is_intermediate": True,
            "use_cache": True,
            "model": {
                "key": "8b8bdeff-0671-424a-b3b5-2ce490438445",
                "hash": "blake3:c3ee838d71d99497db01fae6f304eafd9e734e935f3b783e968d50febb56be2c",
                "name": "FLUX.2 Klein 4B (GGUF Q4)",
                "base": "flux2",
                "type": "main",
                "submodel_type": None,
            },
            "vae_model": {
                "key": "574e7a50-b904-403f-90a7-c5868dd13124",
                "hash": "blake3:531855de70db993d0f6181f82cde27d15411d58b7ffa3b2fdce2b9434c0173c2",
                "name": "FLUX.2 VAE",
                "base": "flux2",
                "type": "vae",
                "submodel_type": None,
            },
            "qwen3_encoder_model": {
                "key": "4cbb7cfb-52d5-4b50-9791-a44d81ac30b8",
                "hash": "blake3:af5840e6770dc99f678e69867949c8b9264835915eb82a990e940fa6e4fa6c81",
                "name": "FLUX.2 Klein Qwen3 4B Encoder",
                "base": "any",
                "type": "qwen3_encoder",
                "submodel_type": None,
            },
            "qwen3_source_model": None,
            "max_seq_len": 512,
            "type": "flux2_klein_model_loader",
        },
        "flux2_klein_text_encoder:TKf6RWlSqq": {
            "id": "flux2_klein_text_encoder:TKf6RWlSqq",
            "is_intermediate": True,
            "use_cache": True,
            "prompt": None,
            "qwen3_encoder": None,
            "max_seq_len": 512,
            "mask": None,
            "type": "flux2_klein_text_encoder",
        },
        _TXT2IMG_DENOISE_NODE: {
            "id": _TXT2IMG_DENOISE_NODE,
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
        _TXT2IMG_METADATA_NODE: {
            "id": _TXT2IMG_METADATA_NODE,
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
                "hash": "blake3:c3ee838d71d99497db01fae6f304eafd9e734e935f3b783e968d50febb56be2c",
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
                "hash": "blake3:531855de70db993d0f6181f82cde27d15411d58b7ffa3b2fdce2b9434c0173c2",
                "name": "FLUX.2 VAE",
                "base": "flux2",
                "type": "vae",
                "submodel_type": None,
            },
            "qwen3_encoder": {
                "key": "4cbb7cfb-52d5-4b50-9791-a44d81ac30b8",
                "hash": "blake3:af5840e6770dc99f678e69867949c8b9264835915eb82a990e940fa6e4fa6c81",
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
        },
        _TXT2IMG_OUTPUT_NODE: {
            "board": {"board_id": BOARD_ID},
            "metadata": None,
            "id": _TXT2IMG_OUTPUT_NODE,
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
                "node_id": "flux2_klein_model_loader:vVjCkJJqjL",
                "field": "qwen3_encoder",
            },
            "destination": {
                "node_id": "flux2_klein_text_encoder:TKf6RWlSqq",
                "field": "qwen3_encoder",
            },
        },
        {
            "source": {
                "node_id": "flux2_klein_model_loader:vVjCkJJqjL",
                "field": "max_seq_len",
            },
            "destination": {
                "node_id": "flux2_klein_text_encoder:TKf6RWlSqq",
                "field": "max_seq_len",
            },
        },
        {
            "source": {
                "node_id": "flux2_klein_model_loader:vVjCkJJqjL",
                "field": "transformer",
            },
            "destination": {"node_id": _TXT2IMG_DENOISE_NODE, "field": "transformer"},
        },
        {
            "source": {
                "node_id": "flux2_klein_model_loader:vVjCkJJqjL",
                "field": "vae",
            },
            "destination": {"node_id": _TXT2IMG_DENOISE_NODE, "field": "vae"},
        },
        {
            "source": {
                "node_id": "flux2_klein_model_loader:vVjCkJJqjL",
                "field": "vae",
            },
            "destination": {"node_id": _TXT2IMG_OUTPUT_NODE, "field": "vae"},
        },
        {
            "source": {"node_id": _TXT2IMG_PROMPT_NODE, "field": "value"},
            "destination": {
                "node_id": "flux2_klein_text_encoder:TKf6RWlSqq",
                "field": "prompt",
            },
        },
        {
            "source": {
                "node_id": "flux2_klein_text_encoder:TKf6RWlSqq",
                "field": "conditioning",
            },
            "destination": {
                "node_id": _TXT2IMG_DENOISE_NODE,
                "field": "positive_text_conditioning",
            },
        },
        {
            "source": {"node_id": _TXT2IMG_SEED_NODE, "field": "value"},
            "destination": {"node_id": _TXT2IMG_DENOISE_NODE, "field": "seed"},
        },
        {
            "source": {"node_id": _TXT2IMG_DENOISE_NODE, "field": "latents"},
            "destination": {"node_id": _TXT2IMG_OUTPUT_NODE, "field": "latents"},
        },
        {
            "source": {"node_id": _TXT2IMG_SEED_NODE, "field": "value"},
            "destination": {"node_id": _TXT2IMG_METADATA_NODE, "field": "seed"},
        },
        {
            "source": {"node_id": _TXT2IMG_PROMPT_NODE, "field": "value"},
            "destination": {
                "node_id": _TXT2IMG_METADATA_NODE,
                "field": "positive_prompt",
            },
        },
        {
            "source": {"node_id": _TXT2IMG_METADATA_NODE, "field": "metadata"},
            "destination": {"node_id": _TXT2IMG_OUTPUT_NODE, "field": "metadata"},
        },
    ],
}

# Node IDs for the reference-image graph (extends txt2img with kontext conditioning)
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
                "hash": "blake3:c3ee838d71d99497db01fae6f304eafd9e734e935f3b783e968d50febb56be2c",
                "name": "FLUX.2 Klein 4B (GGUF Q4)",
                "base": "flux2",
                "type": "main",
                "submodel_type": None,
            },
            "vae_model": {
                "key": "574e7a50-b904-403f-90a7-c5868dd13124",
                "hash": "blake3:531855de70db993d0f6181f82cde27d15411d58b7ffa3b2fdce2b9434c0173c2",
                "name": "FLUX.2 VAE",
                "base": "flux2",
                "type": "vae",
                "submodel_type": None,
            },
            "qwen3_encoder_model": {
                "key": "4cbb7cfb-52d5-4b50-9791-a44d81ac30b8",
                "hash": "blake3:af5840e6770dc99f678e69867949c8b9264835915eb82a990e940fa6e4fa6c81",
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
                "hash": "blake3:c3ee838d71d99497db01fae6f304eafd9e734e935f3b783e968d50febb56be2c",
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
                "hash": "blake3:531855de70db993d0f6181f82cde27d15411d58b7ffa3b2fdce2b9434c0173c2",
                "name": "FLUX.2 VAE",
                "base": "flux2",
                "type": "vae",
                "submodel_type": None,
            },
            "qwen3_encoder": {
                "key": "4cbb7cfb-52d5-4b50-9791-a44d81ac30b8",
                "hash": "blake3:af5840e6770dc99f678e69867949c8b9264835915eb82a990e940fa6e4fa6c81",
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
            "board": {"board_id": BOARD_ID},
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
            "destination": {"node_id": _REF_DENOISE_NODE, "field": "transformer"},
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
            "destination": {"node_id": _REF_METADATA_NODE, "field": "positive_prompt"},
        },
        {
            "source": {"node_id": _REF_KONTEXT_NODE, "field": "kontext_cond"},
            "destination": {"node_id": _REF_KONTEXT_COLLECT_NODE, "field": "item"},
        },
        {
            "source": {"node_id": _REF_KONTEXT_COLLECT_NODE, "field": "collection"},
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


# ---------------------------------------------------------------------------
# Graph builders
# ---------------------------------------------------------------------------


def _build_txt2img_batch(
    prompt: str,
    width: int,
    height: int,
    num_steps: int,
    seed: int,
) -> dict:
    """Build an enqueue_batch payload for text-to-image generation."""
    graph = copy.deepcopy(_TXT2IMG_GRAPH)

    graph["nodes"][_TXT2IMG_PROMPT_NODE]["value"] = prompt
    graph["nodes"][_TXT2IMG_SEED_NODE]["value"] = seed
    graph["nodes"][_TXT2IMG_DENOISE_NODE]["width"] = width
    graph["nodes"][_TXT2IMG_DENOISE_NODE]["height"] = height
    graph["nodes"][_TXT2IMG_DENOISE_NODE]["num_steps"] = num_steps
    graph["nodes"][_TXT2IMG_METADATA_NODE]["width"] = width
    graph["nodes"][_TXT2IMG_METADATA_NODE]["height"] = height
    graph["nodes"][_TXT2IMG_METADATA_NODE]["steps"] = num_steps

    return {
        "queue_id": "default",
        "batch": {
            "data": [],
            "graph": graph,
            "runs": 1,
        },
        "priority": 0,
    }


def _build_ref_img_batch(
    prompt: str,
    reference_image_name: str,
    width: int,
    height: int,
    num_steps: int,
    seed: int,
) -> dict:
    """Build an enqueue_batch payload for reference-image-guided generation."""
    graph = copy.deepcopy(_REF_IMG_GRAPH)

    graph["nodes"][_REF_PROMPT_NODE]["value"] = prompt
    graph["nodes"][_REF_SEED_NODE]["value"] = seed
    graph["nodes"][_REF_DENOISE_NODE]["width"] = width
    graph["nodes"][_REF_DENOISE_NODE]["height"] = height
    graph["nodes"][_REF_DENOISE_NODE]["num_steps"] = num_steps
    graph["nodes"][_REF_METADATA_NODE]["width"] = width
    graph["nodes"][_REF_METADATA_NODE]["height"] = height
    graph["nodes"][_REF_METADATA_NODE]["steps"] = num_steps

    # Set the reference image
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

    return {
        "queue_id": "default",
        "batch": {
            "data": [],
            "graph": graph,
            "runs": 1,
        },
        "priority": 0,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def generate_image(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    num_steps: int = 16,
    seed: int = -1,
    invokeai_url: str = DEFAULT_INVOKEAI_URL,
    poll_interval: float = 2.0,
    timeout: float = 300.0,
    max_retries: int = 3,
) -> GeneratedImage:
    """
    Generate an image from a text prompt using InvokeAI.

    Submits a FLUX 2 Klein text-to-image graph to the InvokeAI queue,
    polls until completion, then downloads the result.

    Args:
        prompt: Text description of the image to generate.
        width: Image width in pixels.
        height: Image height in pixels.
        num_steps: Number of denoising steps.
        seed: Random seed (-1 for random).
        invokeai_url: Base URL of the InvokeAI service.
        poll_interval: Seconds between status polls.
        timeout: Maximum seconds to wait for generation.
        max_retries: Retry attempts for the initial submission.

    Returns:
        GeneratedImage with the image bytes and metadata.

    Raises:
        InvokeAIError: If generation fails.
    """
    if seed < 0:
        seed = random.randint(0, 2**32 - 1)

    batch_payload = _build_txt2img_batch(prompt, width, height, num_steps, seed)
    batch_info = await _submit_batch(batch_payload, invokeai_url, max_retries)
    image_name = await _poll_for_result(
        batch_info, invokeai_url, poll_interval, timeout
    )
    image_bytes = await _download_image(image_name, invokeai_url, max_retries)

    return GeneratedImage(
        image_name=image_name,
        image_bytes=image_bytes,
        width=width,
        height=height,
    )


async def generate_image_with_reference(
    prompt: str,
    reference_image_name: str,
    width: int = 1024,
    height: int = 1024,
    num_steps: int = 16,
    seed: int = -1,
    invokeai_url: str = DEFAULT_INVOKEAI_URL,
    poll_interval: float = 2.0,
    timeout: float = 300.0,
    max_retries: int = 3,
) -> GeneratedImage:
    """
    Generate an image guided by a reference image using InvokeAI.

    Uses FLUX Kontext conditioning to produce an image influenced by
    the reference image and the text prompt.

    Args:
        prompt: Text description / style instruction.
        reference_image_name: Name of an image already uploaded to InvokeAI.
        width: Image width in pixels.
        height: Image height in pixels.
        num_steps: Number of denoising steps.
        seed: Random seed (-1 for random).
        invokeai_url: Base URL of the InvokeAI service.
        poll_interval: Seconds between status polls.
        timeout: Maximum seconds to wait for generation.
        max_retries: Retry attempts for the initial submission.

    Returns:
        GeneratedImage with the image bytes and metadata.

    Raises:
        InvokeAIError: If generation fails.
    """
    if seed < 0:
        seed = random.randint(0, 2**32 - 1)

    batch_payload = _build_ref_img_batch(
        prompt, reference_image_name, width, height, num_steps, seed
    )
    batch_info = await _submit_batch(batch_payload, invokeai_url, max_retries)
    image_name = await _poll_for_result(
        batch_info, invokeai_url, poll_interval, timeout
    )
    image_bytes = await _download_image(image_name, invokeai_url, max_retries)

    return GeneratedImage(
        image_name=image_name,
        image_bytes=image_bytes,
        width=width,
        height=height,
    )


async def upload_image(
    image_bytes: bytes,
    filename: str = "reference.png",
    invokeai_url: str = DEFAULT_INVOKEAI_URL,
) -> str:
    """
    Upload an image to InvokeAI and return the image name.

    Useful for uploading reference images before calling
    generate_image_with_reference().

    Args:
        image_bytes: Raw image bytes (PNG or JPEG).
        filename: Filename hint for MIME type detection.
        invokeai_url: Base URL of the InvokeAI service.

    Returns:
        The image_name assigned by InvokeAI.

    Raises:
        InvokeAIError: If upload fails.
    """
    import mimetypes

    mime_type, _ = mimetypes.guess_type(filename)
    if mime_type is None:
        mime_type = "image/png"

    url = f"{invokeai_url}/api/v1/images/upload"
    params = {
        "image_category": "user",
        "is_intermediate": "false",
        "board_id": BOARD_ID,
    }

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
                raise InvokeAIError("Upload succeeded but no image_name in response")
            logger.info(f"Uploaded image to InvokeAI: {image_name}")
            return image_name

    except httpx.HTTPStatusError as e:
        raise InvokeAIError(f"Image upload failed: HTTP {e.response.status_code}")
    except httpx.RequestError as e:
        raise InvokeAIError(f"Image upload failed: {e}")


async def check_invokeai_health(
    invokeai_url: str = DEFAULT_INVOKEAI_URL,
    timeout: float = 5.0,
) -> bool:
    """Check if the InvokeAI service is reachable."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{invokeai_url}/api/v1/queue/default/status")
            return response.status_code == 200
    except Exception as e:
        logger.warning(f"InvokeAI health check failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _submit_batch(
    batch_payload: dict,
    invokeai_url: str,
    max_retries: int,
) -> dict:
    """Submit a batch to the InvokeAI queue and return batch info."""
    endpoint = f"{invokeai_url}/api/v1/queue/default/enqueue_batch"

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                logger.info(f"Submitting batch to InvokeAI at {endpoint}")
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
                    f"Batch submitted: {batch_info['batch_id']} "
                    f"(items: {batch_info['item_ids']})"
                )
                return batch_info

        except httpx.TimeoutException:
            logger.warning(f"InvokeAI submission timeout (attempt {attempt + 1})")
            if attempt < max_retries - 1:
                await asyncio.sleep(2**attempt)
            else:
                raise InvokeAIError("Batch submission timed out after all retries")

        except httpx.HTTPStatusError as e:
            raise InvokeAIError(
                f"Batch submission failed: HTTP {e.response.status_code}"
            )

        except httpx.RequestError as e:
            logger.warning(f"InvokeAI connection error (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2**attempt)
            else:
                raise InvokeAIError(f"Failed to connect to InvokeAI: {e}")

    raise InvokeAIError("Batch submission failed after all retries")


async def _poll_for_result(
    batch_info: dict,
    invokeai_url: str,
    poll_interval: float,
    timeout: float,
) -> str:
    """Poll a batch until it completes and return the generated image name."""
    queue_id = batch_info["queue_id"]
    batch_id = batch_info["batch_id"]
    item_ids = batch_info["item_ids"]

    elapsed = 0.0
    while elapsed < timeout:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Check batch status
                status_url = (
                    f"{invokeai_url}/api/v1/queue/{queue_id}/b/{batch_id}/status"
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
                        logger.info(f"Batch {batch_id} completed ({completed}/{total})")
                        return await _extract_image_name(
                            queue_id, item_ids, invokeai_url
                        )

                    logger.info(
                        f"Batch {batch_id}: {completed}/{total} completed, waiting..."
                    )

        except InvokeAIError:
            raise
        except Exception as e:
            logger.warning(f"Error polling batch status: {e}")

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    raise InvokeAIError(f"Batch {batch_id} timed out after {timeout}s")


async def _extract_image_name(
    queue_id: str,
    item_ids: list,
    invokeai_url: str,
) -> str:
    """Extract the generated image name from queue item results."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        for item_id in item_ids:
            item_url = f"{invokeai_url}/api/v1/queue/{queue_id}/i/{item_id}"
            response = await client.get(item_url)

            if response.status_code != 200:
                continue

            item_data = response.json()
            session = item_data.get("session", {})
            results = session.get("results", {})

            for node_id, result in results.items():
                if result.get("type") == "image_output":
                    image_name = result.get("image", {}).get("image_name")
                    if image_name:
                        logger.info(f"Generated image: {image_name}")
                        return image_name

    raise InvokeAIError("No image found in batch results")


async def _download_image(
    image_name: str,
    invokeai_url: str,
    max_retries: int,
) -> bytes:
    """Download a generated image by name."""
    url = f"{invokeai_url}/api/v1/images/i/{image_name}/full"

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    logger.info(f"Downloaded image: {image_name}")
                    return response.content
                else:
                    logger.warning(
                        f"Download attempt {attempt + 1}/{max_retries} "
                        f"returned HTTP {response.status_code}"
                    )

        except Exception as e:
            logger.warning(f"Download attempt {attempt + 1}/{max_retries} failed: {e}")

        if attempt < max_retries - 1:
            await asyncio.sleep(2**attempt)

    raise InvokeAIError(
        f"Failed to download image {image_name} after {max_retries} attempts"
    )
