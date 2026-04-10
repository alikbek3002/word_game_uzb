from telegram import KeyboardButton, ReplyKeyboardMarkup

from .i18n import button_text

BTN_REGISTER = "register"
BTN_PLAY = "play"
BTN_PROFILE = "profile"
BTN_SCORE = "score"
BTN_LEADERBOARD = "leaderboard"
BTN_HELP = "help"
BTN_EDIT_NAME = "edit_name"
BTN_EDIT_PHONE = "edit_phone"
BTN_EDIT_PHOTO = "edit_photo"
BTN_BACK = "back"
BTN_CANCEL = "cancel"
BTN_SKIP = "skip"
BTN_LATER = "later"
BTN_SHARE_PHONE = "share_phone"
BTN_LANGUAGE = "language"
BTN_INVITE_FRIENDS = "invite_friends"
BTN_LANG_RU = "lang_ru"
BTN_LANG_UZ = "lang_uz"
BTN_ADMIN_STATS = "📊 Сводка"
BTN_ADMIN_TOP10 = "🏆 Топ-10 лидеров"
BTN_ADMIN_RECENT_FINDS = "🕒 Последние находки"
BTN_ADMIN_RECENT_USERS = "👥 Новые участники"
BTN_ADMIN_BROADCAST = "📣 Рассылка всем"
BTN_ADMIN_DELETE_USER = "🗑 Удалить пользователя"
BTN_ADMIN_DELETE_CONFIRM = "✅ Удалить"
BTN_ADMIN_REFERRALS = "👥 Приглашения"


def guest_menu(language: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [button_text(BTN_REGISTER, language)],
            [button_text(BTN_HELP, language)],
        ],
        resize_keyboard=True,
    )


def main_menu(language: str, show_invite: bool = False) -> ReplyKeyboardMarkup:
    keyboard = [
        [button_text(BTN_PLAY, language), button_text(BTN_PROFILE, language)],
        [button_text(BTN_SCORE, language)],
    ]
    if show_invite:
        keyboard.append([button_text(BTN_INVITE_FRIENDS, language)])
    keyboard.append([button_text(BTN_LANGUAGE, language), button_text(BTN_HELP, language)])
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
    )


def profile_menu(language: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [button_text(BTN_EDIT_NAME, language), button_text(BTN_EDIT_PHONE, language)],
            [button_text(BTN_EDIT_PHOTO, language), button_text(BTN_BACK, language)],
        ],
        resize_keyboard=True,
    )


def phone_request_menu(language: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(button_text(BTN_SHARE_PHONE, language), request_contact=True)],
            [button_text(BTN_CANCEL, language)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def photo_step_menu(language: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[button_text(BTN_CANCEL, language)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def text_step_menu(language: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[button_text(BTN_CANCEL, language)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def registration_offer_menu(language: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [button_text(BTN_LATER, language)],
            [button_text(BTN_CANCEL, language)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def game_menu(language: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[button_text(BTN_SKIP, language), button_text(BTN_CANCEL, language)]],
        resize_keyboard=True,
    )


def language_menu(language: str, include_cancel: bool = False) -> ReplyKeyboardMarkup:
    keyboard = [[button_text(BTN_LANG_RU, language), button_text(BTN_LANG_UZ, language)]]
    if include_cancel:
        keyboard.append([button_text(BTN_CANCEL, language)])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)


def admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [BTN_ADMIN_STATS, BTN_ADMIN_TOP10],
            [BTN_ADMIN_RECENT_FINDS, BTN_ADMIN_RECENT_USERS],
            [BTN_ADMIN_REFERRALS],
            [BTN_ADMIN_BROADCAST, BTN_ADMIN_DELETE_USER],
        ],
        resize_keyboard=True,
    )


def admin_broadcast_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[BTN_CANCEL]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def admin_delete_confirm_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[BTN_ADMIN_DELETE_CONFIRM, BTN_CANCEL]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def invite_step_menu(language: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[button_text(BTN_CANCEL, language)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def invite_after_reg_menu(language: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [button_text(BTN_LATER, language)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
