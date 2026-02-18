import asyncio
import logging
import subprocess

from app.celery_app import celery
from app.clients.invokeai.client import InvokeAIClient
from app.config import settings
from app.database import SessionLocal
from app.models.generation import Generation, GenerationStatus
from app.utils.media import ensure_media_dir

logger = logging.getLogger(__name__)


def _get_generation(db, generation_id: str) -> Generation | None:
    return db.query(Generation).filter(Generation.id == generation_id).first()


@celery.task(bind=True, max_retries=0)
def generate_style_transfer(self, generation_id: str):
    """Run the full style transfer pipeline for a generation.

    Steps:
    1. Extract first frame from the cut's video
    2. Upload reference frame to InvokeAI
    3. Generate styled image via InvokeAI (Kontext conditioning)
    4. Download result and save locally
    """
    db = SessionLocal()
    try:
        generation = _get_generation(db, generation_id)
        if not generation:
            logger.error("Generation %s not found", generation_id)
            return

        cut = generation.cut
        if not cut:
            logger.error("Cut not found for generation %s", generation_id)
            generation.status = GenerationStatus.ERROR.value
            generation.error_message = "Associated cut not found"
            db.commit()
            return

        project_id = str(cut.project_id)
        gen_dir = ensure_media_dir(
            settings.media_dir, project_id, "generations", generation_id
        )

        # Step 1: Extract first frame
        generation.status = GenerationStatus.EXTRACTING_FRAME.value
        db.commit()

        reference_frame_path = str(gen_dir / "reference_frame.png")
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            cut.file_path,
            "-vframes",
            "1",
            reference_frame_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Frame extraction failed: {result.stderr[:500]}")

        generation.reference_frame_path = reference_frame_path
        db.commit()
        logger.info("Extracted reference frame for generation %s", generation_id)

        # Step 2: Upload reference frame to InvokeAI
        generation.status = GenerationStatus.UPLOADING_REFERENCE.value
        db.commit()

        with open(reference_frame_path, "rb") as f:
            frame_bytes = f.read()

        client = InvokeAIClient()
        image_name = asyncio.run(
            client.upload_image(frame_bytes, "reference_frame.png")
        )

        generation.invokeai_reference_image_name = image_name
        db.commit()
        logger.info("Uploaded reference frame to InvokeAI: %s", image_name)

        # Step 3: Generate styled image
        generation.status = GenerationStatus.GENERATING.value
        db.commit()

        generated = asyncio.run(
            client.generate_with_reference(
                prompt=generation.prompt,
                ref_image_name=image_name,
                width=generation.width,
                height=generation.height,
                num_steps=generation.num_steps,
                cfg_scale=generation.cfg_scale,
                seed=generation.seed,
            )
        )

        generation.invokeai_generated_image_name = generated.image_name
        generation.actual_seed = generated.seed
        db.commit()
        logger.info(
            "Generated image for generation %s: %s",
            generation_id,
            generated.image_name,
        )

        # Step 4: Download and save output
        generation.status = GenerationStatus.DOWNLOADING.value
        db.commit()

        output_path = str(gen_dir / "output.png")
        with open(output_path, "wb") as f:
            f.write(generated.image_bytes)

        generation.output_image_path = output_path
        generation.status = GenerationStatus.COMPLETED.value
        db.commit()
        logger.info("Generation %s completed successfully", generation_id)

    except Exception as exc:
        logger.exception("Generation %s failed: %s", generation_id, exc)
        db.rollback()
        generation = _get_generation(db, generation_id)
        if generation:
            generation.status = GenerationStatus.ERROR.value
            generation.error_message = str(exc)[:1000]
            db.commit()
    finally:
        db.close()
