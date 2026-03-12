import clickhouse_connect
import re
import time
from typing import Union, Optional, List, Set
from hashlib import sha256
import pandas as pd
from app.utils.logging import logger
from app.utils.metrics import track_query_performance
from app.context import get_allowed_shop_ids
from config.settings import settings

class ClickHouseClient:
    def __init__(self):
        self.client = self._connect()
        self._query_cache = {}
        self._cache_ttl = settings.QUERY_CACHE_TTL
    
    def _connect(self):
        """Подключение к ClickHouse с оптимизированными настройками"""
        try:
            client = clickhouse_connect.get_client(
                host=settings.CH_HOST,
                port=settings.CH_PORT,
                username=settings.CH_USER,
                password=settings.CH_PASSWORD,
                # Оптимизации
                connect_timeout=10,
                send_receive_timeout=300,
                # Используем сжатие для больших результатов
                compression=True,
            )
            logger.info("Successfully connected to ClickHouse")
            return client
        except Exception as e:
            logger.error(f"ClickHouse connection failed: {str(e)}")
            raise
    
    def _get_query_hash(self, query: str) -> str:
        """Генерация хеша запроса для кэширования"""
        return sha256(query.encode('utf-8')).hexdigest()
    
    def _cleanup_cache(self):
        """Очистка устаревших записей из кэша"""
        current_time = time.time()
        expired_keys = [
            key for key, (_, timestamp) in self._query_cache.items()
            if current_time - timestamp > self._cache_ttl
        ]
        for key in expired_keys:
            del self._query_cache[key]
    
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
    
    @track_query_performance(query_type="clickhouse")
    def execute_safe_query(self, query: str, use_cache: bool = True) -> Union[pd.DataFrame, str]:
        """Выполняет безопасные SQL-запросы только для чтения с кэшированием"""
        try:
            # Очистка и коррекция запроса
            cleaned_query = self.clean_sql_query(query)
            corrected_query = self.auto_correct_table_names(cleaned_query)
            
            # Валидация запроса
            validation_error = self._validate_query(corrected_query)
            if validation_error:
                return validation_error
            
            # Проверка кэша (только для SELECT запросов)
            if use_cache and corrected_query.strip().upper().startswith('SELECT'):
                query_hash = self._get_query_hash(corrected_query)
                if query_hash in self._query_cache:
                    cached_result, timestamp = self._query_cache[query_hash]
                    if time.time() - timestamp < self._cache_ttl:
                        logger.info(f"Cache hit for query: {corrected_query[:100]}...")
                        return cached_result
                    else:
                        del self._query_cache[query_hash]
            
            # Выполнение запроса
            logger.info(f"Executing query: {corrected_query[:200]}...")
            result = self.client.query_df(corrected_query)
            
            if len(result) == 0:
                return "Запрос выполнен успешно, но не вернул данных."
            
            # Сохранение в кэш
            if use_cache and corrected_query.strip().upper().startswith('SELECT'):
                query_hash = self._get_query_hash(corrected_query)
                self._query_cache[query_hash] = (result, time.time())
                # Очистка старых записей (если кэш слишком большой)
                if len(self._query_cache) > settings.MAX_QUERY_CACHE_SIZE:
                    self._cleanup_cache()
            
            return result
            
        except Exception as e:
            error_msg = f"Database query error: {str(e)}"
            logger.error(error_msg)
            return error_msg
    
    def _extract_shop_ids_from_query(self, query: str) -> Set[int]:
        """Извлекает все числовые значения shop_id из запроса (shop_id = N или shop_id IN (N, ...))."""
        ids: Set[int] = set()
        # shop_id = 123 или shop_id=123
        for m in re.finditer(r'shop_id\s*=\s*(\d+)', query, re.IGNORECASE):
            ids.add(int(m.group(1)))
        # shop_id IN (123, 456) или shop_id in (123)
        for m in re.finditer(r'shop_id\s+IN\s*\(\s*([^)]+)\s*\)', query, re.IGNORECASE):
            for part in re.split(r'[\s,]', m.group(1)):
                part = part.strip()
                if part.isdigit():
                    ids.add(int(part))
        return ids

    def _validate_shop_ids(self, query: str, allowed: List[int]) -> Optional[str]:
        """Проверяет, что все shop_id в запросе входят в разрешённый список."""
        if not allowed:
            return None
        allowed_set = set(int(x) for x in allowed)
        found = self._extract_shop_ids_from_query(query)
        if not found:
            return "Error: Запрос должен содержать фильтр по shop_id (WHERE shop_id = ... или shop_id IN (...))."
        forbidden = found - allowed_set
        if forbidden:
            logger.warning(f"Query uses disallowed shop_id(s): {forbidden}")
            return "Error: Доступ запрещён к указанным магазинам. Используйте только разрешённые shop_id."
        return None

    def _validate_query(self, query: str) -> Optional[str]:
        """Валидация SQL-запроса"""
        forbidden_keywords = ['insert', 'update', 'delete', 'drop', 'alter', 'create', 'grant']
        if any(re.search(rf'\b{kw}\b', query.lower()) for kw in forbidden_keywords):
            return "Error: Prohibited operation"
        
        if not re.match(r'^\s*(select|show|describe|with|explain)', query, re.IGNORECASE):
            return "Error: Read-only requests are allowed"
        
        allowed = get_allowed_shop_ids()
        if allowed is not None:
            shop_err = self._validate_shop_ids(query, allowed)
            if shop_err:
                return shop_err
        return None

# Глобальный инстанс клиента
clickhouse_client = ClickHouseClient()
