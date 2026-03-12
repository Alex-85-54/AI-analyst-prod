"""Клиент PostgreSQL для выполнения read-only SQL-запросов."""
import re
import time
from typing import Union, Optional, List, Set
from hashlib import sha256

import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor

from app.utils.logging import logger
from app.utils.metrics import track_query_performance
from app.context import get_allowed_shop_ids
from config.settings import settings


def _is_pg_configured() -> bool:
    return bool(
        getattr(settings, "PG_HOST", None)
        and getattr(settings, "PG_USER", None)
        and getattr(settings, "PG_PASSWORD", None)
        and getattr(settings, "PG_DATABASE", None)
    )


class PostgresClient:
    def __init__(self):
        self._query_cache = {}
        self._cache_ttl = getattr(settings, "QUERY_CACHE_TTL", 300)

    def _get_conn_params(self):
        return {
            "host": settings.PG_HOST,
            "port": settings.PG_PORT,
            "user": settings.PG_USER,
            "password": settings.PG_PASSWORD,
            "dbname": settings.PG_DATABASE,
        }

    def _get_connection(self):
        """Создаёт новое подключение к PostgreSQL."""
        if not _is_pg_configured():
            raise RuntimeError("PostgreSQL is not configured (PG_HOST, PG_USER, PG_PASSWORD, PG_DATABASE).")
        try:
            return psycopg2.connect(**self._get_conn_params())
        except Exception as e:
            logger.error(f"PostgreSQL connection failed: {str(e)}")
            raise

    def _get_query_hash(self, query: str) -> str:
        return sha256(query.encode("utf-8")).hexdigest()

    def _cleanup_cache(self):
        current_time = time.time()
        expired_keys = [
            k for k, (_, ts) in self._query_cache.items()
            if current_time - ts > self._cache_ttl
        ]
        for k in expired_keys:
            del self._query_cache[k]

    def clean_sql_query(self, query: str) -> str:
        """Очищает SQL-запрос от маркеров кода."""
        q = re.sub(r"```sql\s*", "", query, flags=re.IGNORECASE)
        q = re.sub(r"```\s*", "", q)
        q = re.sub(r"^\s*sql\s*", "", q, flags=re.IGNORECASE)
        return q.strip()

    @track_query_performance(query_type="postgres")
    def execute_safe_query(self, query: str, use_cache: bool = True) -> Union[pd.DataFrame, str]:
        """Выполняет безопасные SQL-запросы только для чтения с кэшированием."""
        if not _is_pg_configured():
            return "PostgreSQL не настроен. Задайте PG_HOST, PG_USER, PG_PASSWORD, PG_DATABASE в .env."
        try:
            cleaned_query = self.clean_sql_query(query)

            validation_error = self._validate_query(cleaned_query)
            if validation_error:
                return validation_error

            if use_cache and cleaned_query.strip().upper().startswith("SELECT"):
                query_hash = self._get_query_hash(cleaned_query)
                if query_hash in self._query_cache:
                    cached_result, timestamp = self._query_cache[query_hash]
                    if time.time() - timestamp < self._cache_ttl:
                        logger.info(f"PostgreSQL cache hit for query: {cleaned_query[:100]}...")
                        return cached_result
                    del self._query_cache[query_hash]

            logger.info(f"Executing PostgreSQL query: {cleaned_query[:200]}...")
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(cleaned_query)
                    rows = cur.fetchall()
                    result = pd.DataFrame(rows)
            finally:
                conn.close()

            if len(result) == 0:
                return "Запрос выполнен успешно, но не вернул данных."

            if use_cache and cleaned_query.strip().upper().startswith("SELECT"):
                query_hash = self._get_query_hash(cleaned_query)
                self._query_cache[query_hash] = (result, time.time())
                if len(self._query_cache) > getattr(settings, "MAX_QUERY_CACHE_SIZE", 1000):
                    self._cleanup_cache()

            return result

        except Exception as e:
            error_msg = f"PostgreSQL query error: {str(e)}"
            logger.error(error_msg)
            return error_msg

    def _extract_shop_ids_from_query(self, query: str) -> Set[int]:
        """Извлекает все числовые значения shop_id из запроса."""
        ids: Set[int] = set()
        for m in re.finditer(r"shop_id\s*=\s*(\d+)", query, re.IGNORECASE):
            ids.add(int(m.group(1)))
        for m in re.finditer(r"shop_id\s+IN\s*\(\s*([^)]+)\s*\)", query, re.IGNORECASE):
            for part in re.split(r"[\s,]", m.group(1)):
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
            logger.warning(f"PostgreSQL query uses disallowed shop_id(s): {forbidden}")
            return "Error: Доступ запрещён к указанным магазинам. Используйте только разрешённые shop_id."
        return None

    def _validate_query(self, query: str) -> Optional[str]:
        """Валидация SQL-запроса (только чтение)."""
        forbidden = [
            "insert", "update", "delete", "drop", "alter", "create",
            "grant", "truncate", "copy", "reindex", "vacuum"
        ]
        qlower = query.lower()
        if any(re.search(rf"\b{k}\b", qlower) for k in forbidden):
            return "Error: Prohibited operation"

        if not re.match(r"^\s*(select|with|show|explain)", query, re.IGNORECASE):
            return "Error: Read-only requests are allowed"

        allowed = get_allowed_shop_ids()
        if allowed is not None:
            shop_err = self._validate_shop_ids(query, allowed)
            if shop_err:
                return shop_err
        return None


postgres_client = PostgresClient()
