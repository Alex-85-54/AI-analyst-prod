from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from NEW.app.agents.analyst import ai_analyst
from NEW.app.auth.security import is_user_authorized
from NEW.app.utils.logging import logger
import asyncio
from typing import Dict
import time

# Простой rate limiting
user_requests: Dict[int, float] = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.message.from_user
    
    if not is_user_authorized(user.id, user.username):
        welcome_unauthorized = (
            "👋 Привет! Я ИИ-аналитик компании REES46.\n\n"
            "🔒 Для доступа к боту требуется авторизация.\n\n"
            "📋 Чтобы получить доступ:\n"
            "1. Отправьте сообщение: `my_user_id`\n"
            "2. Перешлите полученные данные администратору\n"
        )
        await update.message.reply_text(welcome_unauthorized, parse_mode='Markdown')
        return
    
    welcome_authorized = (
        "👋 Привет! Я ИИ-аналитик компании REES46.\n"
        "Задайте мне вопрос, и я постараюсь помочь!\n\n"
        "💡 Примеры запросов:\n"
        "• «Статистика заказов для магазина 4987 за 2024 год»\n"
        "• «Топ товаров за последний месяц для магазина 4987»\n"
    )
    await update.message.reply_text(welcome_authorized)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user = update.message.from_user
    question = update.message.text.strip()
    
    # Rate limiting (1 запрос в 5 секунд)
    current_time = time.time()
    if user.id in user_requests:
        time_passed = current_time - user_requests[user.id]
        if time_passed < 5:
            await update.message.reply_text("⚠️ Слишком частые запросы. Подождите немного.")
            return
    
    user_requests[user.id] = current_time
    
    # Обработка my_user_id
    if question.lower() == "my_user_id":
        user_info = (
            f"👤 Ваши данные для доступа:\n"
            f"• User ID: `{user.id}`\n"
            f"• Username: @{user.username if user.username else 'не указан'}\n"
            f"• Имя: {user.first_name}\n"
            f"• Фамилия: {user.last_name if user.last_name else 'не указана'}\n\n"
            f"📋 Перешлите эту информацию администратору для добавления в файл allowed_users.json"
        )
        
        await update.message.reply_text(user_info, parse_mode='Markdown')
        logger.info(f"The user requested his data: {user.first_name} (id:{user.id})")
        return
    
    # Проверка авторизации
    if not is_user_authorized(user.id, user.username):
        await update.message.reply_text("⛔ Доступ запрещен.")
        return
    
    # Индикатор набора
    async def typing_indicator():
        while True:
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id, 
                action="typing"
            )
            await asyncio.sleep(4)
    
    typing_task = asyncio.create_task(typing_indicator())
    
    try:
        # Обработка запроса в thread pool
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, 
            ai_analyst.process_query, 
            question
        )
        
        await update.message.reply_text(response)
        
    except Exception as e:
        logger.error(f"Message handling error: {str(e)}")
        await update.message.reply_text("Произошла ошибка при обработке запроса.")
    finally:
        typing_task.cancel()

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Bot error: {context.error}")
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "Произошла ошибка при обработке вашего запроса."
        )

def get_handlers():
    """Возвращает список обработчиков"""
    return [
        CommandHandler("start", start),
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message),
    ]