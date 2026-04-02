import os
from dataclasses import dataclass
from typing import Optional, Set


def _parse_admin_ids(raw_value: Optional[str]) -> Set[int]:
    if not raw_value:
        return set()

    admin_ids: Set[int] = set()
    for item in raw_value.split(","):
        cleaned = item.strip()
        if not cleaned:
            continue
        try:
            admin_ids.add(int(cleaned))
        except ValueError:
            continue
    return admin_ids


@dataclass(frozen=True)
class Settings:
    db_path: str
    database_url: Optional[str]
    user_bot_token: Optional[str]
    admin_bot_token: Optional[str]
    admin_ids: Set[int]
    app_role: str


def get_settings() -> Settings:
    return Settings(
        db_path=os.getenv("DB_PATH", "find_stranger.db"),
        database_url=os.getenv("DATABASE_URL"),
        user_bot_token=os.getenv("USER_BOT_TOKEN") or os.getenv("BOT_TOKEN"),
        admin_bot_token=os.getenv("ADMIN_BOT_TOKEN"),
        admin_ids=_parse_admin_ids(os.getenv("ADMIN_IDS")),
        app_role=(os.getenv("APP_ROLE", "user").strip().lower() or "user"),
    )


def require_token(token: Optional[str], env_name: str) -> str:
    if token:
        return token
    raise RuntimeError(
        f"Не найден токен. Укажи переменную окружения {env_name} перед запуском бота."
    )
