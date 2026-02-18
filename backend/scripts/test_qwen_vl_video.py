"""Test script for Qwen3-VL video analysis via the backend client.

Usage (from project root):
    docker compose run --rm api uv run python -m scripts.test_qwen_vl_video
"""

import asyncio
import logging
import sys

from app.clients.qwen_vl.client import QwenVLClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

VIDEO_PATH = "/app/media/cut_1.mp4"
PROMPT = (
    "Analyze this video clip. Describe what you see happening, "
    "including the setting, any people or objects, camera movement, "
    "and the overall mood or tone."
)


async def main():
    client = QwenVLClient()

    # Health check
    logger.info("Checking vLLM service health...")
    healthy = await client.check_health()
    if not healthy:
        logger.error("vLLM service is not reachable at %s", client.url)
        sys.exit(1)
    logger.info("vLLM service is healthy")

    # Analyze video
    logger.info("Analyzing video: %s", VIDEO_PATH)
    result = await client.analyze_video(
        video_path=VIDEO_PATH,
        prompt=PROMPT,
        max_tokens=1024,
    )

    print("\n" + "=" * 60)
    print("VIDEO ANALYSIS RESULT")
    print("=" * 60)
    print(f"Model: {result.model}")
    print(f"Prompt tokens: {result.prompt_tokens}")
    print(f"Completion tokens: {result.completion_tokens}")
    print("-" * 60)
    print(result.content)
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
