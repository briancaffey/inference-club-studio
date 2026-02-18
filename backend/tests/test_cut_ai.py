from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

from app.models.cut import Cut, CutStatus
from app.models.cut_ai import CutAIRun, CutAIStatus, PromptDraft
from app.models.project import Project
from app.services.cut_ai import ANALYSIS_CLIP_OVERVIEW, ANALYSIS_FIRST_FRAME


def _make_project(db, name="AI Project"):
    project = Project(name=name)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _make_cut(db, project, filename="cut_01.mp4"):
    cut = Cut(
        project_id=project.id,
        order=0,
        original_filename=filename,
        file_path=f"/app/media/{project.id}/cuts/{filename}",
        file_size=1024,
        status=CutStatus.READY.value,
    )
    db.add(cut)
    db.commit()
    db.refresh(cut)
    return cut


def test_get_cut_ai_state_initializes_row(client, db):
    project = _make_project(db)
    cut = _make_cut(db, project)

    resp = client.get(f"/api/v1/projects/{project.id}/cuts/{cut.id}/ai")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cut_id"] == str(cut.id)
    assert data["clip_overview_status"] == "pending"
    assert data["first_frame_status"] == "pending"
    assert data["clip_overview_text"] is None
    assert data["first_frame_description_text"] is None


@patch("app.routes.cut_ai.generate_first_frame_description")
@patch("app.routes.cut_ai.generate_clip_overview")
def test_regenerate_queues_runs(mock_clip_task, mock_frame_task, client, db):
    project = _make_project(db)
    cut = _make_cut(db, project)

    resp = client.post(
        f"/api/v1/projects/{project.id}/cuts/{cut.id}/ai/regenerate",
        json={"types": [ANALYSIS_CLIP_OVERVIEW, ANALYSIS_FIRST_FRAME]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["clip_overview_status"] == CutAIStatus.QUEUED.value
    assert data["first_frame_status"] == CutAIStatus.QUEUED.value

    assert mock_clip_task.delay.call_count == 1
    assert mock_frame_task.delay.call_count == 1


def test_create_flux_prompt_requires_content_when_no_ai_descriptions(client, db):
    project = _make_project(db)
    cut = _make_cut(db, project)

    resp = client.post(
        f"/api/v1/projects/{project.id}/cuts/{cut.id}/ai/prompt-drafts/flux",
        json={"style": "retro film grain"},
    )
    assert resp.status_code == 400
    assert "No content provided" in resp.json()["detail"]


@patch("app.routes.cut_ai.execute_flux_prompt_run")
def test_create_flux_prompt_draft(mock_execute, client, db):
    project = _make_project(db)
    cut = _make_cut(db, project)

    now = datetime.now(timezone.utc)
    run = CutAIRun(
        id=uuid4(),
        cut_id=cut.id,
        analysis_type="flux_style_content_prompt",
        status="completed",
        prompt_key="flux_style_content_prompt_v1",
        prompt_input={"style": "anime", "content": "person on street"},
        prompt_text="input prompt",
        response_text="final flux prompt",
        model_name="Qwen/Qwen3-VL-4B-Instruct",
        prompt_tokens=123,
        completion_tokens=88,
        temperature=0.4,
        max_tokens=500,
        created_at=now,
        started_at=now,
        completed_at=now,
        updated_at=now,
    )
    draft = PromptDraft(
        id=uuid4(),
        cut_id=cut.id,
        draft_type="flux_style_content_prompt",
        input_payload={"style": "anime", "content": "person on street"},
        prompt_key="flux_style_content_prompt_v1",
        prompt_text="final flux prompt",
        source_run_id=run.id,
        created_at=now,
    )
    mock_execute.return_value = (run, draft)

    resp = client.post(
        f"/api/v1/projects/{project.id}/cuts/{cut.id}/ai/prompt-drafts/flux",
        json={"style": "anime", "content": "person on street"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["prompt_text"] == "final flux prompt"
    assert data["run"]["analysis_type"] == "flux_style_content_prompt"
