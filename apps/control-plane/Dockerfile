# syntax=docker/dockerfile:1

# Base images are pinned by digest for reproducible builds.
# Refresh deliberately with `docker buildx imagetools inspect <image:tag>`.
FROM ghcr.io/astral-sh/uv:0.11.28@sha256:0f36cb9361a3346885ca3677e3767016687b5a170c1a6b88465ec14aefec90aa AS uv

FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev --no-editable


FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS runtime

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app

WORKDIR /app

ENV APP_CONF=/app/config/local.toml \
    PATH=/app/.venv/bin:${PATH} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app docker/entrypoint.sh ./docker-entrypoint.sh
COPY --chown=app:app default-skills ./default-skills

RUN mkdir -p /app/config /app/storage/ai-generate-task-sources /app/storage/skills \
    && chmod 755 /app/docker-entrypoint.sh \
    && chown -R app:app /app

USER app

EXPOSE 9000
VOLUME ["/app/storage"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9000/v1/health', timeout=3)"]

STOPSIGNAL SIGTERM

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["mtx-control-plane", "--config", "/app/config/local.toml"]
