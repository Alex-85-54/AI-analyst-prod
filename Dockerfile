FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS base

ENV PYTHONUNBUFFERED=1 \
    UV_CACHE_DIR=/root/.cache_uv \
    PYTHONPATH=/app \
    PATH="/app/.venv/bin:$PATH" \
    UV_COMPILE_BYTECODE=1 \
    # Настройки логирования по умолчанию для Docker
    LOG_FILE_PATH=/app/logs/app.log \
    LOG_ENABLE_CONSOLE=true

WORKDIR /app

COPY pyproject.toml uv.lock ./

FROM base AS prod

RUN uv sync --frozen --no-dev

COPY .. .

# Создаем директорию для логов
RUN mkdir -p /app/logs

CMD ["uv", "run", "run.py"]