"""
Одноразовый перенос данных из SQLite в Postgres.

Пример:
DATABASE_URL=postgresql://... python migrate_sqlite_to_postgres.py
"""

import os
import sqlite3

from db import IS_POSTGRES, init_db

try:
    import psycopg
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Нужен пакет psycopg[binary] из requirements.txt") from exc


SQLITE_PATH = os.getenv("SQLITE_PATH", "find_stranger.db")
DATABASE_URL = os.getenv("DATABASE_URL")


def main():
    if not DATABASE_URL or not IS_POSTGRES:
        raise RuntimeError("Укажи DATABASE_URL от Postgres перед запуском миграции.")

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row

    init_db()

    users = sqlite_conn.execute("SELECT * FROM users").fetchall()
    found_rows = sqlite_conn.execute("SELECT * FROM found").fetchall()

    with psycopg.connect(DATABASE_URL) as pg_conn:
        with pg_conn.cursor() as cursor:
            for user in users:
                normalized_phone = "".join(ch for ch in (user["phone"] or "") if ch.isdigit())
                cursor.execute(
                    """
                    INSERT INTO users (
                        telegram_id, name, phone, normalized_phone, username,
                        photo_file_id, score, status, registered_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (telegram_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        phone = EXCLUDED.phone,
                        normalized_phone = EXCLUDED.normalized_phone,
                        photo_file_id = EXCLUDED.photo_file_id,
                        score = EXCLUDED.score,
                        registered_at = EXCLUDED.registered_at
                    """,
                    (
                        user["telegram_id"],
                        user["name"],
                        user["phone"],
                        normalized_phone,
                        None,
                        user["photo_file_id"],
                        user["score"],
                        "active",
                        user["registered_at"],
                    ),
                )

            for row in found_rows:
                cursor.execute(
                    """
                    INSERT INTO found (finder_telegram_id, target_telegram_id, found_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        row["finder_telegram_id"],
                        row["target_telegram_id"],
                        row["found_at"],
                    ),
                )

    sqlite_conn.close()
    print(f"Migration complete: {len(users)} users, {len(found_rows)} found rows copied.")


if __name__ == "__main__":
    main()
