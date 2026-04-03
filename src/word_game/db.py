import random
import re
import sqlite3
import zlib
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .config import get_settings

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - optional locally until deps are installed
    psycopg = None
    dict_row = None


SETTINGS = get_settings()
DB_PATH = SETTINGS.db_path
DATABASE_URL = SETTINGS.database_url
IS_POSTGRES = bool(DATABASE_URL)
_LOCK_CONNECTIONS: Dict[str, Any] = {}


def normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def _get_sqlite_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _get_postgres_connection():
    if psycopg is None:
        raise RuntimeError(
            "Для работы с Postgres установи зависимости из requirements.txt "
            "(нужен пакет psycopg[binary])."
        )
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def _get_connection():
    if IS_POSTGRES:
        return _get_postgres_connection()
    return _get_sqlite_connection()


def _worker_lock_key(lock_name: str) -> int:
    return zlib.crc32(lock_name.encode("utf-8")) & 0x7FFFFFFF


def acquire_worker_lock(lock_name: str) -> bool:
    if not IS_POSTGRES:
        return True

    if lock_name in _LOCK_CONNECTIONS:
        return True

    if psycopg is None:
        raise RuntimeError("Для worker lock нужен установленный psycopg.")

    conn = psycopg.connect(DATABASE_URL, autocommit=True)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT pg_try_advisory_lock(%s) AS acquired",
                (_worker_lock_key(lock_name),),
            )
            row = cursor.fetchone()
            acquired = bool(row["acquired"])
    except Exception:
        conn.close()
        raise

    if not acquired:
        conn.close()
        return False

    _LOCK_CONNECTIONS[lock_name] = conn
    return True


def release_worker_lock(lock_name: str):
    if not IS_POSTGRES:
        return

    conn = _LOCK_CONNECTIONS.pop(lock_name, None)
    if conn is None:
        return

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_unlock(%s)",
                (_worker_lock_key(lock_name),),
            )
    finally:
        conn.close()


def _fetch_all(query: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
    if IS_POSTGRES:
        with _get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
        return [dict(row) for row in rows]

    with _get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def _fetch_one(query: str, params: Sequence[Any] = ()) -> Optional[Dict[str, Any]]:
    rows = _fetch_all(query, params)
    return rows[0] if rows else None


def _fetch_value(query: str, params: Sequence[Any] = ()) -> Any:
    row = _fetch_one(query, params)
    if not row:
        return None
    return next(iter(row.values()))


def _execute(query: str, params: Sequence[Any] = ()) -> int:
    if IS_POSTGRES:
        with _get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                rowcount = cursor.rowcount
        return rowcount

    with _get_connection() as conn:
        cursor = conn.execute(query, params)
        return cursor.rowcount


def _execute_many(queries: Sequence[Tuple[str, Sequence[Any]]]):
    if IS_POSTGRES:
        with _get_connection() as conn:
            with conn.cursor() as cursor:
                for query, params in queries:
                    cursor.execute(query, params)
        return

    with _get_connection() as conn:
        for query, params in queries:
            conn.execute(query, params)


def _existing_columns_sqlite(table_name: str) -> Set[str]:
    with _get_connection() as conn:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def _existing_columns_postgres(table_name: str) -> Set[str]:
    rows = _fetch_all(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table_name,),
    )
    return {row["column_name"] for row in rows}


def _ensure_column(table_name: str, column_name: str, column_sql: str):
    if IS_POSTGRES:
        existing_columns = _existing_columns_postgres(table_name)
        if column_name not in existing_columns:
            _execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")
        return

    existing_columns = _existing_columns_sqlite(table_name)
    if column_name not in existing_columns:
        _execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")


def init_db():
    if IS_POSTGRES:
        _execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_id BIGINT PRIMARY KEY,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                normalized_phone TEXT,
                username TEXT,
                photo_file_id TEXT NOT NULL,
                score INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        _execute(
            """
            CREATE TABLE IF NOT EXISTS found (
                finder_telegram_id BIGINT NOT NULL,
                target_telegram_id BIGINT NOT NULL,
                found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (finder_telegram_id, target_telegram_id)
            )
            """
        )
        _execute(
            """
            CREATE TABLE IF NOT EXISTS admin_subscribers (
                telegram_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                status TEXT DEFAULT 'active',
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    else:
        _execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                normalized_phone TEXT,
                username TEXT,
                photo_file_id TEXT NOT NULL,
                score INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        _execute(
            """
            CREATE TABLE IF NOT EXISTS found (
                finder_telegram_id INTEGER NOT NULL,
                target_telegram_id INTEGER NOT NULL,
                found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (finder_telegram_id, target_telegram_id)
            )
            """
        )
        _execute(
            """
            CREATE TABLE IF NOT EXISTS admin_subscribers (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                status TEXT DEFAULT 'active',
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    _ensure_column("users", "normalized_phone", "TEXT")
    _ensure_column("users", "username", "TEXT")
    _ensure_column("users", "status", "TEXT DEFAULT 'active'")
    _ensure_column("admin_subscribers", "username", "TEXT")
    _ensure_column("admin_subscribers", "first_name", "TEXT")
    _ensure_column("admin_subscribers", "last_name", "TEXT")
    _ensure_column("admin_subscribers", "status", "TEXT DEFAULT 'active'")
    _ensure_column("admin_subscribers", "joined_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    _ensure_column("admin_subscribers", "last_seen_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    if IS_POSTGRES:
        rows = _fetch_all(
            "SELECT telegram_id, phone, normalized_phone, status FROM users"
        )
        queries = []
        for row in rows:
            next_phone = row["normalized_phone"] or normalize_phone(row["phone"])
            next_status = row["status"] or "active"
            queries.append(
                (
                    """
                    UPDATE users
                    SET normalized_phone = %s, status = %s
                    WHERE telegram_id = %s
                    """,
                    (next_phone, next_status, row["telegram_id"]),
                )
            )
        if queries:
            _execute_many(queries)

        _execute(
            """
            CREATE INDEX IF NOT EXISTS idx_users_score
            ON users(score DESC, registered_at ASC)
            """
        )
        _execute(
            """
            CREATE INDEX IF NOT EXISTS idx_found_finder
            ON found(finder_telegram_id)
            """
        )
        _execute(
            """
            CREATE INDEX IF NOT EXISTS idx_admin_subscribers_status
            ON admin_subscribers(status, joined_at ASC)
            """
        )
        return

    rows = _fetch_all("SELECT telegram_id, phone, normalized_phone, status FROM users")
    queries = []
    for row in rows:
        next_phone = row["normalized_phone"] or normalize_phone(row["phone"])
        next_status = row["status"] or "active"
        queries.append(
            (
                """
                UPDATE users
                SET normalized_phone = ?, status = ?
                WHERE telegram_id = ?
                """,
                (next_phone, next_status, row["telegram_id"]),
            )
        )
    if queries:
        _execute_many(queries)

    _execute(
        """
        CREATE INDEX IF NOT EXISTS idx_users_score
        ON users(score DESC, registered_at ASC)
        """
    )
    _execute(
        """
        CREATE INDEX IF NOT EXISTS idx_found_finder
        ON found(finder_telegram_id)
        """
    )
    _execute(
        """
        CREATE INDEX IF NOT EXISTS idx_admin_subscribers_status
        ON admin_subscribers(status, joined_at ASC)
        """
    )


def get_user(telegram_id: int) -> Optional[dict]:
    query = "SELECT * FROM users WHERE telegram_id = %s" if IS_POSTGRES else "SELECT * FROM users WHERE telegram_id = ?"
    return _fetch_one(query, (telegram_id,))


def register_user(
    telegram_id: int,
    name: str,
    phone: str,
    photo_file_id: str,
    username: Optional[str] = None,
):
    if IS_POSTGRES:
        _execute(
            """
            INSERT INTO users (
                telegram_id, name, phone, normalized_phone, username, photo_file_id, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'active')
            """,
            (telegram_id, name, phone, normalize_phone(phone), username, photo_file_id),
        )
        return

    _execute(
        """
        INSERT INTO users (
            telegram_id, name, phone, normalized_phone, username, photo_file_id, status
        )
        VALUES (?, ?, ?, ?, ?, ?, 'active')
        """,
        (telegram_id, name, phone, normalize_phone(phone), username, photo_file_id),
    )


def update_user_name(telegram_id: int, name: str):
    query = "UPDATE users SET name = %s WHERE telegram_id = %s" if IS_POSTGRES else "UPDATE users SET name = ? WHERE telegram_id = ?"
    _execute(query, (name, telegram_id))


def update_user_phone(telegram_id: int, phone: str):
    if IS_POSTGRES:
        _execute(
            """
            UPDATE users
            SET phone = %s, normalized_phone = %s
            WHERE telegram_id = %s
            """,
            (phone, normalize_phone(phone), telegram_id),
        )
        return

    _execute(
        """
        UPDATE users
        SET phone = ?, normalized_phone = ?
        WHERE telegram_id = ?
        """,
        (phone, normalize_phone(phone), telegram_id),
    )


def update_user_photo(telegram_id: int, photo_file_id: str):
    query = (
        "UPDATE users SET photo_file_id = %s WHERE telegram_id = %s"
        if IS_POSTGRES
        else "UPDATE users SET photo_file_id = ? WHERE telegram_id = ?"
    )
    _execute(query, (photo_file_id, telegram_id))


def update_user_username(telegram_id: int, username: Optional[str]):
    query = (
        "UPDATE users SET username = %s WHERE telegram_id = %s"
        if IS_POSTGRES
        else "UPDATE users SET username = ? WHERE telegram_id = ?"
    )
    _execute(query, (username, telegram_id))


def set_user_status(telegram_id: int, status: str):
    query = (
        "UPDATE users SET status = %s WHERE telegram_id = %s"
        if IS_POSTGRES
        else "UPDATE users SET status = ? WHERE telegram_id = ?"
    )
    _execute(query, (status, telegram_id))


def get_progress(telegram_id: int) -> dict:
    if IS_POSTGRES:
        total_targets = _fetch_value(
            """
            SELECT COUNT(*)
            FROM users
            WHERE telegram_id != %s AND status = 'active'
            """,
            (telegram_id,),
        )
        found_count = _fetch_value(
            "SELECT COUNT(*) FROM found WHERE finder_telegram_id = %s",
            (telegram_id,),
        )
    else:
        total_targets = _fetch_value(
            """
            SELECT COUNT(*)
            FROM users
            WHERE telegram_id != ? AND status = 'active'
            """,
            (telegram_id,),
        )
        found_count = _fetch_value(
            "SELECT COUNT(*) FROM found WHERE finder_telegram_id = ?",
            (telegram_id,),
        )

    total_targets = int(total_targets or 0)
    found_count = int(found_count or 0)
    return {
        "total_targets": total_targets,
        "found_count": found_count,
        "remaining_count": max(total_targets - found_count, 0),
    }


def get_random_target(finder_id: int, excluded_ids: Optional[List[int]] = None) -> Optional[dict]:
    excluded_ids = excluded_ids or []

    if IS_POSTGRES:
        query = """
            SELECT *
            FROM users
            WHERE telegram_id != %s
              AND status = 'active'
              AND telegram_id NOT IN (
                  SELECT target_telegram_id
                  FROM found
                  WHERE finder_telegram_id = %s
              )
        """
        params: List[Any] = [finder_id, finder_id]
        if excluded_ids:
            placeholders = ", ".join(["%s"] * len(excluded_ids))
            query += f" AND telegram_id NOT IN ({placeholders})"
            params.extend(excluded_ids)
        rows = _fetch_all(query, tuple(params))
    else:
        query = """
            SELECT *
            FROM users
            WHERE telegram_id != ?
              AND status = 'active'
              AND telegram_id NOT IN (
                  SELECT target_telegram_id
                  FROM found
                  WHERE finder_telegram_id = ?
              )
        """
        params = [finder_id, finder_id]
        if excluded_ids:
            placeholders = ", ".join(["?"] * len(excluded_ids))
            query += f" AND telegram_id NOT IN ({placeholders})"
            params.extend(excluded_ids)
        rows = _fetch_all(query, tuple(params))

    if not rows:
        return None
    return dict(random.choice(rows))


def record_found(finder_id: int, target_id: int) -> bool:
    if IS_POSTGRES:
        with _get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO found (finder_telegram_id, target_telegram_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (finder_id, target_id),
                )
                inserted = cursor.rowcount > 0
                if inserted:
                    cursor.execute(
                        "UPDATE users SET score = score + 1 WHERE telegram_id = %s",
                        (finder_id,),
                    )
        return inserted

    with _get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO found (finder_telegram_id, target_telegram_id)
            VALUES (?, ?)
            """,
            (finder_id, target_id),
        )
        inserted = cursor.rowcount > 0
        if inserted:
            conn.execute(
                "UPDATE users SET score = score + 1 WHERE telegram_id = ?",
                (finder_id,),
            )
    return inserted


def get_leaderboard(limit: Optional[int] = None) -> List[dict]:
    if IS_POSTGRES:
        query = """
            SELECT name, score
            FROM users
            WHERE status = 'active'
            ORDER BY score DESC, registered_at ASC, LOWER(name) ASC
        """
        params: Tuple[Any, ...] = ()
        if limit:
            query += " LIMIT %s"
            params = (limit,)
        return _fetch_all(query, params)

    query = """
        SELECT name, score
        FROM users
        WHERE status = 'active'
        ORDER BY score DESC, registered_at ASC, name COLLATE NOCASE ASC
    """
    params = ()
    if limit:
        query += " LIMIT ?"
        params = (limit,)
    return _fetch_all(query, params)


def get_admin_stats() -> dict:
    users_total = int(_fetch_value("SELECT COUNT(*) FROM users") or 0)
    active_users = int(
        _fetch_value("SELECT COUNT(*) FROM users WHERE status = 'active'") or 0
    )
    admin_subscribers = int(
        _fetch_value("SELECT COUNT(*) FROM admin_subscribers WHERE status = 'active'") or 0
    )
    total_finds = int(_fetch_value("SELECT COUNT(*) FROM found") or 0)
    top_score = int(_fetch_value("SELECT COALESCE(MAX(score), 0) FROM users") or 0)
    return {
        "users_total": users_total,
        "active_users": active_users,
        "admin_subscribers": admin_subscribers,
        "total_finds": total_finds,
        "top_score": top_score,
    }


def get_recent_finds(limit: int = 10) -> List[dict]:
    if IS_POSTGRES:
        return _fetch_all(
            """
            SELECT
                f.found_at,
                finder.name AS finder_name,
                target.name AS target_name
            FROM found f
            JOIN users finder ON finder.telegram_id = f.finder_telegram_id
            JOIN users target ON target.telegram_id = f.target_telegram_id
            ORDER BY f.found_at DESC
            LIMIT %s
            """,
            (limit,),
        )

    return _fetch_all(
        """
        SELECT
            f.found_at,
            finder.name AS finder_name,
            target.name AS target_name
        FROM found f
        JOIN users finder ON finder.telegram_id = f.finder_telegram_id
        JOIN users target ON target.telegram_id = f.target_telegram_id
        ORDER BY f.found_at DESC
        LIMIT ?
        """,
        (limit,),
    )


def get_recent_users(limit: int = 10) -> List[dict]:
    if IS_POSTGRES:
        return _fetch_all(
            """
            SELECT name, username, score, registered_at
            FROM users
            ORDER BY registered_at DESC
            LIMIT %s
            """,
            (limit,),
        )

    return _fetch_all(
        """
        SELECT name, username, score, registered_at
        FROM users
        ORDER BY registered_at DESC
        LIMIT ?
        """,
        (limit,),
    )


def get_broadcast_recipients() -> List[int]:
    rows = _fetch_all(
        """
        SELECT telegram_id
        FROM users
        WHERE status = 'active'
        ORDER BY registered_at ASC
        """
    )
    return [int(row["telegram_id"]) for row in rows]


def upsert_admin_subscriber(
    telegram_id: int,
    username: Optional[str],
    first_name: Optional[str],
    last_name: Optional[str],
):
    if IS_POSTGRES:
        _execute(
            """
            INSERT INTO admin_subscribers (
                telegram_id, username, first_name, last_name, status, last_seen_at
            )
            VALUES (%s, %s, %s, %s, 'active', CURRENT_TIMESTAMP)
            ON CONFLICT (telegram_id) DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                status = 'active',
                last_seen_at = CURRENT_TIMESTAMP
            """,
            (telegram_id, username, first_name, last_name),
        )
        return

    _execute(
        """
        INSERT INTO admin_subscribers (
            telegram_id, username, first_name, last_name, status, last_seen_at
        )
        VALUES (?, ?, ?, ?, 'active', CURRENT_TIMESTAMP)
        ON CONFLICT(telegram_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            last_name = excluded.last_name,
            status = 'active',
            last_seen_at = CURRENT_TIMESTAMP
        """,
        (telegram_id, username, first_name, last_name),
    )


def set_admin_subscriber_status(telegram_id: int, status: str):
    query = (
        "UPDATE admin_subscribers SET status = %s, last_seen_at = CURRENT_TIMESTAMP WHERE telegram_id = %s"
        if IS_POSTGRES
        else "UPDATE admin_subscribers SET status = ?, last_seen_at = CURRENT_TIMESTAMP WHERE telegram_id = ?"
    )
    _execute(query, (status, telegram_id))


def get_admin_broadcast_recipients() -> List[int]:
    rows = _fetch_all(
        """
        SELECT telegram_id
        FROM admin_subscribers
        WHERE status = 'active'
        ORDER BY joined_at ASC
        """
    )
    return [int(row["telegram_id"]) for row in rows]
