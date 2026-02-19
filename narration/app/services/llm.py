"""LLM client for article-to-narration segmentation.

Splits articles locally into chunks, then sends each chunk to the LLM
for TTS cleanup (number expansion, abbreviation expansion, etc.).
Chunks are processed concurrently with a semaphore to avoid overloading
the LLM server.
"""

import asyncio
import json
import logging
import os
import re
import time

import httpx

logger = logging.getLogger(__name__)

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://192.168.6.19:8002/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "not-needed")
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "4096"))
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.3"))
LLM_CONCURRENCY = int(os.environ.get("LLM_CONCURRENCY", "8"))

# Prompt for cleaning a single chunk (not the whole article)
CHUNK_PROMPT = """\
You are a text preprocessor that prepares text for text-to-speech narration.

You will receive a short chunk of text from an article. Clean it up for TTS and split it into segments if needed. Each segment should be 1-2 sentences and roughly 40 words maximum.

Apply these transformations:
- Convert numbers to spoken form (e.g. "42%" → "forty-two percent", "$3.5M" → "three point five million dollars", "2024" → "twenty twenty-four" when it's a year)
- Expand abbreviations (e.g. "e.g." → "for example", "etc." → "and so on", "i.e." → "that is")
- Expand acronyms where helpful for spoken clarity (e.g. "LLM" → "large language model", "API" → "A P I")
- Remove URLs entirely or replace with a natural description
- Remove markdown formatting (headers, bold, italic, links, images, code blocks)
- Remove footnotes, references, and citation markers
- Remove any content that doesn't work well when spoken aloud (tables, code, etc.)
- If the chunk is only a heading or non-spoken content, return an empty array

Return ONLY a JSON array of strings. Each string is one TTS segment. No other text, no explanation.
If the input has no speakable content, return [].\
"""


# ---------------------------------------------------------------------------
# Local chunking (no LLM needed)
# ---------------------------------------------------------------------------

# Sentence-ending punctuation followed by whitespace
_SENTENCE_RE = re.compile(r'(?<=[.!?])\s+')
# Markdown headings, horizontal rules, image/link syntax
_MD_BLOCK_RE = re.compile(r'^#{1,6}\s+|^[-*_]{3,}\s*$|^!\[.*?\]\(.*?\)\s*$', re.MULTILINE)


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences at . ! ? boundaries."""
    parts = _SENTENCE_RE.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


def split_into_chunks(text: str, max_chars: int = 500, min_chars: int = 100) -> list[str]:
    """Split article text into chunks suitable for individual LLM processing.

    Strategy:
    1. Split on paragraph breaks (double newlines)
    2. Long paragraphs get split at sentence boundaries
    3. Short consecutive pieces get grouped together up to max_chars
    """
    # Split into paragraphs
    paragraphs = re.split(r'\n\s*\n', text.strip())
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    # Break long paragraphs into sentences, keep short ones whole
    pieces: list[str] = []
    for para in paragraphs:
        # Collapse internal newlines to spaces (single newlines within a paragraph)
        para = re.sub(r'\n', ' ', para).strip()
        if len(para) <= max_chars:
            pieces.append(para)
        else:
            for sent in _split_sentences(para):
                pieces.append(sent)

    # Greedily group small pieces into chunks up to max_chars
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        combined = f"{current}\n{piece}".strip() if current else piece
        if len(combined) <= max_chars:
            current = combined
        else:
            if current:
                chunks.append(current)
            # If a single piece exceeds max_chars, include it anyway
            current = piece
    if current:
        chunks.append(current)

    return chunks


# ---------------------------------------------------------------------------
# LLM calls
# ---------------------------------------------------------------------------

async def _call_llm_chunk(client: httpx.AsyncClient, chunk: str) -> str:
    """Send a single chunk to the LLM for TTS cleanup. Returns raw content."""
    base_url = LLM_BASE_URL.rstrip("/")

    payload = {
        "chat_template_kwargs": {"enable_thinking": False},
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": CHUNK_PROMPT},
            {"role": "user", "content": chunk},
        ],
        "max_tokens": LLM_MAX_TOKENS,
        "temperature": LLM_TEMPERATURE,
    }

    resp = await client.post(
        f"{base_url}/chat/completions",
        json=payload,
        headers={"Authorization": f"Bearer {LLM_API_KEY}"},
    )

    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _parse_segments(content: str) -> list[str]:
    """Parse LLM response content into a list of segment strings."""
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*\n?", "", content)
        content = re.sub(r"\n?```\s*$", "", content)

    segments = json.loads(content)

    if not isinstance(segments, list):
        raise ValueError(f"Expected JSON array, got: {content[:300]}")

    segments = [str(s).strip() for s in segments if str(s).strip()]
    return segments


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def process_single_chunk(text: str) -> list[str]:
    """Process a single chunk through the LLM for TTS cleanup.

    Used for retrying failed chunks from the frontend.
    """
    timeout = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        content = await _call_llm_chunk(client, text)
    return _parse_segments(content)


async def split_article_for_tts(article_text: str) -> list[str]:
    """Split and clean article text into TTS-ready segments.

    Non-streaming version for batch/CLI use.
    """
    chunks = split_into_chunks(article_text)
    logger.info(f"Split article ({len(article_text)} chars) into {len(chunks)} chunks")

    semaphore = asyncio.Semaphore(LLM_CONCURRENCY)
    timeout = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        async def process(chunk: str) -> list[str]:
            async with semaphore:
                content = await _call_llm_chunk(client, chunk)
                return _parse_segments(content)

        results = await asyncio.gather(*[process(c) for c in chunks], return_exceptions=True)

    all_segments = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Chunk {i+1} failed: {result}")
        else:
            all_segments.extend(result)

    if not all_segments:
        raise RuntimeError("All chunks failed to process")

    logger.info(f"LLM returned {len(all_segments)} total segments from {len(chunks)} chunks")
    return all_segments


async def split_article_for_tts_streaming(article_text: str):
    """Stream progress events while processing article text in chunks.

    Yields raw chunks immediately so the frontend can display them,
    then yields chunk_done events as each chunk finishes LLM processing.

    Yields dicts with a "phase" key:
      - splitting: local splitting done, includes raw chunks for immediate display
      - chunk_done: one chunk finished, includes index + processed segments
      - chunk_error: one chunk failed, includes index + error detail
      - done: all chunks processed, final summary
      - error: fatal error (e.g. can't connect to LLM)
    """
    start = time.monotonic()

    chunks = split_into_chunks(article_text)
    yield {
        "phase": "splitting",
        "detail": f"Split article ({len(article_text):,} chars) into {len(chunks)} chunks",
        "chunks": chunks,
        "total": len(chunks),
    }

    semaphore = asyncio.Semaphore(LLM_CONCURRENCY)
    timeout = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)
    # Queue for chunk tasks to report results back to the generator
    queue: asyncio.Queue = asyncio.Queue()
    error_count = 0
    total_segments = 0

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async def process_chunk(i: int, chunk: str):
                async with semaphore:
                    try:
                        content = await _call_llm_chunk(client, chunk)
                        segments = _parse_segments(content)
                        await queue.put({"index": i, "segments": segments})
                    except Exception as e:
                        logger.error(f"Chunk {i+1}/{len(chunks)} failed: {e}")
                        await queue.put({"index": i, "error": f"{type(e).__name__}: {e}"})

            tasks = [asyncio.create_task(process_chunk(i, c)) for i, c in enumerate(chunks)]

            completed = 0
            while completed < len(chunks):
                try:
                    result = await asyncio.wait_for(queue.get(), timeout=2.0)
                    completed += 1
                    if "error" in result:
                        error_count += 1
                        yield {
                            "phase": "chunk_error",
                            "index": result["index"],
                            "detail": result["error"],
                            "completed": completed,
                            "total": len(chunks),
                        }
                    else:
                        total_segments += len(result["segments"])
                        yield {
                            "phase": "chunk_done",
                            "index": result["index"],
                            "segments": result["segments"],
                            "completed": completed,
                            "total": len(chunks),
                        }
                except asyncio.TimeoutError:
                    # Heartbeat so the frontend knows we're alive
                    elapsed = int(time.monotonic() - start)
                    yield {
                        "phase": "processing",
                        "detail": f"Processing chunks... ({completed}/{len(chunks)} done, {elapsed}s elapsed)",
                        "completed": completed,
                        "total": len(chunks),
                        "elapsed": elapsed,
                    }

            await asyncio.gather(*tasks)

    except httpx.ConnectError:
        base_url = LLM_BASE_URL.rstrip("/")
        yield {"phase": "error", "detail": f"Could not connect to LLM at {base_url}. Is the service running?"}
        return
    except Exception as e:
        yield {"phase": "error", "detail": f"{type(e).__name__}: {e}"}
        return

    elapsed = int(time.monotonic() - start)

    if total_segments == 0:
        yield {"phase": "error", "detail": "All chunks failed to process or returned empty results."}
        return

    error_note = f" ({error_count} chunk(s) had errors)" if error_count else ""
    logger.info(f"Processed {len(chunks)} chunks -> {total_segments} segments in {elapsed}s")
    yield {
        "phase": "done",
        "count": total_segments,
        "detail": f"{total_segments} segments from {len(chunks)} chunks in {elapsed}s{error_note}",
    }
