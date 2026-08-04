.PHONY: db-up ingest dev test check

db-up:
	@docker start specpilot-db >/dev/null 2>&1 || docker run -d --name specpilot-db \
		-e POSTGRES_PASSWORD=specpilot \
		-e POSTGRES_DB=specpilot \
		-p 5432:5432 \
		pgvector/pgvector:pg16 >/dev/null
	@echo "Waiting for Postgres..."
	@until docker exec specpilot-db pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done
	@uv run alembic upgrade head
	@echo "OK db-up"

ingest:
	@uv run specpilot ingest --all

dev:
	@uv run uvicorn src.api.app:app --reload --port 8000

test:
	@uv run pytest -q

check:
	@uv run ruff check src tests && echo "OK ruff" || (echo "FAIL ruff" && exit 1)
	@uv run pytest -q --cov=src --cov-report=term-missing --cov-fail-under=80 \
		&& echo "OK pytest (coverage above 80%)" || (echo "FAIL pytest or coverage below 80%" && exit 1)
	@cd frontend && npm run lint && npm test && npm run build \
		&& echo "OK frontend" || (echo "FAIL frontend lint, tests, or build" && exit 1)
	@./scripts/smoke.sh
