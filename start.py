from src.word_game.config import get_settings


def detect_role():
    settings = get_settings()

    if settings.app_role in {"user", "admin"}:
        return settings.app_role

    if settings.user_bot_token and not settings.admin_bot_token:
        return "user"

    if settings.admin_bot_token and not settings.user_bot_token:
        return "admin"

    if settings.user_bot_token and settings.admin_bot_token:
        raise RuntimeError(
            "Найдены оба токена: USER_BOT_TOKEN и ADMIN_BOT_TOKEN. "
            "Укажи APP_ROLE=user или APP_ROLE=admin."
        )

    raise RuntimeError(
        "Не найден токен бота. Укажи USER_BOT_TOKEN или ADMIN_BOT_TOKEN."
    )


def main():
    role = detect_role()

    if role == "admin":
        from src.word_game.admin_bot import main as run_admin

        run_admin()
        return

    if role == "user":
        from src.word_game.user_bot import main as run_user

        run_user()
        return

    raise RuntimeError("APP_ROLE должен быть либо 'user', либо 'admin'.")


if __name__ == "__main__":
    main()
