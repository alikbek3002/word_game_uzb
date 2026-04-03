"""
Отдельный админ-бот для игры "Найди незнакомца".

Переменные окружения:
- ADMIN_BOT_TOKEN
- DB_PATH (опционально)
"""

import asyncio
import logging
import re
from io import BytesIO
from typing import Optional, Tuple

from telegram import Bot, BotCommand, InputFile, Message, Update
from telegram.error import Forbidden, RetryAfter, TelegramError
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
    get_admin_stats,
    get_admin_broadcast_recipients,
    get_leaderboard,
    get_recent_finds,
    get_recent_users,
    init_db,
    set_admin_subscriber_status,
    upsert_admin_subscriber,
)
from .keyboards import (
    BTN_ADMIN_BROADCAST,
    BTN_ADMIN_RECENT_FINDS,
    BTN_ADMIN_RECENT_USERS,
    BTN_ADMIN_STATS,
    BTN_ADMIN_TOP10,
    BTN_CANCEL,
    admin_broadcast_menu,
    admin_menu,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WAITING_BROADCAST_CONTENT = 1


async def post_init(application: Application):
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Открыть админ-панель"),
            BotCommand("stats", "Сводка по игре"),
            BotCommand("top10", "Топ-10 лидеров"),
            BotCommand("recent", "Последние находки"),
            BotCommand("new_users", "Новые участники"),
            BotCommand("broadcast", "Сделать рассылку всем"),
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


async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    recipients = get_admin_broadcast_recipients()
    if not recipients:
        await update.message.reply_text(
            "Пока некому отправлять рассылку: ещё никто не нажал /start в админ-боте.",
            reply_markup=admin_menu(),
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "📣 Режим рассылки включён.\n\n"
        "Отправь одно сообщение, и я разошлю его всем подписчикам этого админ-бота.\n"
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

    recipients = get_admin_broadcast_recipients()
    if not recipients:
        await update.message.reply_text(
            "Пока нет подписчиков для рассылки.",
            reply_markup=admin_menu(),
        )
        return ConversationHandler.END

    delivery_bot = context.application.bot
    reusable_file_id: Optional[str] = None
    sent_count = 0
    failed_ids = []

    await update.message.reply_text(
        f"Начинаю рассылку по {len(recipients)} пользователям...",
        reply_markup=admin_broadcast_menu(),
    )

    for index, chat_id in enumerate(recipients, start=1):
        try:
            reusable_file_id, delivered = await _send_payload(
                delivery_bot,
                chat_id,
                payload,
                reusable_file_id,
            )
            if delivered:
                sent_count += 1
        except RetryAfter as exc:
            await asyncio.sleep(float(exc.retry_after) + 1)
            try:
                reusable_file_id, delivered = await _send_payload(
                    delivery_bot,
                    chat_id,
                    payload,
                    reusable_file_id,
                )
                if delivered:
                    sent_count += 1
            except TelegramError:
                failed_ids.append(chat_id)
        except Forbidden:
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
        f"Не доставлено: {len(failed_ids)}"
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

    await update.message.reply_text("Выбери действие из меню ниже.", reply_markup=admin_menu())


def build_application() -> Application:
    settings = get_settings()
    token = require_token(settings.admin_bot_token, "ADMIN_BOT_TOKEN")

    application = Application.builder().token(token).post_init(post_init).build()

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

    application.add_handler(broadcast_handler)
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
