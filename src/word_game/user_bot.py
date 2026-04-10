"""
Пользовательский Telegram-бот игры "Найди незнакомца".

Переменные окружения:
- USER_BOT_TOKEN
- DB_PATH (опционально)
"""

import logging
import re
from typing import Optional

from telegram import BotCommand, Update
from telegram.error import Conflict
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
    get_leaderboard,
    get_progress,
    get_random_target,
    get_user,
    has_referrals,
    init_db,
    normalize_phone,
    record_found,
    release_worker_lock,
    register_user,
    save_referrals,
    update_user_name,
    update_user_language,
    update_user_phone,
    update_user_photo,
    update_user_username,
)
from .i18n import COMMANDS, button_matches, button_pattern, normalize_language, resolve_language, t
from .keyboards import (
    BTN_BACK,
    BTN_CANCEL,
    BTN_EDIT_NAME,
    BTN_EDIT_PHONE,
    BTN_EDIT_PHOTO,
    BTN_HELP,
    BTN_INVITE_FRIENDS,
    BTN_LANGUAGE,
    BTN_LANG_RU,
    BTN_LANG_UZ,
    BTN_LATER,
    BTN_PLAY,
    BTN_PROFILE,
    BTN_REGISTER,
    BTN_SCORE,
    BTN_SKIP,
    BTN_SHARE_PHONE,
    game_menu,
    guest_menu,
    invite_after_reg_menu,
    invite_step_menu,
    language_menu,
    main_menu,
    phone_request_menu,
    photo_step_menu,
    profile_menu,
    registration_offer_menu,
    text_step_menu,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

CHOOSE_LANGUAGE, ASK_REFERRAL, ASK_NAME, ASK_PHONE, ASK_PHOTO, WAITING_PHONE_GUESS, EDIT_NAME, EDIT_PHONE, EDIT_PHOTO, ASK_INVITE_PHONES, ASK_INVITE_AFTER_REG = range(11)
USER_LOCK_NAME = "word_game_user_bot"
LANGUAGE_NEXT_STEP_KEY = "language_next_step"
NAVIGATION_BUTTON_FILTER = (
    filters.Regex(button_pattern(BTN_REGISTER))
    | filters.Regex(button_pattern(BTN_PLAY))
    | filters.Regex(button_pattern(BTN_PROFILE))
    | filters.Regex(button_pattern(BTN_SCORE))
    | filters.Regex(button_pattern(BTN_HELP))
    | filters.Regex(button_pattern(BTN_BACK))
    | filters.Regex(button_pattern(BTN_INVITE_FRIENDS))
)


def validate_name(name: str) -> bool:
    cleaned = name.strip()
    if len(cleaned) < 2 or len(cleaned) > 40:
        return False
    return bool(re.search(r"[A-Za-zА-Яа-яЁё]", cleaned))


def validate_phone(phone: str) -> bool:
    digits = normalize_phone(phone)
    return 7 <= len(digits) <= 15


def validate_uz_phone(phone: str) -> bool:
    """Validate an Uzbek phone number: must start with +998 and have 12 digits total."""
    digits = normalize_phone(phone)
    return digits.startswith("998") and len(digits) == 12


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


def get_current_language(
    context: ContextTypes.DEFAULT_TYPE,
    user: Optional[dict] = None,
) -> str:
    if user:
        language = resolve_language(user.get("language"))
        context.user_data["lang"] = language
        return language

    return resolve_language(context.user_data.get("lang"))


def reset_user_state(context: ContextTypes.DEFAULT_TYPE):
    language = normalize_language(context.user_data.get("lang"))
    context.user_data.clear()
    if language:
        context.user_data["lang"] = language


def home_text(language: str, user: dict, progress: dict) -> str:
    return t(
        language,
        "home_text",
        name=user["name"],
        score=user["score"],
        found_count=progress["found_count"],
        total_targets=progress["total_targets"],
        remaining_count=progress["remaining_count"],
    )


def _get_main_menu(language: str, telegram_id: int) -> "ReplyKeyboardMarkup":
    """Return main_menu with invite button shown only if user hasn't used it yet."""
    show_invite = not has_referrals(telegram_id)
    return main_menu(language, show_invite=show_invite)


def leaderboard_text(language: str, limit: int = 10) -> str:
    rows = get_leaderboard(limit=limit)
    if not rows:
        return t(language, "leaderboard_empty")

    lines = [t(language, "leaderboard_title")]
    for index, row in enumerate(rows, start=1):
        badge = {1: "🥇", 2: "🥈", 3: "🥉"}.get(index, f"{index}.")
        lines.append(
            t(
                language,
                "leaderboard_line",
                badge=badge,
                name=row["name"],
                score=row["score"],
            )
        )
    return "\n".join(lines)


async def post_init(application: Application):
    for language in ("ru", "uz"):
        commands = [
            BotCommand(command, description)
            for command, description in COMMANDS[language].items()
        ]
        await application.bot.set_my_commands(commands, language_code=language)

    await application.bot.set_my_commands(
        [BotCommand(command, description) for command, description in COMMANDS["ru"].items()]
    )


async def show_language_picker(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    next_step: str,
    include_cancel: bool,
):
    current_language = resolve_language(context.user_data.get("lang"))
    context.user_data[LANGUAGE_NEXT_STEP_KEY] = next_step
    await update.message.reply_text(
        t(current_language, "choose_language"),
        reply_markup=language_menu(current_language, include_cancel=include_cancel),
    )
    return CHOOSE_LANGUAGE


async def choose_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    next_step = context.user_data.get(LANGUAGE_NEXT_STEP_KEY, "guest")

    if button_matches(text, BTN_LANG_RU):
        language = "ru"
    elif button_matches(text, BTN_LANG_UZ):
        language = "uz"
    elif button_matches(text, BTN_CANCEL):
        context.user_data.pop(LANGUAGE_NEXT_STEP_KEY, None)
        user = get_user(update.effective_user.id)
        language = get_current_language(context, user)
        if user:
            await send_registered_home(
                update,
                context,
                intro=t(language, "choose_language_cancelled"),
            )
            return ConversationHandler.END

        await update.message.reply_text(
            t(language, "choose_language_cancelled"),
            reply_markup=guest_menu(language),
        )
        return ConversationHandler.END
    else:
        current_language = resolve_language(context.user_data.get("lang"))
        await update.message.reply_text(
            t(current_language, "choose_language_retry"),
            reply_markup=language_menu(current_language, include_cancel=next_step != "register"),
        )
        return CHOOSE_LANGUAGE

    context.user_data["lang"] = language
    context.user_data.pop(LANGUAGE_NEXT_STEP_KEY, None)
    user = get_user(update.effective_user.id)

    if user:
        update_user_language(update.effective_user.id, language)

    if next_step == "register":
        reset_user_state(context)
        context.user_data["lang"] = language
        await update.message.reply_text(
            t(language, "registration_referral_intro"),
            reply_markup=registration_offer_menu(language),
        )
        return ASK_REFERRAL

    if user:
        await send_registered_home(update, context, intro=t(language, "choose_language_updated"))
        return ConversationHandler.END

    await update.message.reply_text(
        t(language, "choose_language_updated"),
        reply_markup=guest_menu(language),
    )
    return ConversationHandler.END


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    if isinstance(context.error, Conflict):
        logger.error(
            "Telegram вернул 409 Conflict: этот токен уже используется другим polling-инстансом. "
            "Проверь, что user-бот не запущен локально, нет второго Railway deployment и не включено больше одной реплики."
        )
        return

    logger.error(
        "Необработанная ошибка в user-боте: %s",
        context.error,
        exc_info=(type(context.error), context.error, context.error.__traceback__),
    )


async def send_registered_home(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    intro: Optional[str] = None,
):
    user = get_user(update.effective_user.id)
    if not user:
        if not normalize_language(context.user_data.get("lang")):
            return await show_language_picker(update, context, next_step="register", include_cancel=False)

        language = get_current_language(context)
        await update.message.reply_text(
            t(language, "guest_not_registered"),
            reply_markup=guest_menu(language),
        )
        return

    language = get_current_language(context, user)
    sync_username(update, user)
    progress = get_progress(update.effective_user.id)
    text = home_text(language, user, progress)
    if intro:
        text = f"{intro}\n\n{text}"
    await update.message.reply_text(text, reply_markup=_get_main_menu(language, update.effective_user.id))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if user:
        await send_registered_home(update, context, intro=t(user.get("language"), "return_intro"))
        return ConversationHandler.END

    if not normalize_language(context.user_data.get("lang")):
        reset_user_state(context)
        return await show_language_picker(update, context, next_step="register", include_cancel=False)

    language = get_current_language(context)
    reset_user_state(context)
    context.user_data["lang"] = language
    await update.message.reply_text(
        t(language, "registration_referral_intro"),
        reply_markup=registration_offer_menu(language),
    )
    return ASK_REFERRAL


async def ask_referral_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    language = get_current_language(context)
    text = update.message.text.strip()

    if button_matches(text, BTN_LATER):
        await update.message.reply_text(
            t(language, "registration_intro"),
            reply_markup=text_step_menu(language),
        )
        return ASK_NAME

    await update.message.reply_text(
        t(language, "registration_referral_retry"),
        reply_markup=registration_offer_menu(language),
    )
    return ASK_REFERRAL


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    language = get_current_language(context, user)
    reply_markup = _get_main_menu(language, update.effective_user.id) if user else guest_menu(language)
    await update.message.reply_text(
        t(language, "help_text"),
        reply_markup=reply_markup,
    )


async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    language = get_current_language(context)
    name = update.message.text.strip()
    if not validate_name(name):
        await update.message.reply_text(t(language, "invalid_name"))
        return ASK_NAME

    context.user_data["reg_name"] = name
    await update.message.reply_text(
        t(language, "ask_phone"),
        reply_markup=phone_request_menu(language),
    )
    return ASK_PHONE


async def ask_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    language = get_current_language(context)
    if update.message.contact:
        contact = update.message.contact
        if contact.user_id and contact.user_id != update.effective_user.id:
            await update.message.reply_text(t(language, "own_phone_only"))
            return ASK_PHONE
        phone = contact.phone_number
    else:
        phone = update.message.text.strip()
        if button_matches(phone, BTN_SHARE_PHONE):
            await update.message.reply_text(t(language, "press_contact_button"))
            return ASK_PHONE

    if not validate_phone(phone):
        await update.message.reply_text(t(language, "invalid_phone"))
        return ASK_PHONE

    context.user_data["reg_phone"] = phone
    await update.message.reply_text(
        t(language, "ask_photo"),
        reply_markup=photo_step_menu(language),
    )
    return ASK_PHOTO


async def ask_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    language = get_current_language(context)
    if not update.message.photo:
        await update.message.reply_text(t(language, "photo_required"))
        return ASK_PHOTO

    register_user(
        telegram_id=update.effective_user.id,
        name=context.user_data["reg_name"],
        phone=context.user_data["reg_phone"],
        photo_file_id=update.message.photo[-1].file_id,
        language=language,
        username=update.effective_user.username,
    )
    reset_user_state(context)
    context.user_data["lang"] = language
    await update.message.reply_text(
        t(language, "profile_created"),
        reply_markup=_get_main_menu(language, update.effective_user.id),
    )
    # Offer invite friends right after registration
    await update.message.reply_text(
        t(language, "invite_after_registration"),
        reply_markup=invite_after_reg_menu(language),
    )
    return ASK_INVITE_AFTER_REG


async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    language = get_current_language(context)
    reset_user_state(context)
    context.user_data["lang"] = language
    user = get_user(update.effective_user.id)
    if user:
        await update.message.reply_text(
            t(language, "cancel_registered"),
            reply_markup=_get_main_menu(language, update.effective_user.id),
        )
    else:
        await update.message.reply_text(
            t(language, "cancel_guest"),
            reply_markup=guest_menu(language),
        )
    return ConversationHandler.END


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if not user:
        language = get_current_language(context)
        await update.message.reply_text(
            t(language, "register_first"),
            reply_markup=guest_menu(language),
        )
        return

    language = get_current_language(context, user)
    sync_username(update, user)
    progress = get_progress(update.effective_user.id)
    username = f"@{user['username']}" if user.get("username") else t(language, "username_missing")
    await update.message.reply_photo(
        photo=user["photo_file_id"],
        caption=t(
            language,
            "profile_text",
            name=user["name"],
            username=username,
            phone=user["phone"],
            score=user["score"],
            found_count=progress["found_count"],
        ),
        reply_markup=profile_menu(language),
    )


async def score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if not user:
        language = get_current_language(context)
        await update.message.reply_text(
            t(language, "register_first"),
            reply_markup=guest_menu(language),
        )
        return

    language = get_current_language(context, user)
    progress = get_progress(update.effective_user.id)
    await update.message.reply_text(
        t(
            language,
            "score_text",
            score=user["score"],
            found_count=progress["found_count"],
            total_targets=progress["total_targets"],
            remaining_count=progress["remaining_count"],
        ),
        reply_markup=_get_main_menu(language, update.effective_user.id),
    )


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    language = get_current_language(context, user)
    reply_markup = _get_main_menu(language, update.effective_user.id) if user else guest_menu(language)
    await update.message.reply_text(leaderboard_text(language, limit=10), reply_markup=reply_markup)


async def present_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    finder_id = update.effective_user.id
    user = get_user(finder_id)
    language = get_current_language(context, user)
    progress = get_progress(finder_id)
    if progress["total_targets"] == 0:
        await update.message.reply_text(
            t(language, "no_targets"),
            reply_markup=_get_main_menu(language, finder_id),
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
            t(language, "all_found"),
            reply_markup=_get_main_menu(language, finder_id),
        )
        return ConversationHandler.END

    session_target_ids.append(target["telegram_id"])
    context.user_data["session_target_ids"] = session_target_ids
    context.user_data["current_target_id"] = target["telegram_id"]
    context.user_data["current_target_phone"] = target["normalized_phone"] or normalize_phone(target["phone"])
    context.user_data["guess_attempts"] = 0

    await update.message.reply_photo(
        photo=target["photo_file_id"],
        caption=t(
            language,
            "target_caption",
            name=target["name"],
            found_count=progress["found_count"],
            total_targets=progress["total_targets"],
        ),
        reply_markup=game_menu(language),
    )
    return WAITING_PHONE_GUESS


async def guess_who(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if not user:
        language = get_current_language(context)
        await update.message.reply_text(
            t(language, "register_first"),
            reply_markup=guest_menu(language),
        )
        return ConversationHandler.END

    language = get_current_language(context, user)
    sync_username(update, user)
    context.user_data["lang"] = language
    return await present_target(update, context)


async def skip_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await present_target(update, context)


async def check_phone_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    language = get_current_language(context)
    guess = normalize_phone(update.message.text)
    correct_phone = context.user_data.get("current_target_phone")
    target_id = context.user_data.get("current_target_id")

    if not correct_phone or not target_id:
        clear_game_state(context)
        await update.message.reply_text(
            t(language, "session_lost"),
            reply_markup=_get_main_menu(language, update.effective_user.id),
        )
        return ConversationHandler.END

    if guess == correct_phone:
        inserted = record_found(update.effective_user.id, target_id)
        clear_game_state(context)
        user = get_user(update.effective_user.id)
        language = get_current_language(context, user)
        progress = get_progress(update.effective_user.id)
        bonus_text = t(language, "guess_bonus_new") if inserted else t(language, "guess_bonus_repeat")
        await update.message.reply_text(
            t(
                language,
                "guess_correct",
                bonus_text=bonus_text,
                score=user["score"] if user else 0,
                remaining_count=progress["remaining_count"],
            ),
            reply_markup=_get_main_menu(language, update.effective_user.id),
        )
        return ConversationHandler.END

    attempts = context.user_data.get("guess_attempts", 0) + 1
    context.user_data["guess_attempts"] = attempts

    if attempts == 1:
        hint = t(language, "guess_hint_first")
    elif attempts == 2:
        hint = t(language, "guess_hint_second", digits=len(correct_phone))
    else:
        hint = t(language, "guess_hint_third", last_digits=correct_phone[-2:])

    await update.message.reply_text(
        t(language, "guess_wrong", hint=hint),
        reply_markup=game_menu(language),
    )
    return WAITING_PHONE_GUESS


async def cancel_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    language = get_current_language(context)
    clear_game_state(context)
    await update.message.reply_text(
        t(language, "guess_cancelled"),
        reply_markup=_get_main_menu(language, update.effective_user.id),
    )
    return ConversationHandler.END


async def start_edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if not user:
        language = get_current_language(context)
        await update.message.reply_text(
            t(language, "register_first"),
            reply_markup=guest_menu(language),
        )
        return ConversationHandler.END

    language = get_current_language(context, user)
    await update.message.reply_text(t(language, "edit_name_prompt"), reply_markup=profile_menu(language))
    return EDIT_NAME


async def save_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    language = get_current_language(context)
    name = update.message.text.strip()
    if not validate_name(name):
        await update.message.reply_text(t(language, "edit_name_invalid"))
        return EDIT_NAME

    update_user_name(update.effective_user.id, name)
    await update.message.reply_text(t(language, "edit_name_done"), reply_markup=profile_menu(language))
    await profile(update, context)
    return ConversationHandler.END


async def start_edit_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if not user:
        language = get_current_language(context)
        await update.message.reply_text(
            t(language, "register_first"),
            reply_markup=guest_menu(language),
        )
        return ConversationHandler.END

    language = get_current_language(context, user)
    await update.message.reply_text(
        t(language, "edit_phone_prompt"),
        reply_markup=phone_request_menu(language),
    )
    return EDIT_PHONE


async def save_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    language = get_current_language(context)
    if update.message.contact:
        contact = update.message.contact
        if contact.user_id and contact.user_id != update.effective_user.id:
            await update.message.reply_text(t(language, "edit_phone_own_only"))
            return EDIT_PHONE
        phone = contact.phone_number
    else:
        phone = update.message.text.strip()

    if not validate_phone(phone):
        await update.message.reply_text(t(language, "edit_phone_invalid"))
        return EDIT_PHONE

    update_user_phone(update.effective_user.id, phone)
    await update.message.reply_text(t(language, "edit_phone_done"), reply_markup=profile_menu(language))
    await profile(update, context)
    return ConversationHandler.END


async def start_edit_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if not user:
        language = get_current_language(context)
        await update.message.reply_text(
            t(language, "register_first"),
            reply_markup=guest_menu(language),
        )
        return ConversationHandler.END

    language = get_current_language(context, user)
    await update.message.reply_text(
        t(language, "edit_photo_prompt"),
        reply_markup=photo_step_menu(language),
    )
    return EDIT_PHOTO


async def save_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    language = get_current_language(context)
    if not update.message.photo:
        await update.message.reply_text(t(language, "photo_required"))
        return EDIT_PHOTO

    update_user_photo(update.effective_user.id, update.message.photo[-1].file_id)
    await update.message.reply_text(t(language, "edit_photo_done"), reply_markup=profile_menu(language))
    await profile(update, context)
    return ConversationHandler.END


async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_registered_home(update, context)


async def back_to_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await profile(update, context)
    return ConversationHandler.END


async def start_language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if not user:
        language = get_current_language(context)
        await update.message.reply_text(
            t(language, "register_first"),
            reply_markup=guest_menu(language),
        )
        return

    language = get_current_language(context, user)
    context.user_data["lang"] = language
    return await show_language_picker(update, context, next_step="home", include_cancel=True)


async def handle_navigation_during_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_game_state(context)
    return await route_menu_buttons(update, context)


async def handle_navigation_during_phone_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await route_menu_buttons(update, context)


async def route_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if button_matches(text, BTN_REGISTER):
        return await start(update, context)
    if button_matches(text, BTN_PLAY):
        return await guess_who(update, context)
    if button_matches(text, BTN_PROFILE):
        return await profile(update, context)
    if button_matches(text, BTN_SCORE):
        return await score(update, context)
    if button_matches(text, BTN_HELP):
        return await help_command(update, context)
    if button_matches(text, BTN_LANGUAGE):
        return await start_language_selection(update, context)
    if button_matches(text, BTN_INVITE_FRIENDS):
        return await start_invite_friends(update, context)
    if button_matches(text, BTN_BACK):
        return await back_to_menu(update, context)
    if button_matches(text, BTN_CANCEL):
        user = get_user(update.effective_user.id)
        language = get_current_language(context, user)
        if user:
            await update.message.reply_text(
                t(language, "idle_registered"),
                reply_markup=_get_main_menu(language, update.effective_user.id),
            )
        else:
            await update.message.reply_text(
                t(language, "idle_guest"),
                reply_markup=guest_menu(language),
            )
        return

    user = get_user(update.effective_user.id)
    language = get_current_language(context, user)
    if user:
        await update.message.reply_text(
            t(language, "unknown_registered"),
            reply_markup=_get_main_menu(language, update.effective_user.id),
        )
    else:
        if not normalize_language(context.user_data.get("lang")):
            return await show_language_picker(update, context, next_step="register", include_cancel=False)

        await update.message.reply_text(
            t(language, "unknown_guest"),
            reply_markup=guest_menu(language),
        )


async def start_invite_friends(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for invite friends from main menu button."""
    user = get_user(update.effective_user.id)
    if not user:
        language = get_current_language(context)
        await update.message.reply_text(
            t(language, "register_first"),
            reply_markup=guest_menu(language),
        )
        return ConversationHandler.END

    language = get_current_language(context, user)
    if has_referrals(update.effective_user.id):
        await update.message.reply_text(
            t(language, "invite_friends_already_used"),
            reply_markup=_get_main_menu(language, update.effective_user.id),
        )
        return ConversationHandler.END

    await update.message.reply_text(
        t(language, "invite_friends_prompt"),
        reply_markup=invite_step_menu(language),
    )
    return ASK_INVITE_PHONES


async def handle_invite_phones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process 3 phone numbers sent in one message for invite friends."""
    language = get_current_language(context)
    telegram_id = update.effective_user.id

    # Check if already used
    if has_referrals(telegram_id):
        await update.message.reply_text(
            t(language, "invite_friends_already_used"),
            reply_markup=_get_main_menu(language, telegram_id),
        )
        return ConversationHandler.END

    text = update.message.text.strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    if len(lines) != 3:
        await update.message.reply_text(
            t(language, "invite_friends_invalid_format"),
            reply_markup=invite_step_menu(language),
        )
        return ASK_INVITE_PHONES

    # Validate each phone
    phones = []
    for line in lines:
        if not validate_uz_phone(line):
            await update.message.reply_text(
                t(language, "invite_friends_invalid_format"),
                reply_markup=invite_step_menu(language),
            )
            return ASK_INVITE_PHONES
        phones.append(normalize_phone(line))

    # Check for duplicates
    if len(set(phones)) != 3:
        await update.message.reply_text(
            t(language, "invite_friends_duplicate_numbers"),
            reply_markup=invite_step_menu(language),
        )
        return ASK_INVITE_PHONES

    # Save referrals and award bonus
    save_referrals(
        telegram_id=telegram_id,
        phone1=phones[0],
        phone2=phones[1],
        phone3=phones[2],
        bonus=10,
    )

    user = get_user(telegram_id)
    await update.message.reply_text(
        t(language, "invite_friends_success", score=user["score"] if user else 10),
        reply_markup=_get_main_menu(language, telegram_id),
    )
    return ConversationHandler.END


async def cancel_invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    language = get_current_language(context)
    await update.message.reply_text(
        t(language, "invite_friends_cancelled"),
        reply_markup=_get_main_menu(language, update.effective_user.id),
    )
    return ConversationHandler.END


async def handle_invite_after_reg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the invite-after-registration step: user can enter phones or press Later."""
    language = get_current_language(context)
    text = update.message.text.strip()

    if button_matches(text, BTN_LATER):
        await send_registered_home(update, context)
        return ConversationHandler.END

    # Try to process as phone numbers
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) != 3:
        await update.message.reply_text(
            t(language, "invite_friends_invalid_format"),
            reply_markup=invite_after_reg_menu(language),
        )
        return ASK_INVITE_AFTER_REG

    phones = []
    for line in lines:
        if not validate_uz_phone(line):
            await update.message.reply_text(
                t(language, "invite_friends_invalid_format"),
                reply_markup=invite_after_reg_menu(language),
            )
            return ASK_INVITE_AFTER_REG
        phones.append(normalize_phone(line))

    if len(set(phones)) != 3:
        await update.message.reply_text(
            t(language, "invite_friends_duplicate_numbers"),
            reply_markup=invite_after_reg_menu(language),
        )
        return ASK_INVITE_AFTER_REG

    telegram_id = update.effective_user.id
    save_referrals(
        telegram_id=telegram_id,
        phone1=phones[0],
        phone2=phones[1],
        phone3=phones[2],
        bonus=10,
    )

    user = get_user(telegram_id)
    await update.message.reply_text(
        t(language, "invite_friends_success", score=user["score"] if user else 10),
        reply_markup=_get_main_menu(language, telegram_id),
    )
    return ConversationHandler.END


def build_application() -> Application:
    settings = get_settings()
    token = require_token(settings.user_bot_token, "USER_BOT_TOKEN")

    application = Application.builder().token(token).post_init(post_init).build()

    registration_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex(button_pattern(BTN_REGISTER)), start),
        ],
        states={
            CHOOSE_LANGUAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, choose_language),
            ],
            ASK_REFERRAL: [
                MessageHandler(filters.Regex(button_pattern(BTN_CANCEL)), cancel_registration),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_referral_choice),
            ],
            ASK_NAME: [
                MessageHandler(filters.Regex(button_pattern(BTN_CANCEL)), cancel_registration),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name),
            ],
            ASK_PHONE: [
                MessageHandler(filters.Regex(button_pattern(BTN_CANCEL)), cancel_registration),
                MessageHandler(NAVIGATION_BUTTON_FILTER, handle_navigation_during_phone_input),
                MessageHandler(filters.CONTACT, ask_phone),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_phone),
            ],
            ASK_PHOTO: [
                MessageHandler(filters.Regex(button_pattern(BTN_CANCEL)), cancel_registration),
                MessageHandler(filters.PHOTO, ask_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_photo),
            ],
            ASK_INVITE_AFTER_REG: [
                MessageHandler(filters.Regex(button_pattern(BTN_LATER)), handle_invite_after_reg),
                MessageHandler(filters.Regex(button_pattern(BTN_CANCEL)), cancel_invite),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_invite_after_reg),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_registration)],
        allow_reentry=True,
    )

    game_handler = ConversationHandler(
        entry_points=[
            CommandHandler("guess_who", guess_who),
            MessageHandler(filters.Regex(button_pattern(BTN_PLAY)), guess_who),
        ],
        states={
            WAITING_PHONE_GUESS: [
                MessageHandler(filters.Regex(button_pattern(BTN_SKIP)), skip_target),
                MessageHandler(filters.Regex(button_pattern(BTN_CANCEL)), cancel_guess),
                MessageHandler(NAVIGATION_BUTTON_FILTER, handle_navigation_during_guess),
                MessageHandler(filters.TEXT & ~filters.COMMAND, check_phone_guess),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_guess)],
        allow_reentry=True,
    )

    edit_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(button_pattern(BTN_EDIT_NAME)), start_edit_name),
            MessageHandler(filters.Regex(button_pattern(BTN_EDIT_PHONE)), start_edit_phone),
            MessageHandler(filters.Regex(button_pattern(BTN_EDIT_PHOTO)), start_edit_photo),
        ],
        states={
            EDIT_NAME: [
                MessageHandler(filters.Regex(button_pattern(BTN_CANCEL)), cancel_registration),
                MessageHandler(filters.Regex(button_pattern(BTN_BACK)), back_to_profile),
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_name),
            ],
            EDIT_PHONE: [
                MessageHandler(filters.Regex(button_pattern(BTN_CANCEL)), cancel_registration),
                MessageHandler(filters.Regex(button_pattern(BTN_BACK)), back_to_profile),
                MessageHandler(NAVIGATION_BUTTON_FILTER, handle_navigation_during_phone_input),
                MessageHandler(filters.CONTACT, save_phone),
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_phone),
            ],
            EDIT_PHOTO: [
                MessageHandler(filters.Regex(button_pattern(BTN_CANCEL)), cancel_registration),
                MessageHandler(filters.Regex(button_pattern(BTN_BACK)), back_to_profile),
                MessageHandler(filters.PHOTO, save_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_photo),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_registration)],
        allow_reentry=True,
    )

    invite_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(button_pattern(BTN_INVITE_FRIENDS)), start_invite_friends),
        ],
        states={
            ASK_INVITE_PHONES: [
                MessageHandler(filters.Regex(button_pattern(BTN_CANCEL)), cancel_invite),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_invite_phones),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_invite)],
        allow_reentry=True,
    )

    application.add_handler(registration_handler)
    application.add_handler(game_handler)
    application.add_handler(edit_handler)
    application.add_handler(invite_handler)
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("score", score))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.Regex(button_pattern(BTN_BACK)), back_to_menu))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, route_menu_buttons))
    application.add_error_handler(handle_error)
    return application


def main():
    init_db()
    logger.info("Пытаюсь получить lock для user-бота...")
    if not acquire_worker_lock(USER_LOCK_NAME):
        logger.error(
            "Не удалось получить lock для user-бота. "
            "Скорее всего, другой инстанс всё ещё не освободил его после деплоя."
        )
        return

    logger.info("Запускаю пользовательского бота")
    try:
        build_application().run_polling()
    finally:
        release_worker_lock(USER_LOCK_NAME)


if __name__ == "__main__":
    main()
