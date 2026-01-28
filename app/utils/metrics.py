"""Модуль для отслеживания метрик производительности"""
import time
import functools
import json
from typing import Callable, Any
from app.utils.logging import logger

# Создаём отдельный логгер для метрик (можно фильтровать по имени)
metrics_logger = logger.getChild("metrics")


def track_performance(func: Callable) -> Callable:
    """Декоратор для отслеживания производительности с структурированными метриками"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        func_name = f"{func.__module__}.{func.__name__}"
        
        try:
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            
            # Структурированная метрика
            metric = {
                "metric_type": "performance",
                "function": func_name,
                "duration_seconds": round(duration, 3),
                "status": "success"
            }
            
            # Логируем как JSON для удобного парсинга
            metrics_logger.info(json.dumps(metric, ensure_ascii=False))
            
            # Также обычное сообщение для читаемости
            logger.debug(f"⏱️ {func_name} completed in {duration:.2f}s")
            
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            metric = {
                "metric_type": "performance",
                "function": func_name,
                "duration_seconds": round(duration, 3),
                "status": "error",
                "error": str(e)
            }
            metrics_logger.error(json.dumps(metric, ensure_ascii=False))
            logger.error(f"❌ {func_name} failed after {duration:.2f}s: {str(e)}")
            raise
    
    return wrapper


def track_query_performance(query_type: str = "unknown"):
    """Декоратор для отслеживания производительности запросов с дополнительным контекстом"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            func_name = f"{func.__module__}.{func.__name__}"
            
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                
                # Извлекаем информацию о запросе, если возможно
                query_preview = ""
                if args and isinstance(args[0], str):
                    query_preview = args[0][:100]  # Первые 100 символов
                
                metric = {
                    "metric_type": "query_performance",
                    "function": func_name,
                    "query_type": query_type,
                    "duration_seconds": round(duration, 3),
                    "status": "success",
                    "query_preview": query_preview
                }
                
                metrics_logger.info(json.dumps(metric, ensure_ascii=False))
                logger.debug(f"⏱️ {query_type} query completed in {duration:.2f}s")
                
                return result
                
            except Exception as e:
                duration = time.time() - start_time
                metric = {
                    "metric_type": "query_performance",
                    "function": func_name,
                    "query_type": query_type,
                    "duration_seconds": round(duration, 3),
                    "status": "error",
                    "error": str(e)
                }
                metrics_logger.error(json.dumps(metric, ensure_ascii=False))
                logger.error(f"❌ {query_type} query failed after {duration:.2f}s: {str(e)}")
                raise
        
        return wrapper
    return decorator
