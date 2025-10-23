FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
  UV_CACHE_DIR=/root/.cache/uv \
  PYTHONPATH=/app \
  PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev && rm -rf $UV_CACHE_DIR

COPY . .

CMD ["uv", "run", "--no-sync", "main.py"]
