import asyncio
import json
import logging
import re
from typing import Literal

import httpx
from pydantic import BaseModel, Field, model_validator

from app.config import settings

logger = logging.getLogger(__name__)


PLAN_SYSTEM_PROMPT = """\
You design image-sequence plans for narration storyboards.

Return ONLY valid JSON with this schema:
{
  "series_name": "short name",
  "steps": [
    {
      "id": "step_1",
      "parent_id": null,
      "mode": "text_to_image",
      "is_fork": false,
      "prompt": "detailed image prompt"
    }
  ]
}

Rules:
- You may include one or many root steps with parent_id=null and
  mode="text_to_image" for independent scenes.
- Every non-root step must reference an earlier step id via parent_id.
- Use mode="image_to_image" for non-root steps that should preserve continuity.
- Use a new root step (parent_id=null, mode="text_to_image")
  for unrelated images.
- Keep prompts concrete and production-ready for FLUX image generation.
- Keep continuity in subject, composition, and scene identity
  between parent/child steps.
- Use is_fork=true for steps meant to branch creative direction.
- Do not include markdown or commentary.
"""


SUGGEST_SYSTEM_PROMPT = """\
You suggest next prompts for a branching image sequence.

Return ONLY valid JSON:
{
  "suggestions": ["prompt 1", "prompt 2"]
}

Rules:
- Suggestions must be suitable as image-to-image continuation prompts.
- Preserve continuity with provided context.
- Keep each suggestion concise but specific.
- No markdown or commentary.
"""


class SequencePlanStep(BaseModel):
    id: str = Field(min_length=1)
    parent_id: str | None = None
    mode: Literal["text_to_image", "image_to_image"]
    is_fork: bool = False
    prompt: str = Field(min_length=1)


class SequencePlan(BaseModel):
    series_name: str | None = None
    steps: list[SequencePlanStep]

    @model_validator(mode="after")
    def _validate_steps(self) -> "SequencePlan":
        if not self.steps:
            raise ValueError("Plan must include at least one step")

        seen: set[str] = set()
        roots = 0
        for index, step in enumerate(self.steps):
            if step.id in seen:
                raise ValueError(f"Duplicate step id: {step.id}")
            seen.add(step.id)

            if step.parent_id is None:
                roots += 1
                if step.mode != "text_to_image":
                    raise ValueError("Root step must use text_to_image mode")
            else:
                if step.parent_id not in seen:
                    raise ValueError(
                        "Step "
                        f"{step.id} references missing/forward parent "
                        f"{step.parent_id}"
                    )
                if index > 0 and step.mode not in {"text_to_image", "image_to_image"}:
                    raise ValueError(f"Invalid mode for step {step.id}")

        if roots < 1:
            raise ValueError("Plan must include at least one root step")
        return self


def _groq_reasoning_options(base_url: str) -> dict:
    if "groq.com" not in base_url.lower():
        return {}
    return {
        "reasoning_effort": "low",
        "include_reasoning": False,
    }


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*\n?", "", stripped)
        stripped = re.sub(r"\n?```\s*$", "", stripped)
    return stripped.strip()


async def _chat_completion(
    *,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float,
) -> str:
    base_url = settings.openai_base_url.rstrip("/")
    api_key = settings.openai_api_key or settings.groq_api_key or "not-needed"
    payload = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        **_groq_reasoning_options(base_url),
    }

    timeout = httpx.Timeout(connect=10.0, read=90.0, write=10.0, pool=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:300]}")

    data = response.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not content:
        raise RuntimeError("LLM returned empty content")
    return content


async def _generate_image_sequence_plan_async(
    *,
    segment_text: str,
    creative_direction: str,
    target_images: int,
) -> SequencePlan:
    user_prompt = (
        f"Segment narration text:\n{segment_text.strip()}\n\n"
        f"Creative direction:\n{creative_direction.strip()}\n\n"
        f"Target image count: {target_images}\n\n"
        "Build a sequence plan with independent scenes and/or continuity edits/forks, as needed."
    )
    content = await _chat_completion(
        system_prompt=PLAN_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        max_tokens=1400,
        temperature=0.3,
    )
    payload = json.loads(_strip_code_fences(content))
    return SequencePlan.model_validate(payload)


def generate_image_sequence_plan(
    *,
    segment_text: str,
    creative_direction: str,
    target_images: int,
) -> SequencePlan:
    return asyncio.run(
        _generate_image_sequence_plan_async(
            segment_text=segment_text,
            creative_direction=creative_direction,
            target_images=target_images,
        )
    )


async def _suggest_image_prompts_async(
    *,
    segment_text: str,
    source_prompt: str,
    guidance: str | None,
    count: int,
) -> list[str]:
    guidance_text = guidance.strip() if guidance else "None"
    user_prompt = (
        f"Segment narration text:\n{segment_text.strip()}\n\n"
        f"Current image prompt:\n{source_prompt.strip()}\n\n"
        f"Extra guidance:\n{guidance_text}\n\n"
        f"Suggestion count: {count}\n\n"
        "Generate branching continuation prompt suggestions."
    )
    content = await _chat_completion(
        system_prompt=SUGGEST_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        max_tokens=900,
        temperature=0.5,
    )
    payload = json.loads(_strip_code_fences(content))
    suggestions = payload.get("suggestions")
    if not isinstance(suggestions, list):
        raise ValueError("LLM suggestions response missing 'suggestions' array")
    cleaned = [str(item).strip() for item in suggestions if str(item).strip()]
    return cleaned[:count]


def suggest_image_prompts(
    *,
    segment_text: str,
    source_prompt: str,
    guidance: str | None,
    count: int,
) -> list[str]:
    return asyncio.run(
        _suggest_image_prompts_async(
            segment_text=segment_text,
            source_prompt=source_prompt,
            guidance=guidance,
            count=count,
        )
    )
