from langchain.agents import AgentExecutor, initialize_agent
from langchain.agents.agent_types import AgentType
from langchain.schema import SystemMessage
from langchain_openai import ChatOpenAI
from langchain_core.outputs import ChatResult
from app.agents.tools import get_tools, schema_retriever
from app.utils.logging import logger
from app.utils.metrics import track_performance
from config.settings import settings
import re
import pandas as pd
from typing import Any, List, Optional
from langchain_core.messages import BaseMessage
from langchain_core.callbacks import CallbackManagerForLLMRun


class ChatOpenAINoStop(ChatOpenAI):
    """
    ChatOpenAI, который не передаёт параметр stop в API.
    Для моделей OpenAI, не поддерживающих stop (gpt-5.2, o3, o4-mini и т.п.).
    """

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        # Убираем stop из kwargs, чтобы он нигде не попал в запрос к API
        kwargs_no_stop = {k: v for k, v in kwargs.items() if k != "stop"}
        return super()._generate(
            messages,
            stop=None,
            run_manager=run_manager,
            **kwargs_no_stop,
        )


def _openai_models_no_stop() -> set:
    """Возвращает множество имён моделей OpenAI, для которых не передавать stop."""
    raw = (settings.OPENAI_MODELS_NO_STOP or "").strip()
    if not raw:
        return set()
    return {m.strip().lower() for m in raw.split(",") if m.strip()}


def get_llm() -> ChatOpenAI:
    """Создаёт экземпляр LLM в зависимости от настроек (DeepSeek или OpenAI)."""
    provider = (settings.LLM_PROVIDER or "deepseek").strip().lower()
    if provider == "openai":
        api_key = settings.API_KEY_OPENAI
        if not api_key:
            raise ValueError(
                "LLM_PROVIDER=openai задан, но API_KEY_OPENAI не указан в настройках (.env)"
            )
        model_name = (settings.OPENAI_MODEL or "").strip().lower()
        no_stop_models = _openai_models_no_stop()
        use_no_stop = model_name in no_stop_models
        if use_no_stop:
            logger.info(
                f"Using LLM: OpenAI ({settings.OPENAI_MODEL}) with no-stop wrapper (model does not support 'stop')"
            )
            return ChatOpenAINoStop(
                api_key=api_key,
                model=settings.OPENAI_MODEL,
                temperature=0.1,
                timeout=settings.REQUEST_TIMEOUT,
                max_retries=2,
                streaming=False,
            )
        logger.info(f"Using LLM: OpenAI ({settings.OPENAI_MODEL})")
        return ChatOpenAI(
            api_key=api_key,
            model=settings.OPENAI_MODEL,
            temperature=0.1,
            timeout=settings.REQUEST_TIMEOUT,
            max_retries=2,
            streaming=False,
        )
    # DeepSeek (по умолчанию)
    api_key = settings.API_KEY_DEEPSEEK
    if not api_key:
        raise ValueError(
            "LLM_PROVIDER=deepseek задан (или не задан), но API_KEY_DEEPSEEK не указан в настройках (.env)"
        )
    logger.info("Using LLM: DeepSeek (deepseek-chat)")
    return ChatOpenAI(
        api_key=api_key,
        base_url=settings.DEEPSEEK_BASE_URL,
        model="deepseek-chat",
        temperature=0.1,
        timeout=settings.REQUEST_TIMEOUT,
        max_retries=2,
        streaming=False,
    )

class AIAnalyst:
    # Компилируем паттерны один раз при загрузке класса
    _shop_id_patterns = [
        re.compile(r'shop_id\s*[=:]\s*(\d+)', re.IGNORECASE),
        re.compile(r'магазин\w*\s*[№#]?\s*(\d+)', re.IGNORECASE),
        re.compile(r'store\w*\s*[№#]?\s*(\d+)', re.IGNORECASE),
        re.compile(r'\b(\d{3,5})\b.*(магазин|shop|store)', re.IGNORECASE),
        re.compile(r'(магазин|shop|store).*?\b(\d{3,5})\b', re.IGNORECASE),
        re.compile(r'ид\s*магазин\w*\s*(\d+)', re.IGNORECASE),
        re.compile(r'id\s*store\w*\s*(\d+)', re.IGNORECASE)
    ]
    
    _time_patterns = [
        re.compile(r'\d{4}-\d{2}-\d{2}'),
        re.compile(r'\d{2}\.\d{2}\.\d{4}'),
        re.compile(r'\d{4} год|\d{4} г'),
        re.compile(r'за\s+\d{4}|в\s+\d{4}'),
        re.compile(r'с\s+\d|по\s+\d'),
        re.compile(r'месяц|квартал|недел|день'),
        re.compile(r'период|время|дата'),
        re.compile(r'сегодня|вчера|недавн'),
        re.compile(r'последн\w+\s+\d+\s+(дн|мес|нед)'),
        re.compile(r'за\s+последн\w+\s+\d+\s+(дн|мес|нед)')
    ]
    
    def __init__(self):
        self.agent = self._initialize_agent()
    
    def _extract_llm_output_from_error(self, error_str: str) -> str:
        """Извлекает ответ LLM из строки ошибки парсинга"""
        try:
            # Ищем паттерн: "Could not parse LLM output: `...`"
            if "Could not parse LLM output:" in error_str:
                # Находим начало ответа (после "Could not parse LLM output: `")
                start_marker = "Could not parse LLM output: `"
                start_idx = error_str.find(start_marker)
                if start_idx != -1:
                    start_idx += len(start_marker)
                    # Ищем конец ответа - несколько вариантов
                    # Вариант 1: обратный апостроф перед "For troubleshooting"
                    end_marker = "`\nFor troubleshooting"
                    end_idx = error_str.find(end_marker, start_idx)
                    
                    # Вариант 2: обратный апостроф перед "For troubleshooting" (без переноса)
                    if end_idx == -1:
                        end_marker = "` For troubleshooting"
                        end_idx = error_str.find(end_marker, start_idx)
                    
                    # Вариант 3: просто последний обратный апостроф в строке
                    if end_idx == -1:
                        # Ищем последний обратный апостроф, но не в самом начале
                        last_backtick = error_str.rfind("`", start_idx + 100)  # Ищем после начала ответа
                        if last_backtick > start_idx:
                            end_idx = last_backtick
                    
                    if end_idx != -1 and end_idx > start_idx:
                        llm_output = error_str[start_idx:end_idx].strip()
                        # Убираем возможные лишние обратные апострофы в конце
                        llm_output = llm_output.rstrip('`').strip()
                        if llm_output and len(llm_output) > 20:  # Минимальная длина для валидного ответа
                            logger.info(f"Extracted LLM output from error ({len(llm_output)} chars)")
                            return llm_output
        except Exception as e:
            logger.warning(f"Failed to extract LLM output from error: {str(e)}")
        
        return None
    
    def _handle_parsing_error(self, error: Exception) -> str:
        """Кастомный обработчик ошибок парсинга LLM вывода"""
        error_str = str(error)
        logger.warning(f"LLM parsing error: {error_str}")
        
        # Пытаемся извлечь ответ LLM из ошибки
        llm_output = self._extract_llm_output_from_error(error_str)
        
        if llm_output:
            # Если удалось извлечь ответ, возвращаем его с предупреждением
            warning_message = (
                "\n\n⚠️ **Внимание:** Произошла ошибка при обработке ответа, "
                "но данные были успешно получены и представлены выше."
            )
            
            # Проверяем длину и обрезаем при необходимости
            max_length = 3500
            if len(llm_output + warning_message) > max_length:
                # Обрезаем ответ, оставляя место для предупреждения
                available_length = max_length - len(warning_message) - 50
                llm_output = llm_output[:available_length] + "\n\n... (ответ сокращен)"
            
            return llm_output + warning_message
        else:
            # Если не удалось извлечь ответ, возвращаем общее сообщение
            if "Could not parse LLM output" in error_str:
                return (
                    "Извините, произошла ошибка при обработке ответа. "
                    "Попробуйте переформулировать запрос или разбить его на более простые части."
                )
            elif "OUTPUT_PARSING_FAILURE" in error_str:
                return (
                    "Произошла ошибка форматирования ответа. "
                    "Попробуйте уточнить ваш запрос или задать его по-другому."
                )
            else:
                return (
                    "Произошла ошибка при обработке запроса. "
                    "Пожалуйста, попробуйте еще раз или переформулируйте вопрос."
                )
    
    def _initialize_agent(self):
        """Инициализация AI агента"""
        system_prompt = """
        You are a senior data analyst working with TWO databases: ClickHouse and PostgreSQL. You communicate with users in Russian but think in English for technical operations.
        The user does NOT specify which database to use — you must determine it from the Database_Schema search results: each table description includes "База данных: ClickHouse" or "База данных: PostgreSQL". Use ClickHouse_Query for ClickHouse tables and PostgreSQL_Query for PostgreSQL tables.

        IMPORTANT CONTEXT:
        - You are working in a Telegram bot environment
        - Telegram has strict message length limits (4096 characters)
        - Your responses MUST NOT exceed 3500 characters to avoid parsing errors and message truncation
        - If data is too large, summarize it or limit the number of rows shown
        - Prioritize key insights over exhaustive data listing

        TECHNICAL RULES (ENGLISH):
        1. Use Database_Schema first to find relevant tables; each result shows which database the table is in (База данных: ClickHouse / PostgreSQL).
        2. Use ClickHouse_Query for tables in ClickHouse (e.g. rees46.order_items). Use PostgreSQL_Query for tables in PostgreSQL (e.g. bulk_campaigns, campaign_recipients).
        3. Only SELECT/SHOW/DESCRIBE/EXPLAIN queries allowed in both databases
        4. No semicolons in SQL queries
        5. Present results as Markdown tables with STRICT formatting rules
        6. Create complex queries using: WITH alias_1 AS (query_1), alias_2 AS (query_2)  SELECT * FROM alias_1
        7. LIMIT query results to reasonable size (max 15-20 rows for tables) to keep response under 3500 characters

        CRITICAL: You MUST follow the ReAct format strictly:
        - Use "Action:" before calling a tool
        - Use "Action Input:" before providing tool input
        - Use "Final Answer:" when providing the final response to user
        - Always use proper tool names: ClickHouse_Query, PostgreSQL_Query, Database_Schema, Python_REPL
        - Do NOT skip the format - this will cause parsing errors
        - Keep "Final Answer:" responses concise and under 3500 characters total

        TABLE FORMATTING RULES (CRITICAL - MUST FOLLOW):
        - ALWAYS include ALL columns from the query result in the table - NEVER omit any columns
        - Use proper Markdown table syntax with aligned columns (| column | column |)
        - Format numbers: use space as thousands separator (e.g., 12 560.5 instead of 12560.5)
        - For currency/revenue: add "руб." or currency symbol in column header (e.g., "Выручка, руб.")
        - Keep column headers short but descriptive (max 25 characters per header)
        - Use emoji in table title for better readability:
          * 📊 for statistics/general data
          * 💰 for revenue/money
          * 📈 for trends/growth
          * 📉 for declines
          * 🛒 for orders/purchases
          * 👥 for clients/users
          * 📧 for emails/messages
        - ALWAYS show column headers even if data is empty
        - Round decimal numbers to 2 decimal places for readability (e.g., 12 560.50)
        - Use consistent formatting: dates as DD.MM.YYYY, numbers with spaces as separators
        - If user asks about "выручка" (revenue), "прибыль" (profit), "продажи" (sales) - ensure corresponding column is visible and properly formatted
        - Column names should be in Russian and match user's request (Выручка, Количество, Клиенты, Заказы, etc.)

        TABLE FORMAT EXAMPLE:
        ### 📊 Топ писем по выручке за последние 2 месяца (магазин 5028)

        | Код письма       | Тип рассылки        | Количество заказов | Выручка, руб. | Уникальные клиенты |
        |------------------|---------------------|-------------------|---------------|-------------------|
        | welcome_chain    | Триггерная цепочка  | 3                 | 12 560.50     | 3                 |
        | cart_abandoned_1 | Триггерная цепочка  | 2                 | 8 900.00      | 2                 |
        | new_year_promo   | Массовая рассылка   | 1                 | 5 400.00      | 1                 |

        CRITICAL TABLE REQUIREMENTS:
        - NEVER omit columns from the table - ALL columns from SQL result MUST be present
        - If user asks about "выручка" (revenue), make sure "Выручка" or "Выручка, руб." column is visible and properly formatted
        - Always include descriptive column headers that match what user requested
        - Format all numeric values consistently with space separators

        USER COMMUNICATION (RUSSIAN):
        1. Analyze the user's question and determine:
        - Is shop_id specified? If not, request it.
        - Is the time period specified? If not, request it.
        2. If the shop_id or period is not specified: politely request them from the user.
        3. Only when all the parameters are clear, create and execute an SQL query
        4. Present results in a well-formatted Markdown table with ALL columns from query result
        5. Keep tables concise: limit to top 15-20 rows if data is large
        6. Explain results clearly in Russian, but be BRIEF
        7. Provide insights and summaries in Russian, keep recommendations to 3-5 key points
        8. If query fails, explain the issue and next steps in Russian
        9. TOTAL RESPONSE LENGTH MUST NOT EXCEED 3500 CHARACTERS - this is critical for Telegram bot

        SECURITY:
        - STRICTLY FORBIDDEN: INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, GRANT
        - Validate all queries against schema first
        - Never invent or hallucinate data
        - ALL REQUESTS MUST CONTAIN FILTERS: SHOP_ID = specific store number and TIME PERIOD (date BETWEEN 'start date' AND 'end date'). DO NOT EXECUTE REQUESTS WITHOUT THESE FILTERS - this is protection against database overload

        EXAMPLE THINKING PROCESS:
        User: "покажи топ товаров"
        → Use Database_Schema to find tables (orders/items). If result says "База данных: ClickHouse" and table rees46.order_items → use ClickHouse_Query. If "База данных: PostgreSQL" → use PostgreSQL_Query.
        → Generate appropriate SQL (e.g. for ClickHouse: SELECT item_id, COUNT(*) FROM rees46.order_items GROUP BY item_id ORDER BY COUNT(*) DESC LIMIT 10)
        → Execute via the correct tool (ClickHouse_Query or PostgreSQL_Query)
        → Present table in Markdown with ALL columns, formatted numbers, emoji in title
        → Explain in Russian: "Вот топ-10 товаров по количеству покупок..."
        """
        
        tools = get_tools()
        
        return initialize_agent(
            tools=tools,
            llm=get_llm(),
            agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            verbose=False,  # В продакшене отключаем подробный вывод
            memory=None,
            handle_parsing_errors=True,  # Базовый обработчик включен
            max_iterations=settings.AGENT_MAX_ITERATIONS,  # Используем настройку из config
            early_stopping_method="generate",
            max_execution_time=settings.AGENT_MAX_EXECUTION_TIME,  # Ограничение времени выполнения
            agent_kwargs={
                "system_message": SystemMessage(content=system_prompt)
            }
        )
    
    def analyze_query_parameters(self, query: str) -> dict:
        """Анализирует запрос на наличие обязательных параметров"""
        analysis = {
            'has_shop_id': False,
            'has_time_period': False,
            'missing_parameters': [],
            'recommendation': ''
        }
        
        # Используем скомпилированные паттерны для поиска shop_id
        for pattern in self._shop_id_patterns:
            if pattern.search(query):
                analysis['has_shop_id'] = True
                break
        
        # Используем скомпилированные паттерны для временных периодов
        for pattern in self._time_patterns:
            if pattern.search(query):
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
    
    def format_table_response(self, response: str) -> str:
        """Улучшает форматирование таблиц в ответе агента"""
        # Находим все таблицы в ответе
        # Паттерн для поиска markdown таблиц
        table_pattern = r'(\|.*\|(?:\n\|[:\-\s\|]+\|)?(?:\n\|.*\|)*)'
        
        def format_table(match):
            table = match.group(1)
            lines = [line.strip() for line in table.strip().split('\n') if line.strip()]
            
            if len(lines) < 2:
                return table
            
            # Заголовок и разделитель
            header = lines[0]
            separator = lines[1] if len(lines) > 1 else ''
            
            # Форматируем строки данных
            formatted_lines = [header, separator]
            
            for line in lines[2:]:
                if not line.strip() or not line.startswith('|'):
                    continue
                
                # Разбиваем на ячейки (игнорируем первый и последний пустые элементы)
                cells = [cell.strip() for cell in line.split('|')[1:-1]]
                formatted_cells = []
                
                for cell in cells:
                    # Пробуем форматировать числа
                    try:
                        # Убираем пробелы и запятые, заменяем запятую на точку для парсинга
                        cell_clean = cell.replace(' ', '').replace(',', '.')
                        num = float(cell_clean)
                        
                        # Форматируем число
                        if abs(num) >= 1000:
                            # Большие числа: пробелы как разделители тысяч, запятая для десятичных
                            formatted = f"{num:,.2f}".replace(',', ' ').replace('.', ',')
                        elif abs(num) >= 1:
                            # Обычные числа: запятая для десятичных
                            formatted = f"{num:.2f}".replace('.', ',')
                        else:
                            # Малые числа
                            formatted = f"{num:.2f}".replace('.', ',')
                        
                        formatted_cells.append(formatted)
                    except (ValueError, AttributeError):
                        # Не число - оставляем как есть
                        formatted_cells.append(cell)
                
                # Собираем строку обратно
                formatted_line = '| ' + ' | '.join(formatted_cells) + ' |'
                formatted_lines.append(formatted_line)
            
            return '\n'.join(formatted_lines)
        
        # Заменяем все таблицы
        try:
            formatted_response = re.sub(table_pattern, format_table, response, flags=re.MULTILINE)
            return formatted_response
        except Exception as e:
            logger.warning(f"Table formatting error: {str(e)}, returning original response")
            return response
    
    @track_performance
    def process_query(self, query: str) -> str:
        """Обработка пользовательского запроса"""
        try:
            # Анализ параметров
            analysis = self.analyze_query_parameters(query)
            if analysis['missing_parameters']:
                return analysis['recommendation']
            
            # Получение схемы БД
            schema_info = schema_retriever(query)
            
            enhanced_prompt = f"""
            Пользовательский запрос: {query}

            Контекст схемы БД:
            {schema_info}

            Параметры запроса:
            - shop_id: {'УКАЗАН' if analysis['has_shop_id'] else 'НЕ УКАЗАН'}
            - временной период: {'УКАЗАН' if analysis['has_time_period'] else 'НЕ УКАЗАН'}

            INSTRUCTION: Use Database_Schema results to see which database each table is in ("База данных: ClickHouse" or "База данных: PostgreSQL"). Then use ClickHouse_Query for ClickHouse tables or PostgreSQL_Query for PostgreSQL tables. DO NOT invent or hallucinate data! Follow these steps:

            1. Analyze the user's question and database schema (and which database each table belongs to).
            2. Generate appropriate SQL query using available tables and columns for that database.
            3. ALWAYS turn on the filters where applicable:
               - WHERE shop_id = specified identifier
               - AND conditions by date (date BETWEEN or date >=/<=)
            4. Execute query using ClickHouse_Query (for ClickHouse) or PostgreSQL_Query (for PostgreSQL).
            5. Process and analyze the results.
            6. Present findings in Markdown table format with STRICT adherence to formatting rules:
               - Include ALL columns from query result - NEVER omit any columns
               - Format numbers with space as thousands separator (12 560.5)
               - Round decimals to 2 places (12 560.50)
               - Use descriptive Russian column headers (Выручка, Количество, Клиенты, etc.)
               - Add emoji to table title (📊, 💰, 📈, etc.)
               - If user asks about revenue/profit/sales - ensure corresponding column is visible
            7. Give the user recommendations in Russian as a marketer

            CRITICAL FORMATTING REQUIREMENTS:
            - ALL columns from SQL result MUST appear in the table - this is mandatory
            - If user asks about revenue/profit/sales (выручка/прибыль/продажи) - ensure corresponding column is visible
            - Use proper Russian column names (Выручка, Количество, Клиенты, Заказы, etc.)
            - Format currency values with "руб." in header and space separators in values
            - Numbers >= 1000 must have space separators (12 560.50, not 12560.5)
            - LIMIT table rows to 15-20 maximum to keep response under 3500 characters
            - If data is large, show only top results and mention "показаны топ N результатов"

            CRITICAL LENGTH REQUIREMENT:
            - Your ENTIRE response (including table, explanation, recommendations) MUST NOT exceed 3500 characters
            - This is a Telegram bot limitation - exceeding this will cause parsing errors
            - If response is too long: reduce table rows, shorten explanations, limit recommendations to 3-5 key points
            - Count characters carefully before sending "Final Answer:"

            CRITICAL: You are NOT allowed to answer based on assumptions. You MUST use the correct query tool (ClickHouse_Query or PostgreSQL_Query) according to the database indicated in the schema. If the query fails, analyze the error and try a different approach using the schema information.

            Generate the SQL query now and execute it through the appropriate tool.
            """
            
            # Исполнение запроса с обработкой ошибок парсинга
            try:
                result = self.agent.invoke({"input": enhanced_prompt})
                raw_response = result.get("output", "Не удалось получить ответ")
                
                # Применяем постобработку для улучшения форматирования таблиц
                formatted_response = self.format_table_response(raw_response)
                
                # Проверяем длину ответа и обрезаем при необходимости
                max_length = 3500  # Telegram limit is 4096, но оставляем запас для безопасности
                if len(formatted_response) > max_length:
                    logger.warning(f"Response too long ({len(formatted_response)} chars), truncating to {max_length}")
                    # Обрезаем до максимальной длины с предупреждением
                    truncated = formatted_response[:max_length - 100]  # Оставляем место для сообщения
                    formatted_response = truncated + "\n\n... (сообщение сокращено из-за ограничений Telegram)"
                
                return formatted_response
                
            except ValueError as ve:
                # Ошибки парсинга обычно выбрасываются как ValueError
                error_str = str(ve)
                if "Could not parse LLM output" in error_str or "OUTPUT_PARSING" in error_str:
                    logger.error(f"LLM output parsing error: {error_str}")
                    # Пытаемся извлечь полезную информацию из ответа агента
                    # Иногда агент все же возвращает частичный результат
                    try:
                        # Если есть частичный результат, пытаемся его использовать
                        if hasattr(self.agent, 'agent_executor'):
                            intermediate_steps = getattr(self.agent.agent_executor, 'intermediate_steps', [])
                            if intermediate_steps:
                                last_step = intermediate_steps[-1]
                                if isinstance(last_step, tuple) and len(last_step) > 0:
                                    last_output = str(last_step[0])
                                    if last_output and len(last_output) > 50:
                                        logger.info("Using partial result from intermediate steps")
                                        return f"Частичный результат:\n\n{last_output}\n\n⚠️ Произошла ошибка при завершении обработки. Попробуйте уточнить запрос."
                    except Exception:
                        pass
                    
                    return self._handle_parsing_error(ve)
                else:
                    # Другие ValueError - пробрасываем дальше
                    raise
                    
        except Exception as e:
            error_str = str(e)
            logger.error(f"Query processing error: {error_str}", exc_info=True)
            
            # Специальная обработка для ошибок парсинга
            if "Could not parse LLM output" in error_str or "OUTPUT_PARSING" in error_str:
                return self._handle_parsing_error(e)
            
            # Общая обработка ошибок
            return f"Произошла ошибка при обработке запроса: {error_str}"

# Глобальный инстанс аналитика
ai_analyst = AIAnalyst()
