PY ?= .venv/bin/python
.PHONY: install backend frontend dev test test-api test-ui e2e bench openapi docker clean

install:  ## create the virtualenv and install everything
	python3 -m venv .venv
	.venv/bin/pip install -r backend/requirements.lock.txt pytest-cov
	cd frontend && npm ci

backend:  ## run the API on :8000 with auto-reload
	cd backend && ../$(PY) -m uvicorn app.main:app --reload --port 8000

frontend:  ## run the React dev server on :5173 (proxies /api to :8000)
	cd frontend && npm run dev

test: test-api test-ui  ## all unit and API tests

test-api:
	cd backend && ../$(PY) -m pytest --cov=app --cov-report=term-missing

test-ui:
	cd frontend && npm test

e2e:  ## browser tests against a freshly built UI (needs: cd frontend && npx playwright install chromium)
	scripts/e2e.sh docs/screenshots

bench:  ## accuracy and latency benchmarks -> docs/benchmark_results.md
	$(PY) scripts/benchmarks.py

openapi:  ## export the OpenAPI spec -> docs/openapi.json
	$(PY) scripts/export_openapi.py

docker:
	docker compose up --build

clean:
	rm -rf frontend/dist .pytest_cache backend/.pytest_cache
