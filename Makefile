.PHONY: env build up down restart logs test lint fmt migrate shell init doctor bootstrap

init: env build-up

doctor:
	bash ./scripts/docker-doctor.sh

bootstrap:
	bash ./scripts/docker-doctor.sh && docker compose up --build

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
