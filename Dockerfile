# ── Backend API + scheduler ──────────────────────────────────────────────
FROM python:3.12-slim AS backend

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml MANIFEST.in README.md README_EN.md LICENSE.txt ./
COPY .env.example /app/.env.example
COPY src ./src
RUN pip install --upgrade pip && \
    pip install ".[web,sqlalchemy,redis,mongodb]"

# Runtime data (SQLite databases) lives in a mounted volume.
VOLUME /app/data

EXPOSE 8000
CMD ["schedflow-backend", "--host", "0.0.0.0", "--port", "8000"]

# ── Web dashboard build ──────────────────────────────────────────────────
FROM node:22-alpine AS web-build

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/index.html frontend/vite.config.ts frontend/env.d.ts frontend/tsconfig*.json ./
COPY frontend/src ./src
COPY frontend/scripts ./scripts

RUN npm run build-only

# ── Web dashboard (static + /api reverse proxy) ──────────────────────────
FROM nginx:alpine AS web

# The /api origin; compose sets it to http://api:8000. The official image
# renders /etc/nginx/templates/*.template through envsubst at start-up.
ENV SCHEDFLOW_API_URL=http://api:8000
COPY frontend/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=web-build /app/frontend/dist /usr/share/nginx/html

EXPOSE 80
