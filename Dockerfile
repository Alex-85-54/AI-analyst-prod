FROM ghcr.io/astral-sh/uv:python3.12-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    UV_CACHE_DIR=/root/.cache/uv \
    PYTHONPATH=/app \
    PATH="/app/.venv/bin:$PATH" \
    LOG_FILE_PATH=/app/logs/app.log \
    LOG_ENABLE_CONSOLE=true
WORKDIR /app

COPY pyproject.toml uv.lock ./
CMD ["uv", "run", "--no-sync", "run.py"]

FROM base AS dev

RUN uv sync --frozen
COPY . .

FROM base AS prod

ENV UV_COMPILE_BYTECODE=1

RUN uv sync --frozen --no-dev --compile-bytecode && rm -rf "$UV_CACHE_DIR"
COPY . .
