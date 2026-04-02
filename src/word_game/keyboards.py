from telegram import KeyboardButton, ReplyKeyboardMarkup


BTN_REGISTER = "✨ Зарегистрироваться"
BTN_PLAY = "🔍 Найти участника"
BTN_PROFILE = "👤 Мой профиль"
BTN_SCORE = "🏆 Мой счёт"
BTN_LEADERBOARD = "🥇 Лидеры"
BTN_HELP = "❓ Помощь"
BTN_EDIT_NAME = "✏️ Имя"
BTN_EDIT_PHONE = "📱 Телефон"
BTN_EDIT_PHOTO = "🖼 Фото"
BTN_BACK = "⬅️ Назад"
BTN_CANCEL = "❌ Отмена"
BTN_SKIP = "🔄 Другой участник"
BTN_SHARE_PHONE = "📲 Отправить мой номер"
BTN_ADMIN_STATS = "📊 Сводка"
BTN_ADMIN_TOP10 = "🏆 Топ-10 лидеров"
BTN_ADMIN_RECENT_FINDS = "🕒 Последние находки"
BTN_ADMIN_RECENT_USERS = "👥 Новые участники"
BTN_ADMIN_BROADCAST = "📣 Рассылка всем"


def guest_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[BTN_REGISTER], [BTN_HELP]],
        resize_keyboard=True,
    )


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [BTN_PLAY, BTN_PROFILE],
            [BTN_SCORE, BTN_LEADERBOARD],
            [BTN_HELP],
        ],
        resize_keyboard=True,
    )


def profile_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [BTN_EDIT_NAME, BTN_EDIT_PHONE],
            [BTN_EDIT_PHOTO, BTN_BACK],
        ],
        resize_keyboard=True,
    )


def phone_request_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_SHARE_PHONE, request_contact=True)],
            [BTN_CANCEL],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def photo_step_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True, one_time_keyboard=True)


def game_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[BTN_SKIP, BTN_CANCEL]], resize_keyboard=True)


def admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [BTN_ADMIN_STATS, BTN_ADMIN_TOP10],
            [BTN_ADMIN_RECENT_FINDS, BTN_ADMIN_RECENT_USERS],
            [BTN_ADMIN_BROADCAST],
        ],
        resize_keyboard=True,
    )


def admin_broadcast_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[BTN_CANCEL]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
