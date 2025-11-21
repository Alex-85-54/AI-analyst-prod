#!/usr/bin/env python3
"""
Утилита для очистки и управления логами
"""
import os
import glob
import sys

def clean_logs(log_file_path=None, keep_backups=True):
    """Очистка логов"""
    if not log_file_path:
        from NEW.config.settings import settings
        log_file_path = settings.LOG_FILE_PATH
    
    log_dir = os.path.dirname(log_file_path)
    log_base = os.path.basename(log_file_path)
    
    if not os.path.exists(log_dir):
        print(f"Log directory not found: {log_dir}")
        return
    
    # Находим все файлы логов
    log_files = glob.glob(os.path.join(log_dir, f"{log_base}*"))
    
    if not log_files:
        print("No log files found to clean")
        return
    
    print("Found log files:")
    for log_file in sorted(log_files):
        size = os.path.getsize(log_file) if os.path.exists(log_file) else 0
        print(f"  {log_file} ({size} bytes)")
    
    confirm = input("\nDelete these files? (y/N): ")
    if confirm.lower() == 'y':
        for log_file in log_files:
            try:
                if keep_backups and log_file.endswith('.1') or log_file.endswith('.2'):
                    continue
                os.remove(log_file)
                print(f"Deleted: {log_file}")
            except Exception as e:
                print(f"Error deleting {log_file}: {e}")
        print("Log cleanup completed")
    else:
        print("Cleanup cancelled")

def show_log_stats(log_file_path=None):
    """Показать статистику логов"""
    if not log_file_path:
        from NEW.config.settings import settings
        log_file_path = settings.LOG_FILE_PATH
    
    log_dir = os.path.dirname(log_file_path)
    log_base = os.path.basename(log_file_path)
    
    log_files = glob.glob(os.path.join(log_dir, f"{log_base}*"))
    
    total_size = 0
    print("Log files statistics:")
    for log_file in sorted(log_files):
        size = os.path.getsize(log_file) if os.path.exists(log_file) else 0
        total_size += size
        print(f"  {log_file}: {size} bytes")
    
    print(f"\nTotal size: {total_size} bytes ({total_size / 1024 / 1024:.2f} MB)")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Log management for AI Analyst')
    parser.add_argument('--clean', '-c', action='store_true', help='Clean log files')
    parser.add_argument('--stats', '-s', action='store_true', help='Show log statistics')
    parser.add_argument('--file', '-f', help='Log file path')
    parser.add_argument('--keep-backups', action='store_true', help='Keep backup files when cleaning')
    
    args = parser.parse_args()
    
    if args.clean:
        clean_logs(args.file, args.keep_backups)
    elif args.stats:
        show_log_stats(args.file)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()