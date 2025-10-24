FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS base

ENV PYTHONUNBUFFERED=1 \
  UV_CACHE_DIR=/root/.cache/uv \
  PYTHONPATH=/app \
  PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock ./

CMD ["uv", "run", "--no-sync", "main.py"]

FROM base AS dev

RUN uv sync --frozen
COPY . .

FROM base AS prod

ENV UV_COMPILE_BYTECODE=1

RUN uv sync --frozen --no-dev --compile-bytecode && rm -rf "$UV_CACHE_DIR"
COPY . .
