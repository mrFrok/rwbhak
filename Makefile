PY ?= .venv/bin/python
PIP ?= .venv/bin/pip

.PHONY: help install up down logs seed reset-demo test report dev-api dev-ui build-ui

help:
	@echo "make install   — создать venv и поставить Python-зависимости"
	@echo "make up        — docker compose up --build (db + api + ui)"
	@echo "make seed      — заполнить пустую БД в контейнере api"
	@echo "make reset-demo — удалить данные демо и начать заново"
	@echo "make test      — pytest (ядро + API)"
	@echo "make report    — пересчитать модель и reports/model_report.md"
	@echo "make dev-api   — API на localhost:8000 с автоперезагрузкой"
	@echo "make dev-ui    — Vite на localhost:5173"
	@echo "make build-ui  — production-сборка интерфейса"

install:
	python3 -m venv .venv
	$(PIP) install -q -r requirements-dev.txt
	cd ui && npm ci

up:
	docker compose up --build -d
	@echo "UI: http://$$(docker compose port ui 80) · API: http://localhost:8000/docs"

down:
	docker compose down

logs:
	docker compose logs -f api

seed:
	docker compose exec api python -m data.seed

reset-demo:
	docker compose exec api python -m data.seed --reset

test:
	$(PY) -m pytest -q

report:
	$(PY) -m scripts.build_report

dev-api:
	$(PY) -m uvicorn api.main:app --reload --port 8000

dev-ui:
	cd ui && npm run dev

build-ui:
	cd ui && npm run build
