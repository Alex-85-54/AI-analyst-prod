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
    
    # DeepSeek API
    API_KEY_DEEPSEEK: str = Field(..., env="API_KEY_DEEPSEEK")
    DEEPSEEK_BASE_URL: str = Field("https://api.deepseek.com/v1", env="DEEPSEEK_BASE_URL")
    
    # Security - путь к файлу с пользователями
    AUTH_CONFIG_PATH: str = Field("allowed_users.json", env="AUTH_CONFIG_PATH")

    # Logging settings
    LOG_FILE_PATH: str = Field("logs/app.log", env="LOG_FILE_PATH")
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL")
    LOG_MAX_SIZE_MB: int = Field(100, env="LOG_MAX_SIZE_MB")
    LOG_BACKUP_COUNT: int = Field(5, env="LOG_BACKUP_COUNT")
    LOG_ENABLE_CONSOLE: bool = Field(True, env="LOG_ENABLE_CONSOLE")
    
    # App settings
    MAX_CONCURRENT_REQUESTS: int = Field(50, env="MAX_CONCURRENT_REQUESTS")
    REQUEST_TIMEOUT: int = Field(60, env="REQUEST_TIMEOUT")
    DB_SCHEMA_PATH: str = Field("db_schema_docs.md", env="DB_SCHEMA_PATH")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

settings = Settings()