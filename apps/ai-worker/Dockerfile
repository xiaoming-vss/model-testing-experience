# syntax=docker/dockerfile:1.7

FROM node:24-bookworm-slim AS pi-builder

WORKDIR /opt/pi

COPY package.json package-lock.json ./
RUN npm ci --omit=dev


FROM python:3.13-slim-bookworm AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    NANOBOT_SKIP_WEBUI_BUILD=1

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable


FROM python:3.13-slim-bookworm AS runtime

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TESTING_AGENT_NANOBOT_RUNTIME_ROOT=/data/runtime \
    TESTING_AGENT_PI_RUNTIME_ROOT=/data/runtime \
    PI_OFFLINE=1 \
    PI_TELEMETRY=0

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 worker \
    && useradd --system --uid 10001 --gid worker --home-dir /app worker \
    && mkdir -p /app/logs /data/runtime \
    && chown -R worker:worker /app /data/runtime

# Both execution backends ship in one image; `agent.backend` selects at runtime.
COPY --from=pi-builder /usr/local/bin/node /usr/local/bin/node
COPY --from=pi-builder /opt/pi/node_modules /opt/pi/node_modules
RUN ln -s /opt/pi/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js \
    /usr/local/bin/pi

WORKDIR /app

COPY --from=builder --chown=worker:worker /app/.venv /app/.venv
COPY --chown=worker:worker config ./config
COPY --chown=worker:worker config/worker.example.toml ./config/worker.toml

USER 10001:10001

EXPOSE 8080

STOPSIGNAL SIGTERM

CMD ["mtx-ai-worker"]
