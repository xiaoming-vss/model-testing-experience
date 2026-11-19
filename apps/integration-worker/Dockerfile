# Base images are pinned by digest for reproducible builds.
# Refresh deliberately with `docker buildx imagetools inspect <image:tag>`.
FROM ghcr.io/astral-sh/uv:0.11.28@sha256:0f36cb9361a3346885ca3677e3767016687b5a170c1a6b88465ec14aefec90aa AS uv
FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS builder
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
COPY --from=uv /uv /bin/uv
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS runtime
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home app
WORKDIR /app
ENV APP_CONF=/app/config/local.toml PATH=/app/.venv/bin:${PATH} PYTHONUNBUFFERED=1
COPY --from=builder --chown=app:app /app/.venv /app/.venv
RUN mkdir -p /app/config /app/runtime && chown -R app:app /app
USER app
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["mtx-integration-worker", "--healthcheck"]
STOPSIGNAL SIGTERM
CMD ["mtx-integration-worker", "--config", "/app/config/local.toml"]
