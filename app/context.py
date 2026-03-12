"""Контекст запроса: разрешённые shop_id для проверки при выполнении SQL; последний DataFrame для экспорта."""
from contextvars import ContextVar
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

# Список shop_id, которые разрешены для текущего запроса (устанавливается в handler/analyst).
allowed_shop_ids_ctx: ContextVar[Optional[List[int]]] = ContextVar(
    "allowed_shop_ids", default=None
)

# Последний успешный DataFrame из инструментов ClickHouse_Query / PostgreSQL_Query (для PNG и Excel).
last_query_df_ctx: ContextVar[Optional["pd.DataFrame"]] = ContextVar(
    "last_query_df", default=None
)


def set_allowed_shop_ids(shop_ids: Optional[List[int]]) -> None:
    """Установить список разрешённых shop_id для текущего контекста выполнения."""
    allowed_shop_ids_ctx.set(shop_ids)


def get_allowed_shop_ids() -> Optional[List[int]]:
    """Получить список разрешённых shop_id (None = проверка не требуется)."""
    return allowed_shop_ids_ctx.get()


def set_last_query_df(df: Optional["pd.DataFrame"]) -> None:
    """Сохранить последний успешный DataFrame из запроса к БД (для PNG и Excel)."""
    last_query_df_ctx.set(df)


def get_last_query_df() -> Optional["pd.DataFrame"]:
    """Получить последний успешный DataFrame (в контексте текущего потока)."""
    return last_query_df_ctx.get()
