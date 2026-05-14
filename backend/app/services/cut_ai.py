import asyncio
import logging
import subprocess
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.models.cut import Cut
from app.models.cut_ai import (
    CutAIAnalysisType,
    CutAIRun,
    CutAIState,
    CutAIStatus,
    PromptDraft,
)
from app.services.client_factory import build_qwen_vl_client
from app.services.qwen_prompts import (
    CLIP_OVERVIEW_PROFILE,
    FIRST_FRAME_PROFILE,
    FLUX_STYLE_CONTENT_PROFILE,
    build_clip_overview_prompt,
    build_first_frame_prompt,
    build_flux_style_content_prompt,
)
from app.utils.media import ensure_media_dir

logger = logging.getLogger(__name__)

ANALYSIS_CLIP_OVERVIEW = CutAIAnalysisType.CLIP_OVERVIEW.value
ANALYSIS_FIRST_FRAME = CutAIAnalysisType.FIRST_FRAME.value
ANALYSIS_FLUX_PROMPT = CutAIAnalysisType.FLUX_STYLE_CONTENT_PROMPT.value

DEFAULT_ANALYSIS_TYPES = [ANALYSIS_CLIP_OVERVIEW, ANALYSIS_FIRST_FRAME]
VALID_ANALYSIS_TYPES = set(DEFAULT_ANALYSIS_TYPES + [ANALYSIS_FLUX_PROMPT])


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_or_create_ai_state(db: Session, cut_id: uuid.UUID) -> CutAIState:
    state = db.query(CutAIState).filter(CutAIState.cut_id == cut_id).first()
    if state:
        return state

    state = CutAIState(cut_id=cut_id)
    db.add(state)
    db.flush()
    return state


def create_ai_run(
    *,
    db: Session,
    cut_id: uuid.UUID,
    analysis_type: str,
    prompt_key: str,
    prompt_input: dict,
    prompt_text: str,
    temperature: float,
    max_tokens: int,
    model_name: str,
) -> CutAIRun:
    run = CutAIRun(
        cut_id=cut_id,
        analysis_type=analysis_type,
        status=CutAIStatus.QUEUED.value,
        prompt_key=prompt_key,
        prompt_input=prompt_input,
        prompt_text=prompt_text,
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    db.add(run)
    db.flush()
    return run


def _set_state_status(state: CutAIState, analysis_type: str, status: str) -> None:
    if analysis_type == ANALYSIS_CLIP_OVERVIEW:
        state.clip_overview_status = status
    elif analysis_type == ANALYSIS_FIRST_FRAME:
        state.first_frame_status = status


def queue_runs_for_cut(
    *,
    db: Session,
    cut: Cut,
    analysis_types: list[str] | None = None,
    force: bool = False,
) -> list[CutAIRun]:
    types = analysis_types or DEFAULT_ANALYSIS_TYPES
    state = get_or_create_ai_state(db, cut.id)
    runs: list[CutAIRun] = []
    model_name = build_qwen_vl_client(db).model

    for analysis_type in types:
        if analysis_type not in VALID_ANALYSIS_TYPES:
            continue

        if (
            not force
            and analysis_type == ANALYSIS_CLIP_OVERVIEW
            and state.clip_overview_text
        ):
            continue
        if (
            not force
            and analysis_type == ANALYSIS_FIRST_FRAME
            and state.first_frame_description_text
        ):
            continue

        if analysis_type == ANALYSIS_CLIP_OVERVIEW:
            profile = CLIP_OVERVIEW_PROFILE
            prompt_text = build_clip_overview_prompt(cut)
            prompt_input = {
                "filename": cut.original_filename,
                "duration": cut.duration,
                "width": cut.width,
                "height": cut.height,
                "fps": cut.fps,
            }
        elif analysis_type == ANALYSIS_FIRST_FRAME:
            profile = FIRST_FRAME_PROFILE
            prompt_text = build_first_frame_prompt(cut)
            prompt_input = {
                "filename": cut.original_filename,
                "width": cut.width,
                "height": cut.height,
            }
        else:
            continue

        run = create_ai_run(
            db=db,
            cut_id=cut.id,
            analysis_type=analysis_type,
            prompt_key=profile.key,
            prompt_input=prompt_input,
            prompt_text=prompt_text,
            temperature=profile.temperature,
            max_tokens=profile.max_tokens,
            model_name=model_name,
        )
        _set_state_status(state, analysis_type, CutAIStatus.QUEUED.value)
        runs.append(run)

    return runs


def _extract_first_frame(cut: Cut) -> str:
    frame_dir = ensure_media_dir(
        settings.media_dir,
        str(cut.project_id),
        "ai",
        str(cut.id),
    )
    frame_path = str(frame_dir / "first_frame.png")

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        cut.file_path,
        "-vframes",
        "1",
        frame_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"First-frame extraction failed: {result.stderr[:500]}")

    return frame_path


def _run_started(state: CutAIState, run: CutAIRun) -> None:
    run.status = CutAIStatus.RUNNING.value
    run.started_at = utc_now()
    _set_state_status(state, run.analysis_type, CutAIStatus.RUNNING.value)


def _run_error(state: CutAIState, run: CutAIRun, error_message: str) -> None:
    run.status = CutAIStatus.ERROR.value
    run.error_message = error_message
    run.completed_at = utc_now()
    _set_state_status(state, run.analysis_type, CutAIStatus.ERROR.value)
    state.last_error_message = error_message


def execute_clip_overview_run(
    db: Session,
    cut: Cut,
    state: CutAIState,
    run: CutAIRun,
) -> None:
    _run_started(state, run)
    db.commit()

    client = build_qwen_vl_client(db)
    result = asyncio.run(
        client.analyze_video(
            video_path=cut.file_path,
            prompt=run.prompt_text,
            max_tokens=run.max_tokens or CLIP_OVERVIEW_PROFILE.max_tokens,
            temperature=run.temperature or CLIP_OVERVIEW_PROFILE.temperature,
            top_p=CLIP_OVERVIEW_PROFILE.top_p,
        )
    )

    run.status = CutAIStatus.COMPLETED.value
    run.response_text = result.content
    run.model_name = result.model
    run.prompt_tokens = result.prompt_tokens
    run.completion_tokens = result.completion_tokens
    run.completed_at = utc_now()

    state.clip_overview_text = result.content
    state.clip_overview_run_id = run.id
    state.clip_overview_status = CutAIStatus.COMPLETED.value
    state.last_error_message = None
    db.commit()


def execute_first_frame_run(
    db: Session,
    cut: Cut,
    state: CutAIState,
    run: CutAIRun,
) -> None:
    _run_started(state, run)
    db.commit()

    frame_path = _extract_first_frame(cut)
    state.first_frame_path = frame_path
    db.commit()

    client = build_qwen_vl_client(db)
    result = asyncio.run(
        client.analyze_image(
            image_path=frame_path,
            prompt=run.prompt_text,
            max_tokens=run.max_tokens or FIRST_FRAME_PROFILE.max_tokens,
            temperature=run.temperature or FIRST_FRAME_PROFILE.temperature,
            top_p=FIRST_FRAME_PROFILE.top_p,
        )
    )

    run.status = CutAIStatus.COMPLETED.value
    run.response_text = result.content
    run.model_name = result.model
    run.prompt_tokens = result.prompt_tokens
    run.completion_tokens = result.completion_tokens
    run.completed_at = utc_now()

    state.first_frame_description_text = result.content
    state.first_frame_run_id = run.id
    state.first_frame_status = CutAIStatus.COMPLETED.value
    state.last_error_message = None
    db.commit()


def execute_flux_prompt_run(
    *,
    db: Session,
    cut: Cut,
    state: CutAIState,
    style: str,
    content: str,
) -> tuple[CutAIRun, PromptDraft]:
    profile = FLUX_STYLE_CONTENT_PROFILE
    prompt_text = build_flux_style_content_prompt(
        style=style,
        content=content,
        clip_overview=state.clip_overview_text,
        first_frame_description=state.first_frame_description_text,
    )

    run = create_ai_run(
        db=db,
        cut_id=cut.id,
        analysis_type=ANALYSIS_FLUX_PROMPT,
        prompt_key=profile.key,
        prompt_input={
            "style": style,
            "content": content,
            "clip_overview": bool(state.clip_overview_text),
            "first_frame_description": bool(state.first_frame_description_text),
        },
        prompt_text=prompt_text,
        temperature=profile.temperature,
        max_tokens=profile.max_tokens,
        model_name=build_qwen_vl_client(db).model,
    )
    run.status = CutAIStatus.RUNNING.value
    run.started_at = utc_now()
    db.commit()

    try:
        client = build_qwen_vl_client(db)
        result = asyncio.run(
            client.generate_text(
                prompt=prompt_text,
                max_tokens=profile.max_tokens,
                temperature=profile.temperature,
                top_p=profile.top_p,
            )
        )
        run.status = CutAIStatus.COMPLETED.value
        run.response_text = result.content.strip()
        run.model_name = result.model
        run.prompt_tokens = result.prompt_tokens
        run.completion_tokens = result.completion_tokens
        run.completed_at = utc_now()

        draft = PromptDraft(
            cut_id=cut.id,
            draft_type=ANALYSIS_FLUX_PROMPT,
            input_payload={"style": style, "content": content},
            prompt_key=profile.key,
            prompt_text=run.response_text,
            source_run_id=run.id,
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)
        return run, draft
    except Exception as exc:
        db.rollback()
        run = db.query(CutAIRun).filter(CutAIRun.id == run.id).first()
        if run:
            run.status = CutAIStatus.ERROR.value
            run.error_message = str(exc)[:1000]
            run.completed_at = utc_now()
            db.commit()
        raise


def mark_run_error(
    db: Session,
    state: CutAIState,
    run: CutAIRun,
    exc: Exception,
) -> None:
    db.rollback()
    state = db.query(CutAIState).filter(CutAIState.id == state.id).first()
    run = db.query(CutAIRun).filter(CutAIRun.id == run.id).first()
    if not state or not run:
        logger.error("Unable to mark failed run; state/run missing")
        return

    message = str(exc)[:1000]
    _run_error(state, run, message)
    db.commit()


def ensure_content_input(content: str | None, state: CutAIState) -> str:
    if content and content.strip():
        return content.strip()

    candidates = [
        state.first_frame_description_text,
        state.clip_overview_text,
    ]
    for value in candidates:
        if value and value.strip():
            return value.strip()
    return ""
