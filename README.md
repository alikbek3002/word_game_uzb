# Find Stranger Bots

Telegram-проект для игры "Найди незнакомца" с двумя ботами:
- пользовательский бот
- отдельный админ-бот

Оба сервиса используют одну и ту же базу данных. Локально можно работать через `SQLite`, а на Railway проект автоматически использует Postgres через `DATABASE_URL`.

## Структура проекта

```text
.
├── src/
│   └── word_game/
│       ├── admin_bot.py
│       ├── config.py
│       ├── db.py
│       ├── keyboards.py
│       └── user_bot.py
├── scripts/
│   └── migrate_sqlite_to_postgres.py
├── .env.example
├── .gitignore
├── README.md
├── admin_bot.py
├── find_stranger_bot.py
├── railway.json
├── requirements.txt
├── start.py
└── user_bot.py
```

`src/word_game/` содержит весь основной код. В корне оставлены только удобные точки входа и конфиги для Railway/GitHub.

## Локальный запуск

Установить зависимости:

```bash
pip install -r requirements.txt
```

Запуск пользовательского бота:

```bash
export USER_BOT_TOKEN="your-user-bot-token"
python user_bot.py
```

Запуск админ-бота:

```bash
export ADMIN_BOT_TOKEN="your-admin-bot-token"
export ADMIN_IDS="123456789"
python admin_bot.py
```

## Railway

### Что создать

Нужны:
- 1 Postgres database service
- 1 service для пользовательского бота
- 1 service для админ-бота

Оба Python-сервиса можно создать из одного и того же репозитория.

### Общая логика запуска

В проекте есть единый entrypoint `start.py`. Он смотрит на переменную `APP_ROLE`:
- `APP_ROLE=user` запускает пользовательского бота
- `APP_ROLE=admin` запускает админ-бота

`railway.json` уже настроен на:

```bash
python start.py
```

### Переменные для user service

Обязательно:

```bash
APP_ROLE=user
USER_BOT_TOKEN=...
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

Опционально:

```bash
BOT_TOKEN=...
```

### Переменные для admin service

Обязательно:

```bash
APP_ROLE=admin
ADMIN_BOT_TOKEN=...
ADMIN_IDS=123456789
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

`ADMIN_IDS` можно указать списком через запятую, если админов несколько:

```bash
ADMIN_IDS=123456789,987654321
```

### Как задеплоить удобно

1. Заливаешь этот проект в GitHub.
2. Подключаешь репозиторий к Railway.
3. Создаёшь Postgres service.
4. Создаёшь первый Python service для user-бота.
5. Создаёшь второй Python service для admin-бота.
6. Оба сервиса подключаешь к одному Postgres.
7. Для каждого сервиса выставляешь свой `APP_ROLE`.

### Что важно

- На Railway не используй `find_stranger.db` для продакшна.
- При наличии `DATABASE_URL` код автоматически переключается на Postgres.
- Таблицы создаются автоматически при старте.
- Топ-10 лидеров в админ-боте берётся из общей Postgres-базы.

## Перенос текущих данных из SQLite в Railway Postgres

Если хочешь перенести уже существующих пользователей из локального `find_stranger.db`, есть отдельный скрипт:

```bash
export DATABASE_URL="postgresql://..."
python scripts/migrate_sqlite_to_postgres.py
```

Если файл SQLite лежит в другом месте:

```bash
export SQLITE_PATH="/path/to/find_stranger.db"
export DATABASE_URL="postgresql://..."
python scripts/migrate_sqlite_to_postgres.py
```
