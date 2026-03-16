from telegram import BotCommand
from telegram.ext import Application
from app.bot.handlers import get_handlers, error_handler
from app.utils.logging import logger
from config.settings import settings


async def _set_bot_commands(application: Application) -> None:
    """Устанавливает список команд для кнопки «Меню» в Telegram."""
    try:
        await application.bot.set_my_commands([
            BotCommand("start", "Начать работу"),
            BotCommand("help", "Справка"),
            BotCommand("period", "Установить период анализа"),
            BotCommand("shops", "Выбор магазинов"),
        ])
    except Exception as e:
        # Если при установке команд случился таймаут/сетевая ошибка — логируем, но не роняем приложение.
        logger.warning(f"Failed to set bot commands: {e}")


def main():
    """Основная функция запуска приложения"""
    try:
        # Инициализация бота (post_init — команды в меню при нажатии «Меню»)
        builder = Application.builder().token(settings.TELEGRAM_TOKEN)

        # Если задан SOCKS5-прокси (тот же, что и для LLM), направляем трафик Telegram через него.
        proxy_host = getattr(settings, "PROXY_HOST", None)
        proxy_port = getattr(settings, "PROXY_PORT", None)
        if proxy_host and proxy_port:
            proxy_url = f"socks5://{proxy_host}:{proxy_port}"
            logger.info(f"Telegram bot will use SOCKS5 proxy: {proxy_host}:{proxy_port}")
            builder = builder.proxy(proxy_url).get_updates_proxy(proxy_url)

        # Увеличиваем таймауты подключения/чтения, чтобы первый запрос к Telegram не падал.
        builder = builder.connect_timeout(30.0).read_timeout(30.0)

        application = builder.post_init(_set_bot_commands).build()

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