FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim as base

ENV PYTHONUNBUFFERED=1
ENV UV_CACHE_DIR=/root/.cache/uv
ENV PYTHONPATH=/app
ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Копирование файлов зависимостей
ADD pyproject.toml uv.lock ./

# Синхронизируем зависимости
RUN uv sync --frozen --no-dev

CMD ["tail", "-f", "/dev/null"]

FROM base

COPY . /app
CMD ["uv", "run", "main.py"]