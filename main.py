import os
import re
import logging
from logging.handlers import RotatingFileHandler
import textwrap
from langchain.agents import AgentExecutor, initialize_agent, Tool
from langchain.agents.agent_types import AgentType
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_huggingface.embeddings import HuggingFaceEmbeddings
from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_experimental.utilities import PythonREPL
from langchain_openai import ChatOpenAI
import clickhouse_connect
import pandas as pd
from langchain.schema import SystemMessage
from langchain.prompts import MessagesPlaceholder
from langchain.memory import ConversationBufferMemory
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import asyncio
import nest_asyncio
from config import ALLOWED_USERS

nest_asyncio.apply()

# НАСТРОЙКА ЛОГИРОВАНИЯ С РОТАЦИЕЙ
def setup_logging():
    """Настройка логирования с ротацией файлов"""
    # Создаем логгер
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Очищаем существующие обработчики
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Создаем обработчик с ротацией (100 МБ макс, 1 бэкап файл)
    log_handler = RotatingFileHandler(
        filename='logs.log',
        maxBytes=50 * 1024 * 1024,  # 100 МБ
        backupCount=1,  # Храним 1 бэкап файл (logs.log.1)
        encoding='utf-8'
    )
    
    # Форматирование
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    log_handler.setFormatter(formatter)
    
    # Добавляем обработчик к логгеру
    logger.addHandler(log_handler)
    
    return logger

logger = setup_logging()
logger.info("START_LOGGING")

# Конфигурация безопасности
os.environ['AGENT_MODE'] = 'STRICT'

# Подключение к БД
def connect_to_base(host, port, user, password):
    try:
        client = clickhouse_connect.get_client(host=host, port=port, username=user, password=password)
        logger.debug("Connection to the database is successful")
        return client
    except Exception as e:
        logger.error(f"Error connecting to database: {str(e)}")
        raise Exception(f"Error connecting to database: {str(e)}")

client_ch = connect_to_base(os.environ.get('CH_HOST'), os.environ.get('CH_PORT'), os.environ.get('CH_USER'), os.environ.get('CH_PASSWORD'))

def clean_sql_query(query: str):
    """Очищает SQL-запрос от маркеров кода"""
    # Удаляем блоки кода
    q = re.sub(r'```sql\s*', '', query, flags=re.IGNORECASE)
    q = re.sub(r'```\s*', '', q)
    
    # Удаляем слово "sql" в начале строки
    q = re.sub(r'^\s*sql\s*', '', q, flags=re.IGNORECASE)
    
    # Удаляем лишние пробелы и переносы строк
    q = q.strip()
    
    return q

def auto_correct_table_names(query: str) -> str:
    """
    Автоматически добавляет 'rees46.' к именам таблиц в SQL-запросах
    Только если префикс еще не присутствует
    """
    # Список таблиц, которые нужно исправлять
    tables = [
        'also_viewed', 'bulk_messages', 'bulk_messages_hot', 'chain_messages',
        'events', 'order_items', 'popup_events', 'search_events', 'story_events'
    ]
    
    corrected_query = query
    
    for table in tables:
        # Паттерн для поиска таблицы БЕЗ префикса rees46.
        # Используем негативную опережающую проверку чтобы исключить случаи где уже есть rees46.
        pattern = rf'(?<!rees46\.)\b({table})\b'
        replacement = f'rees46.{table}'
        corrected_query = re.sub(pattern, replacement, corrected_query, flags=re.IGNORECASE)
    
    if corrected_query != query:
        logger.info(f"The request was automatically corrected: {query} -> {corrected_query}")
    
    return corrected_query

def safe_clickhouse_query(query: str):
    """Выполняет SQL-запросы только для чтения с валидацией"""

    # Очищаем запрос
    cleaned_query = clean_sql_query(query)

    # Автоматически исправляем имена таблиц
    corrected_query = auto_correct_table_names(cleaned_query)

    # Защита от инъекций
    forbidden_keywords = ['insert', 'update', 'delete', 'drop', 'alter', 'create', 'grant']
    if any(re.search(rf'\b{kw}\b', corrected_query.lower()) for kw in forbidden_keywords):
        error_msg = "Error: Prohibited operation"
        logger.error(error_msg)
        return error_msg
    
    # Только SELECT/SHOW/DESCRIBE/EXPLAIN
    if not re.match(r'^\s*(select|show|describe|with|explain)', corrected_query, re.IGNORECASE):
        error_msg = "Error: Read-only requests are allowed"
        logger.error(error_msg)
        return error_msg
       
    try:
        logger.debug(f"Request corrected: {corrected_query}")
        result = client_ch.query_df(corrected_query)
        logger.debug(f"Request result num: {len(result)} lines")
        
        # Если результат пустой, возвращаем информативное сообщение
        if len(result) == 0:
            return "Запрос выполнен успешно, но не вернул данных. Проверьте условия фильтрации."
        
        return result
    except Exception as e:
        error_msg = f"Database request error: {str(e)}"
        logger.error(error_msg)
        return error_msg

# Разбиение документа на чанки
def get_chunks(splitter, text):
    chunks = []
    for chunk in splitter.split_text(text):
        if hasattr(chunk, 'page_content'):
            page_content = chunk.page_content
            metadata = getattr(chunk, 'metadata', {}).copy()
            metadata.update({"meta": "data"})
            chunks.append(Document(page_content=page_content, metadata=metadata))
        else:
            chunks.append(Document(page_content=chunk, metadata={"meta": "data"}))
    return chunks

# Инструмент 2: RAG для схемы базы данных
def setup_rag_agent():
    """Инициализация векторной базы знаний о схеме"""
    try:
        file_md = open('db_schema_docs.md', encoding='utf-8').read()
        text_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[("#", "Header 1"), ("##", "Header 2")],
            strip_headers=False
        )
        chunks = get_chunks(text_splitter, file_md)
        embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                                            model_kwargs={'device': 'cpu'},
                                            encode_kwargs={'normalize_embeddings': True})
        return FAISS.from_documents(chunks, embeddings)
    except Exception as e:
        logger.error(f"Error when creating a RAG: {str(e)}")
        return FAISS.from_texts(["Ошибка загрузки схемы БД"], HuggingFaceEmbeddings(model_name="cointegrated/rubert-tiny2"))

vector_db = setup_rag_agent()

def schema_retriever(query: str) -> str:
    """Поиск информации о структуре БД"""
    try:
        docs = vector_db.similarity_search(query, k=4)
        return "\n\n".join([d.page_content for d in docs])
    except Exception as e:
        logger.error(f"Ошибка при поиске в схеме БД: {str(e)}")
        return "Ошибка при поиске в схеме БД"

# Инструмент 3: Python для сложных вычислений
python_repl = PythonREPL()

# Инициализация инструментов
tools = [
    Tool(
        name="ClickHouse_Query",
        func=safe_clickhouse_query,
        description=(
            "EXECUTING SQL QUERIES TO A DATABASE. USE THIS TOOL TO GET DATA FROM THE DATABASE. "
            "Input: SQL query. Output: the result is in the form of a table. "
            "EXAMPLE: To get order data, use: SELECT * FROM rees46.order_items WHERE shop_id = 123"
        )
    ),
    Tool(
        name="Database_Schema",
        func=schema_retriever,
        description=(
            "SEARCH FOR INFORMATION ABOUT THE DATABASE STRUCTURE. "
            "Use it to specify the names of tables and columns before executing the query. "
            "Entry: natural language in Russian."
        )
    ),
    Tool(
        name="Python_REPL",
        func=python_repl.run,
        description=(
            "Executing Python code for complex calculations." 
            "Use it only when it is impossible to solve through SQL. "
            "Input: valid Python code."
        )
    )
]

# Системный промпт с ограничениями
system_prompt = """
You are a senior data analyst working with ClickHouse database. You communicate with users in Russian but think in English for technical operations.

TECHNICAL RULES (ENGLISH):
1. ALWAYS use ClickHouse_Query tool for data retrieval
2. Use Database_Schema tool first to understand structure
3. Only SELECT/SHOW/DESCRIBE/EXPLAIN queries allowed
4. No semicolons in SQL queries
5. Present results as Markdown tables
6. Create complex queries using: WITH alias_1 AS (query_1), alias_2 AS (query_2)  SELECT * FROM alias_1

USER COMMUNICATION (RUSSIAN):
1. Analyze the user's question and determine:
   - Is shop_id specified? If not, request it.
   - Is the time period specified? If not, request it.
2. If the shop_id or period is not specified: politely request them from the user.
DIALOG EXAMPLES:
User: "show order statistics"
Answer: "I need clarifications to analyze order statistics.:
- Specify the shop_id (store ID)
- For what period are you interested in the data? (for example, 2024)"
3. Only when all the parameters are clear, create and execute an SQL query
4. Explain results clearly in Russian
5. Provide insights and summaries in Russian
6. If query fails, explain the issue and next steps in Russian

SECURITY:
- STRICTLY FORBIDDEN: INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, GRANT
- Validate all queries against schema first
- Never invent or hallucinate data
- ALL REQUESTS MUST CONTAIN FILTERS: SHOP_ID = specific store number and TIME PERIOD (date BETWEEN 'start date' AND 'end date'). DO NOT EXECUTE REQUESTS WITHOUT THESE FILTERS - this is protection against database overload

EXAMPLE THINKING PROCESS:
User: "покажи топ товаров"
→ Check schema for products/orders tables
→ Generate: SELECT item_id, COUNT(*) FROM rees46.order_items GROUP BY item_id ORDER BY COUNT(*) DESC LIMIT 10
→ Execute via ClickHouse_Query
→ Present table in Markdown
→ Explain in Russian: "Вот топ-10 товаров по количеству покупок..."
"""

# Создаем кастомный промпт, который явно заставляет использовать инструменты

memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

# Инициализация агента с более строгими настройками
agent = initialize_agent(
    tools=tools,
    llm=ChatOpenAI(
        api_key = os.environ.get('API_KEY_DEEPSEEK'),
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
        temperature=0.1
    ),
    agent=AgentType.CONVERSATIONAL_REACT_DESCRIPTION,
    verbose=True,
    memory=None,
    handle_parsing_errors=True,
    max_iterations=5,
    early_stopping_method="generate",
    agent_kwargs={
        "system_message": SystemMessage(content=system_prompt)
    }
)

def analyze_query_parameters(query: str) -> dict:
    """
    Анализирует запрос на наличие shop_id и временного периода
    """
    analysis = {
        'has_shop_id': False,
        'has_time_period': False,
        'missing_parameters': [],
        'recommendation': ''
    }
    
    # паттерны для поиска shop_id
    shop_id_patterns = [
        r'shop_id\s*[=:]\s*(\d+)',
        r'магазин\w*\s*[№#]?\s*(\d+)',
        r'store\w*\s*[№#]?\s*(\d+)',
        r'\b(\d{3,5})\b.*(магазин|shop|store)',
        r'(магазин|shop|store).*?\b(\d{3,5})\b',
        r'ид\s*магазин\w*\s*(\d+)',
        r'id\s*store\w*\s*(\d+)'
    ]
    
    for pattern in shop_id_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            analysis['has_shop_id'] = True
            break
    
    # паттерны для временных периодов
    time_patterns = [
        r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
        r'\d{2}\.\d{2}\.\d{4}', # DD.MM.YYYY
        r'\d{4} год', r'\d{4} г',
        r'за\s+\d{4}', r'в\s+\d{4}',
        r'с\s+\d', r'по\s+\d',
        r'месяц', r'квартал', r'недел', r'день',
        r'период', r'время', r'дата',
        r'сегодня', r'вчера', r'недавн',
        r'последн\w+\s+\d+\s+(дн|мес|нед)',
        r'за\s+последн\w+\s+\d+\s+(дн|мес|нед)'
    ]
    
    for pattern in time_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            analysis['has_time_period'] = True
            break
    
    # Формируем рекомендации
    if not analysis['has_shop_id']:
        analysis['missing_parameters'].append('shop_id')
    if not analysis['has_time_period']:
        analysis['missing_parameters'].append('временной период')
    
    if analysis['missing_parameters']:
        analysis['recommendation'] = (
            "Для выполнения запроса мне нужны уточнения:\n\n"
            + ("- Укажите **shop_id** (идентификатор магазина)\n" if not analysis['has_shop_id'] else "")
            + ("- Укажите **временной период** (например: 2024 год, последний месяц, конкретные даты)\n" if not analysis['has_time_period'] else "")
            + "\nПожалуйста, уточните эти параметры, и я смогу выполнить ваш запрос."
        )
    
    return analysis


# Основная функция для обработки запросов пользователя
def process_user_query(query: str) -> str:
    """Основная функция обработки запросов пользователя с проверкой параметров"""
    
    # Сначала анализируем запрос на наличие обязательных параметров
    analysis = analyze_query_parameters(query)
    
    # Если отсутствуют обязательные параметры - сразу возвращаем запрос на уточнение
    if analysis['missing_parameters']:
        logger.info(f"Request '{query}' requires specification of parameters: {analysis['missing_parameters']}")
        return analysis['recommendation']
    
    # Если все параметры есть - выполняем обычный процесс
    try:
        # Получаем информацию о схеме БД
        schema_info = schema_retriever(query)
        
        enhanced_prompt = f"""
Пользовательский запрос: {query}

Контекст схемы БД:
{schema_info}

Параметры запроса:
- shop_id: {'УКАЗАН' if analysis['has_shop_id'] else 'НЕ УКАЗАН'}
- временной период: {'УКАЗАН' if analysis['has_time_period'] else 'НЕ УКАЗАН'}

INSTRUCTION: You MUST use ClickHouse_Query tool to execute SQL query against the database.
DO NOT invent or hallucinate data! Follow these steps:

1. Analyze the user's question and database schema
2. Generate appropriate SQL query using available tables and columns
3.  ALWAYS turn on the filters.:
   - WHERE shop_id = specified identifier
   - AND conditions by date (date BETWEEN or date >=/<=)
4. Execute query using ClickHouse_Query tool
5. Process and analyze the results
6. Present findings in Markdown table format
7. Give the user recommendations in Russian as a marketer

CRITICAL: You are NOT allowed to answer based on assumptions. You MUST use the query tool.
If the query fails, analyze the error and try a different approach using the schema information.

Generate the SQL query now and execute it through the tool.
"""
        
        # Используем invoke вместо run (рекомендуется в новых версиях LangChain)
        try:
            result = agent.invoke({"input": enhanced_prompt})
            response = result.get("output", "Не удалось получить ответ")
        except Exception as agent_error:
            logger.error(f"Agent invocation error: {agent_error}")
            # Пробуем старый метод как fallback
            result = agent.run(enhanced_prompt)
            response = result

        return response    
        
    except Exception as e:
        logger.error(f"Request processing error: {str(e)}")
        return f"Произошла ошибка при обработке запроса: {str(e)}"

# Обновляем функцию force_tool_usage для использования новой логики
def force_tool_usage(query):
    """Упрощенная версия с использованием process_user_query"""
    return process_user_query(query)


# Функция для обработки запросов к агенту
def get_ai_response(question: str) -> str:
    """Получает ответ от ИИ-агента на заданный вопрос"""
    try:
        response = force_tool_usage(question)
        return response
    except Exception as e:
        logger.error(f"Request processing error tlg: {str(e)}")
        return "Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте позже."
      

# Обработчики для Telegram бота
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет приветственное сообщение при команде /start"""
    user = update.message.from_user
    
    # Проверяем авторизацию
    if not is_user_authorized(user.id, user.username):
        welcome_unauthorized = (
            "👋 Привет! Я ИИ-аналитик компании REES46.\n\n"
            "🔒 Для доступа к боту требуется авторизация.\n\n"
            "📋 Чтобы получить доступ:\n"
            "1. Отправьте сообщение: `my_user_id`\n"
            "2. Перешлите полученные данные администратору\n"
            "3. После добавления в белый список вы получите полный доступ к функциям бота\n\n"
            "💡 Уже есть доступ? Попробуйте отправить любой запрос для проверки."
        )
        await update.message.reply_text(welcome_unauthorized, parse_mode='Markdown')
        return
    
    # Приветствие для авторизованных пользователей
    welcome_authorized = (
        "👋 Привет! Я ИИ-аналитик компании REES46.\n"
        "Задайте мне вопрос, и я постараюсь помочь!\n\n"
        "💡 Примеры запросов:\n"
        "• «Статистика заказов для магазина 4987 за 2024 год»\n"
        "• «Топ товаров за последний месяц для магазина 4987»\n"
        "• «Анализ рассылок для магазина 4987 за 2024 год»"
    )
    await update.message.reply_text(welcome_authorized)

def is_user_authorized(user_id: int, username: str) -> bool:
    """
    Проверяет, есть ли пользователь в белом списке
    """
    # Самый надежный способ - проверка по user_id
    if user_id in ALLOWED_USERS:
        return True
    
    # Менее надежный способ - проверка по username (если указан)
    if username:
        username = username.lower().lstrip('@')
        for allowed_id, user_data in ALLOWED_USERS.items():
            if user_data.get('username', '').lower() == username:
                return True
    
    return False


async def keep_typing_indicator(bot: Bot, chat_id: int, stop_event: asyncio.Event, interval: float = 4.0) -> None:
    """Постоянно обновляет typing, пока не придет ответ."""
    try:
        while not stop_event.is_set():
            await bot.send_chat_action(chat_id=chat_id, action="Готовлю ответ")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue
    except Exception as error:
        logger.warning(f"Typing indicator task exited: {error}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает текстовые сообщения пользователя с проверкой доступа"""
    user = update.message.from_user
    question = update.message.text.strip()
    
    # Обработка кодового слова для получения user_id
    if question.lower() == "my_user_id":
        user_info = (
            f"👤 Ваши данные для доступа:\n"
            f"• User ID: `{user.id}`\n"
            f"• Username: @{user.username if user.username else 'не указан'}\n"
            f"• Имя: {user.first_name}\n"
            f"• Фамилия: {user.last_name if user.last_name else 'не указана'}\n\n"
            f"📋 Перешлите эту информацию администратору для получения доступа к боту."
        )
        
        await update.message.reply_text(user_info, parse_mode='Markdown')
        logger.info(f"The user requested his data: {user.first_name} (id:{user.id})")
        return
    
    # Проверяем авторизацию пользователя для обычных запросов
    if not is_user_authorized(user.id, user.username):
        logger.warning(f"Unauthorized ACCESS: {user.first_name} (id:{user.id}, username:@{user.username})")
        
        access_denied_message = (
            "⛔ Доступ запрещен.\n"
            "Вы не авторизованы для использования этого бота.\n\n"
            "💡 Чтобы получить доступ:\n"
            "1. Отправьте в этот бот сообщение `my_user_id`\n"
            "2. Перешлите полученные данные администратору\n"
            "3. После добавления в белый список вы получите доступ"
        )
        
        await update.message.reply_text(access_denied_message, parse_mode='Markdown')
        return
    
    # Если пользователь авторизован - обрабатываем запрос
    logger.info(f"Question from {user.first_name} ({user.id}): {question}")
    
    stop_typing_event = asyncio.Event()
    typing_task = asyncio.create_task(
        keep_typing_indicator(context.bot, update.effective_chat.id, stop_typing_event)
    )
    
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, get_ai_response, question)
        await update.message.reply_text(response)
    except Exception as e:
        logger.error(f"Error when processing a request from a bot user: {str(e)}")
        await update.message.reply_text("Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте позже.")
    finally:
        stop_typing_event.set()
        try:
            await typing_task
        except Exception as typing_error:
            logger.debug(f"Typing indicator task finished with warning: {typing_error}")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ошибки в боте"""
    logger.error(f"Error processing the message: {context.error}")
    
    if update.effective_message:
        await update.effective_message.reply_text(
            "Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте позже.")

def main():
    """Запускает бота"""
    telegram_token = os.environ.get('TELEGRAM_TOKEN')
    if not telegram_token:
        raise RuntimeError("TELEGRAM_TOKEN не задан. Укажите его в переменных окружения (.env).")
    application = Application.builder().token(telegram_token).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    
    # Регистрируем обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Регистрируем обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    logger.info("Bot running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()  
