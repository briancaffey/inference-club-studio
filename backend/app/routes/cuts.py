import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.cut import Cut
from app.models.project import Project
from app.schemas.cut import CutRead, CutReorderRequest, CutUploadResponse
from app.tasks.cuts import process_cut_metadata
from app.utils.media import ensure_media_dir

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/cuts", tags=["cuts"])


def _get_project_or_404(project_id: uuid.UUID, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("", response_model=CutUploadResponse, status_code=201)
async def upload_cuts(
    project_id: uuid.UUID,
    files: list[UploadFile],
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)

    cuts_dir = ensure_media_dir(settings.media_dir, str(project_id), "cuts")

    # Get current max order
    max_order = (
        db.query(Cut.order)
        .filter(Cut.project_id == project_id)
        .order_by(Cut.order.desc())
        .first()
    )
    next_order = (max_order[0] + 1) if max_order else 0

    uploaded = []
    for i, file in enumerate(files):
        cut_id = uuid.uuid4()
        ext = Path(file.filename).suffix if file.filename else ".mp4"
        dest_filename = f"{cut_id}{ext}"
        dest_path = cuts_dir / dest_filename

        # Write file to disk
        content = await file.read()
        with open(dest_path, "wb") as f:
            f.write(content)

        file_size = os.path.getsize(dest_path)

        cut = Cut(
            id=cut_id,
            project_id=project_id,
            order=next_order + i,
            original_filename=file.filename or f"cut_{next_order + i}{ext}",
            file_path=str(dest_path),
            file_size=file_size,
        )
        db.add(cut)
        uploaded.append(cut)

    db.commit()
    for cut in uploaded:
        db.refresh(cut)

    logger.info("Uploaded %d cuts to project %s", len(uploaded), project_id)

    # Kick off processing for each cut
    for cut in uploaded:
        process_cut_metadata.delay(str(cut.id))

    return CutUploadResponse(uploaded=[CutRead.model_validate(c) for c in uploaded])


@router.get("", response_model=list[CutRead])
def list_cuts(project_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_project_or_404(project_id, db)
    cuts = db.query(Cut).filter(Cut.project_id == project_id).order_by(Cut.order).all()
    return [CutRead.model_validate(c) for c in cuts]


@router.get("/{cut_id}", response_model=CutRead)
def get_cut(project_id: uuid.UUID, cut_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_project_or_404(project_id, db)
    cut = db.query(Cut).filter(Cut.id == cut_id, Cut.project_id == project_id).first()
    if not cut:
        raise HTTPException(status_code=404, detail="Cut not found")
    return CutRead.model_validate(cut)


@router.delete("/{cut_id}", status_code=204)
def delete_cut(project_id: uuid.UUID, cut_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_project_or_404(project_id, db)
    cut = db.query(Cut).filter(Cut.id == cut_id, Cut.project_id == project_id).first()
    if not cut:
        raise HTTPException(status_code=404, detail="Cut not found")

    deleted_order = cut.order

    # Delete associated files
    for path in [cut.file_path, cut.thumbnail_path, cut.audio_path]:
        if path and os.path.exists(path):
            os.remove(path)

    db.delete(cut)

    # Renumber remaining cuts
    remaining = (
        db.query(Cut)
        .filter(Cut.project_id == project_id, Cut.order > deleted_order)
        .order_by(Cut.order)
        .all()
    )
    for c in remaining:
        c.order -= 1

    db.commit()
    logger.info(
        "Deleted cut %s from project %s, renumbered remaining", cut_id, project_id
    )


@router.put("/reorder", response_model=list[CutRead])
def reorder_cuts(
    project_id: uuid.UUID,
    data: CutReorderRequest,
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)

    cuts = db.query(Cut).filter(Cut.project_id == project_id).all()
    cut_map = {c.id: c for c in cuts}

    # Validate all IDs belong to this project
    for i, cut_id in enumerate(data.cut_ids):
        if cut_id not in cut_map:
            raise HTTPException(
                status_code=400,
                detail=f"Cut {cut_id} not found in project",
            )
        cut_map[cut_id].order = i

    if len(data.cut_ids) != len(cuts):
        raise HTTPException(
            status_code=400,
            detail="Must include all cut IDs in reorder request",
        )

    db.commit()
    logger.info("Reordered %d cuts in project %s", len(cuts), project_id)

    # Return in new order
    ordered = sorted(cuts, key=lambda c: c.order)
    return [CutRead.model_validate(c) for c in ordered]
