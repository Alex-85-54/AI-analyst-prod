# О проекте

ИИ-агент аналитик данных. Принимает вопросы пользователей на естественном языке, выдает агрегированную информацию в виде таблицы Markdown, делает караткий анализ и дает рекомендации для маркетолога.
В качестве LLM использется DeepSeek.
Имеет доступ к базам данных: 
- Clickhouse, кластера: rees46

## Запуск через Docker

1. При необходимости полной локальной разработки - клонируем <https://github.com/rees46/infrastructure> и читаем `README.md` (либо просто `make up`)
1. Проверить `.env.example`. Если необходимо редактировать - копируем в `.env` и там вносим изменения
1. Запустить сервис:
   - либо только сам сервис - `make up`

## Строка подключения к БД

```
client_ch = clickhouse_connect.get_client(host=os.environ.get('CH_HOST') port=os.environ.get('CH_PORT'), username=os.environ.get('CH_USER') password=os.environ.get('CH_PASSWORD'))
```

## Команда запуска контейнера

```
docker run -d -e СH_HOST='10.2.1.11' -e CH_PORT=8123 -e CH_USER='read_only' -e CH_PASSWORD='' -e API_KEY_DEEPSEEK='sk-api_key' -it <image_name>
```
## Добавление пользователей
### Показать всех пользователей
```
docker exec -it ai-analyst python user_manager.py list
```
### Добавить пользователя
```
docker exec -it ai-analyst python user_manager.py add 123456789 "username" "Имя Фамилия" "analyst" "4987,4988"
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

## Внедрено использование VPN для доступа к LLM.
Если GPT не доступна, то сервис автоматически переключается на использование DeepSeek. 
Узнать какая LLM в данный момент используется можно кнопкой "Проверка систем" в интерфейсе бота.

