# syntax=docker/dockerfile:1

# --- Stage 1: build the frontend static bundle ---
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json ./
# No package-lock.json here deliberately: npm ci/install against a lockfile generated on
# a different host OS only carries forward that host's platform-specific optional native
# binary (e.g. lightningcss-darwin-arm64), and fails to resolve the linux one this stage
# actually needs. Installing from package.json alone lets npm resolve fresh for whatever
# platform is building this image.
RUN npm install
COPY frontend/ ./
RUN npm run build

# --- Stage 2: install Python dependencies ---
FROM python:3.12-slim AS python-deps
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# --- Stage 3: runtime image ---
FROM python:3.12-slim
WORKDIR /app

RUN groupadd --system specpilot && useradd --system --gid specpilot --create-home specpilot

COPY --from=python-deps /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini pyproject.toml ./
COPY eval/questions.yaml ./eval/questions.yaml
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

RUN mkdir -p /app/eval/reports /app/data && chown -R specpilot:specpilot /app

USER specpilot

EXPOSE 8000

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
