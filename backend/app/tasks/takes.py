import asyncio
import glob
import logging
import subprocess

from app.celery_app import celery
from app.config import settings
from app.database import SessionLocal
from app.models.take import Take, TakeStatus
from app.services.client_factory import build_comfyui_client
from app.utils.media import ensure_media_dir

logger = logging.getLogger(__name__)


def _get_take(db, take_id: str) -> Take | None:
    return db.query(Take).filter(Take.id == take_id).first()


@celery.task(bind=True, max_retries=0)
def generate_video_take(self, take_id: str):
    """Run the full video generation pipeline for a take.

    Steps:
    1. Upload generation's styled image and cut's video to ComfyUI
    2. Submit LTX 2.0 canny workflow
    3. Poll until completion
    4. Download output video and canny images
    5. Encode canny images into video via ffmpeg
    """
    db = SessionLocal()
    try:
        take = _get_take(db, take_id)
        if not take:
            logger.error("Take %s not found", take_id)
            return

        generation = take.generation
        if not generation:
            logger.error("Generation not found for take %s", take_id)
            take.status = TakeStatus.ERROR.value
            take.error_message = "Associated generation not found"
            db.commit()
            return

        cut = generation.cut
        if not cut:
            logger.error("Cut not found for take %s", take_id)
            take.status = TakeStatus.ERROR.value
            take.error_message = "Associated cut not found"
            db.commit()
            return

        project_id = str(cut.project_id)
        take_dir = ensure_media_dir(settings.media_dir, project_id, "takes", take_id)
        canny_dir = ensure_media_dir(
            settings.media_dir, project_id, "takes", take_id, "canny"
        )

        client = build_comfyui_client(db)

        # Step 1: Upload assets to ComfyUI
        take.status = TakeStatus.UPLOADING_ASSETS.value
        db.commit()

        # Upload styled image
        if not generation.output_image_path:
            raise RuntimeError("Generation has no output image")
        with open(generation.output_image_path, "rb") as f:
            image_bytes = f.read()
        image_filename = asyncio.run(
            client.upload_file(image_bytes, f"take_{take_id}_style.png")
        )
        logger.info("Uploaded styled image for take %s: %s", take_id, image_filename)

        # Upload cut video
        if not cut.file_path:
            raise RuntimeError("Cut has no video file")
        with open(cut.file_path, "rb") as f:
            video_bytes = f.read()
        video_filename = asyncio.run(
            client.upload_file(video_bytes, f"take_{take_id}_source.mp4")
        )
        logger.info("Uploaded source video for take %s: %s", take_id, video_filename)

        # Step 2: Submit workflow
        take.status = TakeStatus.GENERATING.value
        db.commit()

        # Resolve seed
        seed = take.seed
        if seed < 0:
            import random

            seed = random.randint(0, 2**32 - 1)
        take.actual_seed = seed

        prompt_id = asyncio.run(
            client.submit_workflow(
                prompt=take.prompt,
                ref_image_filename=image_filename,
                video_filename=video_filename,
                width=take.width,
                height=take.height,
                frame_count=take.frame_count,
                seed=seed,
                filename_prefix=f"take_{take_id}",
            )
        )
        take.comfyui_prompt_id = prompt_id
        db.commit()
        logger.info("Submitted workflow for take %s: %s", take_id, prompt_id)

        # Step 3: Poll until complete
        history = asyncio.run(client.poll_until_complete(prompt_id))

        # Step 4: Download outputs
        take.status = TakeStatus.DOWNLOADING.value
        db.commit()

        outputs = history.get("outputs", {})

        # Download output video from node 161 (SaveVideo)
        # ComfyUI returns video files under "images" key, not "videos"
        node_161 = outputs.get("161", {})
        video_output = node_161.get("images", []) or node_161.get("videos", [])
        if video_output:
            vid = video_output[0]
            video_data = asyncio.run(
                client.download_output(
                    vid["filename"],
                    vid.get("subfolder", ""),
                    vid.get("type", "output"),
                )
            )
            output_video_path = str(take_dir / "output.mp4")
            with open(output_video_path, "wb") as f:
                f.write(video_data)
            take.output_video_path = output_video_path
            logger.info("Saved output video for take %s", take_id)
        else:
            logger.warning("No video output found for take %s", take_id)

        # Download canny images from node 178 (SaveImage)
        canny_output = outputs.get("178", {}).get("images", [])
        for i, img_info in enumerate(canny_output):
            img_data = asyncio.run(
                client.download_output(
                    img_info["filename"],
                    img_info.get("subfolder", ""),
                    img_info.get("type", "output"),
                )
            )
            img_path = str(canny_dir / f"canny_{i:05d}.png")
            with open(img_path, "wb") as f:
                f.write(img_data)

        if canny_output:
            logger.info(
                "Saved %d canny images for take %s",
                len(canny_output),
                take_id,
            )

        # Step 5: Encode canny images into video
        take.status = TakeStatus.ENCODING_CANNY.value
        db.commit()

        canny_video_path = str(take_dir / "canny.mp4")
        canny_images = sorted(glob.glob(str(canny_dir / "canny_*.png")))
        if canny_images:
            cmd = [
                "ffmpeg",
                "-y",
                "-framerate",
                "24",
                "-i",
                str(canny_dir / "canny_%05d.png"),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                canny_video_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.warning("Canny video encoding failed: %s", result.stderr[:500])
            else:
                take.canny_video_path = canny_video_path
                logger.info("Encoded canny video for take %s", take_id)

        take.status = TakeStatus.COMPLETED.value
        db.commit()
        logger.info("Take %s completed successfully", take_id)

    except Exception as exc:
        logger.exception("Take %s failed: %s", take_id, exc)
        db.rollback()
        take = _get_take(db, take_id)
        if take:
            take.status = TakeStatus.ERROR.value
            take.error_message = str(exc)[:1000]
            db.commit()
    finally:
        db.close()
