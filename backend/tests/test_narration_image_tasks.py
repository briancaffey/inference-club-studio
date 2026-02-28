from app.clients.invokeai.client import GeneratedImage, InvokeAIClient
from app.models.narration import NarrationSegment
from app.models.narration_image import (
    NarrationImageFrame,
    NarrationImageFrameStatus,
    NarrationImageGenerationMode,
    NarrationImageSeries,
    NarrationImageSeriesStatus,
)
from app.models.project import Project
from app.tasks import narration_images as narration_image_tasks


def _make_segment(db) -> NarrationSegment:
    project = Project(name="Narration Image Task", project_type="narration")
    db.add(project)
    db.commit()
    db.refresh(project)

    segment = NarrationSegment(
        project_id=project.id,
        position=1,
        text="A man sitting on a bench.",
        sanitized_text="A man sitting on a bench.",
        service="dia",
        status="done",
    )
    db.add(segment)
    db.commit()
    db.refresh(segment)
    return segment


def test_generate_narration_image_series_sequential(db, monkeypatch, tmp_path):
    segment = _make_segment(db)
    series = NarrationImageSeries(
        segment_id=segment.id,
        status=NarrationImageSeriesStatus.QUEUED.value,
    )
    db.add(series)
    db.flush()

    root = NarrationImageFrame(
        series_id=series.id,
        prompt="A man sitting on a bench, wide shot.",
        mode=NarrationImageGenerationMode.TEXT_TO_IMAGE.value,
        status=NarrationImageFrameStatus.PENDING.value,
        step_order=1,
    )
    db.add(root)
    db.flush()
    child = NarrationImageFrame(
        series_id=series.id,
        parent_frame_id=root.id,
        prompt="The man gives a thumbs up, same framing.",
        mode=NarrationImageGenerationMode.IMAGE_TO_IMAGE.value,
        status=NarrationImageFrameStatus.PENDING.value,
        step_order=2,
    )
    db.add(child)
    db.commit()

    monkeypatch.setattr(narration_image_tasks, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    monkeypatch.setattr(narration_image_tasks.settings, "media_dir", str(tmp_path))
    calls: list[tuple] = []

    async def fake_txt2img(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
        num_steps: int = 16,
        cfg_scale: float = 1.0,
        seed: int = -1,
    ) -> GeneratedImage:
        calls.append(("txt2img", prompt, width, height, num_steps, cfg_scale, seed))
        return GeneratedImage(
            image_name="root_image",
            image_bytes=b"root-bytes",
            width=width,
            height=height,
            seed=123,
        )

    async def fake_img2img(
        self,
        prompt: str,
        ref_image_name: str,
        width: int = 1024,
        height: int = 1024,
        num_steps: int = 16,
        cfg_scale: float = 1.0,
        seed: int = -1,
    ) -> GeneratedImage:
        calls.append(
            (
                "img2img",
                prompt,
                ref_image_name,
                width,
                height,
                num_steps,
                cfg_scale,
                seed,
            )
        )
        return GeneratedImage(
            image_name="child_image",
            image_bytes=b"child-bytes",
            width=width,
            height=height,
            seed=456,
        )

    monkeypatch.setattr(InvokeAIClient, "generate_text_to_image", fake_txt2img)
    monkeypatch.setattr(InvokeAIClient, "generate_with_reference", fake_img2img)

    narration_image_tasks.generate_narration_image_series(str(series.id))

    db.refresh(series)
    db.refresh(root)
    db.refresh(child)

    assert series.status == NarrationImageSeriesStatus.COMPLETED.value
    assert root.status == NarrationImageFrameStatus.COMPLETED.value
    assert root.invokeai_generated_image_name == "root_image"
    assert root.output_image_path is not None
    assert child.status == NarrationImageFrameStatus.COMPLETED.value
    assert child.invokeai_reference_image_name == "root_image"
    assert child.invokeai_generated_image_name == "child_image"
    assert child.output_image_path is not None
    assert calls[0][0] == "txt2img"
    assert calls[1][0] == "img2img"
    assert calls[1][2] == "root_image"


def test_generate_narration_image_series_marks_error_when_reference_missing(
    db, monkeypatch
):
    segment = _make_segment(db)
    series = NarrationImageSeries(
        segment_id=segment.id,
        status=NarrationImageSeriesStatus.QUEUED.value,
    )
    db.add(series)
    db.flush()
    frame = NarrationImageFrame(
        series_id=series.id,
        prompt="A variant requiring reference",
        mode=NarrationImageGenerationMode.IMAGE_TO_IMAGE.value,
        status=NarrationImageFrameStatus.PENDING.value,
        step_order=1,
    )
    db.add(frame)
    db.commit()

    monkeypatch.setattr(narration_image_tasks, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    monkeypatch.setattr(narration_image_tasks.settings, "media_dir", "/tmp")
    narration_image_tasks.generate_narration_image_series(str(series.id))

    db.refresh(series)
    db.refresh(frame)
    assert series.status == NarrationImageSeriesStatus.ERROR.value
    assert frame.status == NarrationImageFrameStatus.ERROR.value
    assert "requires a parent frame or reference" in (frame.error_message or "")
