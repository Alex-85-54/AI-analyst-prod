import logging
import sys
import os
from logging.handlers import RotatingFileHandler
import json
from datetime import datetime
from config.settings import settings

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_entry, ensure_ascii=False)

class SimpleFormatter(logging.Formatter):
    """Простой форматтер для консоли"""
    def format(self, record):
        return f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {record.levelname} - {record.name} - {record.getMessage()}"

def setup_logging():
    """Настройка структурированного логирования с конфигурацией из settings"""
    logger = logging.getLogger()
    
    # Устанавливаем уровень логирования
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(log_level)
    
    # Очищаем существующие обработчики
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Создаем директорию для логов, если её нет
    log_dir = os.path.dirname(settings.LOG_FILE_PATH)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
        print(f"Created log directory: {log_dir}")
    
    # Файловый обработчик с ротацией
    try:
        file_handler = RotatingFileHandler(
            filename=settings.LOG_FILE_PATH,
            maxBytes=settings.LOG_MAX_SIZE_MB * 1024 * 1024,  # Конвертируем МБ в байты
            backupCount=settings.LOG_BACKUP_COUNT,
            encoding='utf-8'
        )
        file_handler.setFormatter(JSONFormatter())
        logger.addHandler(file_handler)
        print(f"File logging enabled: {settings.LOG_FILE_PATH}")
    except Exception as e:
        print(f"Failed to setup file logging: {e}")
        # Если не удалось создать файловый handler, продолжаем с консольным
    
    # Консольный обработчик (всегда включен для Docker)
    console_handler = logging.StreamHandler(sys.stdout)
    if settings.LOG_ENABLE_CONSOLE:
        console_handler.setFormatter(SimpleFormatter())
        logger.addHandler(console_handler)
        print("Console logging enabled")
    
    logger.info("Logging system initialized successfully")
    logger.info(f"Log file: {settings.LOG_FILE_PATH}")
    logger.info(f"Log level: {settings.LOG_LEVEL}")
    
    return logger

# Инициализируем логирование при импорте модуля
logger = setup_logging()
