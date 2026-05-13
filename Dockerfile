# Multi-stage build: uv builder → slim Python runtime.
#
# Builder uses the official uv image (uv + Python 3.12 pre-installed) to
# resolve and install the project's dependencies into /app/.venv. The runtime
# stage copies that venv into a plain python:3.12-slim and runs uvicorn.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Resolve deps from the lockfile *before* copying source so that source-only
# changes don't bust the dependency layer cache.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Now install the project itself.
COPY README.md LICENSE ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev


FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    KNO_HOST=0.0.0.0 \
    KNO_PORT=8080

WORKDIR /app

COPY --from=builder /app /app

EXPOSE 8080

# Skip the `kno serve` CLI shim and run uvicorn directly — one fewer process
# layer in the container.
CMD ["uvicorn", "kno.web.app:app", "--host", "0.0.0.0", "--port", "8080"]
