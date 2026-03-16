from telegram import BotCommand
from telegram.ext import Application
from app.bot.handlers import get_handlers, error_handler
from app.utils.logging import logger
from config.settings import settings


async def _set_bot_commands(application: Application) -> None:
    """Устанавливает список команд для кнопки «Меню» в Telegram."""
    await application.bot.set_my_commands([
        BotCommand("start", "Начать работу"),
        BotCommand("help", "Справка"),
        BotCommand("period", "Установить период анализа"),
        BotCommand("shops", "Выбор магазинов"),
    ])


def main():
    """Основная функция запуска приложения"""
    try:
        # Инициализация бота (post_init — команды в меню при нажатии «Меню»)
        application = (
            Application.builder()
            .token(settings.TELEGRAM_TOKEN)
            .post_init(_set_bot_commands)
            .build()
        )

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