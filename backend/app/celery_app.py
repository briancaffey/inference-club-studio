from celery import Celery

from app.config import settings

celery = Celery(
    "inference_club",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_routes={
        "app.tasks.narration.generate_narration_segment_task": {"queue": "dia"},
        "app.tasks.narration.clean_project_studio_voice_task": {"queue": "dia"},
        "app.tasks.narration_images.generate_narration_image_series": {
            "queue": "image-sequences"
        },
    },
)

celery.autodiscover_tasks(["app.tasks"])
