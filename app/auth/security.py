import json
import os
import time
from typing import Dict, Any, Optional
from app.utils.logging import logger
from config.settings import settings

class SecurityManager:
    """Менеджер безопасности и авторизации с загрузкой из JSON файла"""
    
    def __init__(self):
        self.allowed_users = {}
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
        """Загружает список разрешенных пользователей из JSON файла"""
        try:
            if not os.path.exists(self.config_path):
                logger.warning(f"Auth config file not found: {self.config_path}")
                self.allowed_users = {}
                return
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Валидация структуры данных
            validated_data = {}
            for user_id_str, user_data in data.items():
                if isinstance(user_data, dict):
                    validated_data[user_id_str] = user_data
                else:
                    logger.warning(f"Invalid user data format for user {user_id_str}")
            
            self.allowed_users = validated_data
            self.last_modified = self._get_file_modification_time()
            
            logger.info(f"Loaded {len(self.allowed_users)} allowed users from {self.config_path}")
            
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing auth config file {self.config_path}: {str(e)}")
            self.allowed_users = {}
        except Exception as e:
            logger.error(f"Error loading auth config file {self.config_path}: {str(e)}")
            self.allowed_users = {}
    
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
        """Получение информации о пользователе"""
        self._check_reload()
        return self.allowed_users.get(str(user_id))
    
    def get_all_users(self) -> Dict[str, Any]:
        """Получение списка всех пользователей (для админки)"""
        self._check_reload()
        return self.allowed_users.copy()

# Глобальный инстанс менеджера безопасности
security_manager = SecurityManager()

# Функции для импорта
def is_user_authorized(user_id: int, username: Optional[str] = None) -> bool:
    return security_manager.is_user_authorized(user_id, username)

def get_user_info(user_id: int) -> Optional[Dict[str, Any]]:
    return security_manager.get_user_info(user_id)

def get_all_users() -> Dict[str, Any]:
    return security_manager.get_all_users()
