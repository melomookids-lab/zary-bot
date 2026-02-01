import os
import re
import html
import asyncio
import threading
from datetime import datetime, time
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, HTTPServer

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)

# =========================
# CONFIG
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env is empty. Set it in Render Environment Variables")

MANAGER_CHAT_ID = 7195737024  # твой Telegram ID (куда отправлять заявки)
MANAGER_PHONE = "+998771202255"  # номер менеджера (покажем клиентам)

TZ = ZoneInfo("Asia/Tashkent")
WORK_START = time(9, 0)
WORK_END = time(21, 0)

INSTAGRAM_URL = "https://www.instagram.com/zary.co/"
YOUTUBE_URL = "https://www.youtube.com/@ZARYCOOFFICIAL"

# ✅ Твой канал
TELEGRAM_CHANNEL_USERNAME = "zaryco_official"
TELEGRAM_CHANNEL_URL = f"https://t.me/{TELEGRAM_CHANNEL_USERNAME}"

MANAGER_USERNAME = ""  # если есть username менеджера без @, можно оставить пустым

# =========================
# PHOTO CATALOG (file_id)
# =========================
# Позже добавишь items: [{"file_id": "...", "caption_ru": "...", "caption_uz":"..."}]
PHOTO_CATALOG = {
    "hoodie": {"ru": "Худи", "uz": "Xudi", "items": []},
    "outerwear": {"ru": "Куртки/Верх", "uz": "Kurtka/Ustki", "items": []},
    "sets": {"ru": "Костюмы", "uz": "Kostyumlar", "items": []},
    "school": {"ru": "Школьная форма", "uz": "Maktab formasi", "items": []},
    "summer": {"ru": "Лето", "uz": "Yozgi", "items": []},     # ✅ если пусто → telegram
    "new": {"ru": "Новинки", "uz": "Yangi", "items": []},     # ✅ если пусто → telegram
}

# =========================
# SAFE HTML
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

async def safe_edit_call(call: CallbackQuery, text: str, reply_markup=None):
    """
    Чтобы не дублировать сообщения (особенно в прайсе).
    Если edit не получается — просто отправим новым сообщением.
    """
    try:
        await call.message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        await safe_answer_call(call, text, reply_markup=reply_markup)

# =========================
# TEXTS
# =========================
TEXT = {
    "ru": {
        "hello_ask_lang": "Выберите язык 👇",
        "hello": (
            "👋 Добро пожаловать в <b>ZARY &amp; CO</b> 🇺🇿\n\n"
            "✨ <b>ZARY &amp; CO — национальный бренд детской одежды</b>\n"
            "Стиль • качество • комфорт\n\n"
            "Выберите действие кнопками 👇"
        ),

        "menu_title": "Выберите действие 👇",

        # PRICE
        "price_title": "🧾 <b>Прайс (укороченный)</b>\nВыберите раздел:",
        "price_boys": (
            "👶 <b>МАЛЬЧИКИ</b>\n"
            "• Верх: куртка/ветровка/бомбер/парка/анорак/жилетка\n"
            "• Толстовки: худи/свитшот/лонгслив/кардиган/флис\n"
            "• Низ: брюки/джинсы/шорты/комбинезон\n"
            "• Комплекты: спорткостюм/домашний/пижама/летний комплект\n\n"
            "✅ <b>Если выбрали нужную вам одежду — нажмите ✅ Оформить заказ</b>"
        ),
        "price_girls": (
            "👧 <b>ДЕВОЧКИ</b>\n"
            "• Верх: куртка/ветровка/пальто/парка/анорак/жилетка\n"
            "• Платья/юбки: повседневное/нарядное/сарафан/юбка\n"
            "• Толстовки: худи/свитшот/лонгслив/кардиган/флис\n"
            "• Низ: брюки/джинсы/леггинсы/шорты/комбинезон\n"
            "• Комплекты: костюм/домашний/пижама/летний комплект\n\n"
            "✅ <b>Если выбрали нужную вам одежду — нажмите ✅ Оформить заказ</b>"
        ),
        "price_unisex": (
            "🧒 <b>УНИСЕКС / БАЗА</b>\n"
            "• Футболка/лонгслив/водолазка/рубашка\n"
            "• Свитер/жилет/пижама/домашний комплект\n"
            "• Спорткостюм/комбинезоны\n"
            "• Школьный костюм\n"
            "• Индивидуальная модель под ТЗ\n\n"
            "✅ <b>Если выбрали нужную вам одежду — нажмите ✅ Оформить заказ</b>"
        ),

        # CATALOG
        "photos_title": "📸 <b>Каталог (фото)</b>\nВыберите раздел:",
        "photos_empty": "В этом разделе пока нет фото. Напишите менеджеру — отправим варианты и цены.",
        "photos_empty_newsummer": (
            "📸 В этом разделе пока нет фото.\n\n"
            "✅ Новинки/Лето мы публикуем в Telegram-канале:\n"
            f"👉 <b>@{TELEGRAM_CHANNEL_USERNAME}</b>"
        ),

        # SIZE
        "size_title": "📏 <b>Подбор размера (1–15 лет)</b>\nВыберите способ:",
        "size_age_ask": "Напишите возраст ребёнка (1–15). Пример: <code>7</code>",
        "size_height_ask": "Напишите рост в см. Пример: <code>125</code>",
        "size_bad_age": "Введите возраст цифрой от 1 до 15. Пример: <code>7</code>",
        "size_bad_height": "Введите рост цифрой (например: 125).",
        "size_result_by_age": (
            "📏 <b>Рекомендация по возрасту</b>\n"
            "Возраст: {age}\n"
            "Примерный размер: <b>{age_rec}</b>\n\n"
            "ℹ️ Точный размер подтверждает менеджер (по модели и посадке)."
        ),
        "size_result_by_height": (
            "📏 <b>Рекомендация по росту</b>\n"
            "Рост: {height} см\n"
            "Рекомендуем размер: <b>{height_rec}</b>\n\n"
            "ℹ️ Точный размер подтверждает менеджер (по модели и посадке)."
        ),

        # CONTACT
        "contact_title": (
            "📞 <b>Связаться</b>\n"
            "Мы принимаем заявки <b>24/7</b>.\n"
            "Менеджер отвечает <b>с 09:00 до 21:00</b>.\n\n"
            f"☎️ Номер менеджера: <b>{MANAGER_PHONE}</b>\n"
        ),
        "contact_offer_leave": "Если хотите — оставьте ваш номер, и менеджер свяжется с вами 👇",

        # ORDER
        "order_start": "🧾 <b>Оформляем заказ</b>\nКак вас зовут?",
        "order_phone": "📲 Отправьте номер телефона (или нажмите кнопку «📲 Отправить контакт»).",
        "order_city": "🏙 Ваш город?",
        "order_item": "👕 Что хотите заказать? (например: куртка / худи / костюм / школьная форма)",
        "order_size": "👶 Возраст и рост одним сообщением.\nПример: <code>7 лет, 125 см</code>",
        "order_size_bad": "Напишите <b>и возраст, и рост</b> одним сообщением.\nПример: <code>7 лет, 125 см</code>",
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
        "order_sent": (
            "✅ Спасибо! Заказ принят.\n"
            "Менеджер свяжется с вами, чтобы уточнить детали заказа и доставки ✅"
        ),
        "worktime_in": "⏱ Сейчас рабочее время — ответ будет быстрее.",
        "worktime_out": "⏱ Сейчас вне рабочего времени — менеджер ответит в рабочие часы.",
        "edit_choose": "✏️ Что хотите исправить?",
        "cancelled": "❌ Отменено. Возвращаю в меню 👇",
        "unknown": "Пожалуйста, используйте кнопки меню 👇",
        "flow_locked": "Сейчас идёт оформление заказа. Продолжить или выйти в меню?",
        "social_end": (
            "📌 <b>Наши ссылки:</b>\n"
            f"Telegram: {TELEGRAM_CHANNEL_URL}\n"
            f"Instagram: {INSTAGRAM_URL}\n"
            f"YouTube: {YOUTUBE_URL}"
        ),
    },

    "uz": {
        "hello_ask_lang": "Tilni tanlang 👇",
        "hello": (
            "👋 Assalomu alaykum! <b>ZARY &amp; CO</b> 🇺🇿 ga xush kelibsiz!\n\n"
            "✨ <b>ZARY &amp; CO — milliy bolalar kiyim brendi</b>\n"
            "Uslub • sifat • qulaylik\n\n"
            "Bo‘limni tanlang 👇"
        ),

        "menu_title": "Bo‘limni tanlang 👇",

        # PRICE
        "price_title": "🧾 <b>Narxlar (qisqa)</b>\nBo‘limni tanlang:",
        "price_boys": (
            "👶 <b>O‘G‘IL BOLALAR</b>\n"
            "• Ustki: kurtka/vetrovka/bomber/parka/anorak/jilet\n"
            "• Ustki: xudi/svitshot/longsliv/kardigan/flis\n"
            "• Past: shim/jins/shorti/kombinezon\n"
            "• To‘plam: sport/uy/pijama/yozgi\n\n"
            "✅ <b>Agar kerakli kiyimni tanlagan bo‘lsangiz — ✅ Buyurtma tugmasini bosing</b>"
        ),
        "price_girls": (
            "👧 <b>QIZ BOLALAR</b>\n"
            "• Ustki: kurtka/vetrovka/palto/parka/anorak/jilet\n"
            "• Ko‘ylak/yubka: oddiy/bayram/sarafan/yubka\n"
            "• Ustki: xudi/svitshot/longsliv/kardigan/flis\n"
            "• Past: shim/jins/leggins/shorti/kombinezon\n"
            "• To‘plam: kostyum/uy/pijama/yozgi\n\n"
            "✅ <b>Agar kerakli kiyimni tanlagan bo‘lsangiz — ✅ Buyurtma tugmasini bosing</b>"
        ),
        "price_unisex": (
            "🧒 <b>UNISEKS / BAZA</b>\n"
            "• Futbolka/longsliv/vodolazka/ko‘ylak\n"
            "• Sviter/jilet/pijama/uy to‘plami\n"
            "• Sport kostyum/kombinezon\n"
            "• Maktab kostyumi\n"
            "• Individual model (TZ)\n\n"
            "✅ <b>Agar kerakli kiyimni tanlagan bo‘lsangiz — ✅ Buyurtma tugmasini bosing</b>"
        ),

        # CATALOG
        "photos_title": "📸 <b>Katalog (rasm)</b>\nBo‘limni tanlang:",
        "photos_empty": "Bu bo‘limda hozircha rasm yo‘q. Menejerga yozing — variant va narxlarni yuboramiz.",
        "photos_empty_newsummer": (
            "📸 Bu bo‘limda hozircha rasm yo‘q.\n\n"
            "✅ Yangi/Yozgi mahsulotlar Telegram kanalimizda:\n"
            f"👉 <b>@{TELEGRAM_CHANNEL_USERNAME}</b>"
        ),

        # SIZE
        "size_title": "📏 <b>O‘lcham tanlash (1–15 yosh)</b>\nUsulni tanlang:",
        "size_age_ask": "Bolaning yoshini yozing (1–15). Masalan: <code>7</code>",
        "size_height_ask": "Bo‘yini sm da yozing. Masalan: <code>125</code>",
        "size_bad_age": "Yoshni 1 dan 15 gacha raqam bilan yozing. Masalan: <code>7</code>",
        "size_bad_height": "Bo‘yini raqam bilan yozing (masalan: 125).",
        "size_result_by_age": (
            "📏 <b>Yosh bo‘yicha tavsiya</b>\n"
            "Yosh: {age}\n"
            "Taxminiy o‘lcham: <b>{age_rec}</b>\n\n"
            "ℹ️ Aniq o‘lcham menejer tomonidan tasdiqlanadi."
        ),
        "size_result_by_height": (
            "📏 <b>Bo‘y bo‘yicha tavsiya</b>\n"
            "Bo‘y: {height} sm\n"
            "Tavsiya o‘lcham: <b>{height_rec}</b>\n\n"
            "ℹ️ Aniq o‘lcham menejer tomonidan tasdiqlanadi."
        ),

        # CONTACT
        "contact_title": (
            "📞 <b>Aloqa</b>\n"
            "Buyurtmalar <b>24/7</b> qabul qilinadi.\n"
            "Menejer <b>09:00–21:00</b> da javob beradi.\n\n"
            f"☎️ Menejer raqami: <b>{MANAGER_PHONE}</b>\n"
        ),
        "contact_offer_leave": "Xohlasangiz, raqamingizni qoldiring — menejer bog‘lanadi 👇",

        # ORDER
        "order_start": "🧾 <b>Buyurtma</b>\nIsmingiz?",
        "order_phone": "📲 Telefon raqam yuboring (yoki «📲 Kontakt yuborish» tugmasi).",
        "order_city": "🏙 Shahar?",
        "order_item": "👕 Nima buyurtma qilasiz? (masalan: kurtka / xudi / kostyum / maktab formasi)",
        "order_size": "👶 Yosh va bo‘yni bitta xabarda.\nMasalan: <code>7 yosh, 125 sm</code>",
        "order_size_bad": "Iltimos, <b>yosh va bo‘y</b> ni bitta xabarda yozing.\nMasalan: <code>7 yosh, 125 sm</code>",
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
        "order_sent": (
            "✅ Rahmat! Buyurtma qabul qilindi.\n"
            "Menejer bog‘lanib, buyurtma va yetkazib berish tafsilotlarini aniqlashtiradi ✅"
        ),
        "worktime_in": "⏱ Hozir ish vaqti — javob tezroq bo‘ladi.",
        "worktime_out": "⏱ Hozir ish vaqti emas — menejer ish vaqtida javob beradi.",
        "edit_choose": "✏️ Nimani tuzatamiz?",
        "cancelled": "❌ Bekor qilindi. Menyuga qaytdik 👇",
        "unknown": "Iltimos, menyu tugmalaridan foydalaning 👇",
        "flow_locked": "Hozir buyurtma rasmiylashtirilmoqda. Davom etamizmi yoki menyuga chiqamizmi?",
        "social_end": (
            "📌 <b>Havolalarimiz:</b>\n"
            f"Telegram: {TELEGRAM_CHANNEL_URL}\n"
            f"Instagram: {INSTAGRAM_URL}\n"
            f"YouTube: {YOUTUBE_URL}"
        ),
    }
}

# =========================
# STATES
# =========================
class Flow(StatesGroup):
    size_age = State()
    size_height = State()

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
    s = (raw or "").strip()
    s = s.replace(" ", "").replace("-", "")
    return s

def looks_like_phone(s: str) -> bool:
    s = clean_phone(s)
    digits = re.sub(r"\D", "", s)
    return 9 <= len(digits) <= 15

def extract_two_numbers_any_order(text: str):
    """
    Для заказа: ищем возраст (1-15) и рост (70-190) в любом порядке/формате.
    Примеры:
      "7 125", "7лет 125см", "рост 125 возраст 7", "125/7"
    """
    nums = [int(x) for x in re.findall(r"\d{1,3}", text or "")]
    if not nums:
        return None, None

    # кандидаты
    age = None
    height = None
    for n in nums:
        if age is None and 1 <= n <= 15:
            age = n
        # рост чаще 90-180, но возьмём 70-190
        if height is None and 70 <= n <= 190:
            height = n

    # если один найден, попробуем добрать второй из оставшихся
    if age is None:
        for n in nums:
            if 1 <= n <= 15:
                age = n
                break
    if height is None:
        for n in nums:
            if 70 <= n <= 190:
                height = n
                break

    return age, height

async def get_lang(state: FSMContext) -> str:
    data = await state.get_data()
    return data.get("lang", "ru")

async def set_lang_keep(state: FSMContext, lang: str):
    await state.clear()
    await state.update_data(lang=lang)

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

# =========================
# KEYBOARDS
# =========================
def kb_lang() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Русский 🇷🇺", callback_data="lang:ru"),
         InlineKeyboardButton(text="O‘zbek 🇺🇿", callback_data="lang:uz")]
    ])

def kb_menu(lang: str) -> ReplyKeyboardMarkup:
    # ✅ Меню всегда видимое
    if lang == "uz":
        rows = [
            [KeyboardButton(text="🧾 Narxlar"), KeyboardButton(text="📸 Katalog")],
            [KeyboardButton(text="📏 O‘lcham"), KeyboardButton(text="✅ Buyurtma")],
            [KeyboardButton(text="📞 Aloqa"), KeyboardButton(text="🌐 Til")],
            [KeyboardButton(text="❌ Bekor qilish")],
        ]
    else:
        rows = [
            [KeyboardButton(text="🧾 Прайс"), KeyboardButton(text="📸 Каталог")],
            [KeyboardButton(text="📏 Размер"), KeyboardButton(text="✅ Заказ")],
            [KeyboardButton(text="📞 Связаться"), KeyboardButton(text="🌐 Язык")],
            [KeyboardButton(text="❌ Отмена")],
        ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

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
    rows = []
    for key, v in PHOTO_CATALOG.items():
        title = v["uz"] if lang == "uz" else v["ru"]
        rows.append([InlineKeyboardButton(text=title, callback_data=f"photo:{key}")])
    rows.append([InlineKeyboardButton(text="⬅️ Menyu" if lang == "uz" else "⬅️ Меню", callback_data="back:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

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

def kb_edit_fields(lang: str) -> InlineKeyboardMarkup:
    if lang == "uz":
        rows = [
            [InlineKeyboardButton(text="Ism", callback_data="edit:name")],
            [InlineKeyboardButton(text="Telefon", callback_data="edit:phone")],
            [InlineKeyboardButton(text="Shahar", callback_data="edit:city")],
            [InlineKeyboardButton(text="Mahsulot", callback_data="edit:item")],
            [InlineKeyboardButton(text="Yosh/bo‘y", callback_data="edit:size")],
            [InlineKeyboardButton(text="Izoh", callback_data="edit:comment")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="order:back_confirm")],
        ]
    else:
        rows = [
            [InlineKeyboardButton(text="Имя", callback_data="edit:name")],
            [InlineKeyboardButton(text="Телефон", callback_data="edit:phone")],
            [InlineKeyboardButton(text="Город", callback_data="edit:city")],
            [InlineKeyboardButton(text="Товар", callback_data="edit:item")],
            [InlineKeyboardButton(text="Возраст/рост", callback_data="edit:size")],
            [InlineKeyboardButton(text="Комментарий", callback_data="edit:comment")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="order:back_confirm")],
        ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_contact_request(lang: str) -> ReplyKeyboardMarkup:
    # На шаге телефона — показываем request_contact, потом вернём меню
    if lang == "uz":
        btn = KeyboardButton(text="📲 Kontakt yuborish", request_contact=True)
        cancel = KeyboardButton(text="❌ Bekor qilish")
    else:
        btn = KeyboardButton(text="📲 Отправить контакт", request_contact=True)
        cancel = KeyboardButton(text="❌ Отмена")
    return ReplyKeyboardMarkup(keyboard=[[btn], [cancel]], resize_keyboard=True, one_time_keyboard=True)

def kb_contact_actions(lang: str) -> InlineKeyboardMarkup:
    if lang == "uz":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📲 Kontakt qoldirish", callback_data="contact:leave")],
            [InlineKeyboardButton(text="⬅️ Menyu", callback_data="back:menu")],
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📲 Оставить контакт", callback_data="contact:leave")],
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="back:menu")],
    ])

def kb_channel_only(lang: str) -> InlineKeyboardMarkup:
    # ✅ Только телеграм-канал + меню
    channel_text = "📣 Telegram канал" if lang == "ru" else "📣 Telegram kanal"
    menu_text = "⬅️ Меню" if lang == "ru" else "⬅️ Menyu"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=channel_text, url=TELEGRAM_CHANNEL_URL)],
        [InlineKeyboardButton(text=menu_text, callback_data="back:menu")],
    ])

def kb_social_end(lang: str) -> InlineKeyboardMarkup:
    # ✅ показываем ВСЕ ссылки только в конце
    tg_text = "Telegram" if lang == "ru" else "Telegram"
    ig_text = "Instagram" if lang == "ru" else "Instagram"
    yt_text = "YouTube" if lang == "ru" else "YouTube"
    menu_text = "⬅️ Меню" if lang == "ru" else "⬅️ Menyu"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=tg_text, url=TELEGRAM_CHANNEL_URL)],
        [InlineKeyboardButton(text=ig_text, url=INSTAGRAM_URL)],
        [InlineKeyboardButton(text=yt_text, url=YOUTUBE_URL)],
        [InlineKeyboardButton(text=menu_text, callback_data="back:menu")],
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
# CORE MENU / START
# =========================
async def cmd_start(message: Message, state: FSMContext):
    data = await state.get_data()
    if "lang" not in data:
        await safe_answer(message, TEXT["ru"]["hello_ask_lang"], reply_markup=kb_lang())
        return
    lang = await get_lang(state)
    await set_lang_keep(state, lang)
    await safe_answer(message, TEXT[lang]["hello"], reply_markup=kb_menu(lang))

async def cmd_menu(message: Message, state: FSMContext):
    lang = await get_lang(state)
    await safe_answer(message, TEXT[lang]["menu_title"], reply_markup=kb_menu(lang))

async def pick_lang(call: CallbackQuery, state: FSMContext):
    lang = call.data.split(":")[1]
    await set_lang_keep(state, lang)
    await safe_answer_call(call, TEXT[lang]["hello"], reply_markup=kb_menu(lang))
    await call.answer()

async def back_menu(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    await set_lang_keep(state, lang)
    await safe_answer_call(call, TEXT[lang]["menu_title"], reply_markup=kb_menu(lang))
    await call.answer()

# =========================
# MENU BY TEXT (ГЛАВНОЕ: меню не должно исчезать)
# =========================
def is_cancel(lang: str, txt: str) -> bool:
    return (lang == "ru" and txt == "❌ Отмена") or (lang == "uz" and txt == "❌ Bekor qilish")

def is_lang_btn(lang: str, txt: str) -> bool:
    return (lang == "ru" and txt == "🌐 Язык") or (lang == "uz" and txt == "🌐 Til")

def is_price_btn(lang: str, txt: str) -> bool:
    return (lang == "ru" and txt == "🧾 Прайс") or (lang == "uz" and txt == "🧾 Narxlar")

def is_catalog_btn(lang: str, txt: str) -> bool:
    return (lang == "ru" and txt == "📸 Каталог") or (lang == "uz" and txt == "📸 Katalog")

def is_size_btn(lang: str, txt: str) -> bool:
    return (lang == "ru" and txt == "📏 Размер") or (lang == "uz" and txt == "📏 O‘lcham")

def is_order_btn(lang: str, txt: str) -> bool:
    return (lang == "ru" and txt == "✅ Заказ") or (lang == "uz" and txt == "✅ Buyurtma")

def is_contact_btn(lang: str, txt: str) -> bool:
    return (lang == "ru" and txt == "📞 Связаться") or (lang == "uz" and txt == "📞 Aloqa")

async def menu_by_text(message: Message, state: FSMContext):
    lang = await get_lang(state)
    txt = (message.text or "").strip()

    # ✅ Cancel работает всегда
    if is_cancel(lang, txt):
        await set_lang_keep(state, lang)
        await safe_answer(message, TEXT[lang]["cancelled"], reply_markup=kb_menu(lang))
        # ✅ ссылки показываем в конце отмены
        await safe_answer(message, TEXT[lang]["social_end"], reply_markup=kb_social_end(lang))
        return

    # ✅ Если пользователь в процессе заказа — не ломаем сценарий, но меню не исчезает
    st = await state.get_state()
    if st and st.startswith("Flow:order_") and (is_price_btn(lang, txt) or is_catalog_btn(lang, txt) or is_size_btn(lang, txt) or is_lang_btn(lang, txt) or is_contact_btn(lang, txt)):
        # не рвём заказ, даём выбор
        await safe_answer(message, TEXT[lang]["flow_locked"], reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➡️ Продолжить" if lang == "ru" else "➡️ Davom etish", callback_data="order:back_confirm")],
            [InlineKeyboardButton(text="❌ Отмена" if lang == "ru" else "❌ Bekor qilish", callback_data="order:cancel")],
            [InlineKeyboardButton(text="⬅️ Меню" if lang == "ru" else "⬅️ Menyu", callback_data="back:menu")],
        ]))
        return

    if is_lang_btn(lang, txt):
        await safe_answer(message, TEXT[lang]["hello_ask_lang"], reply_markup=kb_lang())
        return

    if is_price_btn(lang, txt):
        await safe_answer(message, TEXT[lang]["price_title"], reply_markup=kb_price(lang))
        return

    if is_catalog_btn(lang, txt):
        await safe_answer(message, TEXT[lang]["photos_title"], reply_markup=kb_photos(lang))
        return

    if is_size_btn(lang, txt):
        await safe_answer(message, TEXT[lang]["size_title"], reply_markup=kb_size_mode(lang))
        return

    if is_order_btn(lang, txt):
        await start_order(message, state)
        return

    if is_contact_btn(lang, txt):
        msg = TEXT[lang]["contact_title"]
        if MANAGER_USERNAME:
            msg += (f"\n👩‍💼 Menejer: @{MANAGER_USERNAME}" if lang == "uz" else f"\n👩‍💼 Менеджер: @{MANAGER_USERNAME}")
        await safe_answer(message, msg, reply_markup=kb_menu(lang))
        await safe_answer(message, TEXT[lang]["contact_offer_leave"], reply_markup=kb_contact_actions(lang))
        return

    # ✅ Любой непонятный текст → просто вернуть меню (важно: кнопки НЕ пропадают)
    await safe_answer(message, TEXT[lang]["unknown"], reply_markup=kb_menu(lang))

# =========================
# PRICE (через edit, чтобы не дублировать)
# =========================
async def price_section(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    sec = call.data.split(":")[1]
    if sec == "boys":
        await safe_edit_call(call, TEXT[lang]["price_boys"], reply_markup=kb_price(lang))
    elif sec == "girls":
        await safe_edit_call(call, TEXT[lang]["price_girls"], reply_markup=kb_price(lang))
    else:
        await safe_edit_call(call, TEXT[lang]["price_unisex"], reply_markup=kb_price(lang))
    await call.answer()

# =========================
# CATALOG
# =========================
async def photo_section(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    key = call.data.split(":")[1]
    block = PHOTO_CATALOG.get(key)

    # если пусто
    if not block or not block.get("items"):
        # ✅ Новинки/Лето → только Telegram канал
        if key in ("new", "summer"):
            await safe_edit_call(call, TEXT[lang]["photos_empty_newsummer"], reply_markup=kb_channel_only(lang))
        else:
            await safe_edit_call(call, TEXT[lang]["photos_empty"], reply_markup=kb_photos(lang))
        await call.answer()
        return

    # если есть фото — отправляем максимум 10
    items = block["items"][:10]
    for it in items:
        cap = it.get("caption_uz") if lang == "uz" else it.get("caption_ru")
        cap = cap or ""
        order_btn_text = "✅ Заказать это" if lang == "ru" else "✅ Shu mahsulot"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=order_btn_text, callback_data=f"order:prefill:{cap[:40] or block.get('ru','')}")],
            [InlineKeyboardButton(text="⬅️ Меню" if lang == "ru" else "⬅️ Menyu", callback_data="back:menu")]
        ])
        await call.message.answer_photo(photo=it["file_id"], caption=cap, reply_markup=kb)

    await call.answer()

# =========================
# SIZE (ВАЖНО: возраст без роста и рост без возраста)
# =========================
async def size_mode(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    mode = call.data.split(":")[1]
    if mode == "age":
        await state.set_state(Flow.size_age)
        await safe_answer_call(call, TEXT[lang]["size_age_ask"], reply_markup=kb_menu(lang))
    else:
        await state.set_state(Flow.size_height)
        await safe_answer_call(call, TEXT[lang]["size_height_ask"], reply_markup=kb_menu(lang))
    await call.answer()

async def size_age(message: Message, state: FSMContext):
    lang = await get_lang(state)
    txt = (message.text or "").strip()
    if not txt.isdigit():
        await safe_answer(message, TEXT[lang]["size_bad_age"], reply_markup=kb_menu(lang))
        return
    age = int(txt)
    if not (1 <= age <= 15):
        await safe_answer(message, TEXT[lang]["size_bad_age"], reply_markup=kb_menu(lang))
        return

    age_rec = age_to_size_range(age)
    await set_lang_keep(state, lang)
    await safe_answer(
        message,
        TEXT[lang]["size_result_by_age"].format(age=age, age_rec=age_rec),
        reply_markup=kb_menu(lang)
    )
    # ✅ ссылки здесь НЕ показываем (по твоему ТЗ)

async def size_height(message: Message, state: FSMContext):
    lang = await get_lang(state)
    txt = (message.text or "").strip()
    if not txt.isdigit():
        await safe_answer(message, TEXT[lang]["size_bad_height"], reply_markup=kb_menu(lang))
        return
    height = int(txt)
    if height < 70 or height > 190:
        await safe_answer(message, TEXT[lang]["size_bad_height"], reply_markup=kb_menu(lang))
        return

    height_rec = height_to_size(height)
    await set_lang_keep(state, lang)
    await safe_answer(
        message,
        TEXT[lang]["size_result_by_height"].format(height=height, height_rec=height_rec),
        reply_markup=kb_menu(lang)
    )
    # ✅ ссылки здесь НЕ показываем

# =========================
# CONTACT leave
# =========================
async def contact_leave(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    await state.set_state(Flow.order_phone)
    await safe_answer_call(call, TEXT[lang]["order_phone"], reply_markup=kb_contact_request(lang))
    await call.answer()

# =========================
# ORDER
# =========================
async def start_order(message: Message, state: FSMContext):
    lang = await get_lang(state)
    await state.set_state(Flow.order_name)
    await safe_answer(message, TEXT[lang]["order_start"], reply_markup=kb_menu(lang))

async def go_order(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    await state.set_state(Flow.order_name)
    await safe_answer_call(call, TEXT[lang]["order_start"], reply_markup=kb_menu(lang))
    await call.answer()

async def order_prefill(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    payload = call.data.split("order:prefill:", 1)[1]
    await state.update_data(order_item=payload)
    await state.set_state(Flow.order_name)
    await safe_answer_call(call, TEXT[lang]["order_start"], reply_markup=kb_menu(lang))
    await call.answer()

async def order_name(message: Message, state: FSMContext):
    lang = await get_lang(state)
    name = (message.text or "").strip()
    if not name or is_cancel(lang, name):
        await safe_answer(message, TEXT[lang]["order_start"], reply_markup=kb_menu(lang))
        return
    await state.update_data(order_name=name)
    await state.set_state(Flow.order_phone)
    await safe_answer(message, TEXT[lang]["order_phone"], reply_markup=kb_contact_request(lang))

async def order_phone(message: Message, state: FSMContext):
    lang = await get_lang(state)

    if message.contact and message.contact.phone_number:
        phone = message.contact.phone_number
    else:
        phone = (message.text or "").strip()

    if is_cancel(lang, phone):
        await order_cancel_by_message(message, state)
        return

    phone = clean_phone(phone)
    if not looks_like_phone(phone):
        await safe_answer(message, TEXT[lang]["order_phone"], reply_markup=kb_contact_request(lang))
        return

    await state.update_data(order_phone=phone)

    # ✅ После телефона возвращаем обычное меню (важно: меню не пропадает)
    await state.set_state(Flow.order_city)
    await safe_answer(message, TEXT[lang]["order_city"], reply_markup=kb_menu(lang))

async def order_city(message: Message, state: FSMContext):
    lang = await get_lang(state)
    city = (message.text or "").strip()
    if is_cancel(lang, city):
        await order_cancel_by_message(message, state)
        return
    if not city:
        await safe_answer(message, TEXT[lang]["order_city"], reply_markup=kb_menu(lang))
        return
    await state.update_data(order_city=city)
    await state.set_state(Flow.order_item)
    await safe_answer(message, TEXT[lang]["order_item"], reply_markup=kb_menu(lang))

async def order_item(message: Message, state: FSMContext):
    lang = await get_lang(state)
    item = (message.text or "").strip()
    if is_cancel(lang, item):
        await order_cancel_by_message(message, state)
        return
    if not item:
        await safe_answer(message, TEXT[lang]["order_item"], reply_markup=kb_menu(lang))
        return
    await state.update_data(order_item=item)
    await state.set_state(Flow.order_size)
    await safe_answer(message, TEXT[lang]["order_size"], reply_markup=kb_menu(lang))

async def order_size(message: Message, state: FSMContext):
    lang = await get_lang(state)
    raw = (message.text or "").strip()
    if is_cancel(lang, raw):
        await order_cancel_by_message(message, state)
        return
    if not raw:
        await safe_answer(message, TEXT[lang]["order_size"], reply_markup=kb_menu(lang))
        return

    age, height = extract_two_numbers_any_order(raw)
    if age is None or height is None:
        await safe_answer(message, TEXT[lang]["order_size_bad"], reply_markup=kb_menu(lang))
        return

    normalized = f"{age} лет, {height} см" if lang == "ru" else f"{age} yosh, {height} sm"
    await state.update_data(order_size=normalized)
    await state.set_state(Flow.order_comment)
    await safe_answer(message, TEXT[lang]["order_comment"], reply_markup=kb_menu(lang))

async def order_comment(message: Message, state: FSMContext):
    lang = await get_lang(state)
    comment = (message.text or "").strip()
    if is_cancel(lang, comment):
        await order_cancel_by_message(message, state)
        return
    if not comment:
        comment = "нет" if lang == "ru" else "yo‘q"

    await state.update_data(order_comment=comment)
    await state.set_state(Flow.order_confirm)
    await show_order_review(message, state, lang)

async def order_cancel_by_message(message: Message, state: FSMContext):
    lang = await get_lang(state)
    await set_lang_keep(state, lang)
    await safe_answer(message, TEXT[lang]["cancelled"], reply_markup=kb_menu(lang))
    # ✅ В конце отмены показываем все ссылки
    await safe_answer(message, TEXT[lang]["social_end"], reply_markup=kb_social_end(lang))

async def order_cancel(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    await set_lang_keep(state, lang)
    await safe_answer_call(call, TEXT[lang]["cancelled"], reply_markup=kb_menu(lang))
    # ✅ В конце отмены показываем все ссылки
    await safe_answer_call(call, TEXT[lang]["social_end"], reply_markup=kb_social_end(lang))
    await call.answer()

async def order_back_confirm(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    await state.set_state(Flow.order_confirm)
    await show_order_review(call, state, lang)
    await call.answer()

async def order_edit(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    await safe_answer_call(call, TEXT[lang]["edit_choose"], reply_markup=kb_edit_fields(lang))
    await call.answer()

async def edit_pick(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    field = call.data.split(":")[1]
    await state.update_data(_edit_field=field)
    await state.set_state(Flow.edit_field)

    prompts = {
        "name": TEXT[lang]["order_start"],
        "phone": TEXT[lang]["order_phone"],
        "city": TEXT[lang]["order_city"],
        "item": TEXT[lang]["order_item"],
        "size": TEXT[lang]["order_size"],
        "comment": TEXT[lang]["order_comment"],
    }

    if field == "phone":
        await safe_answer_call(call, prompts["phone"], reply_markup=kb_contact_request(lang))
    else:
        await safe_answer_call(call, prompts.get(field, TEXT[lang]["unknown"]), reply_markup=kb_menu(lang))

    await call.answer()

async def edit_field_value(message: Message, state: FSMContext):
    lang = await get_lang(state)
    data = await state.get_data()
    field = data.get("_edit_field")

    if field == "phone":
        if message.contact and message.contact.phone_number:
            value = message.contact.phone_number
        else:
            value = (message.text or "").strip()

        if is_cancel(lang, value):
            await order_cancel_by_message(message, state)
            return

        value = clean_phone(value)
        if not looks_like_phone(value):
            await safe_answer(message, TEXT[lang]["order_phone"], reply_markup=kb_contact_request(lang))
            return

    else:
        value = (message.text or "").strip()
        if is_cancel(lang, value):
            await order_cancel_by_message(message, state)
            return
        if not value:
            await safe_answer(message, TEXT[lang]["unknown"], reply_markup=kb_menu(lang))
            return

        if field == "size":
            age, height = extract_two_numbers_any_order(value)
            if age is None or height is None:
                await safe_answer(message, TEXT[lang]["order_size_bad"], reply_markup=kb_menu(lang))
                return
            value = f"{age} лет, {height} см" if lang == "ru" else f"{age} yosh, {height} sm"

    key_map = {
        "name": "order_name",
        "phone": "order_phone",
        "city": "order_city",
        "item": "order_item",
        "size": "order_size",
        "comment": "order_comment",
    }
    if field in key_map:
        await state.update_data(**{key_map[field]: value})

    await state.set_state(Flow.order_confirm)
    await show_order_review(message, state, lang)

async def order_confirm(call: CallbackQuery, state: FSMContext):
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

    # ✅ В конце заказа показываем все ссылки
    await safe_answer_call(call, TEXT[lang]["social_end"], reply_markup=kb_social_end(lang))

    await set_lang_keep(state, lang)
    await call.answer()

# =========================
# RENDER HEALTH SERVER (OK)
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
    print(f"✅ Health server listening on port {port} (Render port binding).")

# =========================
# DISPATCHER
# =========================
def build_dp() -> Dispatcher:
    dp = Dispatcher()

    # commands
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(cmd_menu, Command("menu"))

    # language
    dp.callback_query.register(pick_lang, F.data.startswith("lang:"))
    dp.callback_query.register(back_menu, F.data == "back:menu")

    # price
    dp.callback_query.register(price_section, F.data.startswith("price:"))
    dp.callback_query.register(go_order, F.data == "go:order")

    # catalog
    dp.callback_query.register(photo_section, F.data.startswith("photo:"))
    dp.callback_query.register(order_prefill, F.data.startswith("order:prefill:"))

    # size
    dp.callback_query.register(size_mode, F.data.startswith("size:"))
    dp.message.register(size_age, Flow.size_age)
    dp.message.register(size_height, Flow.size_height)

    # contact -> leave
    dp.callback_query.register(contact_leave, F.data == "contact:leave")

    # order states
    dp.message.register(order_name, Flow.order_name)
    dp.message.register(order_phone, Flow.order_phone)
    dp.message.register(order_city, Flow.order_city)
    dp.message.register(order_item, Flow.order_item)
    dp.message.register(order_size, Flow.order_size)
    dp.message.register(order_comment, Flow.order_comment)

    # order callbacks
    dp.callback_query.register(order_cancel, F.data == "order:cancel")
    dp.callback_query.register(order_confirm, F.data == "order:confirm")
    dp.callback_query.register(order_edit, F.data == "order:edit")
    dp.callback_query.register(order_back_confirm, F.data == "order:back_confirm")

    # edit
    dp.callback_query.register(edit_pick, F.data.startswith("edit:"))
    dp.message.register(edit_field_value, Flow.edit_field)

    # ✅ главный текстовый роутер (в конце!)
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
