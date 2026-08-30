# ── Backend API + scheduler ──────────────────────────────────────────────
FROM python:3.12-slim AS backend

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml MANIFEST.in README.md README_EN.md LICENSE.txt ./
COPY src ./src
RUN pip install --upgrade pip && \
    pip install ".[web,sqlalchemy,redis,mongodb]"

# Runtime data (SQLite databases) lives in a mounted volume.
VOLUME /app/data

EXPOSE 8000
CMD ["schedflow-backend", "--host", "0.0.0.0", "--port", "8000"]

# ── Web dashboard ────────────────────────────────────────────────────────
FROM node:22-alpine AS web

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/index.html frontend/vite.config.ts frontend/env.d.ts frontend/tsconfig*.json ./
COPY frontend/src ./src

# The /api proxy target; compose sets it to http://api:8000.
ENV SCHEDFLOW_API_URL=http://127.0.0.1:8000
RUN npm run build-only

EXPOSE 4173
CMD ["npx", "vite", "preview", "--host", "0.0.0.0", "--port", "4173"]
