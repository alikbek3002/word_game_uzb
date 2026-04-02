from src.word_game.config import get_settings


def main():
    settings = get_settings()
    role = settings.app_role

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
