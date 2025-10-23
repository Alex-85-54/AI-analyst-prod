# О проекте

ИИ-агент аналитик данных. Принимает вопросы пользователей на естественном языке, выдает агрегированную информацию в виде таблицы Markdown, делает караткий анализ и дает рекомендации для маркетолога.
В качестве LLM использется DeepSeek.
Имеет доступ к базам данных: 
- Clickhouse, кластера: rees46

## Строка подключения к БД

```
client_ch = clickhouse_connect.get_client(host=os.environ.get('CH_HOST') port=os.environ.get('CH_PORT'), username=os.environ.get('CH_USER') password=os.environ.get('CH_PASSWORD'))
```

## Команда запуска контейнера

```
docker run -d -e СH_HOST='10.2.1.11' -e CH_PORT=8123 -e CH_USER='read_only' -e CH_PASSWORD='' -e API_KEY_DEEPSEEK='sk-api_key' -it <image_name>
```
## Безопасность
- Настройки БД должны позволять только запросы чтения