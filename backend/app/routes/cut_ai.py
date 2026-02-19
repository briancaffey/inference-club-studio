import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.cut import Cut, CutStatus
from app.models.cut_ai import CutAIRun
from app.models.project import Project, ProjectType
from app.schemas.cut_ai import (
    CutAIRegenerateRequest,
    CutAIRunRead,
    CutAIStateRead,
    FluxPromptDraftRequest,
    FluxPromptDraftResponse,
)
from app.services.cut_ai import (
    ANALYSIS_CLIP_OVERVIEW,
    ANALYSIS_FIRST_FRAME,
    ensure_content_input,
    execute_flux_prompt_run,
    get_or_create_ai_state,
    queue_runs_for_cut,
)
from app.tasks.cut_ai import generate_clip_overview, generate_first_frame_description

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/cuts/{cut_id}/ai", tags=["cut-ai"])

_VALID_REGENERATE_TYPES = {ANALYSIS_CLIP_OVERVIEW, ANALYSIS_FIRST_FRAME}


def _get_project_or_404(project_id: uuid.UUID, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.project_type != ProjectType.VIDEO_TO_VIDEO.value:
        raise HTTPException(
            status_code=400,
            detail="Cut AI is only supported for video-to-video projects",
        )
    return project


def _get_cut_or_404(project_id: uuid.UUID, cut_id: uuid.UUID, db: Session) -> Cut:
    cut = db.query(Cut).filter(Cut.id == cut_id, Cut.project_id == project_id).first()
    if not cut:
        raise HTTPException(status_code=404, detail="Cut not found")
    return cut


@router.get("", response_model=CutAIStateRead)
def get_cut_ai_state(
    project_id: uuid.UUID,
    cut_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)
    cut = _get_cut_or_404(project_id, cut_id, db)

    state = get_or_create_ai_state(db, cut.id)
    db.commit()
    db.refresh(state)
    return CutAIStateRead.model_validate(state)


@router.post("/regenerate", response_model=CutAIStateRead)
def regenerate_cut_ai(
    project_id: uuid.UUID,
    cut_id: uuid.UUID,
    data: CutAIRegenerateRequest,
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)
    cut = _get_cut_or_404(project_id, cut_id, db)

    if cut.status != CutStatus.READY.value:
        raise HTTPException(
            status_code=400,
            detail="Cut must be in 'ready' status to regenerate AI descriptions",
        )

    requested = data.types or [ANALYSIS_CLIP_OVERVIEW, ANALYSIS_FIRST_FRAME]
    invalid = sorted(set(requested) - _VALID_REGENERATE_TYPES)
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid analysis type(s): {', '.join(invalid)}",
        )

    runs = queue_runs_for_cut(
        db=db,
        cut=cut,
        analysis_types=requested,
        force=True,
    )
    state = get_or_create_ai_state(db, cut.id)
    db.commit()
    db.refresh(state)

    for run in runs:
        if run.analysis_type == ANALYSIS_CLIP_OVERVIEW:
            generate_clip_overview.delay(str(cut.id), str(run.id))
        elif run.analysis_type == ANALYSIS_FIRST_FRAME:
            generate_first_frame_description.delay(str(cut.id), str(run.id))

    return CutAIStateRead.model_validate(state)


@router.get("/runs", response_model=list[CutAIRunRead])
def list_cut_ai_runs(
    project_id: uuid.UUID,
    cut_id: uuid.UUID,
    analysis_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)
    cut = _get_cut_or_404(project_id, cut_id, db)

    query = db.query(CutAIRun).filter(CutAIRun.cut_id == cut.id)
    if analysis_type:
        query = query.filter(CutAIRun.analysis_type == analysis_type)
    runs = query.order_by(CutAIRun.created_at.desc()).all()
    return [CutAIRunRead.model_validate(run) for run in runs]


@router.post("/prompt-drafts/flux", response_model=FluxPromptDraftResponse)
def create_flux_prompt_draft(
    project_id: uuid.UUID,
    cut_id: uuid.UUID,
    data: FluxPromptDraftRequest,
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)
    cut = _get_cut_or_404(project_id, cut_id, db)

    if cut.status != CutStatus.READY.value:
        raise HTTPException(
            status_code=400,
            detail="Cut must be in 'ready' status to generate prompt drafts",
        )

    state = get_or_create_ai_state(db, cut.id)
    db.commit()
    db.refresh(state)

    content = ensure_content_input(data.content, state)
    if not content:
        raise HTTPException(
            status_code=400,
            detail=(
                "No content provided and no existing cut descriptions found. "
                "Provide content or generate cut descriptions first."
            ),
        )

    try:
        run, draft = execute_flux_prompt_run(
            db=db,
            cut=cut,
            state=state,
            style=data.style.strip(),
            content=content,
        )
    except Exception as exc:
        logger.exception("Flux prompt draft generation failed for cut %s", cut_id)
        raise HTTPException(
            status_code=502,
            detail=f"Prompt draft generation failed: {exc}",
        )

    return FluxPromptDraftResponse(
        draft_id=draft.id,
        run=CutAIRunRead.model_validate(run),
        prompt_text=draft.prompt_text,
        created_at=draft.created_at,
    )
