# ── Backend API + scheduler ──────────────────────────────────────────────
FROM python:3.12-slim AS backend

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml MANIFEST.in README.md README_EN.md LICENSE.txt ./
COPY src ./src

# Override with --build-arg when the default index is slow or unreachable.
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# Kept plain on purpose: `RUN --mount=type=cache` (the usual way to cache
# downloaded wheels across builds) needs the docker/dockerfile frontend
# image pulled from Docker Hub, which fails on some networks. Set
# DOCKER_BUILDKIT=1 with the frontend mirrored in a reachable registry if
# you want that cache back.
RUN pip install --index-url "$PIP_INDEX_URL" \
        ".[web,sqlalchemy,redis,mongodb]"

# Runtime data (SQLite databases) lives in a mounted volume.
VOLUME /app/data

EXPOSE 8000
CMD ["schedflow-backend", "--host", "0.0.0.0", "--port", "8000"]

# ── Web dashboard build ──────────────────────────────────────────────────
FROM node:22-alpine AS web-build

WORKDIR /app/frontend

# Override with --build-arg when the default registry is slow or unreachable.
ARG NPM_REGISTRY=https://registry.npmmirror.com
ENV npm_config_registry=$NPM_REGISTRY

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
