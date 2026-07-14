# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.11.20 AS uv-bin

FROM python:3.12.11-slim-bookworm AS builder
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /build
COPY --from=uv-bin /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12.11-slim-bookworm AS runtime
ARG APP_VERSION=0.1.0
LABEL org.opencontainers.image.title="IP Country API" \
      org.opencontainers.image.version="${APP_VERSION}"
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_VERSION="${APP_VERSION}" \
    HOME=/tmp
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app
WORKDIR /app
COPY --from=builder --chown=10001:10001 /build/.venv .venv
COPY --chown=10001:10001 alembic.ini ./
COPY --chown=10001:10001 migrations migrations
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "ip_country_api.run"]
