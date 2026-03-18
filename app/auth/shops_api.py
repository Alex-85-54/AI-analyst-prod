"""Получение списка доступных shop_id по Telegram user_id через internal API."""

from __future__ import annotations

import ast
from typing import List, Optional

import httpx

from app.utils.logging import logger
from config.settings import settings


async def fetch_shops_by_telegram_user_id(telegram_user_id: int) -> Optional[List[int]]:
    """
    Возвращает список shop_id для Telegram user_id.

    По требованиям:
    - метод отдаёт list (может быть JSON-массив или строковое представление списка)
    - без заголовков/токенов
    - если вернул [] или None — считаем, что доступа к данным нет
    """
    base = getattr(settings, "SHOPS_API_BASE_URL", "https://app.rees46.ru/api/internal")
    timeout_sec = float(getattr(settings, "SHOPS_API_TIMEOUT", 10.0))
    url = f"{base.rstrip('/')}/shops-by-telegram/{int(telegram_user_id)}"

    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            resp = await client.get(url)
        resp.raise_for_status()

        # Вариант 1: JSON-массив
        try:
            data = resp.json()
        except Exception:
            data = None

        # Вариант 2: "python list" как строка
        if data is None:
            text = (resp.text or "").strip()
            if not text:
                return None
            try:
                data = ast.literal_eval(text)
            except Exception as e:
                logger.warning(f"shops_api: failed to parse response as list: {e}; text={text[:200]!r}")
                return None

        if not isinstance(data, list):
            logger.warning(f"shops_api: unexpected response type: {type(data).__name__}")
            return None

        out: List[int] = []
        for x in data:
            try:
                out.append(int(x))
            except Exception:
                continue
        return out

    except httpx.HTTPStatusError as e:
        logger.error(f"shops_api: HTTP error {e.response.status_code} for {url}")
        return None
    except httpx.RequestError as e:
        logger.error(f"shops_api: request error for {url}: {e}")
        return None
    except Exception as e:
        logger.error(f"shops_api: unexpected error for {url}: {e}")
        return None

