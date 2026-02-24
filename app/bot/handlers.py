from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from telegram.error import BadRequest
from app.agents.analyst import ai_analyst
from app.auth.security import is_user_authorized
from app.utils.logging import logger
from app.utils.metrics import track_performance
from config.settings import settings
import asyncio
import concurrent.futures
from collections.abc import MutableMapping
import re
import time


def markdown_to_telegram_html(text: str) -> str:
    """
    Конвертирует Markdown от агента в HTML для Telegram (parse_mode='HTML').
    Telegram не поддерживает ** для жирного — только <b> или * в Markdown.
    Используем HTML, чтобы ** и другие конструкции отображались корректно.
    """
    if not text or not text.strip():
        return text
    # 1. Экранируем символы, опасные в HTML
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # 2. Жирный: **текст** или __текст__ -> <b>текст</b>
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text, flags=re.DOTALL)
    # 3. Курсив: *один символ* (не **) — осторожно с числами типа 100*2, делаем только *слово*
    # Используем границу слова, чтобы не зацепить 100*2
    text = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"(?<!_)_([^_\n]+?)_(?!_)", r"<i>\1</i>", text)
    # 4. Код: `код` -> <code>код</code>
    text = re.sub(r"`([^`]+?)`", r"<code>\1</code>", text)
    return text

# Оптимизированный rate limiting с автоматической очисткой
class TimedDict(MutableMapping):
    """Словарь с автоматическим удалением устаревших записей"""
    def __init__(self, ttl: float = 5.0):
        self._data = {}
        self._ttl = ttl
    
    def __getitem__(self, key):
        value, timestamp = self._data[key]
        if time.time() - timestamp > self._ttl:
            del self._data[key]
            raise KeyError(key)
        return value
    
    def __setitem__(self, key, value):
        self._data[key] = (value, time.time())
    
    def __delitem__(self, key):
        del self._data[key]
    
    def __iter__(self):
        self._cleanup()
        return iter(self._data)
    
    def __len__(self):
        self._cleanup()
        return len(self._data)
    
    def _cleanup(self):
        """Удаление устаревших записей"""
        current_time = time.time()
        expired_keys = [
            key for key, (_, timestamp) in self._data.items()
            if current_time - timestamp > self._ttl
        ]
        for key in expired_keys:
            del self._data[key]

# Заменяем простой словарь на оптимизированный
user_requests: TimedDict = TimedDict(ttl=settings.RATE_LIMIT_WINDOW)

# Создаем пул потоков для обработки запросов
_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=settings.MAX_CONCURRENT_REQUESTS,
    thread_name_prefix="analyst_worker"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    try:
        user = update.message.from_user
        logger.info(f"Start command from user_id: {user.id}, username: {user.username}")

        if not is_user_authorized(user.id, user.username):
            welcome_unauthorized = (
                "👋 <b>Привет! Я ИИ-аналитик компании REES46.</b>\n\n"
                "🔒 <b>Для доступа к боту требуется авторизация.</b>\n\n"
                "📋 <b>Чтобы получить доступ:</b>\n"
                "1. Отправьте сообщение: <code>my_user_id</code>\n"
                "2. Перешлите полученные данные администратору\n"
            )
            await update.message.reply_text(welcome_unauthorized, parse_mode='HTML')
            return

        welcome_authorized = (
            "👋 <b>Привет! Я ИИ-аналитик компании REES46.</b>\n"
            "Задайте мне вопрос, и я постараюсь помочь!\n\n"
            "💡 <b>Примеры запросов:</b>\n"
            "• «Статистика заказов для магазина 4987 за 2024 год»\n"
            "• «Топ товаров за последний месяц для магазина 4987»\n"
        )
        await update.message.reply_text(welcome_authorized, parse_mode='HTML')

    except Exception as e:
        logger.error(f"Error in start handler: {str(e)}", exc_info=True)
        await update.message.reply_text("Произошла ошибка при обработке команды /start")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    try:
        user = update.message.from_user
        question = update.message.text.strip()

        logger.info(f"Message from user_id: {user.id}, username: {user.username}, message: {question}")

        # Обработка my_user_id - проверка авторизации НЕ требуется!
        if question.lower() == "my_user_id":
            logger.info(f"User requested their ID: {user.id}")

            # HTML версия (более стабильная)
            user_info = (
                f"👤 <b>Ваши данные для доступа:</b>\n"
                f"• User ID: <code>{user.id}</code>\n"
                f"• Username: @{user.username if user.username else 'не указан'}\n"
                f"• Имя: {user.first_name}\n"
                f"• Фамилия: {user.last_name if user.last_name else 'не указана'}\n\n"
                f"📋 Перешлите эту информацию администратору для добавления в файл allowed_users.json"
            )

            await update.message.reply_text(user_info, parse_mode='HTML')
            logger.info(f"The user requested his data: {user.first_name} (id:{user.id})")
            return

        # Rate limiting - только для авторизованных запросов
        try:
            # Проверяем, есть ли активный запрос (TimedDict автоматически очищает устаревшие)
            if user.id in user_requests:
                await update.message.reply_text("⚠️ Слишком частые запросы. Подождите немного.")
                return
            user_requests[user.id] = time.time()
        except KeyError:
            # Если ключа нет, можно продолжать
            user_requests[user.id] = time.time()

        # Проверка авторизации для обычных запросов
        logger.info(f"Checking authorization for user_id: {user.id}")
        if not is_user_authorized(user.id, user.username):
            logger.warning(f"User {user.id} is not authorized for regular requests")

            access_denied_message = (
                "⛔ Доступ запрещен.\n\n"
                "Вы не авторизованы для использования этого бота.\n\n"
                "💡 Чтобы получить доступ:\n"
                "1. Отправьте в этот бот сообщение `my_user_id`\n"
                "2. Перешлите полученные данные администратору\n"
                "3. После добавления в белый список вы получите доступ"
            )

            await update.message.reply_text(access_denied_message, parse_mode='Markdown')
            return

        logger.info(f"User {user.id} is authorized, processing query: {question}")

        # Индикатор набора
        stop_typing = asyncio.Event()

        async def typing_indicator():
            try:
                while not stop_typing.is_set():
                    await context.bot.send_chat_action(
                        chat_id=update.effective_chat.id,
                        action="typing"
                    )
                    await asyncio.sleep(3)  # Отправляем каждые 3 секунды
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.debug(f"Typing indicator error: {e}")

        typing_task = asyncio.create_task(typing_indicator())

        try:
            # Обработка запроса в thread pool с явным таймаутом (без него бот может ждать бесконечно)
            loop = asyncio.get_event_loop()
            timeout_sec = getattr(settings, "BOT_HANDLER_TIMEOUT", 660.0)
            logger.info(f"Starting query processing for: {question} (timeout={timeout_sec}s)")
            try:
                response = await asyncio.wait_for(
                    loop.run_in_executor(
                        _executor,
                        ai_analyst.process_query,
                        question,
                    ),
                    timeout=timeout_sec,
                )
            except asyncio.TimeoutError:
                logger.warning(f"Query processing timed out after {timeout_sec}s")
                await update.message.reply_text(
                    "⏱ Запрос занял слишком много времени и был прерван. "
                    "Попробуйте упростить вопрос или увеличьте BOT_HANDLER_TIMEOUT и AGENT_MAX_EXECUTION_TIME в .env (и перезапустите сервис)."
                )
                return

            logger.info(f"Query processed successfully, response length: {len(response)}")

            # Проверяем, не слишком ли длинный ответ для Telegram
            if len(response) > 4000:
                response = response[:4000] + "\n\n... (сообщение сокращено из-за ограничений Telegram)"

            # Конвертируем Markdown агента в HTML и отправляем с parse_mode для форматирования
            response_html = markdown_to_telegram_html(response)
            try:
                await update.message.reply_text(response_html, parse_mode="HTML")
            except BadRequest as e:
                # Если HTML некорректен (например, неэкранированный символ), отправляем как plain text
                logger.warning(f"Telegram HTML parse error, sending as plain text: {e}")
                await update.message.reply_text(response)

        except Exception as e:
            logger.error(f"Message processing error: {str(e)}", exc_info=True)
            await update.message.reply_text("Произошла ошибка при обработке вашего запроса.")
        finally:
            # Останавливаем индикатор набора
            stop_typing.set()
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass

    except Exception as e:
        logger.error(f"Error in handle_message: {str(e)}", exc_info=True)
        await update.message.reply_text("Произошла внутренняя ошибка при обработке сообщения.")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    try:
        logger.error(f"Bot error: {context.error}", exc_info=True)

        if update and update.effective_message:
            await update.effective_message.reply_text(
                "Произошла ошибка при обработке вашего запроса."
            )
    except Exception as e:
        logger.error(f"Error in error handler: {str(e)}", exc_info=True)


def get_handlers():
    """Возвращает список обработчиков"""
    return [
        CommandHandler("start", start),
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message),
    ]
