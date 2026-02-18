import logging
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.cut import Cut
from app.models.project import Project
from app.schemas.cut import CutRead
from app.schemas.project import (
    ProjectCreate,
    ProjectDetail,
    ProjectSummary,
    ProjectUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectSummary, status_code=201)
def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(
        name=data.name,
        description=data.description,
        metadata_=data.metadata,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    logger.info("Created project %s: %s", project.id, project.name)
    return ProjectSummary(
        id=project.id,
        name=project.name,
        description=project.description,
        cut_count=0,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.get("", response_model=list[ProjectSummary])
def list_projects(db: Session = Depends(get_db)):
    rows = (
        db.query(Project, func.count(Cut.id).label("cut_count"))
        .outerjoin(Cut, Cut.project_id == Project.id)
        .group_by(Project.id)
        .order_by(Project.created_at.desc())
        .all()
    )
    return [
        ProjectSummary(
            id=project.id,
            name=project.name,
            description=project.description,
            cut_count=cut_count,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )
        for project, cut_count in rows
    ]


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(project_id: uuid.UUID, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectDetail(
        id=project.id,
        name=project.name,
        description=project.description,
        metadata=project.metadata_,
        cuts=[CutRead.model_validate(c) for c in project.cuts],
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.patch("/{project_id}", response_model=ProjectSummary)
def update_project(
    project_id: uuid.UUID, data: ProjectUpdate, db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    update_data = data.model_dump(exclude_unset=True)
    if "metadata" in update_data:
        update_data["metadata_"] = update_data.pop("metadata")
    for key, value in update_data.items():
        setattr(project, key, value)

    db.commit()
    db.refresh(project)
    logger.info("Updated project %s", project.id)

    cut_count = (
        db.query(func.count(Cut.id)).filter(Cut.project_id == project.id).scalar()
    )
    return ProjectSummary(
        id=project.id,
        name=project.name,
        description=project.description,
        cut_count=cut_count,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: uuid.UUID, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Delete media files
    project_media = Path(settings.media_dir) / str(project_id)
    if project_media.exists():
        shutil.rmtree(project_media)
        logger.info("Deleted media directory for project %s", project_id)

    db.delete(project)
    db.commit()
    logger.info("Deleted project %s", project_id)
