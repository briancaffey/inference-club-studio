"""LLM-based quality scoring for generated narration audio."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


QUALITY_PROMPT = """\
You evaluate text-to-speech output quality using the original script and ASR transcription.

Return ONLY valid JSON with this exact schema:
{
  "score": number,               // 0 to 10 (higher is better)
  "should_regenerate": boolean,  // true if quality is not acceptable
  "reason": string               // short reason (max 160 chars)
}

Scoring guidance:
- 9-10: near-perfect match, no meaningful omissions/additions
- 7-8: minor issues, still mostly acceptable
- 4-6: noticeable errors, meaning affected in places
- 0-3: severe mismatch or unusable

Ignore punctuation/casing differences unless meaning changes.
Prioritize semantic accuracy and completeness.
If there are major omissions, substitutions, hallucinations, or incorrect names/numbers:
set should_regenerate=true.
"""


@dataclass
class NarrationQualityResult:
    score: float
    should_regenerate: bool
    reason: str


def _groq_reasoning_options(base_url: str) -> dict:
    """Return Groq-compatible low-reasoning request options."""
    if "groq.com" not in base_url.lower():
        return {}
    return {
        "reasoning_effort": "low",
        # Keep reasoning hidden in API responses.
        "include_reasoning": False,
    }


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _clamp_score(value: float) -> float:
    return max(0.0, min(10.0, round(float(value), 1)))


def _normalize_for_similarity(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _fallback_quality_result(
    original_text: str,
    transcription_text: str,
    reason_prefix: str = "Fallback similarity score",
) -> NarrationQualityResult:
    original = _normalize_for_similarity(original_text)
    transcribed = _normalize_for_similarity(transcription_text)
    ratio = SequenceMatcher(None, original, transcribed).ratio()
    score = _clamp_score(ratio * 10.0)
    should_regenerate = score < 8.0
    reason = f"{reason_prefix}: {int(round(ratio * 100))}% textual similarity"
    return NarrationQualityResult(
        score=score,
        should_regenerate=should_regenerate,
        reason=reason[:160],
    )


def _parse_quality_response(content: str) -> NarrationQualityResult:
    payload = json.loads(_strip_code_fences(content))
    if not isinstance(payload, dict):
        raise ValueError("LLM quality response is not a JSON object")

    score = _clamp_score(float(payload.get("score", 0)))
    should_regenerate = bool(payload.get("should_regenerate", score < 8.0))
    reason = str(payload.get("reason", "")).strip() or "No reason provided"

    return NarrationQualityResult(
        score=score,
        should_regenerate=should_regenerate,
        reason=reason[:160],
    )


async def evaluate_narration_quality(
    original_text: str,
    transcription_text: str,
) -> NarrationQualityResult:
    if not transcription_text.strip():
        return NarrationQualityResult(
            score=0.0,
            should_regenerate=True,
            reason="No transcription returned from STT",
        )

    if not original_text.strip():
        return NarrationQualityResult(
            score=0.0,
            should_regenerate=True,
            reason="Original input text is empty",
        )

    base_url = settings.openai_base_url.rstrip("/")
    api_key = settings.openai_api_key or settings.groq_api_key or "not-needed"

    payload = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": QUALITY_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Original text:\n{original_text.strip()}\n\n"
                    f"Transcription:\n{transcription_text.strip()}"
                ),
            },
        ],
        "max_tokens": 256,
        "temperature": 0.1,
        **_groq_reasoning_options(base_url),
    }

    timeout = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:300]}")

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return _parse_quality_response(content)
    except Exception as exc:
        logger.warning("LLM quality evaluation failed, using fallback scoring: %s", exc)
        return _fallback_quality_result(
            original_text,
            transcription_text,
            reason_prefix="LLM unavailable, fallback similarity score",
        )
