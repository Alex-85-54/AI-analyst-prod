from telegram.ext import Application
from app.bot.handlers import get_handlers, error_handler
from app.utils.logging import logger
from config.settings import settings

def main():
    """Основная функция запуска приложения"""
    try:
        # Инициализация бота
        application = Application.builder().token(settings.TELEGRAM_TOKEN).build()
        
        # Регистрация обработчиков
        for handler in get_handlers():
            application.add_handler(handler)
        
        application.add_error_handler(error_handler)
        
        # Запуск бота
        logger.info("Starting AI Analyst bot...")
        application.run_polling(
            allowed_updates=[],
            drop_pending_updates=True
        )
        
    except Exception as e:
        logger.critical(f"Failed to start application: {str(e)}")
        raise

if __name__ == "__main__":
    main()