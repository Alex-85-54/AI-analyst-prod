from io import BytesIO
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram.error import BadRequest
from app.agents.analyst import ai_analyst, get_llm
from app.agents.tools import vector_db, rag_embedding_model
from app.auth.security import is_user_authorized
from app.auth.shops_api import fetch_shops_by_telegram_user_id
from app.context import get_last_query_df
from app.utils.logging import logger
from app.utils.metrics import track_performance
from app.utils.table_image import dataframe_to_png
from app.database.clickhouse import clickhouse_client
from app.database.postgres import postgres_client, _is_pg_configured as is_pg_configured
from config.settings import settings
import asyncio
import concurrent.futures
from collections.abc import MutableMapping
import re
import time
from datetime import datetime

# Кнопка «Проверка систем» в клавиатуре
HEALTH_CHECK_BUTTON = "Проверка систем"
# Эмодзи для выбора магазинов: ✅ выбран (горит), ⭕ не выбран (потух). U+2B55 = hollow red circle
SHOP_SELECTED = "✅"
SHOP_NOT_SELECTED = "⭕"  # U+2B55

# Ограничения UI Telegram для выбора магазинов
SHOPS_INLINE_MAX = 150

_reply_markup = ReplyKeyboardMarkup(
    [[KeyboardButton(HEALTH_CHECK_BUTTON)]],
    resize_keyboard=True,
    one_time_keyboard=False,
)


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

# Последний DataFrame по user_id для кнопки «Выгрузить в Excel» (на случай если user_data не сохраняет объект)
_last_query_df_by_user: dict = {}

# Создаем пул потоков для обработки запросов
_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=settings.MAX_CONCURRENT_REQUESTS,
    thread_name_prefix="analyst_worker"
)


# Маска даты для подсказки пользователю (ГГГГ-ММ-ДД)
DATE_MASK_HINT = "ГГГГ-ММ-ДД"
DATE_EXAMPLE = "2024-01-01"


def _parse_date(text: str) -> str | None:
    """
    Парсит дату из строки. Поддерживает: ГГГГ-ММ-ДД, ДД.ММ.ГГГГ, ДД/ММ/ГГГГ.
    Возвращает дату в формате YYYY-MM-DD или None при ошибке.
    """
    if not text or not text.strip():
        return None
    text = text.strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(text, fmt)
            if 2000 <= dt.year <= 2100:
                return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


async def _refresh_allowed_shop_ids(update: Update, context: ContextTypes.DEFAULT_TYPE) -> list:
    """
    Обновляет список доступных магазинов из internal API и пишет в user_data.

    По требованиям: если API вернул [] или None — блокируем аналитику и отправляем к администратору.
    """
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None:
        return []
    shops = await fetch_shops_by_telegram_user_id(user_id)
    if not shops:
        # жёстко отказываем в работе
        await update.effective_message.reply_text(
            "⛔ У вас нет доступных магазинов для аналитики (или сервис магазинов недоступен).\n\n"
            "Обратитесь к администратору для выдачи доступа."
        )
        context.user_data["allowed_shop_ids"] = []
        context.user_data["allowed_shop_ids_fetched_at"] = time.time()
        context.user_data["selected_shop_ids"] = []
        return []
    shops = [int(s) for s in shops]
    context.user_data["allowed_shop_ids"] = shops
    context.user_data["allowed_shop_ids_fetched_at"] = time.time()
    # если ранее были выбранные — фильтруем, чтобы не осталось недоступных
    selected = [int(s) for s in (context.user_data.get("selected_shop_ids") or [])]
    selected = [s for s in selected if s in set(shops)]
    context.user_data["selected_shop_ids"] = selected
    return shops


def _build_shop_selector_keyboard(allowed_shop_ids: list, selected_shop_ids: list) -> InlineKeyboardMarkup:
    """Клавиатура выбора магазинов: ✅ 4987 (выбран), ⭕ 4987 (не выбран)."""
    selected_set = set(int(s) for s in selected_shop_ids)
    buttons = [
        [InlineKeyboardButton(
            f"{SHOP_SELECTED} {sid}" if int(sid) in selected_set else f"{SHOP_NOT_SELECTED} {sid}",
            callback_data=f"shop_toggle:{sid}",
        )]
        for sid in allowed_shop_ids
    ]
    return InlineKeyboardMarkup(buttons)


def _build_menu_buttons_row() -> list:
    """Ряд кнопок: Справка и Задать период (видно до появления кнопки «Меню» в Telegram)."""
    return [
        InlineKeyboardButton("📖 Справка", callback_data="cmd_help"),
        InlineKeyboardButton("📅 Задать период", callback_data="cmd_period"),
    ]


def _build_selector_with_menu(allowed_shop_ids: list, selected_shop_ids: list) -> InlineKeyboardMarkup:
    """Клавиатура выбора магазинов + ряд «Справка» и «Задать период»."""
    base = _build_shop_selector_keyboard(allowed_shop_ids, selected_shop_ids)
    # base.inline_keyboard может быть tuple — приводим к list для конкатенации
    rows = list(base.inline_keyboard) + [_build_menu_buttons_row()]
    return InlineKeyboardMarkup(rows)


def _build_shops_big_menu() -> InlineKeyboardMarkup:
    """Меню управления магазинами для большого списка (только быстрый режим)."""
    rows = [
        [
            InlineKeyboardButton("🧹 Сбросить выбор", callback_data="shops:reset"),
            InlineKeyboardButton("✅ Готово", callback_data="shops:done"),
        ],
        [
            InlineKeyboardButton("📋 Показать выбранные", callback_data="shops:selected"),
            InlineKeyboardButton("🗑 Очистить выбранные", callback_data="shops:clear_selected"),
        ],
        _build_menu_buttons_row(),
    ]
    return InlineKeyboardMarkup(rows)


def _keyboard_only_menu_buttons() -> InlineKeyboardMarkup:
    """Клавиатура только из кнопок Справка и Задать период."""
    return InlineKeyboardMarkup([_build_menu_buttons_row()])


def _run_health_checks():
    """Синхронные проверки (выполняются в executor). Возвращает список строк для отчёта."""
    lines = []
    # ClickHouse
    try:
        result = clickhouse_client.execute_safe_query("SELECT 1 AS ok")
        if isinstance(result, str) and "Error" in result:
            lines.append(f"❌ ClickHouse: {result}")
        else:
            lines.append("✅ ClickHouse: связь установлена")
    except Exception as e:
        lines.append(f"❌ ClickHouse: {str(e)}")
    # PostgreSQL
    if is_pg_configured():
        try:
            result = postgres_client.execute_safe_query("SELECT 1 AS ok")
            if isinstance(result, str) and ("Error" in result or "не настроен" in result):
                lines.append(f"❌ PostgreSQL: {result}")
            else:
                lines.append("✅ PostgreSQL: связь установлена")
        except Exception as e:
            lines.append(f"❌ PostgreSQL: {str(e)}")
    else:
        lines.append("⏭ PostgreSQL: не настроен (пропуск)")
    # LLM (провайдер из настроек: DeepSeek или OpenAI)
    provider = (settings.LLM_PROVIDER or "deepseek").strip().lower()
    try:
        llm = get_llm()
        llm.invoke("Ответь одним словом: ОК")
        label = "OpenAI" if provider == "openai" else "DeepSeek"
        lines.append(f"✅ LLM ({label}): связь установлена")
    except Exception as e:
        lines.append(f"❌ LLM ({provider}): {str(e)[:100]}")
    # Векторная БД (FAISS)
    try:
        n = vector_db.index.ntotal
        lines.append(f"✅ Векторная БД (RAG): загружено {n} чанков схемы")
    except Exception as e:
        lines.append(f"❌ Векторная БД: {str(e)}")
    # Модель векторизации
    lines.append(f"📌 Модель векторизации (RAG): {rag_embedding_model}")
    return lines


async def health_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки «Проверка систем»: проверка ClickHouse, PostgreSQL, LLM, векторной БД."""
    if not is_user_authorized(update.effective_user.id, update.effective_user.username):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    await update.message.reply_text("🔄 Выполняю проверку систем...")
    loop = asyncio.get_event_loop()
    try:
        lines = await asyncio.wait_for(
            loop.run_in_executor(_executor, _run_health_checks),
            timeout=30.0,
        )
        text = "📋 <b>Проверка систем</b>\n\n" + "\n".join(lines)
        await update.message.reply_text(text, parse_mode="HTML")
    except asyncio.TimeoutError:
        await update.message.reply_text("⏱ Проверка заняла слишком много времени.")
    except Exception as e:
        logger.exception("Health check error")
        await update.message.reply_text(f"Ошибка проверки: {str(e)}")


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

        # Обновляем список доступных магазинов из internal API
        allowed = await _refresh_allowed_shop_ids(update, context)
        if not allowed:
            return
        if len(allowed) > 1:
            context.user_data["selected_shop_ids"] = context.user_data.get("selected_shop_ids") or []
            selector_text = (
                "Выберите магазины для работы (нажмите кнопку, чтобы включить/выключить).\n"
                "<b>✅</b> — выбран, <b>⭕</b> — не выбран. Нужен хотя бы один."
            )
            await update.message.reply_text(
                "👋 <b>Привет! Я ИИ-аналитик компании REES46.</b>\n"
                "Задайте мне вопрос, и я постараюсь помочь!\n\n"
                "У вас несколько магазинов — выберите, с какими работать.\n"
                "Период для анализа задаётся командой /period.\n\n"
                "Прочитать руководство пользователя: /help",
                parse_mode="HTML",
                reply_markup=_reply_markup,
            )
            allowed_sorted = sorted([int(s) for s in allowed])
            selected_sorted = [int(s) for s in (context.user_data.get("selected_shop_ids") or [])]
            # Если магазинов слишком много — используем только быстрый режим как в /shops
            if len(allowed_sorted) > SHOPS_INLINE_MAX:
                context.user_data["allowed_shop_ids"] = allowed_sorted
                context.user_data["shops_big_mode"] = True
                await update.message.reply_text(
                    "У вас доступно много магазинов.\n\n"
                    "Быстрый выбор: отправьте ID магазина (например <code>4987</code>) или несколько через запятую "
                    "(например <code>4987,5002</code>). Это заменит текущий выбор.",
                    parse_mode="HTML",
                    reply_markup=_build_shops_big_menu(),
                )
            else:
                await update.message.reply_text(
                    selector_text,
                    parse_mode="HTML",
                    reply_markup=_build_selector_with_menu(allowed_sorted, selected_sorted),
                )
        else:
            context.user_data["selected_shop_ids"] = allowed
            welcome_authorized = (
                "👋 <b>Привет! Я ИИ-аналитик компании REES46.</b>\n"
                "Задайте мне вопрос, и я постараюсь помочь!\n\n"
                "📅 Период для анализа задаётся командой /period (даты начала и конца).\n\n"
                "💡 <b>Примеры запросов:</b>\n"
                "• «Статистика заказов за период»\n"
                "• «Топ товаров по продажам»\n\n"
                "Прочитать руководство пользователя: /help"
            )
            await update.message.reply_text(
                welcome_authorized,
                parse_mode="HTML",
                reply_markup=_reply_markup,
            )
            await update.message.reply_text(
                "Быстрые действия:",
                reply_markup=_keyboard_only_menu_buttons(),
            )

    except Exception as e:
        logger.error(f"Error in start handler: {str(e)}", exc_info=True)
        await update.message.reply_text("Произошла ошибка при обработке команды /start")


HELP_TEXT = """📖 <b>Краткая справка</b>

Я помогаю анализировать данные по вашим магазинам: заказы, товары, рассылки и др.

<b>Перед первым запросом:</b>
• <b>/period</b> — задайте период анализа (даты начала и конца). Период один раз и действует на все запросы, пока не смените.
• Если у вас несколько магазинов — выберите, с какими работать (кнопки после /start или команда <b>/shops</b>).

<b>Как задавать вопросы:</b>
Пишите запрос обычными словами, например:
• «Статистика заказов за период»
• «Топ товаров по продажам»
• «Конверсия в покупку»

<b>Подсказка:</b>
Если в результате запроса бот выдал ошибку, непонятный результат или отсутствие данных — попробуйте отправить ему тот же самый запрос ещё раз; результат может быть другим."""


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help — краткое руководство для пользователя."""
    await update.message.reply_text(HELP_TEXT, parse_mode="HTML")


async def shops_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /shops — показать выбор магазинов (если их несколько)."""
    if not is_user_authorized(update.effective_user.id, update.effective_user.username):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    allowed = await _refresh_allowed_shop_ids(update, context)
    if not allowed:
        return
    if len(allowed) <= 1:
        await update.message.reply_text("У вас доступен один магазин, выбор не требуется.")
        return
    selected = [int(s) for s in (context.user_data.get("selected_shop_ids") or [])]
    allowed_sorted = sorted([int(s) for s in allowed])
    context.user_data["allowed_shop_ids"] = allowed_sorted

    if len(allowed_sorted) <= SHOPS_INLINE_MAX:
        selector_text = (
            "Выберите магазины для работы (нажмите кнопку, чтобы включить/выключить).\n"
            "<b>✅</b> — выбран, <b>⭕</b> — не выбран."
        )
        await update.message.reply_text(
            selector_text,
            parse_mode="HTML",
            reply_markup=_build_selector_with_menu(allowed_sorted, selected),
        )
        return

    # Большой список: только быстрый режим (ввод ID)
    context.user_data["shops_big_mode"] = True
    await update.message.reply_text(
        "У вас доступно много магазинов.\n\n"
        "Быстрый выбор: отправьте ID магазина (например <code>4987</code>) или несколько через запятую "
        "(например <code>4987,5002</code>). Это заменит текущий выбор.",
        parse_mode="HTML",
        reply_markup=_build_shops_big_menu(),
    )


async def period_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /period — начало диалога задания периода (два шага: дата начала, дата конца)."""
    if not is_user_authorized(update.effective_user.id, update.effective_user.username):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    context.user_data["awaiting_period"] = "start"
    await update.message.reply_text(
        "📅 <b>Укажите период для анализа данных</b>\n\n"
        "Шаг 1 из 2: <b>дата начала</b> периода.\n\n"
        f"Формат: <code>{DATE_MASK_HINT}</code>\n"
        f"Например: <code>{DATE_EXAMPLE}</code>\n\n"
        "Также можно: ДД.ММ.ГГГГ или ДД/ММ/ГГГГ",
        parse_mode="HTML",
    )


async def cmd_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки «Справка» — показать руководство (аналог /help)."""
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(HELP_TEXT, parse_mode="HTML")


async def cmd_period_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки «Задать период» — запуск диалога периода (аналог /period)."""
    query = update.callback_query
    await query.answer()
    if not is_user_authorized(update.effective_user.id, update.effective_user.username):
        await query.message.reply_text("⛔ Доступ запрещён.")
        return
    context.user_data["awaiting_period"] = "start"
    await query.message.reply_text(
        "📅 <b>Укажите период для анализа данных</b>\n\n"
        "Шаг 1 из 2: <b>дата начала</b> периода.\n\n"
        f"Формат: <code>{DATE_MASK_HINT}</code>\n"
        f"Например: <code>{DATE_EXAMPLE}</code>\n\n"
        "Также можно: ДД.ММ.ГГГГ или ДД/ММ/ГГГГ",
        parse_mode="HTML",
    )


async def export_excel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик «Выгрузить таблицу в Excel»: отправляет последний DataFrame как .xlsx."""
    query = update.callback_query
    user_id = update.effective_user.id if update.effective_user else None
    last_df = context.user_data.get("last_query_df")
    if last_df is None and user_id is not None:
        last_df = _last_query_df_by_user.get(user_id)
    if last_df is None or (hasattr(last_df, "empty") and last_df.empty):
        await query.answer(text="Нет последней таблицы для выгрузки.", show_alert=True)
        return
    try:
        filename = f"analyst_{datetime.now():%Y-%m-%d_%H-%M-%S}.xlsx"
        buf = BytesIO()
        last_df.to_excel(buf, index=False, engine="openpyxl")
        buf.seek(0)
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=buf,
            filename=filename,
        )
        await query.answer(text="Файл отправлен")
    except Exception as e:
        logger.exception("Export Excel error")
        await query.answer(text="Ошибка при выгрузке", show_alert=True)
        await query.message.reply_text(f"Ошибка при выгрузке: {str(e)}")


async def shop_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатия на кнопку магазина: переключить выбор."""
    query = update.callback_query
    await query.answer()
    if not query.data or not query.data.startswith("shop_toggle:"):
        return
    try:
        sid = int(query.data.split(":", 1)[1])
    except (ValueError, IndexError):
        return
    allowed = context.user_data.get("allowed_shop_ids") or []
    if sid not in [int(s) for s in allowed]:
        return
    selected = list(context.user_data.get("selected_shop_ids") or [])
    selected_set = set(int(s) for s in selected)
    if sid in selected_set:
        selected_set.discard(sid)
    else:
        selected_set.add(sid)
    context.user_data["selected_shop_ids"] = sorted(selected_set)
    allowed_sorted = sorted([int(s) for s in allowed])
    new_markup = _build_selector_with_menu(allowed_sorted, context.user_data["selected_shop_ids"])
    try:
        await query.edit_message_reply_markup(reply_markup=new_markup)
    except BadRequest:
        pass


async def shops_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback-обработчик управления магазинами (поиск/пагинация/сброс/готово)."""
    query = update.callback_query
    data = query.data or ""
    await query.answer()

    allowed = sorted([int(s) for s in (context.user_data.get("allowed_shop_ids") or [])])
    selected = sorted([int(s) for s in (context.user_data.get("selected_shop_ids") or [])])

    if data == "shops:noop":
        return

    if data == "shops:reset":
        context.user_data["selected_shop_ids"] = []
        if len(allowed) > SHOPS_INLINE_MAX:
            new_markup = _build_shops_big_menu()
        else:
            new_markup = _build_selector_with_menu(allowed, [])
        try:
            await query.edit_message_reply_markup(reply_markup=new_markup)
        except BadRequest:
            pass
        return

    if data == "shops:done":
        chosen = sorted([int(s) for s in (context.user_data.get("selected_shop_ids") or [])])
        if not chosen and len(allowed) > 1:
            await query.message.reply_text("⚠️ Не выбран ни один магазин. Выберите хотя бы один.")
        else:
            txt = ", ".join(str(x) for x in chosen) if chosen else "—"
            await query.message.reply_text(f"✅ Выбранные магазины: <code>{txt}</code>", parse_mode="HTML")
        return

    if data == "shops:selected":
        chosen = sorted([int(s) for s in (context.user_data.get("selected_shop_ids") or [])])
        if not chosen:
            await query.message.reply_text("Сейчас не выбран ни один магазин.")
            return
        # Чтобы не упереться в лимиты Telegram, показываем первые N и общее количество
        limit = 100
        head = chosen[:limit]
        txt = ", ".join(str(x) for x in head)
        suffix = f"\n… и ещё {len(chosen) - limit}" if len(chosen) > limit else ""
        await query.message.reply_text(
            f"📋 Выбрано магазинов: <b>{len(chosen)}</b>\n<code>{txt}</code>{suffix}",
            parse_mode="HTML",
        )
        return

    if data == "shops:clear_selected":
        context.user_data["selected_shop_ids"] = []
        if len(allowed) > SHOPS_INLINE_MAX:
            new_markup = _build_shops_big_menu()
        else:
            new_markup = _build_selector_with_menu(allowed, [])
        try:
            await query.edit_message_reply_markup(reply_markup=new_markup)
        except BadRequest:
            pass
        await query.message.reply_text("🗑 Выбранные магазины очищены.")
        return


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    try:
        user = update.message.from_user
        question = update.message.text.strip()

        logger.info(f"Message from user_id: {user.id}, username: {user.username}, message: {question}")

        # Обработка кнопки «Проверка систем»
        if question.strip() == HEALTH_CHECK_BUTTON:
            await health_check(update, context)
            return

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

        # Обновление списка магазинов при первом сообщении после простоя (TTL)
        fetched_at = float(context.user_data.get("allowed_shop_ids_fetched_at") or 0.0)
        ttl = int(getattr(settings, "SHOPS_CACHE_TTL", 3600))
        if not fetched_at or (time.time() - fetched_at > ttl):
            allowed_refreshed = await _refresh_allowed_shop_ids(update, context)
            if not allowed_refreshed:
                return

        # Диалог задания периода (два шага)
        awaiting = context.user_data.get("awaiting_period")
        if awaiting == "start":
            start_str = _parse_date(question)
            if not start_str:
                await update.message.reply_text(
                    f"⚠️ Неверный формат даты. Введите дату начала в формате <code>{DATE_MASK_HINT}</code>, например <code>{DATE_EXAMPLE}</code>",
                    parse_mode="HTML",
                )
                return
            context.user_data["period_start"] = start_str
            context.user_data["awaiting_period"] = "end"
            await update.message.reply_text(
                "✅ Дата начала сохранена.\n\n"
                "Шаг 2 из 2: <b>дата конца</b> периода.\n\n"
                f"Формат: <code>{DATE_MASK_HINT}</code>\n"
                f"Например: <code>2024-12-31</code>\n\n"
                "Конец периода должен быть не раньше даты начала.",
                parse_mode="HTML",
            )
            return
        if awaiting == "end":
            end_str = _parse_date(question)
            if not end_str:
                await update.message.reply_text(
                    f"⚠️ Неверный формат даты. Введите дату конца в формате <code>{DATE_MASK_HINT}</code>.",
                    parse_mode="HTML",
                )
                return
            start_str = context.user_data.get("period_start")
            if start_str and end_str < start_str:
                await update.message.reply_text(
                    "⚠️ Дата конца периода не может быть раньше даты начала. Введите дату конца заново."
                )
                return
            context.user_data["period_end"] = end_str
            del context.user_data["awaiting_period"]
            await update.message.reply_text(
                f"✅ Период анализа установлен: с <b>{start_str}</b> по <b>{end_str}</b>.\n\n"
                "Теперь можно задавать вопросы по данным за этот период. Чтобы изменить период — снова отправьте /period.",
                parse_mode="HTML",
            )
            return

        allowed_shop_ids = list(context.user_data.get("allowed_shop_ids") or [])
        if not allowed_shop_ids:
            # если нет магазинов — блокируем работу (по требованиям)
            await update.message.reply_text(
                "⛔ У вас нет доступных магазинов для аналитики.\n\n"
                "Обратитесь к администратору для выдачи доступа."
            )
            return

        if len(allowed_shop_ids) > 1:
            selected_shop_ids = list(context.user_data.get("selected_shop_ids") or [])
            selected_shop_ids = [int(s) for s in selected_shop_ids]
            if not selected_shop_ids:
                # быстрый режим (без /shops): если пользователь прислал ID(ы) магазина
                text = (question or "").strip()
                if re.fullmatch(r"\d+(?:\s*[, ]\s*\d+)*", text or ""):
                    parts = [p for p in re.split(r"[, ]+", text) if p]
                    ids = []
                    for p in parts:
                        try:
                            ids.append(int(p))
                        except ValueError:
                            pass
                    allowed_set = set(int(s) for s in allowed_shop_ids)
                    ids = sorted(set([i for i in ids if i in allowed_set]))
                    if ids:
                        context.user_data["selected_shop_ids"] = ids
                        await update.message.reply_text(
                            f"✅ Выбрано магазинов: {len(ids)}. Активные: <code>{', '.join(str(x) for x in ids[:10])}</code>"
                            + (" ..." if len(ids) > 10 else ""),
                            parse_mode="HTML",
                        )
                        return
                # Пустой список выбранных магазинов — не выполняем анализ, показываем ошибку и выбор
                warning_msg = (
                    "⚠️ <b>Сначала выберите магазины</b>\n\n"
                    "У вас доступно несколько магазинов. Выберите хотя бы один (нажмите на кнопки ниже), "
                    "после чего можно будет задавать вопросы по аналитике."
                )
                await update.message.reply_text(warning_msg, parse_mode="HTML")
                await update.message.reply_text(
                    "Нажмите кнопку магазина, чтобы включить или выключить его. <b>✅</b> — выбран, <b>⭕</b> — не выбран.",
                    parse_mode="HTML",
                    reply_markup=_build_shops_big_menu() if len(allowed_shop_ids) > SHOPS_INLINE_MAX else _build_selector_with_menu(allowed_shop_ids, []),
                )
                return
            else:
                # Команды управления выбранными магазинами:
                # "+ 4987" / "+ 4987,5002" — добавить
                # "- 4987" / "- 4987 5002" — убрать
                text = (question or "").strip()
                m = re.fullmatch(r"([+-])\s*(\d+(?:\s*[, ]\s*\d+)*)", text)
                if m:
                    sign = m.group(1)
                    ids_part = m.group(2)
                    parts = [p for p in re.split(r"[, ]+", ids_part) if p]
                    ids = []
                    for p in parts:
                        try:
                            ids.append(int(p))
                        except ValueError:
                            pass
                    allowed_set = set(int(s) for s in allowed_shop_ids)
                    ids = [i for i in ids if i in allowed_set]
                    if not ids:
                        await update.message.reply_text(
                            "⚠️ Указанные магазины не найдены в вашем списке доступа.",
                        )
                        return
                    selected_set = set(int(s) for s in selected_shop_ids)
                    if sign == "+":
                        selected_set.update(ids)
                    else:
                        selected_set.difference_update(ids)
                    new_selected = sorted(selected_set)
                    context.user_data["selected_shop_ids"] = new_selected
                    if not new_selected:
                        await update.message.reply_text(
                            "🗑 Выбранные магазины очищены. Выберите хотя бы один магазин.",
                        )
                        return
                    await update.message.reply_text(
                        f"✅ Выбрано магазинов: {len(new_selected)}. Активные: <code>{', '.join(str(x) for x in new_selected[:10])}</code>"
                        + (" ..." if len(new_selected) > 10 else ""),
                        parse_mode="HTML",
                    )
                    return
        else:
            selected_shop_ids = allowed_shop_ids
            context.user_data["selected_shop_ids"] = selected_shop_ids

        period_start = context.user_data.get("period_start")
        period_end = context.user_data.get("period_end")
        if not period_start or not period_end:
            await update.message.reply_text(
                "⚠️ <b>Сначала укажите период анализа</b>\n\n"
                "Период задаётся один раз и действует на все запросы до смены.\n\n"
                "Отправьте команду <code>/period</code> и введите даты начала и конца периода (формат ГГГГ-ММ-ДД).",
                parse_mode="HTML",
            )
            return

        logger.info(f"User {user.id} is authorized, processing query: {question} (shops: {selected_shop_ids}, period: {period_start}–{period_end})")

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

        def _run_process_query():
            result = ai_analyst.process_query(
                question,
                allowed_shop_ids=allowed_shop_ids,
                selected_shop_ids=selected_shop_ids,
                period_start=period_start,
                period_end=period_end,
            )
            last_df = get_last_query_df()
            return (result, last_df)

        try:
            # Обработка запроса в thread pool с явным таймаутом (без него бот может ждать бесконечно)
            loop = asyncio.get_event_loop()
            timeout_sec = getattr(settings, "BOT_HANDLER_TIMEOUT", 660.0)
            logger.info(f"Starting query processing for: {question} (timeout={timeout_sec}s)")
            try:
                response, last_df = await asyncio.wait_for(
                    loop.run_in_executor(_executor, _run_process_query),
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

            # Сохраняем последний DataFrame для кнопки «Выгрузить в Excel» (user_data + кэш по user_id)
            context.user_data["last_query_df"] = last_df
            if last_df is not None:
                _last_query_df_by_user[user.id] = last_df
                logger.info(f"Last query DataFrame stored for user_id={user.id} (rows={len(last_df)})")
            else:
                logger.debug("No DataFrame from agent for this query (last_df is None)")

            # Проверяем, не слишком ли длинный ответ для Telegram
            if len(response) > 4000:
                response = response[:4000] + "\n\n... (сообщение сокращено из-за ограничений Telegram)"

            # Конвертируем Markdown агента в HTML
            response_html = markdown_to_telegram_html(response)
            # Кнопка «Выгрузить таблицу в Excel» под текстовым ответом
            excel_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("Выгрузить таблицу в Excel", callback_data="export_excel")],
            ])
            try:
                await update.message.reply_text(
                    response_html,
                    parse_mode="HTML",
                    reply_markup=excel_kb,
                )
            except BadRequest as e:
                logger.warning(f"Telegram HTML parse error, sending as plain text: {e}")
                await update.message.reply_text(response, reply_markup=excel_kb)

            # PNG таблицы из последнего DataFrame — вторым сообщением (текст + картинка «одним блоком»)
            if last_df is not None and not last_df.empty:
                try:
                    png_buf = dataframe_to_png(last_df)
                    if png_buf.getvalue():
                        png_buf.seek(0)
                        await context.bot.send_photo(
                            chat_id=update.effective_chat.id,
                            photo=png_buf,
                        )
                except Exception as img_err:
                    logger.warning(f"Failed to send table PNG: {img_err}")

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
        CommandHandler("help", help_command),
        CommandHandler("shops", shops_command),
        CommandHandler("period", period_command),
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message),
        CallbackQueryHandler(cmd_help_callback, pattern="^cmd_help$"),
        CallbackQueryHandler(cmd_period_callback, pattern="^cmd_period$"),
        CallbackQueryHandler(shops_callback, pattern="^shops:"),
        CallbackQueryHandler(shop_toggle_callback, pattern="^shop_toggle:"),
        CallbackQueryHandler(export_excel_callback, pattern="^export_excel$"),
    ]
