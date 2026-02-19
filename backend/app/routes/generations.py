import logging
import os
import shutil
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.cut import Cut, CutStatus
from app.models.generation import Generation
from app.models.project import Project, ProjectType
from app.schemas.generation import GenerationCreate, GenerationRead
from app.tasks.generations import generate_style_transfer

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/projects/{project_id}/cuts/{cut_id}/generations",
    tags=["generations"],
)


def _get_project_or_404(project_id: uuid.UUID, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.project_type != ProjectType.VIDEO_TO_VIDEO.value:
        raise HTTPException(
            status_code=400,
            detail="Generation operations are only supported for video-to-video projects",
        )
    return project


def _get_cut_or_404(project_id: uuid.UUID, cut_id: uuid.UUID, db: Session) -> Cut:
    cut = db.query(Cut).filter(Cut.id == cut_id, Cut.project_id == project_id).first()
    if not cut:
        raise HTTPException(status_code=404, detail="Cut not found")
    return cut


@router.post("", response_model=GenerationRead, status_code=201)
def create_generation(
    project_id: uuid.UUID,
    cut_id: uuid.UUID,
    data: GenerationCreate,
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)
    cut = _get_cut_or_404(project_id, cut_id, db)

    if cut.status != CutStatus.READY.value:
        raise HTTPException(
            status_code=400,
            detail="Cut must be in 'ready' status to generate",
        )

    generation = Generation(
        cut_id=cut_id,
        prompt=data.prompt,
        width=data.width,
        height=data.height,
        num_steps=data.num_steps,
        cfg_scale=data.cfg_scale,
        seed=data.seed,
    )
    db.add(generation)
    db.commit()
    db.refresh(generation)

    logger.info("Created generation %s for cut %s", generation.id, cut_id)

    generate_style_transfer.delay(str(generation.id))

    return GenerationRead.model_validate(generation)


@router.get("", response_model=list[GenerationRead])
def list_generations(
    project_id: uuid.UUID,
    cut_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)
    _get_cut_or_404(project_id, cut_id, db)

    generations = (
        db.query(Generation)
        .filter(Generation.cut_id == cut_id)
        .order_by(Generation.created_at.desc())
        .all()
    )
    return [GenerationRead.model_validate(g) for g in generations]


@router.get("/{generation_id}", response_model=GenerationRead)
def get_generation(
    project_id: uuid.UUID,
    cut_id: uuid.UUID,
    generation_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)
    _get_cut_or_404(project_id, cut_id, db)

    generation = (
        db.query(Generation)
        .filter(
            Generation.id == generation_id,
            Generation.cut_id == cut_id,
        )
        .first()
    )
    if not generation:
        raise HTTPException(status_code=404, detail="Generation not found")
    return GenerationRead.model_validate(generation)


@router.delete("/{generation_id}", status_code=204)
def delete_generation(
    project_id: uuid.UUID,
    cut_id: uuid.UUID,
    generation_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)
    _get_cut_or_404(project_id, cut_id, db)

    generation = (
        db.query(Generation)
        .filter(
            Generation.id == generation_id,
            Generation.cut_id == cut_id,
        )
        .first()
    )
    if not generation:
        raise HTTPException(status_code=404, detail="Generation not found")

    # Delete associated files
    for path in [generation.reference_frame_path, generation.output_image_path]:
        if path and os.path.exists(path):
            os.remove(path)

    # Try to remove the generation directory
    gen_dir = os.path.join(
        settings.media_dir,
        str(project_id),
        "generations",
        str(generation_id),
    )
    if os.path.isdir(gen_dir):
        shutil.rmtree(gen_dir)

    db.delete(generation)
    db.commit()
    logger.info("Deleted generation %s from cut %s", generation_id, cut_id)
