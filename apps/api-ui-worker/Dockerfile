# Keep this version aligned with the playwright version locked in uv.lock.
# Base images are pinned by digest for reproducible builds; refresh deliberately
# with `docker buildx imagetools inspect <image:tag>`.
FROM mcr.microsoft.com/playwright/python:v1.60.0-noble@sha256:8ff591d613b01c884cc488339ed4318b4513eaf0c57a164a878ba49e70e3f384

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    UV_NO_CACHE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.11.28@sha256:0f36cb9361a3346885ca3677e3767016687b5a170c1a6b88465ec14aefec90aa /uv /uvx /bin/

# Install locked third-party dependencies before copying application sources.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev --no-editable \
    && python -c "from importlib.metadata import version; assert version('playwright') == '1.60.0'"

RUN mkdir -p /app/artifacts

VOLUME ["/app/artifacts"]
EXPOSE 8080

# The official Playwright image runs trusted end-to-end tests as root so
# Chromium can launch without a custom seccomp profile. Harden the runtime
# separately when executing tests against untrusted sites.
CMD ["mtx-api-ui-worker"]
