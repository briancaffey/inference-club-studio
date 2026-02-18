import subprocess
from pathlib import Path


def get_media_info(file_path: str) -> dict:
    """Get media file metadata using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            file_path,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")

    import json

    return json.loads(result.stdout)


def ensure_media_dir(base_dir: str, *subdirs: str) -> Path:
    """Create and return a media subdirectory path."""
    path = Path(base_dir).joinpath(*subdirs)
    path.mkdir(parents=True, exist_ok=True)
    return path
