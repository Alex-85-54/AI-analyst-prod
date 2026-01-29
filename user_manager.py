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
    """Добавляет нового пользователя"""
    users = load_users(file_path)
    
    if user_id in users:
        print(f"❌ Пользователь с ID {user_id} уже существует!")
        return False
    
    users[user_id] = {
        "username": username.lstrip('@'),
        "name": name,
        "role": role,
        "shop_ids": shop_ids or [4987],
        "is_active": True
    }
    
    save_users(file_path, users)
    print(f"✅ Пользователь {name} (@{username}) добавлен с ID {user_id}")
    return True

def list_users(file_path: str):
    """Выводит список всех пользователей"""
    users = load_users(file_path)
    
    if not users:
        print("❌ Нет пользователей в базе")
        return
    
    print("📋 Список пользователей:")
    for user_id, user_data in users.items():
        status = "✅" if user_data.get('is_active', True) else "❌"
        print(f"  {status} ID: {user_id}")
        print(f"     Имя: {user_data.get('name', 'Не указано')}")
        print(f"     Username: @{user_data.get('username', 'Не указан')}")
        print(f"     Роль: {user_data.get('role', 'user')}")
        print(f"     Магазины: {user_data.get('shop_ids', [])}")
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
        shop_ids = [int(x) for x in sys.argv[6].split(',')] if len(sys.argv) > 6 else [4987]
        
        add_user(file_path, user_id, username, name, role, shop_ids)
    
    else:
        print(f"❌ Неизвестная команда: {command}")

if __name__ == "__main__":
    main()