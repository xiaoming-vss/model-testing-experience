ARG PYTHON_VERSION=3.12
ARG UV_VERSION=0.11.28
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
COPY --from=uv /uv /bin/uv
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime
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
