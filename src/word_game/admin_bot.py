"""
Отдельный админ-бот для игры "Найди незнакомца".

Переменные окружения:
- ADMIN_BOT_TOKEN
- ADMIN_IDS=123,456
- DB_PATH (опционально)
"""

import logging
import re

from telegram import BotCommand, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from .config import get_settings, require_token
from .db import get_admin_stats, get_leaderboard, get_recent_finds, get_recent_users, init_db
from .keyboards import (
    BTN_ADMIN_RECENT_FINDS,
    BTN_ADMIN_RECENT_USERS,
    BTN_ADMIN_STATS,
    BTN_ADMIN_TOP10,
    admin_menu,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    settings = get_settings()
    return user_id in settings.admin_ids


async def require_admin(update: Update) -> bool:
    if is_admin(update.effective_user.id):
        return True
    await update.message.reply_text("⛔️ Этот бот доступен только администратору.")
    return False


async def post_init(application: Application):
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Открыть админ-панель"),
            BotCommand("stats", "Сводка по игре"),
            BotCommand("top10", "Топ-10 лидеров"),
            BotCommand("recent", "Последние находки"),
            BotCommand("new_users", "Новые участники"),
        ]
    )


def format_top10() -> str:
    rows = get_leaderboard(limit=10)
    if not rows:
        return "Пока нет зарегистрированных участников."

    lines = ["🏆 Топ-10 лидеров:\n"]
    for index, row in enumerate(rows, start=1):
        badge = {1: "🥇", 2: "🥈", 3: "🥉"}.get(index, f"{index}.")
        lines.append(f"{badge} {row['name']} — {row['score']} очк.")
    return "\n".join(lines)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return

    await update.message.reply_text(
        "🛠 Админ-панель готова.\n\n"
        "Здесь можно посмотреть сводку по игре, свежие находки и первых 10 лидеров.",
        reply_markup=admin_menu(),
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return

    summary = get_admin_stats()
    await update.message.reply_text(
        "📊 Сводка по игре\n\n"
        f"Всего участников: {summary['users_total']}\n"
        f"Активных участников: {summary['active_users']}\n"
        f"Всего успешных находок: {summary['total_finds']}\n"
        f"Лучший счёт сейчас: {summary['top_score']}",
        reply_markup=admin_menu(),
    )


async def top10(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return

    await update.message.reply_text(format_top10(), reply_markup=admin_menu())


async def recent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return

    rows = get_recent_finds(limit=10)
    if not rows:
        await update.message.reply_text("Пока ещё нет успешных находок.", reply_markup=admin_menu())
        return

    lines = ["🕒 Последние находки:\n"]
    for row in rows:
        lines.append(f"• {row['finder_name']} нашёл(а) {row['target_name']} — {row['found_at']}")
    await update.message.reply_text("\n".join(lines), reply_markup=admin_menu())


async def new_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return

    rows = get_recent_users(limit=10)
    if not rows:
        await update.message.reply_text("Пока ещё никто не зарегистрировался.", reply_markup=admin_menu())
        return

    lines = ["👥 Последние участники:\n"]
    for row in rows:
        username = f"@{row['username']}" if row["username"] else "без username"
        lines.append(
            f"• {row['name']} ({username}) — {row['score']} очк. — {row['registered_at']}"
        )
    await update.message.reply_text("\n".join(lines), reply_markup=admin_menu())


async def route_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == BTN_ADMIN_STATS:
        return await stats(update, context)
    if text == BTN_ADMIN_TOP10:
        return await top10(update, context)
    if text == BTN_ADMIN_RECENT_FINDS:
        return await recent(update, context)
    if text == BTN_ADMIN_RECENT_USERS:
        return await new_users(update, context)

    if not await require_admin(update):
        return
    await update.message.reply_text("Выбери действие из меню ниже.", reply_markup=admin_menu())


def build_application() -> Application:
    settings = get_settings()
    token = require_token(settings.admin_bot_token, "ADMIN_BOT_TOKEN")

    application = Application.builder().token(token).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("top10", top10))
    application.add_handler(CommandHandler("recent", recent))
    application.add_handler(CommandHandler("new_users", new_users))
    application.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_ADMIN_STATS)}$"), stats))
    application.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_ADMIN_TOP10)}$"), top10))
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_ADMIN_RECENT_FINDS)}$"), recent)
    )
    application.add_handler(
        MessageHandler(filters.Regex(f"^{re.escape(BTN_ADMIN_RECENT_USERS)}$"), new_users)
    )
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, route_buttons))
    return application


def main():
    init_db()
    logger.info("Запускаю админ-бота")
    build_application().run_polling()


if __name__ == "__main__":
    main()
