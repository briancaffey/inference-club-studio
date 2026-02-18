import logging
import subprocess

from app.celery_app import celery
from app.config import settings
from app.database import SessionLocal
from app.models.cut import Cut, CutStatus
from app.tasks.cut_ai import queue_cut_ai_analysis
from app.utils.media import ensure_media_dir, get_media_info

logger = logging.getLogger(__name__)


def _get_cut(db, cut_id: str) -> Cut | None:
    return db.query(Cut).filter(Cut.id == cut_id).first()


@celery.task(bind=True, max_retries=2)
def process_cut_metadata(self, cut_id: str):
    """Extract metadata from a video cut using ffprobe, then chain to thumbnail."""
    db = SessionLocal()
    try:
        cut = _get_cut(db, cut_id)
        if not cut:
            logger.error("Cut %s not found", cut_id)
            return

        cut.status = CutStatus.PROCESSING_METADATA.value
        db.commit()

        logger.info("Extracting metadata for cut %s: %s", cut_id, cut.file_path)
        info = get_media_info(cut.file_path)

        # Parse video stream
        video_stream = next(
            (s for s in info.get("streams", []) if s.get("codec_type") == "video"),
            None,
        )
        audio_stream = next(
            (s for s in info.get("streams", []) if s.get("codec_type") == "audio"),
            None,
        )
        format_info = info.get("format", {})

        if video_stream:
            cut.width = int(video_stream.get("width", 0)) or None
            cut.height = int(video_stream.get("height", 0)) or None
            cut.codec = video_stream.get("codec_name")

            # Parse FPS from r_frame_rate (e.g., "24000/1001")
            r_frame_rate = video_stream.get("r_frame_rate", "0/1")
            try:
                num, den = r_frame_rate.split("/")
                cut.fps = round(int(num) / int(den), 3) if int(den) else None
            except (ValueError, ZeroDivisionError):
                cut.fps = None

            if cut.width and cut.height:
                from math import gcd

                g = gcd(cut.width, cut.height)
                cut.aspect_ratio = f"{cut.width // g}:{cut.height // g}"

        if audio_stream:
            cut.audio_codec = audio_stream.get("codec_name")

        duration = format_info.get("duration")
        if duration:
            cut.duration = round(float(duration), 3)

        db.commit()
        logger.info("Metadata extracted for cut %s", cut_id)

        # Chain to thumbnail extraction
        extract_cut_thumbnail.delay(cut_id)

    except Exception as exc:
        logger.exception("Failed to extract metadata for cut %s", cut_id)
        db.rollback()
        cut = _get_cut(db, cut_id)
        if cut:
            cut.status = CutStatus.ERROR.value
            cut.error_message = str(exc)[:1000]
            db.commit()
    finally:
        db.close()


@celery.task(bind=True, max_retries=2)
def extract_cut_thumbnail(self, cut_id: str):
    """Generate a thumbnail JPEG at 25% duration, 480px wide."""
    db = SessionLocal()
    try:
        cut = _get_cut(db, cut_id)
        if not cut:
            logger.error("Cut %s not found", cut_id)
            return

        # Calculate timestamp at 25% of duration
        seek_time = (cut.duration or 1.0) * 0.25

        thumbnail_dir = ensure_media_dir(
            settings.media_dir, str(cut.project_id), "thumbnails"
        )
        thumbnail_path = str(thumbnail_dir / f"{cut.id}.jpg")

        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(seek_time),
            "-i",
            cut.file_path,
            "-vframes",
            "1",
            "-vf",
            "scale=480:-1",
            thumbnail_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            cut.thumbnail_path = thumbnail_path
            logger.info("Thumbnail generated for cut %s", cut_id)
        else:
            logger.warning(
                "Thumbnail generation failed for cut %s: %s",
                cut_id,
                result.stderr[:500],
            )
            # Non-critical — continue to audio extraction

        db.commit()

        # Chain to audio extraction
        extract_cut_audio.delay(cut_id)

    except Exception:
        logger.exception("Thumbnail extraction error for cut %s", cut_id)
        db.rollback()
        # Non-critical — still chain to audio
        extract_cut_audio.delay(cut_id)
    finally:
        db.close()


@celery.task(bind=True, max_retries=2)
def extract_cut_audio(self, cut_id: str):
    """Extract audio as WAV 44.1kHz stereo."""
    db = SessionLocal()
    try:
        cut = _get_cut(db, cut_id)
        if not cut:
            logger.error("Cut %s not found", cut_id)
            return

        cut.status = CutStatus.EXTRACTING_AUDIO.value
        db.commit()

        audio_dir = ensure_media_dir(settings.media_dir, str(cut.project_id), "audio")
        audio_path = str(audio_dir / f"{cut.id}.wav")

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            cut.file_path,
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "44100",
            "-ac",
            "2",
            audio_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            cut.audio_path = audio_path
            cut.status = CutStatus.READY.value
            logger.info("Audio extracted for cut %s — status READY", cut_id)
        else:
            cut.status = CutStatus.ERROR.value
            cut.error_message = f"Audio extraction failed: {result.stderr[:500]}"
            logger.error(
                "Audio extraction failed for cut %s: %s", cut_id, result.stderr[:500]
            )

        db.commit()
        if cut.status == CutStatus.READY.value:
            queue_cut_ai_analysis.delay(cut_id)

    except Exception as exc:
        logger.exception("Audio extraction error for cut %s", cut_id)
        db.rollback()
        cut = _get_cut(db, cut_id)
        if cut:
            cut.status = CutStatus.ERROR.value
            cut.error_message = str(exc)[:1000]
            db.commit()
    finally:
        db.close()
