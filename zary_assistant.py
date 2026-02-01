import os
import re
import html
import asyncio
import threading
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, HTTPServer

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

# =========================
# CONFIG
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env is empty. Set it in Render Environment Variables")

MANAGER_CHAT_ID = int(os.getenv("MANAGER_CHAT_ID", "7195737024"))
MANAGER_PHONE = os.getenv("MANAGER_PHONE", "+998771202255")
MANAGER_USERNAME = os.getenv("MANAGER_USERNAME", "").strip()  # без @ (можно пустым)

# ✅ ТВОИ ССЫЛКИ (показываем ТОЛЬКО в конце заказа: confirm или cancel)
CHANNEL_URL = os.getenv("CHANNEL_URL", "https://t.me/zaryco_official")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@zaryco_official")
INSTAGRAM_URL = os.getenv("INSTAGRAM_URL", "https://www.instagram.com/zary.co/")
YOUTUBE_URL = os.getenv("YOUTUBE_URL", "https://www.youtube.com/@ZARYCOOFFICIAL")

TZ = ZoneInfo("Asia/Tashkent")
WORK_START = time(9, 0)
WORK_END = time(21, 0)

# ⏱ авто-сброс если человек пропал
SESSION_TTL_MINUTES = int(os.getenv("SESSION_TTL_MINUTES", "15"))

# =========================
# SAFE SEND (HTML)
# =========================
def esc(s: str) -> str:
    return html.escape(s or "")

async def safe_answer(message: Message, text: str, reply_markup=None):
    try:
        await message.answer(text, reply_markup=reply_markup)
    except Exception:
        await message.answer(esc(text), reply_markup=reply_markup)

async def safe_answer_call(call: CallbackQuery, text: str, reply_markup=None):
    try:
        await call.message.answer(text, reply_markup=reply_markup)
    except Exception:
        await call.message.answer(esc(text), reply_markup=reply_markup)

# =========================
# TEXTS
# =========================
TEXT = {
    "ru": {
        "hello_ask_lang": "Выберите язык 👇",
        "hello": (
            "👋 Добро пожаловать в <b>ZARY &amp; CO</b> 🇺🇿\n"
            "Стильная и качественная детская одежда.\n\n"
            "Выберите действие кнопками 👇"
        ),
        "menu_title": "Выберите действие 👇",

        "brand": (
            "✨ <b>ZARY &amp; CO — национальный бренд детской одежды 🇺🇿</b>\n"
            "Удобно, красиво и качественно.\n"
            "ZARY &amp; CO — когда комфорт и стиль вместе."
        ),

        # Каталог всегда ведёт в канал (без инсты/ютуба)
        "photos_title": "📸 <b>Каталог</b>\nВыберите раздел:",
        "photos_go_channel": (
            "📸 Фото и новинки мы публикуем в <b>Telegram-канале</b>.\n"
            "Нажмите кнопку ниже 👇"
        ),

        "price_title": "🧾 <b>Прайс (укороченный)</b>\nВыберите раздел:",
        "price_boys": (
            "👶 <b>МАЛЬЧИКИ</b>\n"
            "• Верх: куртка/ветровка/бомбер/парка/анорак/жилетка\n"
            "• Толстовки: худи/свитшот/лонгслив/кардиган/флис\n"
            "• Низ: брюки/джинсы/шорты/комбинезон\n"
            "• Комплекты: спорткостюм/пижама/летний комплект"
        ),
        "price_girls": (
            "👧 <b>ДЕВОЧКИ</b>\n"
            "• Верх: куртка/ветровка/пальто/парка/анорак/жилетка\n"
            "• Платья/юбки: повседневное/нарядное/сарафан/юбка\n"
            "• Толстовки: худи/свитшот/лонгслив/кардиган/флис\n"
            "• Низ: брюки/джинсы/леггинсы/шорты/комбинезон\n"
            "• Комплекты: костюм/пижама/летний комплект"
        ),
        "price_unisex": (
            "🧒 <b>УНИСЕКС / БАЗА</b>\n"
            "• Футболка/лонгслив/водолазка/рубашка\n"
            "• Свитер/жилет/пижама\n"
            "• Спорткостюм/комбинезоны\n"
            "• Школьный костюм"
        ),

        "size_title": "📏 <b>Подбор размера (1–15 лет)</b>\nВыберите способ:",
        "size_age_ask": "Напишите возраст ребёнка (1–15). Пример: <code>7</code>",
        "size_height_ask": "Напишите рост в см. Пример: <code>125</code>",
        "size_bad_age": "Введите возраст цифрой от 1 до 15. Пример: <code>7</code>",
        "size_bad_height": "Введите рост цифрой (например: 125).",

        # ✅ Важно: если выбрали “по возрасту” — рост НЕ обязателен
        "size_result_age": (
            "📏 <b>Рекомендация по возрасту:</b>\n"
            "Возраст: {age} → примерно <b>{age_rec}</b>\n\n"
            "Если хотите — можете уточнить по росту (не обязательно)."
        ),
        "size_result_height": (
            "📏 <b>Рекомендация по росту:</b>\n"
            "Рост: {height} см → рекомендуем <b>{height_rec}</b>"
        ),

        "contact_title": (
            "📞 <b>Связаться</b>\n"
            "Заявки принимаем <b>24/7</b>.\n"
            "Менеджер отвечает <b>с 09:00 до 21:00</b>.\n\n"
            f"☎️ Номер менеджера: <b>{MANAGER_PHONE}</b>\n"
        ),

        "order_start": "🧾 <b>Оформляем заказ</b>\nКак вас зовут?",
        "order_phone": "📲 Отправьте номер телефона (или нажмите кнопку «📲 Отправить контакт»).",
        "order_city": "🏙 Ваш город/район?",
        "order_item": "👕 Что хотите заказать? (например: школьная форма / костюм / рубашка)",
        "order_size": (
            "👶 Возраст и рост одним сообщением.\n"
            "Пример: <code>7 лет, 125 см</code>\n\n"
            "Или нажмите: <b>📏 Подбор размера</b>"
        ),
        "order_size_bad": (
            "Нужно <b>и возраст, и рост</b>.\n"
            "Пример: <code>7 лет, 125 см</code>\n"
            "Или нажмите: <b>📏 Подбор размера</b>"
        ),
        "order_comment": "✍️ Комментарий (цвет/кол-во) или напишите «нет»",
        "order_review": (
            "🧾 <b>Проверьте заказ:</b>\n"
            "• Имя: {name}\n"
            "• Телефон: {phone}\n"
            "• Город: {city}\n"
            "• Товар: {item}\n"
            "• Возраст/рост: {size}\n"
            "• Комментарий: {comment}\n\n"
            "Подтвердить?"
        ),
        "order_sent": "✅ Спасибо! Заказ принят.\nМенеджер свяжется с вами ✅",

        "worktime_in": "⏱ Сейчас рабочее время — ответ будет быстрее.",
        "worktime_out": "⏱ Сейчас вне рабочего времени — менеджер ответит в рабочие часы.",

        "edit_choose": "✏️ Что хотите исправить?",
        "cancelled": "❌ Заказ отменён. Возвращаю в меню 👇",
        "unknown": "Пожалуйста, используйте кнопки меню 👇",
        "session_reset": "⏱ Вы долго не отвечали — я вернул вас в меню. Выберите действие 👇",

        # ✅ Только в конце (confirm/cancel)
        "end_links": (
            "📌 <b>Наши официальные страницы:</b>\n"
            f"📢 Telegram: {CHANNEL_URL}\n"
            f"📷 Instagram: {INSTAGRAM_URL}\n"
            f"▶️ YouTube: {YOUTUBE_URL}"
        ),
    },

    "uz": {
        "hello_ask_lang": "Tilni tanlang 👇",
        "hello": (
            "👋 Assalomu alaykum! <b>ZARY &amp; CO</b> 🇺🇿 ga xush kelibsiz!\n"
            "Zamonaviy va sifatli bolalar kiyimlari.\n\n"
            "Bo‘limni tanlang 👇"
        ),
        "menu_title": "Bo‘limni tanlang 👇",

        "brand": (
            "✨ <b>ZARY &amp; CO — milliy bolalar kiyim brendi 🇺🇿</b>\n"
            "Qulay, chiroyli va sifatli.\n"
            "ZARY &amp; CO — qulaylik va uslub birga."
        ),

        "photos_title": "📸 <b>Katalog</b>\nBo‘limni tanlang:",
        "photos_go_channel": (
            "📸 Rasm va yangiliklar <b>Telegram kanal</b>da joylanadi.\n"
            "Quyidagi tugmani bosing 👇"
        ),

        "price_title": "🧾 <b>Narxlar (qisqa)</b>\nBo‘limni tanlang:",
        "price_boys": (
            "👶 <b>O‘G‘IL BOLALAR</b>\n"
            "• Ustki: kurtka/vetrovka/bomber/parka/anorak/jilet\n"
            "• Ustki: xudi/svitshot/longsliv/kardigan/flis\n"
            "• Past: shim/jins/shorti/kombinezon\n"
            "• To‘plam: sport/pijama/yozgi"
        ),
        "price_girls": (
            "👧 <b>QIZ BOLALAR</b>\n"
            "• Ustki: kurtka/vetrovka/palto/parka/anorak/jilet\n"
            "• Ko‘ylak/yubka: oddiy/bayram/sarafan/yubka\n"
            "• Ustki: xudi/svitshot/longsliv/kardigan/flis\n"
            "• Past: shim/jins/leggins/shorti/kombinezon\n"
            "• To‘plam: kostyum/pijama/yozgi"
        ),
        "price_unisex": (
            "🧒 <b>UNISEKS / BAZA</b>\n"
            "• Futbolka/longsliv/vodolazka/ko‘ylak\n"
            "• Sviter/jilet/pijama\n"
            "• Sport kostyum/kombinezon\n"
            "• Maktab kostyumi"
        ),

        "size_title": "📏 <b>O‘lcham tanlash (1–15 yosh)</b>\nUsulni tanlang:",
        "size_age_ask": "Bolaning yoshini yozing (1–15). Masalan: <code>7</code>",
        "size_height_ask": "Bo‘yini sm da yozing. Masalan: <code>125</code>",
        "size_bad_age": "Yoshni 1 dan 15 gacha raqam bilan yozing. Masalan: <code>7</code>",
        "size_bad_height": "Bo‘yini raqam bilan yozing (masalan: 125).",

        "size_result_age": (
            "📏 <b>Yosh bo‘yicha tavsiya:</b>\n"
            "Yosh: {age} → taxminan <b>{age_rec}</b>\n\n"
            "Xohlasangiz bo‘y bo‘yicha aniqlaymiz (majburiy emas)."
        ),
        "size_result_height": (
            "📏 <b>Bo‘y bo‘yicha tavsiya:</b>\n"
            "Bo‘y: {height} sm → tavsiya <b>{height_rec}</b>"
        ),

        "contact_title": (
            "📞 <b>Aloqa</b>\n"
            "Buyurtmalar <b>24/7</b> qabul qilinadi.\n"
            "Menejer <b>09:00–21:00</b> javob beradi.\n\n"
            f"☎️ Menejer raqami: <b>{MANAGER_PHONE}</b>\n"
        ),

        "order_start": "🧾 <b>Buyurtma</b>\nIsmingiz?",
        "order_phone": "📲 Telefon raqam yuboring (yoki «📲 Kontakt yuborish» tugmasi).",
        "order_city": "🏙 Shahar/tuman?",
        "order_item": "👕 Nima buyurtma qilasiz? (masalan: maktab formasi / kostyum / ko‘ylak)",
        "order_size": (
            "👶 Yosh va bo‘yni bitta xabarda.\n"
            "Masalan: <code>7 yosh, 125 sm</code>\n\n"
            "Yoki bosing: <b>📏 O‘lcham</b>"
        ),
        "order_size_bad": (
            "Iltimos, <b>yosh va bo‘y</b> ni yozing.\n"
            "Masalan: <code>7 yosh, 125 sm</code>\n"
            "Yoki bosing: <b>📏 O‘lcham</b>"
        ),
        "order_comment": "✍️ Izoh (rang/soni) yoki «yo‘q» deb yozing",
        "order_review": (
            "🧾 <b>Buyurtmani tekshiring:</b>\n"
            "• Ism: {name}\n"
            "• Telefon: {phone}\n"
            "• Shahar: {city}\n"
            "• Mahsulot: {item}\n"
            "• Yosh/bo‘y: {size}\n"
            "• Izoh: {comment}\n\n"
            "Tasdiqlaysizmi?"
        ),
        "order_sent": "✅ Rahmat! Buyurtma qabul qilindi.\nMenejer bog‘lanadi ✅",

        "worktime_in": "⏱ Hozir ish vaqti — javob tezroq bo‘ladi.",
        "worktime_out": "⏱ Hozir ish vaqti emas — menejer ish vaqtida javob beradi.",

        "edit_choose": "✏️ Nimani tuzatamiz?",
        "cancelled": "❌ Buyurtma bekor qilindi. Menyuga qaytdik 👇",
        "unknown": "Iltimos, menyu tugmalaridan foydalaning 👇",
        "session_reset": "⏱ Siz uzoq javob bermadingiz — menyuga qaytdik. Bo‘limni tanlang 👇",

        "end_links": (
            "📌 <b>Rasmiy sahifalarimiz:</b>\n"
            f"📢 Telegram: {CHANNEL_URL}\n"
            f"📷 Instagram: {INSTAGRAM_URL}\n"
            f"▶️ YouTube: {YOUTUBE_URL}"
        ),
    }
}

# =========================
# STATES
# =========================
class Flow(StatesGroup):
    size_age_only = State()
    size_height_only = State()

    order_name = State()
    order_phone = State()
    order_city = State()
    order_item = State()
    order_size = State()
    order_comment = State()
    order_confirm = State()

    edit_field = State()

# =========================
# HELPERS
# =========================
def now_local() -> datetime:
    return datetime.now(TZ)

def in_work_time(dt: datetime) -> bool:
    t = dt.time()
    return WORK_START <= t <= WORK_END

def clean_phone(raw: str) -> str:
    s = (raw or "").strip().replace(" ", "").replace("-", "")
    return s

def looks_like_phone(s: str) -> bool:
    s = clean_phone(s)
    digits = re.sub(r"\D", "", s)
    return 9 <= len(digits) <= 15

def parse_age_height(text: str):
    nums = re.findall(r"\d{1,3}", text or "")
    if len(nums) >= 2:
        return int(nums[0]), int(nums[1])
    return None, None

async def get_lang(state: FSMContext) -> str:
    data = await state.get_data()
    return data.get("lang", "ru")

async def set_lang_keep(state: FSMContext, lang: str):
    await state.clear()
    await state.update_data(lang=lang, last_ts=now_local().isoformat())

def age_to_size_range(age: int) -> str:
    mapping = {
        1: "86–92", 2: "92–98", 3: "98–104", 4: "104–110", 5: "110–116",
        6: "116–122", 7: "122–128", 8: "128–134", 9: "134–140",
        10: "140–146", 11: "146–152", 12: "152–158", 13: "158–164",
        14: "164", 15: "164",
    }
    return mapping.get(age, "—")

def height_to_size(height: int) -> int:
    sizes = [86, 92, 98, 104, 110, 116, 122, 128, 134, 140, 146, 152, 158, 164]
    return min(sizes, key=lambda x: abs(x - height))

async def touch_session(state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    await state.update_data(lang=lang, last_ts=now_local().isoformat())

async def check_session_timeout(message_or_call, state: FSMContext) -> bool:
    data = await state.get_data()
    lang = data.get("lang", "ru")
    last_ts = data.get("last_ts")
    st = await state.get_state()

    if not st or not last_ts:
        await touch_session(state)
        return False

    try:
        last = datetime.fromisoformat(last_ts)
    except Exception:
        await touch_session(state)
        return False

    if now_local() - last > timedelta(minutes=SESSION_TTL_MINUTES):
        await set_lang_keep(state, lang)
        if isinstance(message_or_call, Message):
            await safe_answer(message_or_call, TEXT[lang]["session_reset"], reply_markup=kb_menu(lang))
        else:
            await safe_answer_call(message_or_call, TEXT[lang]["session_reset"], reply_markup=kb_menu(lang))
            await message_or_call.answer()
        return True

    await touch_session(state)
    return False

# =========================
# KEYBOARDS
# =========================
def kb_lang() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Русский 🇷🇺", callback_data="lang:ru"),
         InlineKeyboardButton(text="O‘zbek 🇺🇿", callback_data="lang:uz")]
    ])

def kb_menu(lang: str) -> ReplyKeyboardMarkup:
    if lang == "uz":
        rows = [
            [KeyboardButton(text="🧾 Narxlar"), KeyboardButton(text="📸 Katalog")],
            [KeyboardButton(text="📏 O‘lcham"), KeyboardButton(text="✅ Buyurtma")],
            [KeyboardButton(text="📞 Aloqa"), KeyboardButton(text="✨ Brend")],
            [KeyboardButton(text="🌐 Til")],
        ]
    else:
        rows = [
            [KeyboardButton(text="🧾 Прайс"), KeyboardButton(text="📸 Каталог")],
            [KeyboardButton(text="📏 Размер"), KeyboardButton(text="✅ Заказ")],
            [KeyboardButton(text="📞 Связаться"), KeyboardButton(text="✨ О бренде")],
            [KeyboardButton(text="🌐 Язык")],
        ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def kb_order_nav(lang: str) -> ReplyKeyboardMarkup:
    # ✅ Меню всегда доступно во время заказа
    if lang == "uz":
        rows = [
            [KeyboardButton(text="📏 O‘lcham"), KeyboardButton(text="⬅️ Menyu")],
            [KeyboardButton(text="❌ Bekor qilish")],
        ]
    else:
        rows = [
            [KeyboardButton(text="📏 Размер"), KeyboardButton(text="⬅️ Меню")],
            [KeyboardButton(text="❌ Отмена")],
        ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=False)

def kb_price(lang: str) -> InlineKeyboardMarkup:
    if lang == "uz":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👶 O‘g‘il bolalar", callback_data="price:boys")],
            [InlineKeyboardButton(text="👧 Qiz bolalar", callback_data="price:girls")],
            [InlineKeyboardButton(text="🧒 Uniseks/Baza", callback_data="price:unisex")],
            [InlineKeyboardButton(text="✅ Buyurtma", callback_data="go:order")],
            [InlineKeyboardButton(text="⬅️ Menyu", callback_data="back:menu")],
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👶 Мальчики", callback_data="price:boys")],
        [InlineKeyboardButton(text="👧 Девочки", callback_data="price:girls")],
        [InlineKeyboardButton(text="🧒 Унисекс/База", callback_data="price:unisex")],
        [InlineKeyboardButton(text="✅ Оформить заказ", callback_data="go:order")],
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="back:menu")],
    ])

def kb_photos(lang: str) -> InlineKeyboardMarkup:
    # ✅ Каталог: по кнопкам просто отправим в канал
    if lang == "uz":
        rows = [
            [InlineKeyboardButton(text="Yangi", callback_data="photo:new")],
            [InlineKeyboardButton(text="Yozgi", callback_data="photo:summer")],
            [InlineKeyboardButton(text="Maktab formasi", callback_data="photo:school")],
            [InlineKeyboardButton(text="Kostyumlar", callback_data="photo:sets")],
            [InlineKeyboardButton(text="Xudi", callback_data="photo:hoodie")],
            [InlineKeyboardButton(text="Kurtka/Ustki", callback_data="photo:outerwear")],
            [InlineKeyboardButton(text="⬅️ Menyu", callback_data="back:menu")],
        ]
    else:
        rows = [
            [InlineKeyboardButton(text="Новинки", callback_data="photo:new")],
            [InlineKeyboardButton(text="Лето", callback_data="photo:summer")],
            [InlineKeyboardButton(text="Школьная форма", callback_data="photo:school")],
            [InlineKeyboardButton(text="Костюмы", callback_data="photo:sets")],
            [InlineKeyboardButton(text="Худи", callback_data="photo:hoodie")],
            [InlineKeyboardButton(text="Куртки/Верх", callback_data="photo:outerwear")],
            [InlineKeyboardButton(text="⬅️ Меню", callback_data="back:menu")],
        ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_go_channel(lang: str) -> InlineKeyboardMarkup:
    # ✅ Только Telegram канал (без инсты/ютуба)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📢 Перейти в канал" if lang == "ru" else "📢 Kanalga o‘tish",
            url=CHANNEL_URL
        )],
        [InlineKeyboardButton(text="⬅️ Меню" if lang == "ru" else "⬅️ Menyu", callback_data="back:menu")],
    ])

def kb_size_mode(lang: str) -> InlineKeyboardMarkup:
    if lang == "uz":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👶 Yosh bo‘yicha", callback_data="size:age")],
            [InlineKeyboardButton(text="📏 Bo‘y bo‘yicha", callback_data="size:height")],
            [InlineKeyboardButton(text="⬅️ Menyu", callback_data="back:menu")],
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👶 По возрасту", callback_data="size:age")],
        [InlineKeyboardButton(text="📏 По росту", callback_data="size:height")],
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="back:menu")],
    ])

def kb_size_after_age(lang: str) -> InlineKeyboardMarkup:
    if lang == "uz":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📏 Bo‘y bilan aniqlash", callback_data="size:height_follow")],
            [InlineKeyboardButton(text="⬅️ Menyu", callback_data="back:menu")],
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📏 Уточнить по росту", callback_data="size:height_follow")],
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="back:menu")],
    ])

def kb_order_confirm(lang: str) -> InlineKeyboardMarkup:
    if lang == "uz":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="order:confirm")],
            [InlineKeyboardButton(text="✏️ Tuzatish", callback_data="order:edit")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="order:cancel")],
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="order:confirm")],
        [InlineKeyboardButton(text="✏️ Исправить", callback_data="order:edit")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="order:cancel")],
    ])

def kb_all_links_end(lang: str) -> InlineKeyboardMarkup:
    # ✅ ВСЕ ТРИ ССЫЛКИ — только в конце заказа (confirm/cancel)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Telegram", url=CHANNEL_URL)],
        [InlineKeyboardButton(text="📷 Instagram", url=INSTAGRAM_URL)],
        [InlineKeyboardButton(text="▶️ YouTube", url=YOUTUBE_URL)],
        [InlineKeyboardButton(text="⬅️ Меню" if lang == "ru" else "⬅️ Menyu", callback_data="back:menu")],
    ])

# =========================
# ORDER VIEW
# =========================
async def show_order_review(target, state: FSMContext, lang: str):
    data = await state.get_data()
    review = TEXT[lang]["order_review"].format(
        name=esc(data.get("order_name", "-")),
        phone=esc(data.get("order_phone", "-")),
        city=esc(data.get("order_city", "-")),
        item=esc(data.get("order_item", "-")),
        size=esc(data.get("order_size", "-")),
        comment=esc(data.get("order_comment", "-")),
    )
    if isinstance(target, Message):
        await safe_answer(target, review, reply_markup=kb_order_confirm(lang))
    else:
        await safe_answer_call(target, review, reply_markup=kb_order_confirm(lang))

# =========================
# GLOBAL NAV (Меню/Отмена)
# =========================
async def global_nav(message: Message, state: FSMContext) -> bool:
    lang = await get_lang(state)
    txt = (message.text or "").strip()

    is_cancel = (lang == "ru" and txt == "❌ Отмена") or (lang == "uz" and txt == "❌ Bekor qilish")
    is_menu = (lang == "ru" and txt == "⬅️ Меню") or (lang == "uz" and txt == "⬅️ Menyu")

    # ❌ ВАЖНО: если человек отменил заказ — показываем 3 ссылки (как ты хочешь)
    if is_cancel:
        await set_lang_keep(state, lang)
        await safe_answer(message, TEXT[lang]["cancelled"], reply_markup=kb_menu(lang))
        await safe_answer(message, TEXT[lang]["end_links"], reply_markup=kb_all_links_end(lang))
        return True

    if is_menu:
        await set_lang_keep(state, lang)
        await safe_answer(message, TEXT[lang]["menu_title"], reply_markup=kb_menu(lang))
        return True

    return False

# =========================
# HANDLERS
# =========================
async def cmd_start(message: Message, state: FSMContext):
    if await check_session_timeout(message, state):
        return

    data = await state.get_data()
    if "lang" not in data:
        await safe_answer(message, TEXT["ru"]["hello_ask_lang"], reply_markup=kb_lang())
        return
    lang = await get_lang(state)
    await set_lang_keep(state, lang)
    await safe_answer(message, TEXT[lang]["hello"], reply_markup=kb_menu(lang))

async def pick_lang(call: CallbackQuery, state: FSMContext):
    if await check_session_timeout(call, state):
        return
    lang = call.data.split(":")[1]
    await set_lang_keep(state, lang)
    await safe_answer_call(call, TEXT[lang]["hello"], reply_markup=kb_menu(lang))
    await call.answer()

async def back_menu(call: CallbackQuery, state: FSMContext):
    if await check_session_timeout(call, state):
        return
    lang = await get_lang(state)
    await set_lang_keep(state, lang)
    await safe_answer_call(call, TEXT[lang]["menu_title"], reply_markup=kb_menu(lang))
    await call.answer()

# ---------- MENU BY TEXT ----------
async def menu_by_text(message: Message, state: FSMContext):
    if await check_session_timeout(message, state):
        return

    # ✅ ловим Меню/Отмена везде
    if await global_nav(message, state):
        return

    lang = await get_lang(state)
    txt = (message.text or "").strip()

    if (lang == "ru" and txt == "🌐 Язык") or (lang == "uz" and txt == "🌐 Til"):
        await safe_answer(message, TEXT[lang]["hello_ask_lang"], reply_markup=kb_lang())
        return

    if (lang == "ru" and txt == "✨ О бренде") or (lang == "uz" and txt == "✨ Brend"):
        await safe_answer(message, TEXT[lang]["brand"], reply_markup=kb_menu(lang))
        return

    if (lang == "ru" and txt == "🧾 Прайс") or (lang == "uz" and txt == "🧾 Narxlar"):
        await safe_answer(message, TEXT[lang]["price_title"], reply_markup=kb_price(lang))
        return

    if (lang == "ru" and txt == "📸 Каталог") or (lang == "uz" and txt == "📸 Katalog"):
        await safe_answer(message, TEXT[lang]["photos_title"], reply_markup=kb_photos(lang))
        return

    if (lang == "ru" and txt == "📏 Размер") or (lang == "uz" and txt == "📏 O‘lcham"):
        await safe_answer(message, TEXT[lang]["size_title"], reply_markup=kb_size_mode(lang))
        return

    if (lang == "ru" and txt == "✅ Заказ") or (lang == "uz" and txt == "✅ Buyurtma"):
        await start_order(message, state)
        return

    if (lang == "ru" and txt == "📞 Связаться") or (lang == "uz" and txt == "📞 Aloqa"):
        msg = TEXT[lang]["contact_title"]
        if MANAGER_USERNAME:
            msg += (f"\n👩‍💼 Menejer: @{MANAGER_USERNAME}" if lang == "uz" else f"\n👩‍💼 Менеджер: @{MANAGER_USERNAME}")
        await safe_answer(message, msg, reply_markup=kb_menu(lang))
        return

    await safe_answer(message, TEXT[lang]["unknown"], reply_markup=kb_menu(lang))

# ---------- PRICE ----------
async def price_section(call: CallbackQuery, state: FSMContext):
    if await check_session_timeout(call, state):
        return
    lang = await get_lang(state)
    sec = call.data.split(":")[1]
    if sec == "boys":
        await safe_answer_call(call, TEXT[lang]["price_boys"], reply_markup=kb_price(lang))
    elif sec == "girls":
        await safe_answer_call(call, TEXT[lang]["price_girls"], reply_markup=kb_price(lang))
    else:
        await safe_answer_call(call, TEXT[lang]["price_unisex"], reply_markup=kb_price(lang))
    await call.answer()

# ---------- PHOTOS (always to channel) ----------
async def photo_section(call: CallbackQuery, state: FSMContext):
    if await check_session_timeout(call, state):
        return
    lang = await get_lang(state)
    # любой раздел каталога -> только канал
    await safe_answer_call(call, TEXT[lang]["photos_go_channel"], reply_markup=kb_go_channel(lang))
    await call.answer()

# ---------- SIZE ----------
async def size_mode(call: CallbackQuery, state: FSMContext):
    if await check_session_timeout(call, state):
        return
    lang = await get_lang(state)
    mode = call.data.split(":")[1]
    if mode == "age":
        await state.set_state(Flow.size_age_only)
        await safe_answer_call(call, TEXT[lang]["size_age_ask"], reply_markup=kb_order_nav(lang))
    else:
        await state.set_state(Flow.size_height_only)
        await safe_answer_call(call, TEXT[lang]["size_height_ask"], reply_markup=kb_order_nav(lang))
    await call.answer()

async def size_height_follow(call: CallbackQuery, state: FSMContext):
    if await check_session_timeout(call, state):
        return
    lang = await get_lang(state)
    await state.set_state(Flow.size_height_only)
    await safe_answer_call(call, TEXT[lang]["size_height_ask"], reply_markup=kb_order_nav(lang))
    await call.answer()

async def size_age_only(message: Message, state: FSMContext):
    if await check_session_timeout(message, state):
        return
    if await global_nav(message, state):
        return
    lang = await get_lang(state)
    txt = (message.text or "").strip()
    if not txt.isdigit():
        await safe_answer(message, TEXT[lang]["size_bad_age"], reply_markup=kb_order_nav(lang))
        return
    age = int(txt)
    if not (1 <= age <= 15):
        await safe_answer(message, TEXT[lang]["size_bad_age"], reply_markup=kb_order_nav(lang))
        return
    age_rec = age_to_size_range(age)
    await safe_answer(
        message,
        TEXT[lang]["size_result_age"].format(age=age, age_rec=age_rec),
        reply_markup=kb_size_after_age(lang)
    )

async def size_height_only(message: Message, state: FSMContext):
    if await check_session_timeout(message, state):
        return
    if await global_nav(message, state):
        return
    lang = await get_lang(state)
    txt = (message.text or "").strip()
    if not txt.isdigit():
        await safe_answer(message, TEXT[lang]["size_bad_height"], reply_markup=kb_order_nav(lang))
        return
    height = int(txt)
    if height < 70 or height > 190:
        await safe_answer(message, TEXT[lang]["size_bad_height"], reply_markup=kb_order_nav(lang))
        return
    height_rec = height_to_size(height)
    await set_lang_keep(state, lang)
    await safe_answer(message, TEXT[lang]["size_result_height"].format(height=height, height_rec=height_rec), reply_markup=kb_menu(lang))

# ---------- ORDER ----------
async def start_order(message: Message, state: FSMContext):
    if await check_session_timeout(message, state):
        return
    lang = await get_lang(state)
    await state.set_state(Flow.order_name)
    await safe_answer(message, TEXT[lang]["order_start"], reply_markup=kb_order_nav(lang))

async def go_order(call: CallbackQuery, state: FSMContext):
    if await check_session_timeout(call, state):
        return
    lang = await get_lang(state)
    await state.set_state(Flow.order_name)
    await safe_answer_call(call, TEXT[lang]["order_start"], reply_markup=kb_order_nav(lang))
    await call.answer()

async def order_name(message: Message, state: FSMContext):
    if await check_session_timeout(message, state):
        return
    if await global_nav(message, state):
        return
    lang = await get_lang(state)
    name = (message.text or "").strip()
    if not name:
        await safe_answer(message, TEXT[lang]["order_start"], reply_markup=kb_order_nav(lang))
        return
    await state.update_data(order_name=name)
    await state.set_state(Flow.order_phone)
    await safe_answer(message, TEXT[lang]["order_phone"], reply_markup=kb_order_nav(lang))

async def order_phone(message: Message, state: FSMContext):
    if await check_session_timeout(message, state):
        return
    if await global_nav(message, state):
        return
    lang = await get_lang(state)
    phone = (message.text or "").strip()
    phone = clean_phone(phone)
    if not looks_like_phone(phone):
        await safe_answer(message, TEXT[lang]["order_phone"], reply_markup=kb_order_nav(lang))
        return
    await state.update_data(order_phone=phone)
    await state.set_state(Flow.order_city)
    await safe_answer(message, TEXT[lang]["order_city"], reply_markup=kb_order_nav(lang))

async def order_city(message: Message, state: FSMContext):
    if await check_session_timeout(message, state):
        return
    if await global_nav(message, state):
        return
    lang = await get_lang(state)
    city = (message.text or "").strip()
    if not city:
        await safe_answer(message, TEXT[lang]["order_city"], reply_markup=kb_order_nav(lang))
        return
    await state.update_data(order_city=city)
    await state.set_state(Flow.order_item)
    await safe_answer(message, TEXT[lang]["order_item"], reply_markup=kb_order_nav(lang))

async def order_item(message: Message, state: FSMContext):
    if await check_session_timeout(message, state):
        return
    if await global_nav(message, state):
        return
    lang = await get_lang(state)
    item = (message.text or "").strip()
    if not item:
        await safe_answer(message, TEXT[lang]["order_item"], reply_markup=kb_order_nav(lang))
        return
    await state.update_data(order_item=item)
    await state.set_state(Flow.order_size)
    await safe_answer(message, TEXT[lang]["order_size"], reply_markup=kb_order_nav(lang))

async def order_size(message: Message, state: FSMContext):
    if await check_session_timeout(message, state):
        return

    lang = await get_lang(state)
    txt = (message.text or "").strip()

    # если в заказе нажали подбор размера
    if (lang == "ru" and txt == "📏 Размер") or (lang == "uz" and txt == "📏 O‘lcham"):
        await safe_answer(message, TEXT[lang]["size_title"], reply_markup=kb_size_mode(lang))
        return

    if await global_nav(message, state):
        return

    a, h = parse_age_height(txt)
    if a is None or h is None:
        await safe_answer(message, TEXT[lang]["order_size_bad"], reply_markup=kb_order_nav(lang))
        return

    await state.update_data(order_size=txt)
    await state.set_state(Flow.order_comment)
    await safe_answer(message, TEXT[lang]["order_comment"], reply_markup=kb_order_nav(lang))

async def order_comment(message: Message, state: FSMContext):
    if await check_session_timeout(message, state):
        return
    if await global_nav(message, state):
        return
    lang = await get_lang(state)
    comment = (message.text or "").strip() or ("нет" if lang == "ru" else "yo‘q")
    await state.update_data(order_comment=comment)
    await state.set_state(Flow.order_confirm)
    await show_order_review(message, state, lang)

async def order_cancel(call: CallbackQuery, state: FSMContext):
    if await check_session_timeout(call, state):
        return
    lang = await get_lang(state)
    await set_lang_keep(state, lang)
    await safe_answer_call(call, TEXT[lang]["cancelled"], reply_markup=kb_menu(lang))
    await safe_answer_call(call, TEXT[lang]["end_links"], reply_markup=kb_all_links_end(lang))
    await call.answer()

async def order_confirm(call: CallbackQuery, state: FSMContext):
    if await check_session_timeout(call, state):
        return

    lang = await get_lang(state)
    data = await state.get_data()
    ts = now_local().strftime("%Y-%m-%d %H:%M")

    manager_text = (
        f"🛎 <b>Новый заказ</b> ({esc(ts)})\n\n"
        f"• Имя: <b>{esc(data.get('order_name','-'))}</b>\n"
        f"• Телефон: <b>{esc(data.get('order_phone','-'))}</b>\n"
        f"• Город: <b>{esc(data.get('order_city','-'))}</b>\n"
        f"• Товар: <b>{esc(data.get('order_item','-'))}</b>\n"
        f"• Возраст/рост: <b>{esc(data.get('order_size','-'))}</b>\n"
        f"• Комментарий: <b>{esc(data.get('order_comment','-'))}</b>\n\n"
        f"👤 user_id: <code>{call.from_user.id}</code>\n"
        f"👤 username: <code>@{esc(call.from_user.username) if call.from_user.username else '-'}</code>"
    )

    try:
        await call.message.bot.send_message(chat_id=MANAGER_CHAT_ID, text=manager_text)
    except Exception as e:
        print(f"Manager send error: {e}")

    await safe_answer_call(call, TEXT[lang]["order_sent"], reply_markup=kb_menu(lang))
    await safe_answer_call(call, TEXT[lang]["worktime_in"] if in_work_time(now_local()) else TEXT[lang]["worktime_out"], reply_markup=kb_menu(lang))

    # ✅ ТОЛЬКО СЕЙЧАС показываем 3 ссылки (как ты просил)
    await safe_answer_call(call, TEXT[lang]["end_links"], reply_markup=kb_all_links_end(lang))

    await set_lang_keep(state, lang)
    await safe_answer_call(call, TEXT[lang]["menu_title"], reply_markup=kb_menu(lang))
    await call.answer()

# =========================
# RENDER PORT BINDING (health server)
# =========================
class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        return

def start_health_server():
    port = int(os.getenv("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print(f"✅ Health server listening on port {port}.")

# =========================
# DISPATCHER
# =========================
def build_dp() -> Dispatcher:
    dp = Dispatcher()

    dp.message.register(cmd_start, CommandStart())
    dp.callback_query.register(pick_lang, F.data.startswith("lang:"))
    dp.callback_query.register(back_menu, F.data == "back:menu")

    dp.callback_query.register(price_section, F.data.startswith("price:"))
    dp.callback_query.register(go_order, F.data == "go:order")

    dp.callback_query.register(photo_section, F.data.startswith("photo:"))

    dp.callback_query.register(size_mode, F.data.startswith("size:age"))
    dp.callback_query.register(size_mode, F.data.startswith("size:height"))
    dp.callback_query.register(size_height_follow, F.data == "size:height_follow")

    dp.message.register(size_age_only, Flow.size_age_only)
    dp.message.register(size_height_only, Flow.size_height_only)

    dp.message.register(order_name, Flow.order_name)
    dp.message.register(order_phone, Flow.order_phone)
    dp.message.register(order_city, Flow.order_city)
    dp.message.register(order_item, Flow.order_item)
    dp.message.register(order_size, Flow.order_size)
    dp.message.register(order_comment, Flow.order_comment)

    dp.callback_query.register(order_cancel, F.data == "order:cancel")
    dp.callback_query.register(order_confirm, F.data == "order:confirm")

    dp.message.register(menu_by_text, F.text)
    return dp

async def main():
    start_health_server()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dp()
    print("✅ ZARY & CO assistant started (polling).")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
