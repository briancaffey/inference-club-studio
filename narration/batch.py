#!/usr/bin/env python3
"""Batch generation CLI - generates audio for all segments without the web server."""

import argparse
import asyncio
import logging
import os
import re
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def make_output_filename(position: int, text: str) -> str:
    clean = re.sub(r"\[S\d+\]\s*", "", text)
    words = clean.split()[:5]
    name = "_".join(words)
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"\s+", "_", name).lower()[:50]
    return f"{position:03d}_{name}.wav"


async def main():
    parser = argparse.ArgumentParser(description="Batch generate narration audio")
    parser.add_argument("script_file", nargs="?", help="Script file to import (optional if segments already exist)")
    parser.add_argument("--service", default="dia", choices=["dia", "magpie"], help="TTS service to use")
    parser.add_argument("--force", action="store_true", help="Regenerate all segments, even completed ones")
    args = parser.parse_args()

    from app.db import init_db, list_segments, import_script, get_segment, update_segment
    from app.services.dia import generate as dia_generate, get_wav_duration

    await init_db()

    output_dir = os.environ.get("OUTPUT_DIR", "output")
    os.makedirs(output_dir, exist_ok=True)

    # Import script file if provided
    if args.script_file:
        with open(args.script_file, "r") as f:
            lines = [line.strip() for line in f if line.strip()]
        logger.info(f"Importing {len(lines)} lines from {args.script_file}")
        await import_script(lines, args.service)

    segments = await list_segments()
    if not segments:
        logger.error("No segments found. Provide a script file or import segments first.")
        sys.exit(1)

    pending = segments if args.force else [s for s in segments if s["status"] != "done"]
    logger.info(f"{len(pending)} segments to generate ({len(segments)} total)")

    success = 0
    failed = 0

    for i, seg in enumerate(pending):
        logger.info(f"[{i + 1}/{len(pending)}] Segment {seg['position']}: {seg['text'][:60]}...")

        await update_segment(seg["id"], status="generating")

        filename = make_output_filename(seg["position"], seg["text"])
        output_path = os.path.join(output_dir, filename)

        try:
            if seg["service"] == "dia" or args.service == "dia":
                await dia_generate(seg["sanitized_text"], output_path)
            else:
                raise RuntimeError("Magpie not yet implemented")

            duration = get_wav_duration(output_path)
            await update_segment(
                seg["id"],
                status="done",
                audio_path=output_path,
                duration_seconds=round(duration, 2),
            )
            logger.info(f"  Done: {duration:.1f}s -> {output_path}")
            success += 1
        except Exception as e:
            logger.error(f"  Failed: {e}")
            await update_segment(seg["id"], status="error", error_message=str(e))
            failed += 1

    logger.info(f"Complete: {success} generated, {failed} failed")


if __name__ == "__main__":
    asyncio.run(main())
