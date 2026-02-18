"""ComfyUI client for video generation using LTX 2.0 + canny control."""

import asyncio
import copy
import json
import logging
import random
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Load workflow template at module level
_WORKFLOW_PATH = Path(__file__).parent / "video_ltx2_canny_to_video_distilled.json"
with open(_WORKFLOW_PATH) as _f:
    _WORKFLOW_TEMPLATE = json.load(_f)


class ComfyUIError(Exception):
    """Exception raised when ComfyUI operations fail."""

    pass


class ComfyUIClient:
    """Client for ComfyUI video generation service."""

    def __init__(
        self,
        url: str | None = None,
        poll_interval: float = 5.0,
        timeout: float = 600.0,
    ):
        self.url = url or settings.comfyui_url
        self.poll_interval = poll_interval
        self.timeout = timeout

    async def upload_file(self, file_bytes: bytes, filename: str) -> str:
        """Upload a file (image or video) to ComfyUI's input directory.

        Returns the filename as stored by ComfyUI.
        """
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.url}/upload/image",
                    files={"image": (filename, file_bytes)},
                    data={"overwrite": "true"},
                )
                response.raise_for_status()
                data = response.json()
                stored_name = data.get("name", filename)
                logger.info("Uploaded file to ComfyUI: %s", stored_name)
                return stored_name
        except httpx.HTTPStatusError as e:
            raise ComfyUIError(f"File upload failed: HTTP {e.response.status_code}")
        except httpx.RequestError as e:
            raise ComfyUIError(f"File upload failed: {e}")

    async def submit_workflow(
        self,
        prompt: str,
        ref_image_filename: str,
        video_filename: str,
        width: int,
        height: int,
        frame_count: int,
        seed: int,
        filename_prefix: str = "take",
    ) -> str:
        """Build and submit a workflow to ComfyUI.

        Returns the prompt_id for tracking.
        """
        if seed < 0:
            seed = random.randint(0, 2**32 - 1)

        workflow = copy.deepcopy(_WORKFLOW_TEMPLATE)

        # Parameterize nodes
        workflow["127"]["inputs"]["file"] = video_filename
        workflow["160"]["inputs"]["image"] = ref_image_filename
        workflow["166"]["inputs"]["value"] = width
        workflow["167"]["inputs"]["value"] = height
        workflow["168"]["inputs"]["value"] = frame_count
        workflow["162:124"]["inputs"]["text"] = prompt
        workflow["162:126"]["inputs"]["noise_seed"] = seed
        workflow["162:143"]["inputs"]["noise_seed"] = seed
        workflow["161"]["inputs"]["filename_prefix"] = f"video/{filename_prefix}"
        workflow["178"]["inputs"]["filename_prefix"] = f"canny/{filename_prefix}"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.url}/prompt",
                    json={"prompt": workflow},
                )
                response.raise_for_status()
                data = response.json()
                prompt_id = data.get("prompt_id")
                if not prompt_id:
                    raise ComfyUIError("No prompt_id in response")
                logger.info("Submitted workflow to ComfyUI: %s", prompt_id)
                return prompt_id
        except httpx.HTTPStatusError as e:
            raise ComfyUIError(
                f"Workflow submission failed: HTTP {e.response.status_code}"
            )
        except httpx.RequestError as e:
            raise ComfyUIError(f"Workflow submission failed: {e}")

    async def poll_until_complete(
        self, prompt_id: str, timeout: int | None = None
    ) -> dict:
        """Poll /history/{prompt_id} until outputs appear or timeout."""
        timeout = timeout or int(self.timeout)
        elapsed = 0.0

        while elapsed < timeout:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(f"{self.url}/history/{prompt_id}")
                    if response.status_code == 200:
                        data = response.json()
                        if prompt_id in data:
                            history = data[prompt_id]
                            outputs = history.get("outputs", {})
                            status = history.get("status", {})
                            status_str = status.get("status_str", "")

                            if status_str == "error":
                                messages = status.get("messages", [])
                                raise ComfyUIError(f"Workflow failed: {messages}")

                            if outputs:
                                logger.info(
                                    "Workflow %s completed with %d output nodes",
                                    prompt_id,
                                    len(outputs),
                                )
                                return history

                            logger.info(
                                "Workflow %s still running (%.0fs elapsed)",
                                prompt_id,
                                elapsed,
                            )
            except ComfyUIError:
                raise
            except Exception as e:
                logger.warning("Error polling workflow status: %s", e)

            await asyncio.sleep(self.poll_interval)
            elapsed += self.poll_interval

        raise ComfyUIError(f"Workflow {prompt_id} timed out after {timeout}s")

    async def download_output(
        self, filename: str, subfolder: str, output_type: str = "output"
    ) -> bytes:
        """Download an output file from ComfyUI."""
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.get(
                    f"{self.url}/view",
                    params={
                        "filename": filename,
                        "subfolder": subfolder,
                        "type": output_type,
                    },
                )
                response.raise_for_status()
                logger.info(
                    "Downloaded output: %s/%s (%d bytes)",
                    subfolder,
                    filename,
                    len(response.content),
                )
                return response.content
        except httpx.HTTPStatusError as e:
            raise ComfyUIError(f"Download failed: HTTP {e.response.status_code}")
        except httpx.RequestError as e:
            raise ComfyUIError(f"Download failed: {e}")

    async def check_health(self) -> bool:
        """Check if the ComfyUI service is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.url}/system_stats")
                return response.status_code == 200
        except Exception as e:
            logger.warning("ComfyUI health check failed: %s", e)
            return False
