"""
Пользовательский Telegram-бот игры "Найди незнакомца".

Переменные окружения:
- USER_BOT_TOKEN или BOT_TOKEN
- DB_PATH (опционально)
"""

import logging
import re
from typing import Optional

from telegram import BotCommand, Update
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
    get_leaderboard,
    get_progress,
    get_random_target,
    get_user,
    init_db,
    normalize_phone,
    record_found,
    register_user,
    update_user_name,
    update_user_phone,
    update_user_photo,
    update_user_username,
)
from .keyboards import (
    BTN_BACK,
    BTN_CANCEL,
    BTN_EDIT_NAME,
    BTN_EDIT_PHONE,
    BTN_EDIT_PHOTO,
    BTN_HELP,
    BTN_LEADERBOARD,
    BTN_PLAY,
    BTN_PROFILE,
    BTN_REGISTER,
    BTN_SCORE,
    BTN_SKIP,
    BTN_SHARE_PHONE,
    game_menu,
    guest_menu,
    main_menu,
    phone_request_menu,
    photo_step_menu,
    profile_menu,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ASK_NAME, ASK_PHONE, ASK_PHOTO, WAITING_PHONE_GUESS, EDIT_NAME, EDIT_PHONE, EDIT_PHOTO = range(7)


def validate_name(name: str) -> bool:
    cleaned = name.strip()
    if len(cleaned) < 2 or len(cleaned) > 40:
        return False
    return bool(re.search(r"[A-Za-zА-Яа-яЁё]", cleaned))


def validate_phone(phone: str) -> bool:
    digits = normalize_phone(phone)
    return 7 <= len(digits) <= 15


def mask_phone(phone: str) -> str:
    digits = normalize_phone(phone)
    if len(digits) <= 4:
        return phone
    return f"+{digits[:3]} ••• •• {digits[-2:]}"


def sync_username(update: Update, user: Optional[dict]):
    telegram_username = update.effective_user.username
    if user and user.get("username") != telegram_username:
        update_user_username(update.effective_user.id, telegram_username)


def clear_game_state(context: ContextTypes.DEFAULT_TYPE):
    for key in ("current_target_id", "current_target_phone", "guess_attempts", "session_target_ids"):
        context.user_data.pop(key, None)


def home_text(user: dict, progress: dict) -> str:
    return (
        f"🎉 {user['name']}, ты в игре!\n\n"
        f"🏆 Очки: {user['score']}\n"
        f"✅ Найдено: {progress['found_count']} из {progress['total_targets']}\n"
        f"🎯 Осталось: {progress['remaining_count']}\n\n"
        "Нажми кнопку ниже и бот сразу даст следующего участника."
    )


def leaderboard_text(limit: int = 10) -> str:
    rows = get_leaderboard(limit=limit)
    if not rows:
        return "📊 Пока в таблице лидеров никого нет."

    lines = ["🏆 Топ игроков:\n"]
    for index, row in enumerate(rows, start=1):
        badge = {1: "🥇", 2: "🥈", 3: "🥉"}.get(index, f"{index}.")
        lines.append(f"{badge} {row['name']} — {row['score']} очк.")
    return "\n".join(lines)


async def post_init(application: Application):
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Открыть меню и регистрацию"),
            BotCommand("guess_who", "Получить следующего участника"),
            BotCommand("profile", "Показать профиль"),
            BotCommand("score", "Показать счёт"),
            BotCommand("leaderboard", "Показать лидеров"),
            BotCommand("help", "Краткая помощь"),
        ]
    )


async def send_registered_home(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    intro: Optional[str] = None,
):
    user = get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text(
            "✨ Ты ещё не зарегистрирован. Нажми кнопку ниже, и начнём.",
            reply_markup=guest_menu(),
        )
        return

    sync_username(update, user)
    progress = get_progress(update.effective_user.id)
    text = home_text(user, progress)
    if intro:
        text = f"{intro}\n\n{text}"
    await update.message.reply_text(text, reply_markup=main_menu())


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if user:
        await send_registered_home(update, context, intro="👋 С возвращением!")
        return ConversationHandler.END

    context.user_data.clear()
    await update.message.reply_text(
        "👋 Добро пожаловать в «Найди незнакомца»!\n\n"
        "Сначала создадим твою карточку участника. Как тебя зовут?",
        reply_markup=guest_menu(),
    )
    return ASK_NAME


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    reply_markup = main_menu() if user else guest_menu()
    await update.message.reply_text(
        "Как это работает:\n"
        "1. Регистрируешься: имя, номер, фото.\n"
        "2. Нажимаешь «Найти участника».\n"
        "3. Бот показывает фото и имя человека.\n"
        "4. Находишь его вживую, узнаёшь номер и отправляешь в бот.\n\n"
        "Команда /cancel отменяет текущий шаг.",
        reply_markup=reply_markup,
    )


async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if not validate_name(name):
        await update.message.reply_text(
            "Напиши имя длиной от 2 до 40 символов. Желательно без цифр и лишних знаков."
        )
        return ASK_NAME

    context.user_data["reg_name"] = name
    await update.message.reply_text(
        "📱 Теперь отправь свой номер.\n"
        "Можно нажать кнопку ниже или ввести вручную в любом удобном формате.",
        reply_markup=phone_request_menu(),
    )
    return ASK_PHONE


async def ask_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.contact:
        contact = update.message.contact
        if contact.user_id and contact.user_id != update.effective_user.id:
            await update.message.reply_text("Пожалуйста, отправь свой собственный номер.")
            return ASK_PHONE
        phone = contact.phone_number
    else:
        phone = update.message.text.strip()
        if phone == BTN_SHARE_PHONE:
            await update.message.reply_text("Нажми системную кнопку отправки контакта ниже.")
            return ASK_PHONE

    if not validate_phone(phone):
        await update.message.reply_text(
            "Номер выглядит странно. Отправь телефон ещё раз, например: +998 90 123 45 67"
        )
        return ASK_PHONE

    context.user_data["reg_phone"] = phone
    await update.message.reply_text(
        "🖼 Отлично. Теперь отправь своё фото как обычную фотографию, не файлом.\n"
        "Именно его увидят другие участники во время поиска.",
        reply_markup=photo_step_menu(),
    )
    return ASK_PHOTO


async def ask_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("Нужно именно фото. Попробуй отправить его ещё раз.")
        return ASK_PHOTO

    register_user(
        telegram_id=update.effective_user.id,
        name=context.user_data["reg_name"],
        phone=context.user_data["reg_phone"],
        photo_file_id=update.message.photo[-1].file_id,
        username=update.effective_user.username,
    )
    context.user_data.clear()
    await update.message.reply_text(
        "✅ Готово! Профиль создан.\n\n"
        "Теперь можно искать участников, смотреть счёт и редактировать профиль прямо из меню.",
        reply_markup=main_menu(),
    )
    await send_registered_home(update, context)
    return ConversationHandler.END


async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    user = get_user(update.effective_user.id)
    if user:
        await update.message.reply_text("Регистрация или редактирование отменены.", reply_markup=main_menu())
    else:
        await update.message.reply_text("Регистрация отменена.", reply_markup=guest_menu())
    return ConversationHandler.END


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text(
            "Сначала зарегистрируйся через /start.",
            reply_markup=guest_menu(),
        )
        return

    sync_username(update, user)
    progress = get_progress(update.effective_user.id)
    username = f"@{user['username']}" if user.get("username") else "не указан"
    await update.message.reply_text(
        "👤 Твой профиль\n\n"
        f"Имя: {user['name']}\n"
        f"Username: {username}\n"
        f"Телефон: {mask_phone(user['phone'])}\n"
        f"Очки: {user['score']}\n"
        f"Найдено участников: {progress['found_count']}\n\n"
        "Если хочешь что-то обновить, выбери нужный пункт ниже.",
        reply_markup=profile_menu(),
    )


async def score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("Сначала зарегистрируйся через /start.", reply_markup=guest_menu())
        return

    progress = get_progress(update.effective_user.id)
    await update.message.reply_text(
        f"🏆 У тебя {user['score']} очк.\n"
        f"✅ Найдено: {progress['found_count']} из {progress['total_targets']}\n"
        f"🎯 Осталось: {progress['remaining_count']}",
        reply_markup=main_menu(),
    )


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    reply_markup = main_menu() if user else guest_menu()
    await update.message.reply_text(leaderboard_text(limit=10), reply_markup=reply_markup)


async def present_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    finder_id = update.effective_user.id
    progress = get_progress(finder_id)
    if progress["total_targets"] == 0:
        await update.message.reply_text(
            "😅 Пока кроме тебя никого нет в игре. Подожди, пока зарегистрируются другие.",
            reply_markup=main_menu(),
        )
        return ConversationHandler.END

    session_target_ids = context.user_data.get("session_target_ids", [])
    target = get_random_target(finder_id, excluded_ids=session_target_ids)
    if not target and session_target_ids:
        session_target_ids = []
        target = get_random_target(finder_id)

    if not target:
        clear_game_state(context)
        await update.message.reply_text(
            "🏁 Ты уже нашёл всех доступных участников. Отличная работа!",
            reply_markup=main_menu(),
        )
        return ConversationHandler.END

    session_target_ids.append(target["telegram_id"])
    context.user_data["session_target_ids"] = session_target_ids
    context.user_data["current_target_id"] = target["telegram_id"]
    context.user_data["current_target_phone"] = target["normalized_phone"] or normalize_phone(target["phone"])
    context.user_data["guess_attempts"] = 0

    await update.message.reply_photo(
        photo=target["photo_file_id"],
        caption=(
            "🔍 Новый поиск\n\n"
            f"👤 Имя: {target['name']}\n"
            f"🏆 Твой прогресс: {progress['found_count']} из {progress['total_targets']}\n\n"
            "Найди этого человека на мероприятии, узнай его номер и пришли сюда.\n"
            "Если хочешь другую цель, нажми «Другой участник»."
        ),
        reply_markup=game_menu(),
    )
    return WAITING_PHONE_GUESS


async def guess_who(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("Сначала зарегистрируйся через /start.", reply_markup=guest_menu())
        return ConversationHandler.END

    sync_username(update, user)
    return await present_target(update, context)


async def skip_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await present_target(update, context)


async def check_phone_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    guess = normalize_phone(update.message.text)
    correct_phone = context.user_data.get("current_target_phone")
    target_id = context.user_data.get("current_target_id")

    if not correct_phone or not target_id:
        clear_game_state(context)
        await update.message.reply_text(
            "Сессия поиска сбилась. Нажми «Найти участника» ещё раз.",
            reply_markup=main_menu(),
        )
        return ConversationHandler.END

    if guess == correct_phone:
        inserted = record_found(update.effective_user.id, target_id)
        clear_game_state(context)
        user = get_user(update.effective_user.id)
        progress = get_progress(update.effective_user.id)
        bonus_text = "+1 очко!" if inserted else "Повтор уже был засчитан раньше."
        await update.message.reply_text(
            "✅ Номер совпал.\n"
            f"{bonus_text}\n"
            f"🏆 Твой счёт: {user['score'] if user else 0}\n"
            f"🎯 Осталось участников: {progress['remaining_count']}",
            reply_markup=main_menu(),
        )
        return ConversationHandler.END

    attempts = context.user_data.get("guess_attempts", 0) + 1
    context.user_data["guess_attempts"] = attempts

    if attempts == 1:
        hint = "Пока не совпало. Попробуй ещё раз."
    elif attempts == 2:
        hint = f"Подсказка: в номере {len(correct_phone)} цифр."
    else:
        hint = f"Подсказка: последние 2 цифры номера — {correct_phone[-2:]}."

    await update.message.reply_text(
        f"❌ Неверный номер.\n{hint}\n\n"
        "Можешь ввести номер ещё раз или выбрать другого участника.",
        reply_markup=game_menu(),
    )
    return WAITING_PHONE_GUESS


async def cancel_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_game_state(context)
    await update.message.reply_text(
        "Поиск остановлен. Когда будешь готов, нажми «Найти участника».",
        reply_markup=main_menu(),
    )
    return ConversationHandler.END


async def start_edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not get_user(update.effective_user.id):
        await update.message.reply_text("Сначала зарегистрируйся через /start.", reply_markup=guest_menu())
        return ConversationHandler.END

    await update.message.reply_text("Напиши новое имя:", reply_markup=profile_menu())
    return EDIT_NAME


async def save_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if not validate_name(name):
        await update.message.reply_text("Имя должно быть от 2 до 40 символов и выглядеть как имя.")
        return EDIT_NAME

    update_user_name(update.effective_user.id, name)
    await update.message.reply_text("Имя обновлено ✅", reply_markup=profile_menu())
    await profile(update, context)
    return ConversationHandler.END


async def start_edit_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not get_user(update.effective_user.id):
        await update.message.reply_text("Сначала зарегистрируйся через /start.", reply_markup=guest_menu())
        return ConversationHandler.END

    await update.message.reply_text(
        "Отправь новый номер телефона.",
        reply_markup=phone_request_menu(),
    )
    return EDIT_PHONE


async def save_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.contact:
        contact = update.message.contact
        if contact.user_id and contact.user_id != update.effective_user.id:
            await update.message.reply_text("Отправь, пожалуйста, свой собственный номер.")
            return EDIT_PHONE
        phone = contact.phone_number
    else:
        phone = update.message.text.strip()

    if not validate_phone(phone):
        await update.message.reply_text("Номер не подошёл. Попробуй ещё раз.")
        return EDIT_PHONE

    update_user_phone(update.effective_user.id, phone)
    await update.message.reply_text("Телефон обновлён ✅", reply_markup=profile_menu())
    await profile(update, context)
    return ConversationHandler.END


async def start_edit_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not get_user(update.effective_user.id):
        await update.message.reply_text("Сначала зарегистрируйся через /start.", reply_markup=guest_menu())
        return ConversationHandler.END

    await update.message.reply_text(
        "Отправь новое фото профиля как обычную фотографию.",
        reply_markup=photo_step_menu(),
    )
    return EDIT_PHOTO


async def save_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("Нужно именно фото. Попробуй ещё раз.")
        return EDIT_PHOTO

    update_user_photo(update.effective_user.id, update.message.photo[-1].file_id)
    await update.message.reply_text("Фото обновлено ✅", reply_markup=profile_menu())
    await profile(update, context)
    return ConversationHandler.END


async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_registered_home(update, context)


async def back_to_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await profile(update, context)
    return ConversationHandler.END


async def route_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == BTN_REGISTER:
        return await start(update, context)
    if text == BTN_PLAY:
        return await guess_who(update, context)
    if text == BTN_PROFILE:
        return await profile(update, context)
    if text == BTN_SCORE:
        return await score(update, context)
    if text == BTN_LEADERBOARD:
        return await leaderboard(update, context)
    if text == BTN_HELP:
        return await help_command(update, context)
    if text == BTN_BACK:
        return await back_to_menu(update, context)
    if text == BTN_CANCEL:
        user = get_user(update.effective_user.id)
        if user:
            await update.message.reply_text("Сейчас ничего не выполняется.", reply_markup=main_menu())
        else:
            await update.message.reply_text("Сейчас нет активного шага регистрации.", reply_markup=guest_menu())
        return

    user = get_user(update.effective_user.id)
    if user:
        await update.message.reply_text(
            "Я не понял это сообщение. Выбери действие из меню ниже.",
            reply_markup=main_menu(),
        )
    else:
        await update.message.reply_text(
            "Я не понял это сообщение. Нажми «Зарегистрироваться», и начнём.",
            reply_markup=guest_menu(),
        )


def build_application() -> Application:
    settings = get_settings()
    token = require_token(settings.user_bot_token, "USER_BOT_TOKEN")

    application = Application.builder().token(token).post_init(post_init).build()

    registration_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex(f"^{re.escape(BTN_REGISTER)}$"), start),
        ],
        states={
            ASK_NAME: [
                MessageHandler(filters.Regex(f"^{re.escape(BTN_CANCEL)}$"), cancel_registration),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name),
            ],
            ASK_PHONE: [
                MessageHandler(filters.Regex(f"^{re.escape(BTN_CANCEL)}$"), cancel_registration),
                MessageHandler(filters.CONTACT, ask_phone),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_phone),
            ],
            ASK_PHOTO: [
                MessageHandler(filters.Regex(f"^{re.escape(BTN_CANCEL)}$"), cancel_registration),
                MessageHandler(filters.PHOTO, ask_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_photo),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_registration)],
        allow_reentry=True,
    )

    game_handler = ConversationHandler(
        entry_points=[
            CommandHandler("guess_who", guess_who),
            MessageHandler(filters.Regex(f"^{re.escape(BTN_PLAY)}$"), guess_who),
        ],
        states={
            WAITING_PHONE_GUESS: [
                MessageHandler(filters.Regex(f"^{re.escape(BTN_SKIP)}$"), skip_target),
                MessageHandler(filters.Regex(f"^{re.escape(BTN_CANCEL)}$"), cancel_guess),
                MessageHandler(filters.TEXT & ~filters.COMMAND, check_phone_guess),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_guess)],
        allow_reentry=True,
    )

    edit_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(f"^{re.escape(BTN_EDIT_NAME)}$"), start_edit_name),
            MessageHandler(filters.Regex(f"^{re.escape(BTN_EDIT_PHONE)}$"), start_edit_phone),
            MessageHandler(filters.Regex(f"^{re.escape(BTN_EDIT_PHOTO)}$"), start_edit_photo),
        ],
        states={
            EDIT_NAME: [
                MessageHandler(filters.Regex(f"^{re.escape(BTN_CANCEL)}$"), cancel_registration),
                MessageHandler(filters.Regex(f"^{re.escape(BTN_BACK)}$"), back_to_profile),
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_name),
            ],
            EDIT_PHONE: [
                MessageHandler(filters.Regex(f"^{re.escape(BTN_CANCEL)}$"), cancel_registration),
                MessageHandler(filters.Regex(f"^{re.escape(BTN_BACK)}$"), back_to_profile),
                MessageHandler(filters.CONTACT, save_phone),
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_phone),
            ],
            EDIT_PHOTO: [
                MessageHandler(filters.Regex(f"^{re.escape(BTN_CANCEL)}$"), cancel_registration),
                MessageHandler(filters.Regex(f"^{re.escape(BTN_BACK)}$"), back_to_profile),
                MessageHandler(filters.PHOTO, save_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_photo),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_registration)],
        allow_reentry=True,
    )

    application.add_handler(registration_handler)
    application.add_handler(game_handler)
    application.add_handler(edit_handler)
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("score", score))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.Regex(f"^{re.escape(BTN_BACK)}$"), back_to_menu))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, route_menu_buttons))
    return application


def main():
    init_db()
    logger.info("Запускаю пользовательского бота")
    build_application().run_polling()


if __name__ == "__main__":
    main()
