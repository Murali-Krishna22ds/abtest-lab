# syntax=docker/dockerfile:1
# --- stage 1: build the React app
FROM node:22-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- stage 2: API + static front end in one container
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 ABLAB_WARMUP_PYMC=true
# g++ lets PyTensor compile PyMC models to C (about 10x faster sampling than the Python fallback)
RUN apt-get update && apt-get install -y --no-install-recommends g++ curl && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home app
WORKDIR /srv
COPY backend/requirements.txt backend/requirements.lock.txt backend/
RUN pip install -r backend/requirements.lock.txt
COPY backend/ backend/
COPY data/ data/
COPY --from=ui /ui/dist frontend/dist
RUN mkdir -p /home/app/.pytensor && chown -R app /home/app
USER app
WORKDIR /srv/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD curl -fs http://localhost:8000/api/health || exit 1
# One worker on purpose: uploaded datasets live in process memory (see docs/ARCHITECTURE.md, "Scaling").
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
