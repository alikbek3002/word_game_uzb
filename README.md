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
├── requirements.txt
├── start_admin.py
├── start.py
├── start_user.py
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

Используй разные `Start Command` для каждого сервиса:

```bash
user service  -> python start_user.py
admin service -> python start_admin.py
```

`start.py` можно оставить для локальных экспериментов, но в Railway лучше не использовать его вообще, чтобы сервисы не путались.

### Что создать

Нужны:
- 1 Postgres database service
- 1 service для пользовательского бота
- 1 service для админ-бота

Оба Python-сервиса можно создать из одного и того же репозитория.

### Переменные для user service

`Start Command`:

```bash
python start_user.py
```

Обязательно:

```bash
USER_BOT_TOKEN=...
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

Не добавляй сюда `ADMIN_BOT_TOKEN` и не используй общий `BOT_TOKEN`.

### Переменные для admin service

`Start Command`:

```bash
python start_admin.py
```

Обязательно:

```bash
ADMIN_BOT_TOKEN=...
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

Не добавляй сюда `USER_BOT_TOKEN`.

### Как задеплоить удобно

1. Заливаешь этот проект в GitHub.
2. Подключаешь репозиторий к Railway.
3. Создаёшь Postgres service.
4. Создаёшь первый Python service для user-бота с пустым `Root Directory` и `Start Command = python start_user.py`.
5. Создаёшь второй Python service для admin-бота с пустым `Root Directory` и `Start Command = python start_admin.py`.
6. Оба сервиса подключаешь к одному Postgres.
7. Для каждого сервиса выставляешь свои env-переменные.

### Что важно

- На Railway не используй `find_stranger.db` для продакшна.
- При наличии `DATABASE_URL` код автоматически переключается на Postgres.
- Таблицы создаются автоматически при старте.
- Для Railway не используй `python start.py`, чтобы user/admin сервисы не перепутались.
- У user-бота и admin-бота должны быть два разных токена из `@BotFather`.
- Если один и тот же токен запущен в двух местах, Telegram вернёт `409 Conflict`, и бот будет работать нестабильно.
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
