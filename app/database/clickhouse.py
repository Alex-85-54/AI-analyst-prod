import clickhouse_connect
import re
from typing import Union, Optional
import pandas as pd
from app.utils.logging import logger
from config.settings import settings

class ClickHouseClient:
    def __init__(self):
        self.client = self._connect()
    
    def _connect(self):
        """Подключение к ClickHouse с ретраями"""
        try:
            client = clickhouse_connect.get_client(
                host=settings.CH_HOST,
                port=settings.CH_PORT,
                username=settings.CH_USER,
                password=settings.CH_PASSWORD
            )
            logger.info("Successfully connected to ClickHouse")
            return client
        except Exception as e:
            logger.error(f"ClickHouse connection failed: {str(e)}")
            raise
    
    def clean_sql_query(self, query: str) -> str:
        """Очищает SQL-запрос от маркеров кода"""
        q = re.sub(r'```sql\s*', '', query, flags=re.IGNORECASE)
        q = re.sub(r'```\s*', '', q)
        q = re.sub(r'^\s*sql\s*', '', q, flags=re.IGNORECASE)
        return q.strip()
    
    def auto_correct_table_names(self, query: str) -> str:
        """Автоматически добавляет 'rees46.' к именам таблиц"""
        tables = [
            'also_viewed', 'bulk_messages', 'bulk_messages_hot', 'chain_messages',
            'events', 'order_items', 'popup_events', 'search_events', 'story_events'
        ]
        
        corrected_query = query
        for table in tables:
            pattern = rf'(?<!rees46\.)\b({table})\b'
            replacement = f'rees46.{table}'
            corrected_query = re.sub(pattern, replacement, corrected_query, flags=re.IGNORECASE)
        
        if corrected_query != query:
            logger.info(f"Query auto-corrected: {query[:100]}...")
        
        return corrected_query
    
    def execute_safe_query(self, query: str) -> Union[pd.DataFrame, str]:
        """Выполняет безопасные SQL-запросы только для чтения"""
        try:
            # Очистка и коррекция запроса
            cleaned_query = self.clean_sql_query(query)
            corrected_query = self.auto_correct_table_names(cleaned_query)
            
            # Валидация запроса
            validation_error = self._validate_query(corrected_query)
            if validation_error:
                return validation_error
            
            # Выполнение запроса
            logger.info(f"Executing query: {corrected_query[:200]}...")
            result = self.client.query_df(corrected_query)
            
            if len(result) == 0:
                return "Запрос выполнен успешно, но не вернул данных."
            
            return result
            
        except Exception as e:
            error_msg = f"Database query error: {str(e)}"
            logger.error(error_msg)
            return error_msg
    
    def _validate_query(self, query: str) -> Optional[str]:
        """Валидация SQL-запроса"""
        forbidden_keywords = ['insert', 'update', 'delete', 'drop', 'alter', 'create', 'grant']
        if any(re.search(rf'\b{kw}\b', query.lower()) for kw in forbidden_keywords):
            return "Error: Prohibited operation"
        
        if not re.match(r'^\s*(select|show|describe|with|explain)', query, re.IGNORECASE):
            return "Error: Read-only requests are allowed"
        
        return None

# Глобальный инстанс клиента
clickhouse_client = ClickHouseClient()
