import time
from typing import Callable, Dict, Any
from telegram import Update
from telegram.ext import ContextTypes
from NEW.app.utils.logging import logger

class RateLimitMiddleware:
    """Middleware для ограничения частоты запросов"""
    
    def __init__(self, requests_per_minute: int = 30):
        self.requests_per_minute = requests_per_minute
        self.user_requests: Dict[int, list] = {}
    
    async def __call__(self, update: Update, context: ContextTypes.DEFAULT_TYPE, handler: Callable):
        user_id = update.effective_user.id
        current_time = time.time()
        
        # Очистка старых запросов
        if user_id in self.user_requests:
            self.user_requests[user_id] = [
                req_time for req_time in self.user_requests[user_id]
                if current_time - req_time < 60
            ]
        
        # Проверка лимита
        if user_id in self.user_requests and len(self.user_requests[user_id]) >= self.requests_per_minute:
            logger.warning(f"Rate limit exceeded for user {user_id}")
            await update.message.reply_text(
                "⚠️ Слишком много запросов. Пожалуйста, подождите 1 минуту."
            )
            return
        
        # Добавление текущего запроса
        if user_id not in self.user_requests:
            self.user_requests[user_id] = []
        self.user_requests[user_id].append(current_time)
        
        # Продолжаем обработку
        return await handler(update, context)

class LoggingMiddleware:
    """Middleware для логирования всех запросов"""
    
    async def __call__(self, update: Update, context: ContextTypes.DEFAULT_TYPE, handler: Callable):
        user = update.effective_user
        message_text = update.message.text if update.message else "No text"
        
        logger.info(f"User {user.id} (@{user.username}): {message_text[:100]}...")
        
        start_time = time.time()
        try:
            result = await handler(update, context)
            processing_time = time.time() - start_time
            
            logger.info(f"Request from user {user.id} processed in {processing_time:.2f}s")
            return result
            
        except Exception as e:
            logger.error(f"Error processing request from user {user.id}: {str(e)}")
            raise

# Глобальные инстансы middleware
rate_limit_middleware = RateLimitMiddleware()
logging_middleware = LoggingMiddleware()