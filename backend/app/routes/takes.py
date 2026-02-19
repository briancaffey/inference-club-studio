import logging
import os
import shutil
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.cut import Cut
from app.models.generation import Generation, GenerationStatus
from app.models.project import Project, ProjectType
from app.models.take import Take
from app.schemas.take import TakeCreate, TakeRead
from app.tasks.takes import generate_video_take

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/projects/{project_id}/cuts/{cut_id}/generations/{generation_id}/takes",
    tags=["takes"],
)


def _get_project_or_404(project_id: uuid.UUID, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.project_type != ProjectType.VIDEO_TO_VIDEO.value:
        raise HTTPException(
            status_code=400,
            detail="Take operations are only supported for video-to-video projects",
        )
    return project


def _get_cut_or_404(project_id: uuid.UUID, cut_id: uuid.UUID, db: Session) -> Cut:
    cut = db.query(Cut).filter(Cut.id == cut_id, Cut.project_id == project_id).first()
    if not cut:
        raise HTTPException(status_code=404, detail="Cut not found")
    return cut


def _get_generation_or_404(
    generation_id: uuid.UUID, cut_id: uuid.UUID, db: Session
) -> Generation:
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
    return generation


@router.post("", response_model=TakeRead, status_code=201)
def create_take(
    project_id: uuid.UUID,
    cut_id: uuid.UUID,
    generation_id: uuid.UUID,
    data: TakeCreate,
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)
    _get_cut_or_404(project_id, cut_id, db)
    generation = _get_generation_or_404(generation_id, cut_id, db)

    if generation.status != GenerationStatus.COMPLETED.value:
        raise HTTPException(
            status_code=400,
            detail="Generation must be in 'completed' status to create a take",
        )

    take = Take(
        generation_id=generation_id,
        prompt=data.prompt,
        width=data.width,
        height=data.height,
        frame_count=data.frame_count,
        seed=data.seed,
    )
    db.add(take)
    db.commit()
    db.refresh(take)

    logger.info("Created take %s for generation %s", take.id, generation_id)

    generate_video_take.delay(str(take.id))

    return TakeRead.model_validate(take)


@router.get("", response_model=list[TakeRead])
def list_takes(
    project_id: uuid.UUID,
    cut_id: uuid.UUID,
    generation_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)
    _get_cut_or_404(project_id, cut_id, db)
    _get_generation_or_404(generation_id, cut_id, db)

    takes = (
        db.query(Take)
        .filter(Take.generation_id == generation_id)
        .order_by(Take.created_at.desc())
        .all()
    )
    return [TakeRead.model_validate(t) for t in takes]


@router.get("/{take_id}", response_model=TakeRead)
def get_take(
    project_id: uuid.UUID,
    cut_id: uuid.UUID,
    generation_id: uuid.UUID,
    take_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)
    _get_cut_or_404(project_id, cut_id, db)
    _get_generation_or_404(generation_id, cut_id, db)

    take = (
        db.query(Take)
        .filter(
            Take.id == take_id,
            Take.generation_id == generation_id,
        )
        .first()
    )
    if not take:
        raise HTTPException(status_code=404, detail="Take not found")
    return TakeRead.model_validate(take)


@router.delete("/{take_id}", status_code=204)
def delete_take(
    project_id: uuid.UUID,
    cut_id: uuid.UUID,
    generation_id: uuid.UUID,
    take_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)
    _get_cut_or_404(project_id, cut_id, db)
    _get_generation_or_404(generation_id, cut_id, db)

    take = (
        db.query(Take)
        .filter(
            Take.id == take_id,
            Take.generation_id == generation_id,
        )
        .first()
    )
    if not take:
        raise HTTPException(status_code=404, detail="Take not found")

    # Delete associated files
    for path in [take.output_video_path, take.canny_video_path]:
        if path and os.path.exists(path):
            os.remove(path)

    # Try to remove the take directory
    take_dir = os.path.join(
        settings.media_dir,
        str(project_id),
        "takes",
        str(take_id),
    )
    if os.path.isdir(take_dir):
        shutil.rmtree(take_dir)

    db.delete(take)
    db.commit()
    logger.info("Deleted take %s from generation %s", take_id, generation_id)
