"""
Отдельный админ-бот для игры "Найди незнакомца".

Переменные окружения:
- ADMIN_BOT_TOKEN
- USER_BOT_TOKEN (опционально, для рассылки игрокам user-бота)
- DB_PATH (опционально)
"""

import asyncio
import logging
import re
from io import BytesIO
from typing import Optional, Tuple

from telegram import Bot, BotCommand, InputFile, Message, Update
from telegram.error import Conflict, Forbidden, RetryAfter, TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from .config import get_settings, require_token
from .db import (
    acquire_worker_lock,
    delete_user_and_cleanup,
    get_admin_stats,
    get_admin_broadcast_recipients,
    get_broadcast_recipients,
    get_leaderboard,
    get_recent_finds,
    get_recent_users,
    init_db,
    release_worker_lock,
    search_users_for_admin,
    set_admin_subscriber_status,
    set_user_status,
    upsert_admin_subscriber,
)
from .keyboards import (
    BTN_ADMIN_BROADCAST,
    BTN_ADMIN_DELETE_CONFIRM,
    BTN_ADMIN_DELETE_USER,
    BTN_ADMIN_RECENT_FINDS,
    BTN_ADMIN_RECENT_USERS,
    BTN_ADMIN_STATS,
    BTN_ADMIN_TOP10,
    BTN_CANCEL,
    admin_broadcast_menu,
    admin_delete_confirm_menu,
    admin_menu,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

WAITING_BROADCAST_CONTENT = 1
WAITING_DELETE_QUERY = 2
WAITING_DELETE_CONFIRM = 3
USER_DELIVERY_BOT_KEY = "user_delivery_bot"
SETTINGS_KEY = "settings"
ADMIN_LOCK_NAME = "word_game_admin_bot"
DELETE_CANDIDATE_KEY = "delete_candidate_id"


def build_broadcast_targets(settings) -> dict:
    user_recipients = get_broadcast_recipients()
    admin_recipients = get_admin_broadcast_recipients()
    user_recipient_ids = set(user_recipients)
    admin_only_recipients = [
        chat_id for chat_id in admin_recipients if chat_id not in user_recipient_ids
    ]

    targets = []
    if settings.user_bot_token:
        targets.extend(
            {"chat_id": chat_id, "channel": "user"}
            for chat_id in user_recipients
        )
    targets.extend(
        {"chat_id": chat_id, "channel": "admin"}
        for chat_id in admin_only_recipients
    )

    return {
        "targets": targets,
        "user_count": len(user_recipients),
        "admin_only_count": len(admin_only_recipients),
        "skipped_user_count": 0 if settings.user_bot_token else len(user_recipients),
        "total_count": len(targets),
    }


async def post_init(application: Application):
    settings = application.bot_data[SETTINGS_KEY]

    await application.bot.set_my_commands(
        [
            BotCommand("start", "Открыть админ-панель"),
            BotCommand("stats", "Сводка по игре"),
            BotCommand("top10", "Топ-10 лидеров"),
            BotCommand("recent", "Последние находки"),
            BotCommand("new_users", "Новые участники"),
            BotCommand("broadcast", "Сделать рассылку всем"),
            BotCommand("delete_user", "Удалить пользователя"),
        ]
    )

    if settings.user_bot_token:
        delivery_bot = Bot(settings.user_bot_token)
        await delivery_bot.initialize()
        application.bot_data[USER_DELIVERY_BOT_KEY] = delivery_bot
        logger.info("Подключил user-бота для рассылки игрокам.")
    else:
        logger.warning(
            "USER_BOT_TOKEN не задан в admin service. "
            "Рассылка сможет дойти только тем, кто нажал /start в админ-боте."
        )


async def post_shutdown(application: Application):
    delivery_bot = application.bot_data.pop(USER_DELIVERY_BOT_KEY, None)
    if delivery_bot is not None:
        await delivery_bot.shutdown()


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    if isinstance(context.error, Conflict):
        logger.error(
            "Telegram вернул 409 Conflict: этот токен уже используется другим polling-инстансом. "
            "Проверь, что бот не запущен локально, нет второго Railway deployment и не включено больше одной реплики."
        )
        return

    logger.error(
        "Необработанная ошибка в админ-боте: %s",
        context.error,
        exc_info=(type(context.error), context.error, context.error.__traceback__),
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


def _guess_filename(message: Message, kind: str) -> str:
    if kind == "document":
        return message.document.file_name or "broadcast_document"
    if kind == "photo":
        return "broadcast_photo.jpg"
    if kind == "video":
        return "broadcast_video.mp4"
    if kind == "audio":
        return message.audio.file_name or "broadcast_audio.mp3"
    if kind == "voice":
        return "broadcast_voice.ogg"
    if kind == "animation":
        return "broadcast_animation.mp4"
    return "broadcast_file"


async def _download_file_bytes(file_obj) -> bytes:
    downloaded = await file_obj.download_as_bytearray()
    return bytes(downloaded)


async def build_broadcast_payload(message: Message) -> Optional[dict]:
    if message.text:
        return {
            "kind": "text",
            "text": message.text,
            "entities": message.entities,
        }

    caption = message.caption
    caption_entities = message.caption_entities

    if message.photo:
        file_obj = await message.photo[-1].get_file()
        return {
            "kind": "photo",
            "bytes": await _download_file_bytes(file_obj),
            "filename": _guess_filename(message, "photo"),
            "caption": caption,
            "caption_entities": caption_entities,
        }

    if message.document:
        file_obj = await message.document.get_file()
        return {
            "kind": "document",
            "bytes": await _download_file_bytes(file_obj),
            "filename": _guess_filename(message, "document"),
            "caption": caption,
            "caption_entities": caption_entities,
        }

    if message.video:
        file_obj = await message.video.get_file()
        return {
            "kind": "video",
            "bytes": await _download_file_bytes(file_obj),
            "filename": _guess_filename(message, "video"),
            "caption": caption,
            "caption_entities": caption_entities,
        }

    if message.audio:
        file_obj = await message.audio.get_file()
        return {
            "kind": "audio",
            "bytes": await _download_file_bytes(file_obj),
            "filename": _guess_filename(message, "audio"),
            "caption": caption,
            "caption_entities": caption_entities,
        }

    if message.voice:
        file_obj = await message.voice.get_file()
        return {
            "kind": "voice",
            "bytes": await _download_file_bytes(file_obj),
            "filename": _guess_filename(message, "voice"),
            "caption": caption,
            "caption_entities": caption_entities,
        }

    if message.animation:
        file_obj = await message.animation.get_file()
        return {
            "kind": "animation",
            "bytes": await _download_file_bytes(file_obj),
            "filename": _guess_filename(message, "animation"),
            "caption": caption,
            "caption_entities": caption_entities,
        }

    return None


def _build_input_file(payload: dict) -> InputFile:
    return InputFile(BytesIO(payload["bytes"]), filename=payload["filename"])


async def _send_payload(
    bot: Bot,
    chat_id: int,
    payload: dict,
    reusable_file_id: Optional[str],
) -> Tuple[Optional[str], bool]:
    kind = payload["kind"]

    if kind == "text":
        await bot.send_message(
            chat_id=chat_id,
            text=payload["text"],
            entities=payload.get("entities"),
        )
        return None, True

    if kind == "photo":
        message = await bot.send_photo(
            chat_id=chat_id,
            photo=reusable_file_id or _build_input_file(payload),
            caption=payload.get("caption"),
            caption_entities=payload.get("caption_entities"),
        )
        return reusable_file_id or message.photo[-1].file_id, True

    if kind == "document":
        message = await bot.send_document(
            chat_id=chat_id,
            document=reusable_file_id or _build_input_file(payload),
            caption=payload.get("caption"),
            caption_entities=payload.get("caption_entities"),
        )
        return reusable_file_id or message.document.file_id, True

    if kind == "video":
        message = await bot.send_video(
            chat_id=chat_id,
            video=reusable_file_id or _build_input_file(payload),
            caption=payload.get("caption"),
            caption_entities=payload.get("caption_entities"),
        )
        return reusable_file_id or message.video.file_id, True

    if kind == "audio":
        message = await bot.send_audio(
            chat_id=chat_id,
            audio=reusable_file_id or _build_input_file(payload),
            caption=payload.get("caption"),
            caption_entities=payload.get("caption_entities"),
        )
        return reusable_file_id or message.audio.file_id, True

    if kind == "voice":
        message = await bot.send_voice(
            chat_id=chat_id,
            voice=reusable_file_id or _build_input_file(payload),
            caption=payload.get("caption"),
            caption_entities=payload.get("caption_entities"),
        )
        return reusable_file_id or message.voice.file_id, True

    if kind == "animation":
        message = await bot.send_animation(
            chat_id=chat_id,
            animation=reusable_file_id or _build_input_file(payload),
            caption=payload.get("caption"),
            caption_entities=payload.get("caption_entities"),
        )
        return reusable_file_id or message.animation.file_id, True

    return None, False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_user = update.effective_user
    upsert_admin_subscriber(
        telegram_id=telegram_user.id,
        username=telegram_user.username,
        first_name=telegram_user.first_name,
        last_name=telegram_user.last_name,
    )

    await update.message.reply_text(
        "🛠 Панель готова.\n\n"
        "Ты подписан на этот бот и можешь пользоваться всей панелью: смотреть сводку, лидеров, новых участников и делать массовую рассылку всем, кто нажал /start здесь.",
        reply_markup=admin_menu(),
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    summary = get_admin_stats()
    await update.message.reply_text(
        "📊 Сводка по игре\n\n"
        f"Всего участников: {summary['users_total']}\n"
        f"Активных участников: {summary['active_users']}\n"
        f"Подписчиков админ-бота: {summary['admin_subscribers']}\n"
        f"Всего успешных находок: {summary['total_finds']}\n"
        f"Лучший счёт сейчас: {summary['top_score']}",
        reply_markup=admin_menu(),
    )


async def top10(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(format_top10(), reply_markup=admin_menu())


async def recent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_recent_finds(limit=10)
    if not rows:
        await update.message.reply_text("Пока ещё нет успешных находок.", reply_markup=admin_menu())
        return

    lines = ["🕒 Последние находки:\n"]
    for row in rows:
        lines.append(f"• {row['finder_name']} нашёл(а) {row['target_name']} — {row['found_at']}")
    await update.message.reply_text("\n".join(lines), reply_markup=admin_menu())


async def new_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
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


def format_user_match(row: dict) -> str:
    username = f"@{row['username']}" if row.get("username") else "без username"
    return (
        f"• ID: {row['telegram_id']} | {row['name']} | {username} | "
        f"{row['score']} очк. | статус: {row['status']}"
    )


async def start_delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop(DELETE_CANDIDATE_KEY, None)
    await update.message.reply_text(
        "🗑 Режим удаления пользователя.\n\n"
        "Пришли Telegram ID, @username или часть имени.\n"
        "Я найду совпадения и попрошу подтвердить удаление.",
        reply_markup=admin_broadcast_menu(),
    )
    return WAITING_DELETE_QUERY


async def cancel_delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop(DELETE_CANDIDATE_KEY, None)
    await update.message.reply_text(
        "Удаление пользователя отменено.",
        reply_markup=admin_menu(),
    )
    return ConversationHandler.END


async def handle_delete_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    matches = search_users_for_admin(query, limit=10)

    if not matches:
        await update.message.reply_text(
            "Ничего не нашёл.\n"
            "Пришли другой ID, @username или часть имени, либо нажми «Отмена».",
            reply_markup=admin_broadcast_menu(),
        )
        return WAITING_DELETE_QUERY

    if len(matches) == 1:
        user = matches[0]
        context.user_data[DELETE_CANDIDATE_KEY] = int(user["telegram_id"])
        await update.message.reply_text(
            "Нашёл пользователя:\n\n"
            f"{format_user_match(user)}\n\n"
            "Если это он, нажми «Удалить». "
            "Будут удалены сам пользователь и все связанные записи находок, а очки пересчитаются.",
            reply_markup=admin_delete_confirm_menu(),
        )
        return WAITING_DELETE_CONFIRM

    lines = ["Нашёл несколько совпадений. Пришли точный ID одного пользователя:\n"]
    for row in matches:
        lines.append(format_user_match(row))

    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=admin_broadcast_menu(),
    )
    return WAITING_DELETE_QUERY


async def confirm_delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = context.user_data.get(DELETE_CANDIDATE_KEY)
    if not telegram_id:
        await update.message.reply_text(
            "Кандидат на удаление не выбран. Начни заново.",
            reply_markup=admin_menu(),
        )
        return ConversationHandler.END

    deleted_user = delete_user_and_cleanup(int(telegram_id))
    context.user_data.pop(DELETE_CANDIDATE_KEY, None)

    if not deleted_user:
        await update.message.reply_text(
            "Пользователь уже не найден в базе.",
            reply_markup=admin_menu(),
        )
        return ConversationHandler.END

    username = f"@{deleted_user['username']}" if deleted_user.get("username") else "без username"
    await update.message.reply_text(
        "✅ Пользователь удалён.\n\n"
        f"ID: {deleted_user['telegram_id']}\n"
        f"Имя: {deleted_user['name']}\n"
        f"Username: {username}\n\n"
        "Связанные находки удалены, очки пересчитаны.",
        reply_markup=admin_menu(),
    )
    return ConversationHandler.END


async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings = context.application.bot_data[SETTINGS_KEY]
    plan = build_broadcast_targets(settings)

    if not plan["targets"]:
        await update.message.reply_text(
            "Пока некому отправлять рассылку.\n\n"
            "Либо ещё нет игроков, либо в admin service не указан USER_BOT_TOKEN, "
            "и ещё никто не нажал /start в админ-боте.",
            reply_markup=admin_menu(),
        )
        return ConversationHandler.END

    warning = ""
    if plan["skipped_user_count"]:
        warning = (
            "\n\n⚠️ USER_BOT_TOKEN не задан в admin service, поэтому "
            f"{plan['skipped_user_count']} игрокам user-бота сообщение сейчас не уйдёт."
        )

    await update.message.reply_text(
        "📣 Режим рассылки включён.\n\n"
        "Отправь одно сообщение, и я разошлю его всем доступным получателям.\n"
        f"Игроки user-бота: {plan['user_count']}\n"
        f"Только подписчики admin-бота: {plan['admin_only_count']}\n"
        f"Итого получателей сейчас: {plan['total_count']}"
        f"{warning}\n"
        "Поддерживаются: текст, фото, документ, видео, аудио, голосовое, анимация.\n\n"
        "Если передумал, нажми «Отмена».",
        reply_markup=admin_broadcast_menu(),
    )
    return WAITING_BROADCAST_CONTENT


async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Рассылка отменена.",
        reply_markup=admin_menu(),
    )
    return ConversationHandler.END


async def handle_broadcast_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payload = await build_broadcast_payload(update.message)
    if not payload:
        await update.message.reply_text(
            "Это сообщение я пока не умею массово рассылать.\n"
            "Поддерживаются: текст, фото, документ, видео, аудио, голосовое и анимация.",
            reply_markup=admin_broadcast_menu(),
        )
        return WAITING_BROADCAST_CONTENT

    settings = context.application.bot_data[SETTINGS_KEY]
    plan = build_broadcast_targets(settings)
    if not plan["targets"]:
        await update.message.reply_text(
            "Пока нет подписчиков для рассылки.",
            reply_markup=admin_menu(),
        )
        return ConversationHandler.END

    user_delivery_bot = context.application.bot_data.get(USER_DELIVERY_BOT_KEY)
    admin_delivery_bot = context.application.bot
    reusable_file_ids = {"user": None, "admin": None}
    sent_count = 0
    failed_ids = []
    skipped_ids = []

    await update.message.reply_text(
        f"Начинаю рассылку по {plan['total_count']} пользователям...",
        reply_markup=admin_broadcast_menu(),
    )

    for index, target in enumerate(plan["targets"], start=1):
        chat_id = target["chat_id"]
        channel = target["channel"]
        delivery_bot = user_delivery_bot if channel == "user" else admin_delivery_bot

        if delivery_bot is None:
            skipped_ids.append(chat_id)
            continue

        try:
            reusable_file_ids[channel], delivered = await _send_payload(
                delivery_bot,
                chat_id,
                payload,
                reusable_file_ids[channel],
            )
            if delivered:
                sent_count += 1
        except RetryAfter as exc:
            await asyncio.sleep(float(exc.retry_after) + 1)
            try:
                reusable_file_ids[channel], delivered = await _send_payload(
                    delivery_bot,
                    chat_id,
                    payload,
                    reusable_file_ids[channel],
                )
                if delivered:
                    sent_count += 1
            except TelegramError:
                failed_ids.append(chat_id)
        except Forbidden:
            if channel == "user":
                set_user_status(chat_id, "blocked")
            else:
                set_admin_subscriber_status(chat_id, "blocked")
            failed_ids.append(chat_id)
        except TelegramError:
            failed_ids.append(chat_id)

        if index % 25 == 0:
            await asyncio.sleep(1)

    failed_preview = ", ".join(str(chat_id) for chat_id in failed_ids[:10])
    failed_tail = ""
    if len(failed_ids) > 10:
        failed_tail = f"\nПервые недоставленные ID: {failed_preview} ..."
    elif failed_ids:
        failed_tail = f"\nНедоставленные ID: {failed_preview}"

    await update.message.reply_text(
        "✅ Рассылка завершена.\n\n"
        f"Успешно отправлено: {sent_count}\n"
        f"Не доставлено: {len(failed_ids)}\n"
        f"Пропущено: {len(skipped_ids)}"
        f"{failed_tail}",
        reply_markup=admin_menu(),
    )
    return ConversationHandler.END


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
    if text == BTN_ADMIN_BROADCAST:
        return await start_broadcast(update, context)
    if text == BTN_ADMIN_DELETE_USER:
        return await start_delete_user(update, context)

    await update.message.reply_text("Выбери действие из меню ниже.", reply_markup=admin_menu())


def build_application() -> Application:
    settings = get_settings()
    token = require_token(settings.admin_bot_token, "ADMIN_BOT_TOKEN")

    application = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    application.bot_data[SETTINGS_KEY] = settings

    broadcast_handler = ConversationHandler(
        entry_points=[
            CommandHandler("broadcast", start_broadcast),
            MessageHandler(filters.Regex(f"^{re.escape(BTN_ADMIN_BROADCAST)}$"), start_broadcast),
        ],
        states={
            WAITING_BROADCAST_CONTENT: [
                MessageHandler(filters.Regex(f"^{re.escape(BTN_CANCEL)}$"), cancel_broadcast),
                MessageHandler(~filters.COMMAND, handle_broadcast_content),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_broadcast)],
        allow_reentry=True,
    )

    delete_handler = ConversationHandler(
        entry_points=[
            CommandHandler("delete_user", start_delete_user),
            MessageHandler(filters.Regex(f"^{re.escape(BTN_ADMIN_DELETE_USER)}$"), start_delete_user),
        ],
        states={
            WAITING_DELETE_QUERY: [
                MessageHandler(filters.Regex(f"^{re.escape(BTN_CANCEL)}$"), cancel_delete_user),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_delete_query),
            ],
            WAITING_DELETE_CONFIRM: [
                MessageHandler(filters.Regex(f"^{re.escape(BTN_CANCEL)}$"), cancel_delete_user),
                MessageHandler(
                    filters.Regex(f"^{re.escape(BTN_ADMIN_DELETE_CONFIRM)}$"),
                    confirm_delete_user,
                ),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_delete_user)],
        allow_reentry=True,
    )

    application.add_handler(broadcast_handler)
    application.add_handler(delete_handler)
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
    application.add_error_handler(handle_error)
    return application


def main():
    init_db()
    if not acquire_worker_lock(ADMIN_LOCK_NAME):
        logger.error(
            "Админ-бот уже запущен в другом инстансе с этой же базой. "
            "Останавливаю текущий процесс, чтобы не словить двойной polling."
        )
        return

    logger.info("Запускаю админ-бота")
    try:
        build_application().run_polling()
    finally:
        release_worker_lock(ADMIN_LOCK_NAME)


if __name__ == "__main__":
    main()
