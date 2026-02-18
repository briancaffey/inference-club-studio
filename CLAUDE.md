# Inference Club Studio

## Project Structure
- `frontend/` — Nuxt 4 app (see `frontend/CLAUDE.md`)
- `backend/` — FastAPI + Celery (see `backend/CLAUDE.md`)
- `media/` — Shared media file storage (mounted into containers)
- `docker-compose.yml` — All services (api, celery-worker, migrate, postgres, redis, flower)

## Critical Rules

### Backend Development
- **NEVER** run `python`, `python3`, `pip`, or `uv` commands directly on the host
- **ALWAYS** use `docker compose run --rm api ...` for one-off commands
- **ALWAYS** use `docker compose exec api ...` for commands in a running container
- Use `make` targets when available (see `Makefile`)
- All backend tests, linting, and formatting run through Docker Compose
- **NEVER** use `print()` — always use the `logging` module
- Migrations run automatically on `docker compose up` via the `migrate` service

### Common Commands
```bash
make build          # Build all containers
make up             # Start all services (runs migrations automatically)
make down           # Stop all services
make test           # Run backend tests
make lint           # Run black, isort, flake8 checks
make format         # Auto-format backend code
make shell          # Open bash in the api container
make migrate        # Run migrations manually
make migration      # Create a new migration
make logs           # Tail all service logs
```

### Testing
- Use **functions**, not classes, for all pytest tests
- Tests live in `backend/tests/`
- Run with `make test`
