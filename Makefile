.PHONY: setup dev test test-e2e eval seed lint web-build compose-check clean

setup:
	python -m pip install -e ".[dev]"
	cd apps/web && npm install

dev:
	python -m apps.api.app.seed
	python -m uvicorn apps.api.app.main:app --reload --host 0.0.0.0 --port 8000

test:
	python -m pytest tests/unit tests/integration tests/api

test-e2e:
	cd apps/web && npm run test:e2e

eval:
	python -m tests.evaluation.run_eval

seed:
	python -m apps.api.app.seed

lint:
	python -m ruff check apps services packages tests
	cd apps/web && npm run lint

web-build:
	cd apps/web && npm run build

compose-check:
	docker compose config --quiet

clean:
	python -m apps.api.app.seed --reset
