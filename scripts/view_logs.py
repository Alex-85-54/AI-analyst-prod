#!/usr/bin/env python3
"""
Утилита для просмотра логов
"""
import os
import sys
import json
from datetime import datetime

def view_logs(log_file_path=None, lines=50, follow=False, level=None):
    """Просмотр логов"""
    if not log_file_path:
        from config.settings import settings
        log_file_path = settings.LOG_FILE_PATH
    
    if not os.path.exists(log_file_path):
        print(f"Log file not found: {log_file_path}")
        return
    
    print(f"Viewing logs from: {log_file_path}")
    print("-" * 80)
    
    with open(log_file_path, 'r', encoding='utf-8') as f:
        if follow:
            # Режим follow (как tail -f)
            import time
            f.seek(0, 2)  # Переходим в конец файла
            while True:
                line = f.readline()
                if line:
                    try:
                        log_entry = json.loads(line.strip())
                        if level and log_entry.get('level') != level.upper():
                            continue
                        print(format_log_entry(log_entry))
                    except json.JSONDecodeError:
                        print(line.strip())
                else:
                    time.sleep(0.1)
        else:
            # Чтение последних N строк
            lines_content = f.readlines()[-lines:]
            for line in lines_content:
                try:
                    log_entry = json.loads(line.strip())
                    if level and log_entry.get('level') != level.upper():
                        continue
                    print(format_log_entry(log_entry))
                except json.JSONDecodeError:
                    print(line.strip())

def format_log_entry(log_entry):
    """Форматирование JSON лога в читаемый вид"""
    timestamp = log_entry.get('timestamp', '')
    level = log_entry.get('level', 'INFO')
    message = log_entry.get('message', '')
    module = log_entry.get('module', '')
    
    level_colors = {
        'INFO': '\033[94m',    # Синий
        'WARNING': '\033[93m', # Желтый
        'ERROR': '\033[91m',   # Красный
        'DEBUG': '\033[90m',   # Серый
    }
    
    color = level_colors.get(level, '\033[0m')
    reset = '\033[0m'
    
    return f"{timestamp} {color}{level:8}{reset} {module:15} {message}"

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Log viewer for AI Analyst')
    parser.add_argument('--file', '-f', help='Log file path')
    parser.add_argument('--lines', '-n', type=int, default=50, help='Number of lines to show')
    parser.add_argument('--follow', '-F', action='store_true', help='Follow log file')
    parser.add_argument('--level', '-l', choices=['INFO', 'WARNING', 'ERROR', 'DEBUG'], 
                       help='Filter by log level')
    
    args = parser.parse_args()
    
    view_logs(
        log_file_path=args.file,
        lines=args.lines,
        follow=args.follow,
        level=args.level
    )

if __name__ == "__main__":
    main()