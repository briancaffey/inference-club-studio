.PHONY: build up down logs shell test lint format migrate migration restart

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f

logs-api:
	docker compose logs -f api

logs-worker:
	docker compose logs -f celery-worker

logs-dia-worker:
	docker compose logs -f celery-dia-worker

logs-migrate:
	docker compose logs migrate

shell:
	docker compose exec api bash

test:
	docker compose run --rm api uv run pytest -v

lint:
	docker compose run --rm api sh -c "uv run black --check app tests && uv run isort --check app tests && uv run flake8 app tests"

format:
	docker compose run --rm api sh -c "uv run black app tests && uv run isort app tests"

migrate:
	docker compose run --rm migrate

migration:
	@read -p "Migration message: " msg; \
	docker compose run --rm api uv run alembic revision --autogenerate -m "$$msg"
