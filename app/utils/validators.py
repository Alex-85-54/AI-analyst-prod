<<<<<<< HEAD
import re
from typing import Tuple, Optional

class QueryValidator:
    """Валидатор пользовательских запросов"""
    
    @staticmethod
    def validate_shop_id(shop_id: str) -> Tuple[bool, Optional[str]]:
        """Валидация shop_id"""
        if not shop_id:
            return False, "Shop ID не может быть пустым"
        
        if not re.match(r'^\d+$', str(shop_id)):
            return False, "Shop ID должен содержать только цифры"
        
        shop_num = int(shop_id)
        if shop_num <= 0:
            return False, "Shop ID должен быть положительным числом"
        
        if shop_num > 99999:
            return False, "Shop ID слишком большой"
        
        return True, None
    
    @staticmethod
    def validate_date_range(date_str: str) -> Tuple[bool, Optional[str]]:
        """Базовая валидация формата даты"""
        date_patterns = [
            r'^\d{4}$',  # Год: 2024
            r'^\d{4}-\d{2}$',  # Год-месяц: 2024-01
            r'^\d{4}-\d{2}-\d{2}$',  # Полная дата: 2024-01-15
            r'^\d{2}\.\d{2}\.\d{4}$',  # Русский формат: 15.01.2024
        ]
        
        for pattern in date_patterns:
            if re.match(pattern, date_str):
                return True, None
        
        return False, "Неверный формат даты. Используйте: ГГГГ, ГГГГ-ММ, ГГГГ-ММ-ДД"
    
    @staticmethod
    def sanitize_input(text: str) -> str:
        """Очистка пользовательского ввода от потенциально опасных символов"""
        # Удаляем или экранируем специальные символы
        sanitized = re.sub(r'[;\'"\\/*]', '', text)
        return sanitized.strip()
    
    @staticmethod
    def validate_query_complexity(query: str) -> Tuple[bool, Optional[str]]:
        """Проверка сложности запроса (защита от слишком тяжелых запросов)"""
        # Слишком длинный запрос
        if len(query) > 1000:
            return False, "Запрос слишком длинный"
        
        # Слишком много условий (простейшая эвристика)
        condition_indicators = [' AND ', ' OR ', ' WHERE ', ' JOIN ', ' GROUP BY ', ' ORDER BY ']
        condition_count = sum(1 for indicator in condition_indicators if indicator in query.upper())
        
        if condition_count > 8:
            return False, "Слишком сложный запрос. Упростите условия."
        
        return True, None

# Глобальный инстанс валидатора
=======
import re
from typing import Tuple, Optional
from app.utils.logging import logger

class QueryValidator:
    """Валидатор пользовательских запросов"""
    
    @staticmethod
    def validate_shop_id(shop_id: str) -> Tuple[bool, Optional[str]]:
        """Валидация shop_id"""
        if not shop_id:
            return False, "Shop ID не может быть пустым"
        
        if not re.match(r'^\d+$', str(shop_id)):
            return False, "Shop ID должен содержать только цифры"
        
        shop_num = int(shop_id)
        if shop_num <= 0:
            return False, "Shop ID должен быть положительным числом"
        
        if shop_num > 99999:
            return False, "Shop ID слишком большой"
        
        return True, None
    
    @staticmethod
    def validate_date_range(date_str: str) -> Tuple[bool, Optional[str]]:
        """Базовая валидация формата даты"""
        date_patterns = [
            r'^\d{4}$',  # Год: 2024
            r'^\d{4}-\d{2}$',  # Год-месяц: 2024-01
            r'^\d{4}-\d{2}-\d{2}$',  # Полная дата: 2024-01-15
            r'^\d{2}\.\d{2}\.\d{4}$',  # Русский формат: 15.01.2024
        ]
        
        for pattern in date_patterns:
            if re.match(pattern, date_str):
                return True, None
        
        return False, "Неверный формат даты. Используйте: ГГГГ, ГГГГ-ММ, ГГГГ-ММ-ДД"
    
    @staticmethod
    def sanitize_input(text: str) -> str:
        """Очистка пользовательского ввода от потенциально опасных символов"""
        # Удаляем или экранируем специальные символы
        sanitized = re.sub(r'[;\'"\\/*]', '', text)
        return sanitized.strip()
    
    @staticmethod
    def validate_query_complexity(query: str) -> Tuple[bool, Optional[str]]:
        """Проверка сложности запроса (защита от слишком тяжелых запросов)"""
        # Слишком длинный запрос
        if len(query) > 1000:
            return False, "Запрос слишком длинный"
        
        # Слишком много условий (простейшая эвристика)
        condition_indicators = [' AND ', ' OR ', ' WHERE ', ' JOIN ', ' GROUP BY ', ' ORDER BY ']
        condition_count = sum(1 for indicator in condition_indicators if indicator in query.upper())
        
        if condition_count > 8:
            return False, "Слишком сложный запрос. Упростите условия."
        
        return True, None

# Глобальный инстанс валидатора
>>>>>>> 43781fe (Локальные изменения перед синхронизацией с develop)
query_validator = QueryValidator()