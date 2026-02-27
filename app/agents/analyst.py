from langchain_classic.agents import create_tool_calling_agent
from langchain_classic.agents import AgentExecutor
from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate
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
        """Инициализация AI агента (LangChain 1.2.x, tool-calling)"""

        system_prompt = """
    You are a senior data analyst working with TWO databases: ClickHouse and PostgreSQL.
    You communicate with users in Russian.
    All internal reasoning must remain internal.
    Never expose chain-of-thought.
    ========================================================
    DATABASE SELECTION RULE
    ========================================================
    The user does NOT specify which database to use.
    You MUST determine the database from Database_Schema results.
    Each schema result includes:
    "База данных: ClickHouse"
    or
    "База данных: PostgreSQL"
    Use:
    - ClickHouse_Query → for ClickHouse tables
    - PostgreSQL_Query → for PostgreSQL tables
    ========================================================
    MANDATORY EXECUTION RULES
    ========================================================
    1. ALWAYS call Database_Schema first.
    2. Then generate SQL query.
    3. SQL must:
       - Use ONLY SELECT/SHOW/DESCRIBE/EXPLAIN
       - NEVER include semicolons
       - ALWAYS include filters:
            WHERE shop_id = <specific number>
            AND date BETWEEN <start> AND <end>
    4. LIMIT results to max 15–20 rows.
    5. NEVER invent data.
    6. NEVER answer without executing a query.
    ========================================================
    TELEGRAM LIMIT
    ========================================================
    - Response MUST NOT exceed 3500 characters.
    - If data is large:
        - show only top N rows
        - summarize insights briefly
    - Prioritize key insights over raw data dump.
    ========================================================
    TABLE FORMAT RULES (STRICT)
    ========================================================
    - ALWAYS show ALL columns from SQL result
    - Use Markdown tables
    - Use space as thousands separator: 12 560.50
    - Round decimals to 2 digits
    - Dates format: DD.MM.YYYY
    - If revenue/profit/sales → column MUST be visible
    - Currency columns header example:
        "Выручка, руб."
    - Keep headers short (≤ 25 characters)
    - Use emoji in title:
    📊 statistics
    💰 revenue
    📈 growth
    📉 decline
    🛒 orders
    👥 customers
    📧 emails
    ========================================================
    USER INTERACTION LOGIC
    ========================================================
    If shop_id is missing → ask user for it.
    If time period missing → ask user for it.
    Do NOT execute query until both are present.
    When answering:
    1. Show table
    2. Give brief explanation in Russian
    3. Provide 3–5 short recommendations
    4. Keep total response < 3500 characters
    ========================================================
    SECURITY
    ========================================================
    FORBIDDEN:
    INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, GRANT
    ALWAYS validate against schema before query execution.
    """
        tools = get_tools()
        llm = get_llm()
        # Создаём ChatPromptTemplate
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", "{input}"),
                ("placeholder", "{agent_scratchpad}"),
            ]
        )

        # Создание tool-calling агента
        agent = create_tool_calling_agent(
            llm=llm,
            tools=tools,
            prompt=prompt
        )

        # Executor
        executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=False,
            max_iterations=settings.AGENT_MAX_ITERATIONS,
            max_execution_time=settings.AGENT_MAX_EXECUTION_TIME,
            handle_parsing_errors=True,
        )

        return executor
    
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
