# Multi-stage build optimised for image size.
#
# Builder: official uv Alpine image (uv + Python 3.12, musl libc).
# Runtime: python:3.12-alpine (~50MB vs ~140MB for slim-bookworm).
#
# Deps in use today (fastapi / starlette / pydantic / uvicorn[standard]'s
# uvloop+httptools+watchfiles+websockets) all publish musl wheels on PyPI,
# so no source-builds happen at install time.

FROM ghcr.io/astral-sh/uv:python3.12-alpine AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_NO_CACHE=1

WORKDIR /app

# Resolve + install deps from the lockfile before copying source so source-
# only changes don't bust the dependency layer cache.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Install the project itself.
COPY README.md LICENSE ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev


FROM python:3.12-alpine AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    KNO_HOST=0.0.0.0 \
    KNO_PORT=8080

# Non-root user for defense-in-depth (image is public). Create BEFORE COPY so
# `--chown` doesn't double the layer size with a separate `chown -R` step.
RUN adduser -D -u 10001 kno

WORKDIR /app

COPY --from=builder --chown=kno:kno /app /app

USER kno

EXPOSE 8080

# Local docker healthcheck — pairs with Fly's http_service.checks for prod.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/api/health || exit 1

# uvicorn finalizes cleaner on SIGINT than SIGTERM; explicit STOPSIGNAL.
STOPSIGNAL SIGINT

# Skip the `kno serve` CLI shim — one fewer process at PID 1.
CMD ["uvicorn", "kno.web.app:app", "--host", "0.0.0.0", "--port", "8080", \
     "--timeout-graceful-shutdown", "20"]
