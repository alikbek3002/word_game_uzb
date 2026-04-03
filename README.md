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
python admin_bot.py
```

## Railway

Деплой делай только из корня репозитория.

Проект зафиксирован на Python `3.12.12` через [`.python-version`](/Users/alikbekmukanbetov/Desktop/Word%20Class%20Uzb/.python-version), потому что `python-telegram-bot==20.8` у Railway на Python 3.13 может падать при старте.

`Root Directory`:

```text
пусто
```

`Start Command` у обоих сервисов:

```bash
python start.py
```

`start.py` сам определит, какой бот запускать:
- если есть `USER_BOT_TOKEN`, запустится user-бот
- если есть `ADMIN_BOT_TOKEN`, запустится admin-бот

`services/...` больше использовать не нужно.

### Что создать

Нужны:
- 1 Postgres database service
- 1 service для пользовательского бота
- 1 service для админ-бота

Оба Python-сервиса можно создать из одного и того же репозитория.

### Переменные для user service

Обязательно:

```bash
USER_BOT_TOKEN=...
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

### Переменные для admin service

Обязательно:

```bash
ADMIN_BOT_TOKEN=...
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

### Как задеплоить удобно

1. Заливаешь этот проект в GitHub.
2. Подключаешь репозиторий к Railway.
3. Создаёшь Postgres service.
4. Создаёшь первый Python service для user-бота с пустым `Root Directory`.
5. Создаёшь второй Python service для admin-бота с пустым `Root Directory`.
6. Оба сервиса подключаешь к одному Postgres.
7. Для каждого сервиса выставляешь свои env-переменные.

### Что важно

- На Railway не используй `find_stranger.db` для продакшна.
- При наличии `DATABASE_URL` код автоматически переключается на Postgres.
- Таблицы создаются автоматически при старте.
- Топ-10 лидеров в админ-боте берётся из общей Postgres-базы.
- Для получения рассылки пользователь должен хотя бы один раз нажать `/start` в админ-боте.
- Рассылка из админ-бота идёт только подписчикам этого же админ-бота.
- Любой пользователь, который зашёл в админ-бот, получает полный доступ к его панели.

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
