# Keep this version aligned with the playwright version locked in uv.lock.
FROM mcr.microsoft.com/playwright/python:v1.60.0-noble

ARG UV_VERSION=0.11.28

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    UV_NO_CACHE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

RUN python -m pip install --no-cache-dir "uv==${UV_VERSION}"

# Install locked third-party dependencies before copying application sources.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev --no-editable \
    && python -c "from importlib.metadata import version; assert version('playwright') == '1.60.0'"

RUN mkdir -p /app/artifacts

VOLUME ["/app/artifacts"]
EXPOSE 9010

# The official Playwright image runs trusted end-to-end tests as root so
# Chromium can launch without a custom seccomp profile. Harden the runtime
# separately when executing tests against untrusted sites.
CMD ["testing-agent-api-ui-worker"]
