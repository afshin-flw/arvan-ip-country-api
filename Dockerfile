# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.11.20 AS uv-bin

FROM python:3.12.11-slim-bookworm AS builder
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
WORKDIR /build
COPY --from=uv-bin /uv /usr/local/bin/uv
COPY app/pyproject.toml app/uv.lock app/README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app/src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12.11-slim-bookworm AS runtime
ARG APP_VERSION=0.1.0
LABEL org.opencontainers.image.title="IP Country API" \
      org.opencontainers.image.version="${APP_VERSION}"
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_VERSION="${APP_VERSION}" \
    APP_HOST=0.0.0.0 \
    APP_PORT=8080 \
    HOME=/tmp
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app
WORKDIR /app
COPY --from=builder --chown=10001:10001 /opt/venv /opt/venv
COPY --chown=10001:10001 app/alembic.ini ./
COPY --chown=10001:10001 app/migrations migrations
USER 10001:10001
EXPOSE 8080
CMD ["python", "-m", "ip_country_api.run"]
