"""
Утилита для управления пользователями
"""
import json
import sys
import os
from typing import Dict, Any

def load_users(file_path: str) -> Dict[str, Any]:
    """Загружает пользователей из файла"""
    if not os.path.exists(file_path):
        return {}
    
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_users(file_path: str, users: Dict[str, Any]) -> None:
    """Сохраняет пользователей в файл"""
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def add_user(file_path: str, user_id: str, username: str, name: str, role: str = "user", shop_ids: list = None):
    """Добавляет нового пользователя.

    Поведение:
    - shop_ids == []  → доступ ко всем магазинам из all_shop_ids в конфиге
    - shop_ids == None → считается ошибкой (некорректный shop_id)
    """
    users = load_users(file_path)
    if user_id in users:
        print(f"❌ Пользователь с ID {user_id} уже существует!")
        return False

    if shop_ids is None:
        print("❌ Некорректный shop_id. Укажите явный список ID магазинов или 'all'/'все' для доступа ко всем.")
        return False

    effective_ids = shop_ids
    users[user_id] = {
        "username": username.lstrip('@'),
        "name": name,
        "role": role,
        "shop_ids": effective_ids,
        "is_active": True
    }
    save_users(file_path, users)
    label = "все магазины" if effective_ids == [] else str(effective_ids)
    print(f"✅ Пользователь {name} (@{username}) добавлен с ID {user_id}, магазины: {label}")
    return True

ALL_SHOP_IDS_KEY = "all_shop_ids"


def list_users(file_path: str):
    """Выводит список всех пользователей (запись all_shop_ids в файле не выводится как пользователь)."""
    users = load_users(file_path)
    if not users:
        print("❌ Нет пользователей в базе")
        return
    print("📋 Список пользователей:")
    for user_id, user_data in users.items():
        if user_id == ALL_SHOP_IDS_KEY or not isinstance(user_data, dict):
            continue
        status = "✅" if user_data.get('is_active', True) else "❌"
        shops = user_data.get('shop_ids', [])
        shops_label = "все (из all_shop_ids)" if shops == [] else shops
        print(f"  {status} ID: {user_id}")
        print(f"     Имя: {user_data.get('name', 'Не указано')}")
        print(f"     Username: @{user_data.get('username', 'Не указан')}")
        print(f"     Роль: {user_data.get('role', 'user')}")
        print(f"     Магазины: {shops_label}")
        print()

def main():
    file_path = "allowed_users.json"
    
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python user_manager.py list - показать всех пользователей")
        print("  python user_manager.py add <user_id> <username> <name> [role] [shop_ids] - добавить пользователя")
        return
    
    command = sys.argv[1]
    
    if command == "list":
        list_users(file_path)
    
    elif command == "add":
        if len(sys.argv) < 5:
            print("Использование: python user_manager.py add <user_id> <username> <name> [role] [shop_ids]")
            return
        
        user_id = sys.argv[2]
        username = sys.argv[3]
        name = sys.argv[4]
        role = sys.argv[5] if len(sys.argv) > 5 else "user"
        if len(sys.argv) <= 6:
            shop_ids = None
        elif sys.argv[6].strip().lower() in ("", "all", "все"):
            shop_ids = []
        else:
            shop_ids = [int(x) for x in sys.argv[6].split(',')]
        add_user(file_path, user_id, username, name, role, shop_ids)
    
    else:
        print(f"❌ Неизвестная команда: {command}")

if __name__ == "__main__":
    main()