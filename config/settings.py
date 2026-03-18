import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Настройки приложения"""
    
    # Telegram
    TELEGRAM_TOKEN: str = Field(..., env="TELEGRAM_TOKEN")
    
    # ClickHouse
    CH_HOST: str = Field(..., env="CH_HOST")
    CH_PORT: int = Field(..., env="CH_PORT")
    CH_USER: str = Field(..., env="CH_USER")
    CH_PASSWORD: str = Field(..., env="CH_PASSWORD")

    # PostgreSQL (опционально; если не заданы — агент работает только с ClickHouse)
    PG_HOST: Optional[str] = Field(None, env="PG_HOST")
    PG_PORT: int = Field(5432, env="PG_PORT")
    PG_USER: Optional[str] = Field(None, env="PG_USER")
    PG_PASSWORD: Optional[str] = Field(None, env="PG_PASSWORD")
    PG_DATABASE: Optional[str] = Field(None, env="PG_DATABASE")
    
    # LLM: выбор провайдера ("deepseek" | "openai")
    LLM_PROVIDER: str = Field("deepseek", env="LLM_PROVIDER")
    # Прокси для запросов к LLM (только LLM, не Telegram). SOCKS5. Опционально.
    PROXY_HOST: Optional[str] = Field(None, env="PROXY_HOST")
    PROXY_PORT: Optional[str] = Field(None, env="PROXY_PORT")
    # DeepSeek API (используется при LLM_PROVIDER=deepseek)
    API_KEY_DEEPSEEK: Optional[str] = Field(None, env="API_KEY_DEEPSEEK")
    DEEPSEEK_BASE_URL: str = Field("https://api.deepseek.com/v1", env="DEEPSEEK_BASE_URL")
    # OpenAI API (используется при LLM_PROVIDER=openai)
    API_KEY_OPENAI: Optional[str] = Field(None, env="API_KEY_OPENAI")
    OPENAI_MODEL: str = Field("gpt-5.2", env="OPENAI_MODEL")
    # Модели OpenAI, не поддерживающие параметр stop (через запятую). Для них используется обёртка без stop.
    OPENAI_MODELS_NO_STOP: str = Field(
        "gpt-5.2,o3,o4-mini",
        env="OPENAI_MODELS_NO_STOP",
        description="Comma-separated list of OpenAI model names that do not support the 'stop' parameter",
    )
    
    # Security - путь к файлу с пользователями
    AUTH_CONFIG_PATH: str = Field("allowed_users.json", env="AUTH_CONFIG_PATH")

    # Internal API: список магазинов по Telegram user_id
    SHOPS_API_BASE_URL: str = Field(
        "https://app.rees46.ru/api/internal",
        env="SHOPS_API_BASE_URL",
        description="Base URL for internal API (shops-by-telegram/<user_id>)",
    )
    SHOPS_API_TIMEOUT: float = Field(10.0, env="SHOPS_API_TIMEOUT")
    # TTL кэша магазинов в user_data (сек). После протухания обновляем при первом сообщении.
    SHOPS_CACHE_TTL: int = Field(3600, env="SHOPS_CACHE_TTL")

    # Logging settings
    LOG_FILE_PATH: str = Field("logs/app.log", env="LOG_FILE_PATH")
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL")
    LOG_MAX_SIZE_MB: int = Field(100, env="LOG_MAX_SIZE_MB")
    LOG_BACKUP_COUNT: int = Field(5, env="LOG_BACKUP_COUNT")
    LOG_ENABLE_CONSOLE: bool = Field(True, env="LOG_ENABLE_CONSOLE")
    
    # App settings
    MAX_CONCURRENT_REQUESTS: int = Field(50, env="MAX_CONCURRENT_REQUESTS")
    # Таймаут одного HTTP-запроса к LLM (DeepSeek). Сложные ответы могут занимать 60–120 с.
    REQUEST_TIMEOUT: int = Field(180, env="REQUEST_TIMEOUT")
    DB_SCHEMA_PATH: str = Field("app/agents/db_schema_docs.md", env="DB_SCHEMA_PATH")
    DB_SCHEMA_PATH_PG: str = Field("app/agents/db_schema_pg.md", env="DB_SCHEMA_PATH_PG")
    DATA_CATALOG_PATH: str = Field("app/agents/data_catalog.md", env="DATA_CATALOG_PATH")
    # Директория кэша моделей HuggingFace (FRIDA и др.). На хосте монтировать в эту же path в контейнере.
    HF_CACHE_DIR: str = Field("cache/huggingface", env="HF_CACHE_DIR")
    # Режим приложения: dev — FAISS загружается/сохраняется на хосте; prod — FAISS каждый раз пересоздаётся, не сохраняется.
    MODE: str = Field("prod", env="MODE", description="dev | prod")
    # Директория на хосте для сохранения/загрузки индекса FAISS (только в режиме dev).
    FAISS_INDEX_PATH: str = Field("cache/faiss_index", env="FAISS_INDEX_PATH")

    # Performance optimization settings
    QUERY_CACHE_TTL: int = Field(300, env="QUERY_CACHE_TTL")  # 5 минут
    SCHEMA_CACHE_SIZE: int = Field(100, env="SCHEMA_CACHE_SIZE")
    MAX_QUERY_CACHE_SIZE: int = Field(1000, env="MAX_QUERY_CACHE_SIZE")
    RATE_LIMIT_WINDOW: int = Field(5, env="RATE_LIMIT_WINDOW")  # секунды
    # Агент: макс. число шагов (вызов схемы + запрос к БД + финальный ответ = несколько итераций)
    AGENT_MAX_ITERATIONS: int = Field(10, env="AGENT_MAX_ITERATIONS")
    # Агент: макс. время работы в секундах (схема + запросы к БД + несколько вызовов LLM)
    AGENT_MAX_EXECUTION_TIME: float = Field(600.0, env="AGENT_MAX_EXECUTION_TIME")
    # Обработчик бота: макс. время ожидания ответа агента (должен быть >= AGENT_MAX_EXECUTION_TIME)
    BOT_HANDLER_TIMEOUT: float = Field(660.0, env="BOT_HANDLER_TIMEOUT")

    # Размер фигуры matplotlib для PNG-таблицы (ширина и высота в дюймах)
    CHART_TABLE_FIG_WIDTH: float = Field(12.0, env="CHART_TABLE_FIG_WIDTH")
    CHART_TABLE_FIG_HEIGHT: float = Field(8.0, env="CHART_TABLE_FIG_HEIGHT")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

settings = Settings()