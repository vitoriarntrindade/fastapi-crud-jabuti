.PHONY: env build up down restart logs test lint fmt migrate shell

env:
	cp .env.example .env

build:
	docker compose build --no-cache

up:
	docker compose up -d

build-up:
	docker compose up --build -d

down:
	docker compose down

restart:
	docker compose restart app

logs:
	docker compose logs -f app

test:
	.venv/bin/python -m pytest tests/ -v

lint:
	.venv/bin/ruff check app tests

fmt:
	.venv/bin/ruff format app tests

migrate:
	docker compose exec app alembic upgrade head

shell:
	docker compose exec app bash
