#!/usr/bin/env python3
"""
Blender narration timeline importer for narration projects.

This script:
1. Downloads narration audio zip, image zip, and timeline metadata from the backend API
2. Stores each import batch in timestamped subfolders next to the .blend file
3. Appends narration audio strips and image strips to fixed channels in VSE

Usage:
    blender --background --python blender.py

Environment variables:
    BACKEND_URL: Base URL of the backend API (default: http://localhost:8000)
    PROJECT_NAME: Name of the narration project (default: "something")
    OUTPUT_BLEND: Path to save the .blend file (default: ./narration_project.blend)
"""

import json
import os
import time
import urllib.request
import zipfile
from pathlib import Path

import bpy


# Configuration
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
PROJECT_NAME = os.environ.get("PROJECT_NAME", "something")
OUTPUT_BLEND_ENV = os.environ.get("OUTPUT_BLEND")
OUTPUT_BLEND = OUTPUT_BLEND_ENV or "./narration_project.blend"
AUDIO_CHANNEL = 3
IMAGE_CHANNEL = 4
AUDIO_GAIN = 1.9

# Hardcoded project ID for "something" project
# Update this if the project ID changes
PROJECT_ID = os.environ.get("PROJECT_ID", "")


def resolve_output_blend_path() -> Path:
    """Resolve the .blend file path used for saving and relative assets."""
    if OUTPUT_BLEND_ENV:
        return Path(OUTPUT_BLEND).expanduser().resolve()
    if bpy.data.filepath:
        return Path(bpy.data.filepath).resolve()
    return Path(OUTPUT_BLEND).expanduser().resolve()


def get_narration_dir(output_blend_path: Path) -> Path:
    """Return the narration directory adjacent to the blend file."""
    return output_blend_path.parent / "narration"


def get_image_dir(output_blend_path: Path) -> Path:
    """Return the image directory adjacent to the blend file."""
    return output_blend_path.parent / "image"


def get_meta_dir(output_blend_path: Path) -> Path:
    """Return the metadata directory adjacent to the blend file."""
    return output_blend_path.parent / "meta"


def get_batch_dirs(output_blend_path: Path, epoch_token: str) -> tuple[Path, Path, Path]:
    """Return timestamped batch directories for narration/image/meta assets."""
    narration_dir = get_narration_dir(output_blend_path) / epoch_token
    image_dir = get_image_dir(output_blend_path) / epoch_token
    meta_dir = get_meta_dir(output_blend_path) / epoch_token
    narration_dir.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    return narration_dir, image_dir, meta_dir


def get_project_id_by_name(project_name: str) -> str | None:
    """Fetch project ID by name from the API."""
    import json

    api_url = f"{BACKEND_URL}/api/projects"
    try:
        with urllib.request.urlopen(api_url) as response:
            data = json.loads(response.read().decode())
            # Handle both list of dicts and list of objects with id/name attributes
            for project in data:
                name = project.get("name") if isinstance(project, dict) else project.name
                if name == project_name:
                    proj_id = (
                        project.get("id") if isinstance(project, dict) else project.id
                    )
                    return str(proj_id)
    except Exception as e:
        print(f"Error fetching projects: {e}")
    return None


def download_file(api_url: str, output_path: Path) -> Path:
    """Download a file from the API."""
    print(f"Downloading from: {api_url}")

    try:
        urllib.request.urlretrieve(api_url, output_path)
        print(f"Downloaded to: {output_path}")
        return output_path
    except Exception as e:
        print(f"Error downloading file: {e}")
        raise


def download_json(api_url: str, output_path: Path) -> dict:
    """Download JSON from API and persist it to disk."""
    print(f"Downloading metadata from: {api_url}")
    try:
        with urllib.request.urlopen(api_url) as response:
            payload = json.loads(response.read().decode())
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Saved metadata to: {output_path}")
        return payload
    except Exception as e:
        print(f"Error downloading metadata: {e}")
        raise


def extract_zip(zip_path: Path, extract_dir: Path) -> list[Path]:
    """Extract a zip file and return extracted files."""
    print(f"Extracting {zip_path.name} to: {extract_dir}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)

    extracted_files = sorted(
        (path for path in extract_dir.rglob("*") if path.is_file()),
        key=lambda path: path.name,
    )
    print(f"Found {len(extracted_files)} extracted files")
    return extracted_files


def get_strip_collection(seq_editor):
    """Return VSE strip collection across Blender API versions."""
    return seq_editor.strips if hasattr(seq_editor, "strips") else seq_editor.sequences


def setup_video_editing_scene():
    """Configure Blender for video editing."""
    scene = bpy.context.scene
    scene.use_nodes = False

    # Switch to Video Editing workspace if available
    if "Video Editing" in bpy.data.workspaces:
        bpy.context.window.workspace = bpy.data.workspaces["Video Editing"]

    # Get or create sequence editor
    seq_editor = scene.sequence_editor
    if not seq_editor:
        seq_editor = scene.sequence_editor_create()

    return seq_editor


def ensure_channels_clear(seq_editor, channels: set[int]) -> None:
    """Exit early if target channels are not empty."""
    strips = get_strip_collection(seq_editor)
    occupied = [strip for strip in strips if strip.channel in channels]
    if not occupied:
        return

    print("Target channels are not clear. Aborting import to avoid deleting existing data.")
    for strip in occupied:
        print(
            f"  Channel {strip.channel}: {strip.name} "
            f"(frames {strip.frame_start}-{strip.frame_final_end})"
        )
    raise RuntimeError("Target channels are occupied")


def add_audio_from_metadata(metadata: dict, narration_dir: Path) -> int:
    """Add audio strips to the timeline using metadata frame windows."""
    scene = bpy.context.scene
    seq_editor = scene.sequence_editor or scene.sequence_editor_create()
    strips = get_strip_collection(seq_editor)
    last_end_exclusive = 1

    for segment in metadata.get("segments", []):
        audio_meta = segment.get("audio", {})
        filename = audio_meta.get("filename")
        if not filename:
            continue
        audio_path = narration_dir / filename
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        frame_start = int(audio_meta.get("start_frame", 1))
        frame_end_exclusive = int(audio_meta.get("end_frame_exclusive", frame_start + 1))
        if frame_end_exclusive <= frame_start:
            raise ValueError(
                f"Invalid audio frame range for segment {segment.get('segment_id')}: "
                f"{frame_start}..{frame_end_exclusive}"
            )

        segment_label = int(segment.get("position", 0))
        print(
            f"Adding audio segment {segment_label:03d}: "
            f"{audio_path.name} [{frame_start}, {frame_end_exclusive})"
        )
        strip = strips.new_sound(
            name=f"Narration_{segment_label:03d}",
            filepath=str(audio_path),
            channel=AUDIO_CHANNEL,
            frame_start=frame_start,
        )
        strip.frame_final_end = frame_end_exclusive
        strip.volume = AUDIO_GAIN
        last_end_exclusive = max(last_end_exclusive, frame_end_exclusive)
    return last_end_exclusive


def add_images_from_metadata(metadata: dict, image_dir: Path) -> int:
    """Add image strips to timeline using metadata frame windows."""
    scene = bpy.context.scene
    seq_editor = scene.sequence_editor or scene.sequence_editor_create()
    strips = get_strip_collection(seq_editor)
    last_end_exclusive = 1

    for segment in metadata.get("segments", []):
        for image in segment.get("images", []):
            filename = image.get("filename")
            if not filename:
                continue
            image_path = image_dir / filename
            if not image_path.exists():
                raise FileNotFoundError(f"Image file not found: {image_path}")

            frame_start = int(image.get("start_frame", 1))
            frame_end_exclusive = int(image.get("end_frame_exclusive", frame_start + 1))
            if frame_end_exclusive <= frame_start:
                raise ValueError(
                    f"Invalid image frame range for file {filename}: "
                    f"{frame_start}..{frame_end_exclusive}"
                )

            print(
                f"Adding image strip: {image_path.name} "
                f"[{frame_start}, {frame_end_exclusive})"
            )
            strip = strips.new_image(
                name=f"Image_{segment.get('position', 0):03d}_{image.get('step_order', 0):03d}",
                filepath=str(image_path),
                channel=IMAGE_CHANNEL,
                frame_start=frame_start,
            )
            strip.frame_final_end = frame_end_exclusive
            last_end_exclusive = max(last_end_exclusive, frame_end_exclusive)
    return last_end_exclusive


def main():
    """Main entry point."""
    print("=" * 60)
    print("Blender Narration Audio Importer")
    print("=" * 60)

    # Set render FPS for consistent timing and metadata math.
    bpy.context.scene.render.fps = 24
    bpy.context.scene.render.fps_base = 1.0

    # Determine project ID
    project_id = PROJECT_ID
    if not project_id:
        print(f"Looking up project ID for: {PROJECT_NAME}")
        project_id = get_project_id_by_name(PROJECT_NAME)
        if not project_id:
            print(f"Error: Could not find project '{PROJECT_NAME}'")
            bpy.ops.wm.quit_blender()
            return

    print(f"Project ID: {project_id}")

    output_blend_path = resolve_output_blend_path()
    epoch_token = str(int(time.time()))
    narration_dir, image_dir, meta_dir = get_batch_dirs(output_blend_path, epoch_token)
    print(f"Using asset batch: {epoch_token}")
    print(f"  Narration dir: {narration_dir}")
    print(f"  Image dir: {image_dir}")
    print(f"  Meta dir: {meta_dir}")

    fps = bpy.context.scene.render.fps
    metadata_url = f"{BACKEND_URL}/api/projects/{project_id}/export-timeline-metadata?fps={fps}"
    audio_zip_url = f"{BACKEND_URL}/api/projects/{project_id}/export-zip"
    image_zip_url = f"{BACKEND_URL}/api/projects/{project_id}/export-images-zip"

    metadata_path = meta_dir / "timeline_metadata.json"
    audio_zip_path = narration_dir / "audio_segments.zip"
    image_zip_path = image_dir / "image_segments.zip"

    metadata = download_json(metadata_url, metadata_path)
    download_file(audio_zip_url, audio_zip_path)
    download_file(image_zip_url, image_zip_path)

    try:
        extract_zip(audio_zip_path, narration_dir)
        extract_zip(image_zip_path, image_dir)
    finally:
        if audio_zip_path.exists():
            audio_zip_path.unlink()
            print(f"Removed zip file: {audio_zip_path}")
        if image_zip_path.exists():
            image_zip_path.unlink()
            print(f"Removed zip file: {image_zip_path}")

    if not metadata.get("segments"):
        print("No segment metadata returned")
        bpy.ops.wm.quit_blender()
        return

    seq_editor = setup_video_editing_scene()
    try:
        ensure_channels_clear(seq_editor, channels={AUDIO_CHANNEL, IMAGE_CHANNEL})
    except RuntimeError as exc:
        print(str(exc))
        bpy.ops.wm.quit_blender()
        return

    audio_end_exclusive = add_audio_from_metadata(metadata, narration_dir)
    image_end_exclusive = add_images_from_metadata(metadata, image_dir)
    timeline_end_exclusive = int(
        metadata.get("timeline", {}).get(
            "end_frame_exclusive",
            max(audio_end_exclusive, image_end_exclusive),
        )
    )
    max_end_exclusive = max(audio_end_exclusive, image_end_exclusive, timeline_end_exclusive)

    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = max(1, max_end_exclusive - 1)
    bpy.context.scene.frame_current = 1

    print(f"Timeline set to frames 1-{bpy.context.scene.frame_end}")
    print(
        f"Placed strips on channels: audio={AUDIO_CHANNEL} (volume={AUDIO_GAIN}), "
        f"images={IMAGE_CHANNEL}"
    )

    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend_path))
    print(f"Saved Blender project to: {output_blend_path}")

    print("=" * 60)
    print("Import complete!")
    print("=" * 60)

    if not bpy.app.background:
        print("Switch to Video Editing workspace to view the timeline")


if __name__ == "__main__":
    main()
