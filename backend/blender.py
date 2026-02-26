#!/usr/bin/env python3
"""
Blender audio segment importer for narration projects.

This script:
1. Downloads the audio segments zip file from the backend API
2. Extracts the zip into a persistent narration directory next to the .blend file
3. Appends each audio file (in order) to the Blender video editor timeline

Usage:
    blender --background --python blender.py

Environment variables:
    BACKEND_URL: Base URL of the backend API (default: http://localhost:8000)
    PROJECT_NAME: Name of the narration project (default: "something")
    OUTPUT_BLEND: Path to save the .blend file (default: ./narration_project.blend)
"""

import os
import shutil
import urllib.request
import zipfile
from pathlib import Path

import bpy


# Configuration
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
PROJECT_NAME = os.environ.get("PROJECT_NAME", "something")
OUTPUT_BLEND_ENV = os.environ.get("OUTPUT_BLEND")
OUTPUT_BLEND = OUTPUT_BLEND_ENV or "./narration_project.blend"

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


def prepare_narration_dir(narration_dir: Path) -> None:
    """Ensure narration directory exists and is empty before extraction."""
    narration_dir.mkdir(parents=True, exist_ok=True)
    for child in narration_dir.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


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


def download_zip(project_id: str, output_path: Path) -> Path:
    """Download the audio segments zip file from the API."""
    api_url = f"{BACKEND_URL}/api/projects/{project_id}/export-zip"
    print(f"Downloading audio segments from: {api_url}")

    try:
        urllib.request.urlretrieve(api_url, output_path)
        print(f"Downloaded zip to: {output_path}")
        return output_path
    except Exception as e:
        print(f"Error downloading zip: {e}")
        raise


def extract_zip(zip_path: Path, extract_dir: Path) -> list[Path]:
    """Extract the zip file and return sorted list of audio files."""
    print(f"Extracting zip to: {extract_dir}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)

    # Get all WAV files and sort by filename (which includes position prefix)
    audio_files = sorted(
        (path for path in extract_dir.rglob("*.wav") if path.is_file()),
        key=lambda path: path.name,
    )
    print(f"Found {len(audio_files)} audio segments")

    for i, audio_file in enumerate(audio_files, 1):
        print(f"  {i}. {audio_file.name}")

    return audio_files


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

    strips = get_strip_collection(seq_editor)

    # Clear only strips on channels 2+ so channel 1 content is preserved.
    for strip in list(strips):
        if strip.channel >= 2:
            strips.remove(strip)

    return seq_editor


def add_audio_to_timeline(audio_files: list[Path], start_channel: int = 1) -> int:
    """
    Add audio files sequentially to the video editor timeline.

    Args:
        audio_files: Sorted list of audio file paths
        start_channel: Starting channel for audio strips

    Returns:
        The end frame of the last audio strip
    """
    scene = bpy.context.scene
    seq_editor = scene.sequence_editor

    if not seq_editor:
        seq_editor = scene.sequence_editor_create()

    strips = get_strip_collection(seq_editor)

    current_frame = 1
    audio_strips = []

    for i, audio_path in enumerate(audio_files):
        print(f"Adding audio strip {i + 1}/{len(audio_files)}: {audio_path.name}")

        # Add sound strip
        strip = strips.new_sound(
            name=f"Segment_{i + 1:03d}",
            filepath=str(audio_path),
            channel=start_channel,
            frame_start=current_frame,
        )

        # Trim to actual audio length
        strip.frame_final_end = current_frame + int(
            strip.frame_final_duration * scene.render.fps / 24
        )

        audio_strips.append(strip)

        # Next strip starts where this one ends
        current_frame = int(strip.frame_final_end)

        print(
            f"  Duration: {strip.frame_final_duration} frames "
            f"(~{strip.frame_final_duration / scene.render.fps:.2f}s)"
        )

    return current_frame - 1


def main():
    """Main entry point."""
    print("=" * 60)
    print("Blender Narration Audio Importer")
    print("=" * 60)

    # Set render FPS for consistent timing
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
    narration_dir = get_narration_dir(output_blend_path)
    print(f"Using narration directory: {narration_dir}")

    # Start from a clean narration directory so stale files do not break references.
    prepare_narration_dir(narration_dir)

    zip_path = narration_dir / "audio_segments.zip"

    # Download and extract into persistent narration folder.
    download_zip(project_id, zip_path)
    try:
        audio_files = extract_zip(zip_path, narration_dir)
    finally:
        # Cleanup downloaded zip after extraction (or failure).
        if zip_path.exists():
            zip_path.unlink()
            print(f"Removed zip file: {zip_path}")

    if not audio_files:
        print("No audio files found in zip")
        bpy.ops.wm.quit_blender()
        return

    # Setup video editing scene
    setup_video_editing_scene()

    # Add audio strips to timeline (starting at channel 2)
    end_frame = add_audio_to_timeline(audio_files, start_channel=2)

    # Set timeline range
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = end_frame
    bpy.context.scene.frame_current = 1

    print(f"Timeline set to frames 1-{end_frame}")

    # Save the blend file
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend_path))
    print(f"Saved Blender project to: {output_blend_path}")

    print("=" * 60)
    print("Import complete!")
    print("=" * 60)

    # Don't quit when running interactively
    if not bpy.app.background:
        print("Switch to Video Editing workspace to view the timeline")


if __name__ == "__main__":
    main()
