from app.celery_app import celery


@celery.task
def add(x: int, y: int) -> int:
    """Example task for verifying Celery is working."""
    return x + y
