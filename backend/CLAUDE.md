# Backend — FastAPI + Celery

## Stack
- **FastAPI** web framework with OpenAPI docs at `/docs` and `/redoc`
- **Celery** with Redis broker for async tasks
- **SQLAlchemy** ORM + **Alembic** migrations (auto-run on startup)
- **PostgreSQL 17** database
- **Redis 7** for Celery broker/backend
- **Flower** for Celery monitoring at `http://localhost:5555`
- **uv** for dependency management (`pyproject.toml`)

## Directory Structure
```
app/
  main.py          # FastAPI entrypoint, mounts routers and static files
  config.py        # pydantic-settings config (env-driven)
  celery_app.py    # Celery app configuration
  db/
    migrate.py     # Migration runner (used by docker compose migrate service)
  routes/          # FastAPI routers (health.py, etc.)
  tasks/           # Celery tasks
  clients/         # External service clients
  utils/           # Helpers (media.py, etc.)
  models/          # SQLAlchemy models
  schemas/         # Pydantic request/response schemas
alembic/
  env.py           # Reads DATABASE_URL from env, imports models for autogenerate
  versions/        # Migration files
tests/
  conftest.py      # Shared fixtures
  test_*.py        # Test files (function-based, no classes)
```

## Conventions
- API routes prefixed with `/api/v1`
- Config via environment variables (see `app/config.py`)
- Media files stored at `/app/media` inside containers, bind-mounted from `./media`
- Use `ffmpeg-python` and `pydub` for media processing
- Use `openai` and `llama-index` for AI/LLM workflows
- **NEVER** use `print()` — always use `logging` module
- Global exception handler returns `{"detail": "Internal server error"}` for unhandled exceptions

## Dependencies
- Add runtime deps to `[project.dependencies]` in `pyproject.toml`
- Add dev deps to `[dependency-groups.dev]`
- After changing deps: `make build` to rebuild the container

## Dev Commands (all via Docker Compose)
```bash
make test           # pytest -v
make lint           # black --check, isort --check, flake8
make format         # black + isort auto-format
make shell          # bash in api container
make migrate        # alembic upgrade head (also runs automatically on startup)
make migration      # alembic revision --autogenerate
```
