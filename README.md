# О проекте

ИИ-агент аналитик данных. Принимает вопросы пользователей на естественном языке, выдает агрегированную информацию в виде таблицы Markdown, делает караткий анализ и дает рекомендации для маркетолога.
В качестве LLM использется DeepSeek и GPT
Имеет доступ к базам данных: 
- Clickhouse
- PostgreSQL

## Строка подключения к БД

```
client_ch = clickhouse_connect.get_client(host=os.environ.get('CH_HOST') port=os.environ.get('CH_PORT'), username=os.environ.get('CH_USER') password=os.environ.get('CH_PASSWORD'))
```

## Добавление пользователей
### Показать всех пользователей
```
docker exec -it ai-analyst python user_manager.py list
```
### Добавить пользователя
```
docker exec -it ai-analyst python user_manager.py add <user_id> <username> <Имя Фамилия> <role>
```
## Управление логированием
### Просмотр последних 100 строк
```
docker exec -it ai-analyst python scripts/view_logs.py --lines 100
```
### Просмотр логов в реальном времени
```
docker exec -it ai-analyst python scripts/view_logs.py --follow
```
### Просмотр только ошибок
```
docker exec -it ai-analyst python scripts/view_logs.py --level ERROR
```
### Очистить файл логов
```
docker exec -it ai-analyst python scripts/clean_logs.py --clean
```
#### Статистика логов
 --stats
#### Расположение файла
 --file
#### Сделать бэкап
--keep-backups

## Безопасность
- Настройки БД должны позволять только запросы чтения

## Режимы работы
- в файле ./config/settings.py параметр MODE указывает на режим работы: dev или prod. 
В режиме dev векторная база сохраняется на хосте для ускорения перезапуска приложения. В режиме prod FAISS всегда создается заново.
- в файле .env так же указывается режим MODE

## Внедрено использование VPN
### LLM
Если GPT не доступна, то сервис автоматически переключается на использование DeepSeek. 
Узнать какая LLM в данный момент используется можно кнопкой "Проверка систем" в интерфейсе бота.
### Telegram
Telegram API работает через VPN.

## Ограничение доступа к данным других магазинов
- доступные магазины для пользователя берутся из internal API по Telegram user_id (см. ниже)
- если API возвращает пустой список или недоступен — бот блокирует аналитику и просит обратиться к администратору


