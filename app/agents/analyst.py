from langchain.agents import AgentExecutor, initialize_agent
from langchain.agents.agent_types import AgentType
from langchain.schema import SystemMessage
from langchain_openai import ChatOpenAI
from NEW.app.agents.tools import get_tools, schema_retriever
from NEW.app.utils.logging import logger
from NEW.config.settings import settings
import re

class AIAnalyst:
    def __init__(self):
        self.agent = self._initialize_agent()
    
    def _initialize_agent(self):
        """Инициализация AI агента"""
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
        
        tools = get_tools()
        
        return initialize_agent(
            tools=tools,
            llm=ChatOpenAI(
                api_key=settings.API_KEY_DEEPSEEK,
                base_url=settings.DEEPSEEK_BASE_URL,
                model="deepseek-chat",
                temperature=0.1,
                timeout=settings.REQUEST_TIMEOUT
            ),
            agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            verbose=False,  # В продакшене отключаем подробный вывод
            memory=None,
            handle_parsing_errors=True,
            max_iterations=5,
            early_stopping_method="generate",
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
            
            # Исполнение запроса
            result = self.agent.invoke({"input": enhanced_prompt})
            return result.get("output", "Не удалось получить ответ")
            
        except Exception as e:
            logger.error(f"Query processing error: {str(e)}")
            return f"Произошла ошибка при обработке запроса: {str(e)}"

# Глобальный инстанс аналитика
ai_analyst = AIAnalyst()