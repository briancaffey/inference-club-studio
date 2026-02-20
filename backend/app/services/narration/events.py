"""Redis-backed event + job tracking helpers for narration generation."""

from __future__ import annotations

import json
import logging
import time

import redis
from fastapi.encoders import jsonable_encoder

from app.config import settings

logger = logging.getLogger(__name__)

NARRATION_EVENTS_CHANNEL = "narration:events"
NARRATION_JOB_KEY_PREFIX = "narration:job"
NARRATION_QUEUE_DEPTH_KEY = "narration:queue_depth"
NARRATION_ACTIVE_JOB_KEY = "narration:active_job_id"
NARRATION_JOB_TTL_SECONDS = 3600


def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _job_key(job_id: str) -> str:
    return f"{NARRATION_JOB_KEY_PREFIX}:{job_id}"


def publish_narration_event(event: dict) -> None:
    payload = json.dumps(jsonable_encoder(event), default=str)
    client = _redis_client()
    try:
        client.publish(NARRATION_EVENTS_CHANNEL, payload)
    except Exception:
        logger.exception("Failed publishing narration event")
    finally:
        client.close()


def init_narration_job(job_id: str, total: int) -> None:
    client = _redis_client()
    try:
        key = _job_key(job_id)
        client.hset(
            key,
            mapping={
                "total": max(0, int(total)),
                "completed": 0,
                "generated": 0,
                "failed": 0,
                "skipped": 0,
                "cancelled": 0,
                "updated_at": int(time.time()),
            },
        )
        client.expire(key, NARRATION_JOB_TTL_SECONDS)
    except Exception:
        logger.exception("Failed initializing narration job state for %s", job_id)
    finally:
        client.close()


def mark_narration_job_cancelled(job_id: str) -> None:
    client = _redis_client()
    try:
        key = _job_key(job_id)
        client.hset(key, mapping={"cancelled": 1, "updated_at": int(time.time())})
        client.expire(key, NARRATION_JOB_TTL_SECONDS)
    except Exception:
        logger.exception("Failed marking narration job %s cancelled", job_id)
    finally:
        client.close()


def is_narration_job_cancelled(job_id: str) -> bool:
    client = _redis_client()
    try:
        value = client.hget(_job_key(job_id), "cancelled")
        return str(value or "0") == "1"
    except Exception:
        logger.exception("Failed reading cancelled state for narration job %s", job_id)
        return False
    finally:
        client.close()


def increment_narration_queue_depth(delta: int) -> int:
    if delta == 0:
        return get_narration_queue_depth()

    client = _redis_client()
    try:
        current = client.incrby(NARRATION_QUEUE_DEPTH_KEY, int(delta))
        if current < 0:
            client.set(NARRATION_QUEUE_DEPTH_KEY, 0)
            current = 0
        return int(current)
    except Exception:
        logger.exception("Failed updating narration queue depth by %s", delta)
        return 0
    finally:
        client.close()


def get_narration_queue_depth() -> int:
    client = _redis_client()
    try:
        value = client.get(NARRATION_QUEUE_DEPTH_KEY)
        return max(0, int(value or 0))
    except Exception:
        logger.exception("Failed reading narration queue depth")
        return 0
    finally:
        client.close()


def set_narration_active_job(job_id: str | None) -> None:
    client = _redis_client()
    try:
        if job_id:
            client.set(NARRATION_ACTIVE_JOB_KEY, job_id)
        else:
            client.delete(NARRATION_ACTIVE_JOB_KEY)
    except Exception:
        logger.exception("Failed setting narration active job to %s", job_id)
    finally:
        client.close()


def get_narration_active_job() -> str | None:
    client = _redis_client()
    try:
        value = client.get(NARRATION_ACTIVE_JOB_KEY)
        return str(value) if value else None
    except Exception:
        logger.exception("Failed reading narration active job")
        return None
    finally:
        client.close()


def mark_narration_job_progress(
    job_id: str,
    *,
    generated: bool = False,
    failed: bool = False,
    skipped: bool = False,
) -> dict:
    client = _redis_client()
    key = _job_key(job_id)
    try:
        with client.pipeline() as pipe:
            pipe.hincrby(key, "completed", 1)
            if generated:
                pipe.hincrby(key, "generated", 1)
            if failed:
                pipe.hincrby(key, "failed", 1)
            if skipped:
                pipe.hincrby(key, "skipped", 1)
            pipe.hset(key, mapping={"updated_at": int(time.time())})
            pipe.expire(key, NARRATION_JOB_TTL_SECONDS)
            pipe.hgetall(key)
            result = pipe.execute()
        raw = result[-1] if result else {}
    except Exception:
        logger.exception("Failed updating progress for narration job %s", job_id)
        raw = {}
    finally:
        client.close()

    def _to_int(value: str | None) -> int:
        try:
            return int(value or 0)
        except Exception:
            return 0

    return {
        "job_id": job_id,
        "total": _to_int(raw.get("total")),
        "completed": _to_int(raw.get("completed")),
        "generated": _to_int(raw.get("generated")),
        "failed": _to_int(raw.get("failed")),
        "skipped": _to_int(raw.get("skipped")),
        "cancelled": _to_int(raw.get("cancelled")) == 1,
    }


def clear_narration_job(job_id: str) -> None:
    client = _redis_client()
    try:
        client.delete(_job_key(job_id))
    except Exception:
        logger.exception("Failed clearing narration job state for %s", job_id)
    finally:
        client.close()


def narration_queue_status_payload() -> dict:
    return {
        "type": "queue_status",
        "queue_length": get_narration_queue_depth(),
        "active_job_id": get_narration_active_job(),
    }
