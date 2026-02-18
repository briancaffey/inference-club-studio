import logging
import uuid

from app.celery_app import celery
from app.database import SessionLocal
from app.models.cut import Cut, CutStatus
from app.models.cut_ai import CutAIRun, CutAIState
from app.services.cut_ai import (
    ANALYSIS_CLIP_OVERVIEW,
    ANALYSIS_FIRST_FRAME,
    execute_clip_overview_run,
    execute_first_frame_run,
    get_or_create_ai_state,
    mark_run_error,
    queue_runs_for_cut,
)

logger = logging.getLogger(__name__)


def _get_cut(db, cut_id: str) -> Cut | None:
    try:
        parsed = uuid.UUID(cut_id)
    except ValueError:
        return None
    return db.query(Cut).filter(Cut.id == parsed).first()


def _get_run(db, run_id: str) -> CutAIRun | None:
    try:
        parsed = uuid.UUID(run_id)
    except ValueError:
        return None
    return db.query(CutAIRun).filter(CutAIRun.id == parsed).first()


@celery.task(bind=True, max_retries=0)
def queue_cut_ai_analysis(self, cut_id: str, force: bool = False):
    db = SessionLocal()
    try:
        cut = _get_cut(db, cut_id)
        if not cut:
            logger.error("Cut %s not found for AI queue", cut_id)
            return

        if cut.status != CutStatus.READY.value:
            logger.info("Cut %s not ready; skipping AI queue", cut_id)
            return

        runs = queue_runs_for_cut(db=db, cut=cut, force=force)
        db.commit()

        for run in runs:
            if run.analysis_type == ANALYSIS_CLIP_OVERVIEW:
                generate_clip_overview.delay(cut_id, str(run.id))
            elif run.analysis_type == ANALYSIS_FIRST_FRAME:
                generate_first_frame_description.delay(cut_id, str(run.id))

        logger.info("Queued %d AI runs for cut %s", len(runs), cut_id)
    except Exception:
        logger.exception("Failed to queue AI runs for cut %s", cut_id)
        db.rollback()
    finally:
        db.close()


@celery.task(bind=True, max_retries=0)
def generate_clip_overview(self, cut_id: str, run_id: str):
    db = SessionLocal()
    try:
        cut = _get_cut(db, cut_id)
        run = _get_run(db, run_id)
        if not cut or not run:
            logger.error(
                "Missing cut/run for clip overview: cut=%s run=%s",
                cut_id,
                run_id,
            )
            return
        state = get_or_create_ai_state(db, cut.id)
        execute_clip_overview_run(db, cut, state, run)
        logger.info("Completed clip overview run %s for cut %s", run_id, cut_id)
    except Exception as exc:
        logger.exception("Clip overview run failed %s for cut %s", run_id, cut_id)
        cut = _get_cut(db, cut_id)
        state = (
            db.query(CutAIState).filter(CutAIState.cut_id == cut.id).first()
            if cut
            else None
        )
        run = _get_run(db, run_id)
        if state and run:
            mark_run_error(db, state, run, exc)
    finally:
        db.close()


@celery.task(bind=True, max_retries=0)
def generate_first_frame_description(self, cut_id: str, run_id: str):
    db = SessionLocal()
    try:
        cut = _get_cut(db, cut_id)
        run = _get_run(db, run_id)
        if not cut or not run:
            logger.error(
                "Missing cut/run for first-frame: cut=%s run=%s",
                cut_id,
                run_id,
            )
            return
        state = get_or_create_ai_state(db, cut.id)
        execute_first_frame_run(db, cut, state, run)
        logger.info("Completed first-frame run %s for cut %s", run_id, cut_id)
    except Exception as exc:
        logger.exception("First-frame run failed %s for cut %s", run_id, cut_id)
        cut = _get_cut(db, cut_id)
        state = (
            db.query(CutAIState).filter(CutAIState.cut_id == cut.id).first()
            if cut
            else None
        )
        run = _get_run(db, run_id)
        if state and run:
            mark_run_error(db, state, run, exc)
    finally:
        db.close()
