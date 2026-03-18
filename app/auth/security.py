import json
import os
import time
from typing import Dict, Any, Optional
from app.utils.logging import logger
from config.settings import settings

class SecurityManager:
    """Менеджер безопасности и авторизации с загрузкой из JSON файла"""

    # Исторический ключ в JSON для общего списка всех магазинов.
    # В текущей версии список магазинов берётся из internal API shops-by-telegram/<user_id>.
    ALL_SHOP_IDS_KEY = "all_shop_ids"

    def __init__(self):
        self.allowed_users = {}
        self.all_shop_ids: list = []
        self.last_modified = 0
        self.config_path = settings.AUTH_CONFIG_PATH
        self._load_allowed_users()

    def _get_file_modification_time(self) -> float:
        """Получает время последнего изменения файла"""
        try:
            return os.path.getmtime(self.config_path)
        except OSError:
            return 0

    def _load_allowed_users(self) -> None:
        """Загружает список разрешенных пользователей из JSON файла."""
        try:
            if not os.path.exists(self.config_path):
                logger.warning(f"Auth config file not found: {self.config_path}")
                self.allowed_users = {}
                self.all_shop_ids = []
                return

            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Общий список магазинов (корневой ключ all_shop_ids)
            raw_all = data.get(self.ALL_SHOP_IDS_KEY)
            if isinstance(raw_all, list):
                self.all_shop_ids = [int(x) for x in raw_all if str(x).isdigit()]
            else:
                self.all_shop_ids = []

            # Валидация: только записи пользователей (ключ — числовой user_id), без all_shop_ids
            validated_data = {}
            for user_id_str, user_data in data.items():
                if user_id_str == self.ALL_SHOP_IDS_KEY:
                    continue
                if isinstance(user_data, dict):
                    validated_data[user_id_str] = user_data
                else:
                    logger.warning(f"Invalid user data format for user {user_id_str}")

            self.allowed_users = validated_data
            self.last_modified = self._get_file_modification_time()

            logger.info(f"Loaded {len(self.allowed_users)} allowed users, all_shop_ids count={len(self.all_shop_ids)} from {self.config_path}")

        except json.JSONDecodeError as e:
            logger.error(f"Error parsing auth config file {self.config_path}: {str(e)}")
            self.allowed_users = {}
            self.all_shop_ids = []
        except Exception as e:
            logger.error(f"Error loading auth config file {self.config_path}: {str(e)}")
            self.allowed_users = {}
            self.all_shop_ids = []
    
    def _check_reload(self) -> None:
        """Проверяет, нужно ли перезагрузить конфигурацию (если файл изменился)"""
        current_modified = self._get_file_modification_time()
        if current_modified > self.last_modified:
            logger.info("Auth config file changed, reloading...")
            self._load_allowed_users()
    
    def is_user_authorized(self, user_id: int, username: Optional[str] = None) -> bool:
        """Проверка авторизации пользователя с авто-перезагрузкой конфига"""
        self._check_reload()
        
        user_id_str = str(user_id)
        
        # Проверка по user_id
        if user_id_str in self.allowed_users:
            logger.debug(f"User {user_id} authorized by user_id")
            return True
        
        # Проверка по username (если указан)
        if username:
            username_clean = username.lower().lstrip('@')
            for allowed_id, user_data in self.allowed_users.items():
                if user_data.get('username', '').lower().lstrip('@') == username_clean:
                    logger.debug(f"User {user_id} authorized by username @{username}")
                    return True
        
        logger.warning(f"Unauthorized access attempt: user_id={user_id}, username={username}")
        return False
    
    def get_user_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение информации о пользователе по user_id"""
        self._check_reload()
        return self.allowed_users.get(str(user_id))

    def get_user_info_for_authorized(
        self, user_id: int, username: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Получение информации о пользователе для авторизованного (по user_id или username)."""
        self._check_reload()
        info = self.allowed_users.get(str(user_id))
        if info is not None:
            return info
        if not username:
            return None
        username_clean = username.lower().lstrip("@")
        for _, user_data in self.allowed_users.items():
            if isinstance(user_data, dict) and user_data.get("username", "").lower().lstrip("@") == username_clean:
                return user_data
        return None
    
    def get_all_users(self) -> Dict[str, Any]:
        """Получение списка всех пользователей (для админки)"""
        self._check_reload()
        return self.allowed_users.copy()

    def get_all_shop_ids(self) -> list:
        """Общий список всех магазинов из конфига. Пустой shop_ids у пользователя = доступ ко всем из этого списка."""
        self._check_reload()
        return list(self.all_shop_ids)

# Глобальный инстанс менеджера безопасности
security_manager = SecurityManager()

# Функции для импорта
def is_user_authorized(user_id: int, username: Optional[str] = None) -> bool:
    return security_manager.is_user_authorized(user_id, username)

def get_user_info(user_id: int) -> Optional[Dict[str, Any]]:
    return security_manager.get_user_info(user_id)


def get_user_info_for_authorized(
    user_id: int, username: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Возвращает данные пользователя из allowed_users по user_id или username."""
    return security_manager.get_user_info_for_authorized(user_id, username)

def get_all_users() -> Dict[str, Any]:
    return security_manager.get_all_users()


def get_all_shop_ids() -> list:
    """Список всех магазинов из конфига. Для пользователей с пустым shop_ids подставляется этот список."""
    return security_manager.get_all_shop_ids()
