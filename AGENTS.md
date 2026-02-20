# AGENTS.md

## Scope
These rules apply to backend/Python commands in this repository.

## Core Rules
- Never run backend tooling directly on the host (`python`, `python3`, `pip`, `uv`, `pytest`, `alembic`, etc.).
- Run backend/Python commands from repo root: `/Users/brian/git/inference-club-studio`.
- Prefer `make` targets first when available.

## Preferred `make` Targets
- `make up`, `make down`, `make restart`
- `make logs`, `make logs-api`, `make logs-worker`, `make logs-migrate`
- `make shell`
- `make test`, `make lint`, `make format`
- `make migrate`, `make migration`

## Docker Compose Fallback (when no `make` target fits)
- Use the `api` service.
- Default for one-off/non-interactive commands: `docker compose run --rm api ...`
- Use `docker compose exec api ...` for interactive or repeated commands when `api` is already running.
- If `exec` fails because `api` is not running, switch to `run --rm`.
