import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Settings:
    db_path: str
    database_url: Optional[str]
    user_bot_token: Optional[str]
    admin_bot_token: Optional[str]
    app_role: Optional[str]


def _read_env(name: str) -> Optional[str]:
    value = os.getenv(name)
    if value is None:
        return None

    value = value.strip()
    return value or None


def get_settings() -> Settings:
    settings = Settings(
        db_path=os.getenv("DB_PATH", "find_stranger.db"),
        database_url=_read_env("DATABASE_URL"),
        user_bot_token=_read_env("USER_BOT_TOKEN"),
        admin_bot_token=_read_env("ADMIN_BOT_TOKEN"),
        app_role=(_read_env("APP_ROLE") or "").lower() or None,
    )

    if (
        settings.user_bot_token
        and settings.admin_bot_token
        and settings.user_bot_token == settings.admin_bot_token
    ):
        raise RuntimeError(
            "USER_BOT_TOKEN и ADMIN_BOT_TOKEN совпадают. "
            "Для user-бота и admin-бота нужны два разных Telegram-бота."
        )

    return settings


def require_token(token: Optional[str], env_name: str) -> str:
    if token:
        return token
    raise RuntimeError(
        f"Не найден токен. Укажи переменную окружения {env_name} перед запуском бота."
    )
