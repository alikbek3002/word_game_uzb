import re
from typing import Dict, Optional


DEFAULT_LANGUAGE = "ru"
SUPPORTED_LANGUAGES = ("ru", "uz")


BUTTONS: Dict[str, Dict[str, str]] = {
    "register": {
        "ru": "✨ Зарегистрироваться",
        "uz": "✨ Ro'yxatdan o'tish",
    },
    "play": {
        "ru": "🔍 Найти участника",
        "uz": "🔍 Ishtirokchini topish",
    },
    "profile": {
        "ru": "👤 Мой профиль",
        "uz": "👤 Mening profilim",
    },
    "score": {
        "ru": "🏆 Мой счёт",
        "uz": "🏆 Mening hisobim",
    },
    "leaderboard": {
        "ru": "🥇 Лидеры",
        "uz": "🥇 Liderlar",
    },
    "help": {
        "ru": "❓ Помощь",
        "uz": "❓ Yordam",
    },
    "edit_name": {
        "ru": "✏️ Имя",
        "uz": "✏️ Ism",
    },
    "edit_phone": {
        "ru": "📱 Телефон",
        "uz": "📱 Telefon",
    },
    "edit_photo": {
        "ru": "🖼 Фото",
        "uz": "🖼 Foto",
    },
    "back": {
        "ru": "⬅️ Назад",
        "uz": "⬅️ Orqaga",
    },
    "cancel": {
        "ru": "❌ Отмена",
        "uz": "❌ Bekor qilish",
    },
    "skip": {
        "ru": "🔄 Другой участник",
        "uz": "🔄 Boshqa ishtirokchi",
    },
    "later": {
        "ru": "⏰ Позже",
        "uz": "⏰ Keyinroq",
    },
    "share_phone": {
        "ru": "📲 Отправить мой номер",
        "uz": "📲 Raqamimni yuborish",
    },
    "language": {
        "ru": "🌐 Язык",
        "uz": "🌐 Til",
    },
    "lang_ru": {
        "ru": "🇷🇺 Русский",
        "uz": "🇷🇺 Русский",
    },
    "lang_uz": {
        "ru": "🇺🇿 O'zbekcha",
        "uz": "🇺🇿 O'zbekcha",
    },
    "invite_friends": {
        "ru": "👥 Пригласить друзей",
        "uz": "👥 Do'stlarni taklif qilish",
    },
}


TEXTS: Dict[str, Dict[str, str]] = {
    "ru": {
        "choose_language": (
            "🌐 Выбери язык\n\n"
            "Бот покажет регистрацию, меню и весь игровой процесс на выбранном языке."
        ),
        "choose_language_retry": "Выбери один из двух языков кнопками ниже.",
        "choose_language_updated": "🌐 Язык обновлён. Теперь продолжаем на русском.",
        "choose_language_cancelled": "Смена языка отменена.",
        "guest_not_registered": "✨ Ты ещё не зарегистрирован. Нажми кнопку ниже, и начнём.",
        "home_text": (
            "🎉 {name}, ты в игре!\n\n"
            "🏆 Очки: {score}\n"
            "✅ Найдено: {found_count} из {total_targets}\n"
            "🎯 Осталось: {remaining_count}\n\n"
            "Нажми кнопку ниже и бот сразу даст следующего участника."
        ),
        "return_intro": "👋 С возвращением!",
        "registration_referral_intro": (
            "🎁 Бонус на старте!\n\n"
            "Если порекомендуешь World Class 3 друзьям, получишь +10 баллов.\n"
            "Можно заполнить позже, для продолжения нажми кнопку «Позже»."
        ),
        "registration_referral_retry": (
            "Чтобы продолжить регистрацию, нажми «Позже».\n"
            "На шаге ниже нужно будет ввести своё имя."
        ),
        "registration_intro": (
            "👋 Добро пожаловать в «Найди незнакомца»!\n\n"
            "Сначала создадим твою карточку участника.\n"
            "✍️ Напиши своё имя текстом (например: Алина)."
        ),
        "help_text": (
            "Как это работает:\n"
            "1. Регистрируешься: имя, номер, фото.\n"
            "2. Нажимаешь «Найти участника».\n"
            "3. Бот показывает фото и имя человека.\n"
            "4. Находишь его вживую, узнаёшь номер и отправляешь в бот.\n\n"
            "Рекомендации друзей:\n"
            "Напишите номера телефонов своих трех друзей, кому вы порекомендуете World Class, и получите сразу +10 баллов.\n"
            "Этой рекомендацией можно воспользоваться только один раз.\n\n"
            "Команда /cancel отменяет текущий шаг."
        ),
        "invite_friends_prompt": (
            "👥 Пригласить друзей\n\n"
            "Напишите номера телефонов 3 друзей, которым вы рекомендуете World Class.\n\n"
            "📌 Правила:\n"
            "• Напишите ВСЕ 3 номера в ОДНОМ сообщении\n"
            "• Каждый номер с новой строки\n"
            "• Формат: +998XXXXXXXXX (узбекский код)\n"
            "• Все 3 номера должны быть разными\n"
            "• Воспользоваться можно только ОДИН раз\n\n"
            "✅ За приглашение вы получите сразу +10 баллов!\n\n"
            "Пример:\n"
            "+998901234567\n"
            "+998937654321\n"
            "+998991112233"
        ),
        "invite_friends_success": (
            "🎉 Спасибо! Номера успешно сохранены.\n\n"
            "✅ Вам начислено +10 баллов!\n"
            "🏆 Ваш текущий счёт: {score}"
        ),
        "invite_friends_already_used": "❌ Вы уже воспользовались приглашением друзей. Эта функция доступна только один раз.",
        "invite_friends_invalid_format": (
            "❌ Неверный формат. Пожалуйста, отправьте ровно 3 номера в одном сообщении.\n\n"
            "Каждый номер с новой строки, формат: +998XXXXXXXXX\n\n"
            "Пример:\n"
            "+998901234567\n"
            "+998937654321\n"
            "+998991112233"
        ),
        "invite_friends_duplicate_numbers": "❌ Все 3 номера должны быть разными. Пожалуйста, проверьте и отправьте заново.",
        "invite_friends_cancelled": "Приглашение друзей отменено.",
        "invalid_name": "Напиши имя длиной от 2 до 40 символов. Желательно без цифр и лишних знаков.",
        "ask_phone": (
            "📱 Теперь отправь свой номер.\n"
            "Можно нажать кнопку ниже или ввести вручную в любом удобном формате."
        ),
        "own_phone_only": "Пожалуйста, отправь свой собственный номер.",
        "press_contact_button": "Нажми системную кнопку отправки контакта ниже.",
        "invalid_phone": "Номер выглядит странно. Отправь телефон ещё раз, например: +998 90 123 45 67",
        "ask_photo": (
            "🖼 Отлично. Теперь отправь своё фото как обычную фотографию, не файлом.\n"
            "Именно его увидят другие участники во время поиска."
        ),
        "photo_required": "Нужно именно фото. Попробуй отправить его ещё раз.",
        "profile_created": (
            "✅ Готово! Профиль создан.\n\n"
            "Теперь можно искать участников, смотреть счёт и редактировать профиль прямо из меню."
        ),
        "cancel_registered": "Регистрация или редактирование отменены.",
        "cancel_guest": "Регистрация отменена.",
        "register_first": "Сначала зарегистрируйся через /start.",
        "username_missing": "не указан",
        "profile_text": (
            "👤 Твой профиль\n\n"
            "Имя: {name}\n"
            "Username: {username}\n"
            "Телефон: {phone}\n"
            "Очки: {score}\n"
            "Найдено участников: {found_count}\n\n"
            "Если хочешь что-то обновить, выбери нужный пункт ниже."
        ),
        "score_text": (
            "🏆 У тебя {score} очк.\n"
            "✅ Найдено: {found_count} из {total_targets}\n"
            "🎯 Осталось: {remaining_count}"
        ),
        "leaderboard_empty": "📊 Пока в таблице лидеров никого нет.",
        "leaderboard_title": "🏆 Топ игроков:\n",
        "leaderboard_line": "{badge} {name} — {score} очк.",
        "no_targets": "😅 Пока кроме тебя никого нет в игре. Подожди, пока зарегистрируются другие.",
        "all_found": "🏁 Ты уже нашёл всех доступных участников. Отличная работа!",
        "target_caption": (
            "🔍 Новый поиск\n\n"
            "👤 Имя: {name}\n"
            "🏆 Твой прогресс: {found_count} из {total_targets}\n\n"
            "Найди этого человека на мероприятии, узнай его номер и пришли сюда.\n"
            "Если хочешь другую цель, нажми «Другой участник»."
        ),
        "session_lost": "Сессия поиска сбилась. Нажми «Найти участника» ещё раз.",
        "guess_bonus_new": "+1 очко!",
        "guess_bonus_repeat": "Повтор уже был засчитан раньше.",
        "guess_correct": (
            "✅ Номер совпал.\n"
            "{bonus_text}\n"
            "🏆 Твой счёт: {score}\n"
            "🎯 Осталось участников: {remaining_count}"
        ),
        "guess_hint_first": "Пока не совпало. Попробуй ещё раз.",
        "guess_hint_second": "Подсказка: в номере {digits} цифр.",
        "guess_hint_third": "Подсказка: последние 2 цифры номера — {last_digits}.",
        "guess_wrong": (
            "❌ Неверный номер.\n"
            "{hint}\n\n"
            "Можешь ввести номер ещё раз или выбрать другого участника."
        ),
        "guess_cancelled": "Поиск остановлен. Когда будешь готов, нажми «Найти участника».",
        "edit_name_prompt": "Напиши новое имя:",
        "edit_name_invalid": "Имя должно быть от 2 до 40 символов и выглядеть как имя.",
        "edit_name_done": "Имя обновлено ✅",
        "edit_phone_prompt": "Отправь новый номер телефона.",
        "edit_phone_own_only": "Отправь, пожалуйста, свой собственный номер.",
        "edit_phone_invalid": "Номер не подошёл. Попробуй ещё раз.",
        "edit_phone_done": "Телефон обновлён ✅",
        "edit_photo_prompt": "Отправь новое фото профиля как обычную фотографию.",
        "edit_photo_done": "Фото обновлено ✅",
        "idle_registered": "Сейчас ничего не выполняется.",
        "idle_guest": "Сейчас нет активного шага регистрации.",
        "unknown_registered": "Я не понял это сообщение. Выбери действие из меню ниже.",
        "unknown_guest": "Я не понял это сообщение. Нажми «Зарегистрироваться», и начнём.",
        "invite_after_registration": (
            "🎁 Хотите сразу получить +10 баллов?\n\n"
            "Пригласите 3 друзей в World Class! Напишите их номера телефонов "
            "(формат: +998XXXXXXXXX), по одному на строке, в одном сообщении.\n\n"
            "Если не сейчас, нажмите «Позже» — кнопка будет в меню."
        ),
    },
    "uz": {
        "choose_language": (
            "🌐 Tilni tanlang\n\n"
            "Bot ro'yxatdan o'tish, menyu va o'yin jarayonini tanlangan tilda ko'rsatadi."
        ),
        "choose_language_retry": "Pastdagi tugmalardan birini tanlang.",
        "choose_language_updated": "🌐 Til yangilandi. Endi davom etamiz.",
        "choose_language_cancelled": "Tilni almashtirish bekor qilindi.",
        "guest_not_registered": "✨ Siz hali ro'yxatdan o'tmagansiz. Pastdagi tugmani bosing va boshlaymiz.",
        "home_text": (
            "🎉 {name}, siz o'yindasiz!\n\n"
            "🏆 Ballar: {score}\n"
            "✅ Topilganlar: {found_count} / {total_targets}\n"
            "🎯 Qolganlari: {remaining_count}\n\n"
            "Pastdagi tugmani bosing, bot sizga darhol keyingi ishtirokchini beradi."
        ),
        "return_intro": "👋 Yana ko'rganimdan xursandman!",
        "registration_referral_intro": (
            "🎁 Boshlanish bonus!\n\n"
            "Agar World Class'ni 3 nafar do'stingizga tavsiya qilsangiz, +10 ball olasiz.\n"
            "Buni keyinroq ham to'ldirishingiz mumkin, davom etish uchun «Keyinroq» tugmasini bosing."
        ),
        "registration_referral_retry": (
            "Ro'yxatdan o'tishni davom ettirish uchun «Keyinroq» tugmasini bosing.\n"
            "Keyingi bosqichda ismingizni yozasiz."
        ),
        "registration_intro": (
            "👋 «Noma'lumni top» o'yiniga xush kelibsiz!\n\n"
            "Avval sizning ishtirokchi kartangizni yaratamiz.\n"
            "✍️ Ismingizni matn ko'rinishida yozing (masalan: Aliya)."
        ),
        "help_text": (
            "Bu qanday ishlaydi:\n"
            "1. Ro'yxatdan o'tasiz: ism, telefon, foto.\n"
            "2. «Ishtirokchini topish» tugmasini bosasiz.\n"
            "3. Bot odamning fotosi va ismini ko'rsatadi.\n"
            "4. Uni tadbirda topasiz, raqamini bilib olasiz va botga yuborasiz.\n\n"
            "Do'stlarni tavsiya qilish:\n"
            "3 nafar do'stingizning telefon raqamlarini yozing va darhol +10 ball oling.\n"
            "Bu tavsiyadan faqat bir marta foydalanish mumkin.\n\n"
            "/cancel buyrug'i joriy bosqichni bekor qiladi."
        ),
        "invalid_name": "2 tadan 40 tagacha belgidan iborat ism yuboring. Iloji bo'lsa, raqam va ortiqcha belgilar ishlatmang.",
        "ask_phone": (
            "📱 Endi telefon raqamingizni yuboring.\n"
            "Pastdagi tugmani bosishingiz yoki qo'lda yozishingiz mumkin."
        ),
        "own_phone_only": "Iltimos, o'zingizning telefon raqamingizni yuboring.",
        "press_contact_button": "Pastdagi tizim tugmasi orqali kontakt yuboring.",
        "invalid_phone": "Raqam noto'g'ri ko'rinyapti. Masalan, yana yuboring: +998 90 123 45 67",
        "ask_photo": (
            "🖼 Ajoyib. Endi profilingiz uchun oddiy foto yuboring, fayl emas.\n"
            "Qidiruv paytida boshqa ishtirokchilar aynan shu suratni ko'rishadi."
        ),
        "photo_required": "Aynan foto yuborish kerak. Iltimos, yana urinib ko'ring.",
        "profile_created": (
            "✅ Tayyor! Profil yaratildi.\n\n"
            "Endi menyu orqali ishtirokchilarni qidirishingiz, hisobni ko'rishingiz va profilingizni tahrirlashingiz mumkin."
        ),
        "cancel_registered": "Ro'yxatdan o'tish yoki tahrirlash bekor qilindi.",
        "cancel_guest": "Ro'yxatdan o'tish bekor qilindi.",
        "register_first": "Avval /start orqali ro'yxatdan o'ting.",
        "username_missing": "ko'rsatilmagan",
        "profile_text": (
            "👤 Sizning profilingiz\n\n"
            "Ism: {name}\n"
            "Username: {username}\n"
            "Telefon: {phone}\n"
            "Ballar: {score}\n"
            "Topilgan ishtirokchilar: {found_count}\n\n"
            "Biror narsani yangilamoqchi bo'lsangiz, pastdan kerakli bo'limni tanlang."
        ),
        "score_text": (
            "🏆 Sizda {score} ball bor.\n"
            "✅ Topilganlar: {found_count} / {total_targets}\n"
            "🎯 Qolganlari: {remaining_count}"
        ),
        "leaderboard_empty": "📊 Hali liderlar jadvalida hech kim yo'q.",
        "leaderboard_title": "🏆 O'yinchilar topi:\n",
        "leaderboard_line": "{badge} {name} — {score} ball.",
        "no_targets": "😅 Hozircha o'yinda sizdan boshqa hech kim yo'q. Boshqalar ro'yxatdan o'tishini kuting.",
        "all_found": "🏁 Siz barcha mavjud ishtirokchilarni topib bo'ldingiz. Zo'r ish!",
        "target_caption": (
            "🔍 Yangi qidiruv\n\n"
            "👤 Ism: {name}\n"
            "🏆 Sizning progress: {found_count} / {total_targets}\n\n"
            "Bu odamni tadbirda toping, raqamini bilib oling va shu yerga yuboring.\n"
            "Agar boshqa maqsad kerak bo'lsa, «Boshqa ishtirokchi» tugmasini bosing."
        ),
        "session_lost": "Qidiruv sessiyasi uzildi. Yana «Ishtirokchini topish» tugmasini bosing.",
        "guess_bonus_new": "+1 ball!",
        "guess_bonus_repeat": "Bu topish avvalroq ham hisoblangan edi.",
        "guess_correct": (
            "✅ Raqam mos keldi.\n"
            "{bonus_text}\n"
            "🏆 Sizning hisob: {score}\n"
            "🎯 Qolgan ishtirokchilar: {remaining_count}"
        ),
        "guess_hint_first": "Hali to'g'ri emas. Yana bir bor urinib ko'ring.",
        "guess_hint_second": "Maslahat: raqamda {digits} ta raqam bor.",
        "guess_hint_third": "Maslahat: raqamning oxirgi 2 ta soni — {last_digits}.",
        "guess_wrong": (
            "❌ Noto'g'ri raqam.\n"
            "{hint}\n\n"
            "Raqamni yana yuborishingiz yoki boshqa ishtirokchini tanlashingiz mumkin."
        ),
        "guess_cancelled": "Qidiruv to'xtatildi. Tayyor bo'lsangiz, «Ishtirokchini topish» tugmasini bosing.",
        "edit_name_prompt": "Yangi ismni yozing:",
        "edit_name_invalid": "Ism 2 tadan 40 tagacha belgidan iborat bo'lishi va ismga o'xshashi kerak.",
        "edit_name_done": "Ism yangilandi ✅",
        "edit_phone_prompt": "Yangi telefon raqamini yuboring.",
        "edit_phone_own_only": "Iltimos, o'zingizning telefon raqamingizni yuboring.",
        "edit_phone_invalid": "Raqam mos kelmadi. Yana urinib ko'ring.",
        "edit_phone_done": "Telefon yangilandi ✅",
        "edit_photo_prompt": "Yangi profil rasmini oddiy foto sifatida yuboring.",
        "edit_photo_done": "Foto yangilandi ✅",
        "idle_registered": "Hozir faol amal yo'q.",
        "idle_guest": "Hozir ro'yxatdan o'tishning faol bosqichi yo'q.",
        "unknown_registered": "Bu xabar tushunarsiz bo'ldi. Pastdagi menyudan amalni tanlang.",
        "unknown_guest": "Bu xabar tushunarsiz bo'ldi. «Ro'yxatdan o'tish» tugmasini bosing va boshlaymiz.",
        "invite_friends_prompt": (
            "👥 Do'stlarni taklif qilish\n\n"
            "World Class'ni tavsiya qilmoqchi bo'lgan 3 do'stingizning telefon raqamlarini yozing.\n\n"
            "📌 Qoidalar:\n"
            "• BARCHA 3 raqamni BITTA xabarda yozing\n"
            "• Har bir raqam yangi qatordan\n"
            "• Format: +998XXXXXXXXX (O'zbekiston kodi)\n"
            "• Barcha 3 raqam turli bo'lishi kerak\n"
            "• Faqat BIR MARTA foydalanish mumkin\n\n"
            "✅ Taklif uchun siz darhol +10 ball olasiz!\n\n"
            "Misol:\n"
            "+998901234567\n"
            "+998937654321\n"
            "+998991112233"
        ),
        "invite_friends_success": (
            "🎉 Rahmat! Raqamlar muvaffaqiyatli saqlandi.\n\n"
            "✅ Sizga +10 ball berildi!\n"
            "🏆 Joriy hisobingiz: {score}"
        ),
        "invite_friends_already_used": "❌ Siz allaqachon do'stlarni taklif qilish imkoniyatidan foydalangansiz. Bu funksiya faqat bir marta ishlaydi.",
        "invite_friends_invalid_format": (
            "❌ Noto'g'ri format. Iltimos, bitta xabarda aynan 3 raqam yuboring.\n\n"
            "Har bir raqam yangi qatordan, format: +998XXXXXXXXX\n\n"
            "Misol:\n"
            "+998901234567\n"
            "+998937654321\n"
            "+998991112233"
        ),
        "invite_friends_duplicate_numbers": "❌ Barcha 3 raqam turli bo'lishi kerak. Iltimos, tekshiring va qayta yuboring.",
        "invite_friends_cancelled": "Do'stlarni taklif qilish bekor qilindi.",
        "invite_after_registration": (
            "🎁 Darhol +10 ball olmoqchimisiz?\n\n"
            "3 nafar do'stingizni World Class'ga taklif qiling! Ularning telefon raqamlarini yozing "
            "(format: +998XXXXXXXXX), har biri yangi qatordan, bitta xabarda.\n\n"
            "Agar hozir emas, «Keyinroq» tugmasini bosing — tugma menyuda bo'ladi."
        ),
    },
}


COMMANDS: Dict[str, Dict[str, str]] = {
    "ru": {
        "start": "Открыть меню и регистрацию",
        "guess_who": "Получить следующего участника",
        "profile": "Показать профиль",
        "score": "Показать счёт",
        "help": "Краткая помощь",
    },
    "uz": {
        "start": "Menyu va ro'yxatdan o'tishni ochish",
        "guess_who": "Keyingi ishtirokchini olish",
        "profile": "Profilni ko'rsatish",
        "score": "Hisobni ko'rsatish",
        "help": "Qisqa yordam",
    },
}


def normalize_language(value: Optional[str]) -> Optional[str]:
    if not value:
        return None

    value = value.strip().lower()
    for language in SUPPORTED_LANGUAGES:
        if value == language or value.startswith(f"{language}-"):
            return language
    return None


def resolve_language(value: Optional[str], default: str = DEFAULT_LANGUAGE) -> str:
    return normalize_language(value) or default


def t(language: Optional[str], key: str, **kwargs) -> str:
    language = resolve_language(language)
    return TEXTS[language][key].format(**kwargs)


def button_text(key: str, language: Optional[str]) -> str:
    language = resolve_language(language)
    return BUTTONS[key][language]


def button_matches(text: str, key: str) -> bool:
    cleaned = (text or "").strip()
    return cleaned in {button_text(key, language) for language in SUPPORTED_LANGUAGES}


def button_pattern(key: str) -> str:
    labels = [re.escape(button_text(key, language)) for language in SUPPORTED_LANGUAGES]
    return f"^({'|'.join(labels)})$"
