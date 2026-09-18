FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-cache

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

COPY --from=builder /app/.venv /app/.venv
COPY app ./app
COPY main.py ./main.py
COPY config/zentao.example.toml ./config/zentao.toml

# Supply container defaults; mount a custom TOML file to override them.
RUN sed -i 's/app_env = "local"/app_env = "production"/; s/host = "127.0.0.1"/host = "0.0.0.0"/' config/zentao.toml

USER app
EXPOSE 8010

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "from urllib.request import urlopen; from app.config import get_settings; s = get_settings(); urlopen(f'http://127.0.0.1:{s.port}{s.api_v1_prefix}/health/live', timeout=3).close()"

CMD ["python", "main.py"]
