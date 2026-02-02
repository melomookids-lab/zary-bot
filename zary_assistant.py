import os
import re
import html
import asyncio
import threading
import sqlite3
from datetime import datetime, time, timedelta
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
)

# =========================
# CONFIG
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env is empty. Set it in Render Environment Variables")

MANAGER_CHAT_ID = 7195737024
MANAGER_PHONE = "+998771202255"
MANAGER_USERNAME = ""  # optional without @

TZ = ZoneInfo("Asia/Tashkent")
WORK_START = time(9, 0)
WORK_END = time(21, 0)

INSTAGRAM_URL = "https://www.instagram.com/zary.co/"
YOUTUBE_URL = "https://www.youtube.com/@ZARYCOOFFICIAL"

TELEGRAM_CHANNEL_USERNAME = "zaryco_official"
TELEGRAM_CHANNEL_URL = f"https://t.me/{TELEGRAM_CHANNEL_USERNAME}"

DB_PATH = os.getenv("DB_PATH", "bot.db")

# =========================
# PHOTO CATALOG (sections)
# =========================
PHOTO_CATALOG = {
    "hoodie": {"ru": "Худи", "uz": "Xudi"},
    "outerwear": {"ru": "Куртки/Верх", "uz": "Kurtka/Ustki"},
    "sets": {"ru": "Костюмы", "uz": "Kostyumlar"},
    "school": {"ru": "Школьная форма", "uz": "Maktab formasi"},
    "summer": {"ru": "Лето", "uz": "Yozgi"},
    "new": {"ru": "Новинки", "uz": "Yangi"},
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
    try:
        await call.message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        await safe_answer_call(call, text, reply_markup=reply_markup)

# =========================
# TIME / HELPERS
# =========================
def now_local() -> datetime:
    return datetime.now(TZ)

def now_ts() -> int:
    return int(now_local().timestamp())

def in_work_time(dt: datetime) -> bool:
    t = dt.time()
    return WORK_START <= t <= WORK_END

def clean_phone(raw: str) -> str:
    s = (raw or "").strip().replace(" ", "").replace("-", "")
    return s

def looks_like_phone(s: str) -> bool:
    digits = re.sub(r"\D", "", clean_phone(s))
    return 9 <= len(digits) <= 15

def extract_two_numbers_any_order(text: str):
    nums = [int(x) for x in re.findall(r"\d{1,3}", text or "")]
    age = None
    height = None
    for n in nums:
        if age is None and 1 <= n <= 15:
            age = n
        if height is None and 70 <= n <= 190:
            height = n
    return age, height

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

async def get_lang(state: FSMContext) -> str:
    data = await state.get_data()
    return data.get("lang", "ru")

async def set_lang_keep(state: FSMContext, lang: str):
    await state.clear()
    await state.update_data(lang=lang)

# =========================
# DATABASE
# =========================
def db_conn():
    return sqlite3.connect(DB_PATH)

def db_init():
    con = db_conn()
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS carts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item TEXT NOT NULL,
            qty INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            created_ts INTEGER NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            name TEXT,
            phone TEXT,
            city TEXT,
            item TEXT,
            size TEXT,
            comment TEXT,
            status TEXT NOT NULL DEFAULT 'new',
            created_at TEXT NOT NULL,
            created_ts INTEGER NOT NULL,
            reminded_ts INTEGER NOT NULL DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            phone TEXT,
            status TEXT NOT NULL DEFAULT 'new',
            created_at TEXT NOT NULL,
            created_ts INTEGER NOT NULL
        )
    """)

    con.commit()
    con.close()

def cart_add(user_id: int, item: str, qty: int = 1):
    con = db_conn()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO carts (user_id, item, qty, created_at, created_ts) VALUES (?, ?, ?, ?, ?)",
        (user_id, item, qty, now_local().strftime("%Y-%m-%d %H:%M:%S"), now_ts())
    )
    con.commit()
    con.close()

def cart_list(user_id: int):
    con = db_conn()
    cur = con.cursor()
    cur.execute("SELECT id, item, qty FROM carts WHERE user_id=? ORDER BY id DESC LIMIT 50", (user_id,))
    rows = cur.fetchall()
    con.close()
    return [{"id": r[0], "item": r[1], "qty": r[2]} for r in rows]

def cart_clear(user_id: int):
    con = db_conn()
    cur = con.cursor()
    cur.execute("DELETE FROM carts WHERE user_id=?", (user_id,))
    con.commit()
    con.close()

def orders_insert(user_id: int, username: str, name: str, phone: str, city: str, item: str, size: str, comment: str):
    con = db_conn()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO orders (user_id, username, name, phone, city, item, size, comment, status, created_at, created_ts, reminded_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, 0)
    """, (
        user_id, username or "", name or "", phone or "", city or "", item or "", size or "", comment or "",
        now_local().strftime("%Y-%m-%d %H:%M:%S"),
        now_ts()
    ))
    con.commit()
    con.close()

def orders_list(user_id: int, limit: int = 10):
    con = db_conn()
    cur = con.cursor()
    cur.execute("""
        SELECT id, item, city, status, created_at
        FROM orders
        WHERE user_id=?
        ORDER BY id DESC LIMIT ?
    """, (user_id, limit))
    rows = cur.fetchall()
    con.close()
    return [{"id": r[0], "item": r[1], "city": r[2], "status": r[3], "created_at": r[4]} for r in rows]

def leads_insert(user_id: int, username: str, phone: str):
    con = db_conn()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO leads (user_id, username, phone, status, created_at, created_ts)
        VALUES (?, ?, ?, 'new', ?, ?)
    """, (user_id, username or "", phone or "", now_local().strftime("%Y-%m-%d %H:%M:%S"), now_ts()))
    con.commit()
    con.close()

def daily_counts(date_str: str):
    # date_str: YYYY-MM-DD (local)
    con = db_conn()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM orders WHERE substr(created_at,1,10)=?", (date_str,))
    orders_cnt = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM leads WHERE substr(created_at,1,10)=?", (date_str,))
    leads_cnt = cur.fetchone()[0]
    con.close()
    return orders_cnt, leads_cnt

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

        "subscribe_hint": (
            "📣 <b>Чтобы не пропустить новинки</b>\n"
            "Все коллекции и фото мы публикуем в Telegram-канале 👇\n"
            f"👉 <b>@{TELEGRAM_CHANNEL_USERNAME}</b>\n\n"
            "Нажмите кнопку ниже, чтобы перейти и подписаться 😊✨"
        ),

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
        "photos_title": "📸 <b>Каталог (разделы)</b>\nВыберите раздел:",
        "photos_no": (
            "Извините, сейчас в этом разделе фото нет.\n"
            "Все фото-коллекции и новинки мы выкладываем в Telegram-канале 👇\n"
            f"👉 <b>@{TELEGRAM_CHANNEL_USERNAME}</b>\n\n"
            "Нажмите кнопку ниже, чтобы перейти и подписаться 😊✨"
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
            "ℹ️ Точный размер подтверждает менеджер (по модели и посадке). 😊"
        ),
        "size_result_by_height": (
            "📏 <b>Рекомендация по росту</b>\n"
            "Рост: {height} см\n"
            "Рекомендуем размер: <b>{height_rec}</b>\n\n"
            "ℹ️ Точный размер подтверждает менеджер (по модели и посадке). 😊"
        ),

        # CONTACT
        "contact_title": (
            "📞 <b>Связаться</b>\n"
            "Мы принимаем заявки <b>24/7</b>.\n"
            "Менеджер отвечает <b>с 09:00 до 21:00</b>.\n\n"
            f"☎️ Номер менеджера: <b>{MANAGER_PHONE}</b>\n"
        ),
        "contact_offer_leave": "Если хотите — оставьте ваш номер, и менеджер свяжется с вами 👇",
        "contact_phone_ask": "📲 Отправьте номер телефона (или нажмите кнопку «📲 Отправить контакт»).",
        "contact_thanks": (
            "✅ Спасибо! Вы с нами 😊\n"
            "Очень скоро менеджер позвонит и уточнит детали.\n\n"
            "Пока переходите в Telegram-канал и посмотрите коллекции 👇\n"
            "Пожалуйста, не забудьте подписаться 😊✨"
        ),

        # ORDER
        "order_start": "🧾 <b>Оформляем заказ</b>\nКак вас зовут? 😊",
        "order_phone": "📲 Отправьте номер телефона (или нажмите кнопку «📲 Отправить контакт»).",
        "order_city": "🏙 Ваш город/район?",
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
            "✅ Спасибо! Заказ принят 😊\n"
            "Менеджер свяжется с вами, чтобы уточнить детали заказа и доставки."
        ),
        "payment_info": (
            "💳 <b>Оплата</b>\n"
            "После подтверждения заказа менеджер отправит реквизиты/карту для оплаты.\n\n"
            "✅ После оплаты отправьте, пожалуйста, чек/скрин менеджеру — и мы сразу оформим доставку 😊"
        ),
        "worktime_in": "⏱ Сейчас рабочее время — ответ будет быстрее 😊",
        "worktime_out": "⏱ Сейчас вне рабочего времени — менеджер ответит в рабочие часы 😊",
        "edit_choose": "✏️ Что хотите исправить?",
        "cancelled": "❌ Отменено. Возвращаю в меню 👇",
        "unknown": "Пожалуйста, используйте кнопки меню 👇",
        "flow_locked": "Сейчас идёт оформление заказа. Продолжить или выйти в меню?",
        "social_end": (
            "📌 <b>Наши ссылки:</b>\n"
            f"📣 Telegram: {TELEGRAM_CHANNEL_URL}\n"
            f"📸 Instagram: {INSTAGRAM_URL}\n"
            f"▶️ YouTube: {YOUTUBE_URL}\n\n"
            "Спасибо, что вы с нами 😊✨"
        ),

        # CART / HISTORY
        "cart_title": "🧺 <b>Ваша корзина</b>",
        "cart_empty": "🧺 Корзина пустая. Нажмите «➕ Добавить в корзину» и напишите название товара 😊",
        "cart_add_ask": "🧺 Напишите название товара для корзины (например: «школьная форма»).",
        "cart_added": "✅ Добавлено в корзину 😊",
        "cart_cleared": "🧹 Корзина очищена.",
        "history_title": "📜 <b>История заказов</b>",
        "history_empty": "📜 История заказов пока пустая.",
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

        "subscribe_hint": (
            "📣 <b>Yangiliklarni o‘tkazib yubormaslik uchun</b>\n"
            "Barcha kolleksiyalar va rasmlar Telegram kanalimizda 👇\n"
            f"👉 <b>@{TELEGRAM_CHANNEL_USERNAME}</b>\n\n"
            "Pastdagi tugmani bosing va obuna bo‘ling 😊✨"
        ),

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

        "photos_title": "📸 <b>Katalog (bo‘limlar)</b>\nBo‘limni tanlang:",
        "photos_no": (
            "Kechirasiz, hozir bu bo‘limda rasm yo‘q.\n"
            "Barcha kolleksiyalar va yangiliklar Telegram kanalimizda 👇\n"
            f"👉 <b>@{TELEGRAM_CHANNEL_USERNAME}</b>\n\n"
            "Pastdagi tugmani bosing va obuna bo‘ling 😊✨"
        ),

        "size_title": "📏 <b>O‘lcham tanlash (1–15 yosh)</b>\nUsulni tanlang:",
        "size_age_ask": "Bolaning yoshini yozing (1–15). Masalan: <code>7</code>",
        "size_height_ask": "Bo‘yini sm da yozing. Masalan: <code>125</code>",
        "size_bad_age": "Yoshni 1 dan 15 gacha raqam bilan yozing. Masalan: <code>7</code>",
        "size_bad_height": "Bo‘yini raqam bilan yozing (masalan: 125).",
        "size_result_by_age": (
            "📏 <b>Yosh bo‘yicha tavsiya</b>\n"
            "Yosh: {age}\n"
            "Taxminiy o‘lcham: <b>{age_rec}</b>\n\n"
            "ℹ️ Aniq o‘lcham menejer tomonidan tasdiqlanadi 😊"
        ),
        "size_result_by_height": (
            "📏 <b>Bo‘y bo‘yicha tavsiya</b>\n"
            "Bo‘y: {height} sm\n"
            "Tavsiya o‘lcham: <b>{height_rec}</b>\n\n"
            "ℹ️ Aniq o‘lcham menejer tomonidan tasdiqlanadi 😊"
        ),

        "contact_title": (
            "📞 <b>Aloqa</b>\n"
            "Buyurtmalar <b>24/7</b> qabul qilinadi.\n"
            "Menejer <b>09:00–21:00</b> da javob beradi.\n\n"
            f"☎️ Menejer raqami: <b>{MANAGER_PHONE}</b>\n"
        ),
        "contact_offer_leave": "Xohlasangiz, raqamingizni qoldiring — menejer bog‘lanadi 👇",
        "contact_phone_ask": "📲 Telefon raqam yuboring (yoki «📲 Kontakt yuborish» tugmasi).",
        "contact_thanks": (
            "✅ Rahmat! Biz bilan ekansiz 😊\n"
            "Menejer tez orada qo‘ng‘iroq qilib, tafsilotlarni aniqlaydi.\n\n"
            "Hozircha Telegram kanalimizga o‘ting va kolleksiyalarni ko‘ring 👇\n"
            "Iltimos, obuna bo‘lishni unutmang 😊✨"
        ),

        "order_start": "🧾 <b>Buyurtma</b>\nIsmingiz? 😊",
        "order_phone": "📲 Telefon raqam yuboring (yoki «📲 Kontakt yuborish» tugmasi).",
        "order_city": "🏙 Shahar/tuman?",
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
            "✅ Rahmat! Buyurtma qabul qilindi 😊\n"
            "Menejer bog‘lanib, buyurtma va yetkazib berish tafsilotlarini aniqlashtiradi."
        ),
        "payment_info": (
            "💳 <b>To‘lov</b>\n"
            "Buyurtma tasdiqlangandan so‘ng menejer to‘lov uchun karta/revizitlarni yuboradi.\n\n"
            "✅ To‘lovdan keyin чек/skrinni menejerga yuboring — yetkazib berishni tez boshlaymiz 😊"
        ),
        "worktime_in": "⏱ Hozir ish vaqti — javob tezroq bo‘ladi 😊",
        "worktime_out": "⏱ Hozir ish vaqti emas — menejer ish vaqtida javob beradi 😊",
        "edit_choose": "✏️ Nimani tuzatamiz?",
        "cancelled": "❌ Bekor qilindi. Menyuga qaytdik 👇",
        "unknown": "Iltimos, menyu tugmalaridan foydalaning 👇",
        "flow_locked": "Hozir buyurtma rasmiylashtirilmoqda. Davom etamizmi yoki menyuga chiqamizmi?",
        "social_end": (
            "📌 <b>Havolalarimiz:</b>\n"
            f"📣 Telegram: {TELEGRAM_CHANNEL_URL}\n"
            f"📸 Instagram: {INSTAGRAM_URL}\n"
            f"▶️ YouTube: {YOUTUBE_URL}\n\n"
            "Rahmat 😊✨"
        ),

        "cart_title": "🧺 <b>Savatingiz</b>",
        "cart_empty": "🧺 Savat bo‘sh. «➕ Savatga qo‘shish» ni bosing va mahsulot nomini yozing 😊",
        "cart_add_ask": "🧺 Savat uchun mahsulot nomini yozing (masalan: «maktab formasi»).",
        "cart_added": "✅ Savatga qo‘shildi 😊",
        "cart_cleared": "🧹 Savat tozalandi.",
        "history_title": "📜 <b>Buyurtmalar tarixi</b>",
        "history_empty": "📜 Hozircha buyurtmalar tarixi yo‘q.",
    }
}

# =========================
# STATES
# =========================
class Flow(StatesGroup):
    size_age = State()
    size_height = State()

    contact_phone = State()

    cart_add_item = State()

    order_name = State()
    order_phone = State()
    order_city = State()
    order_item = State()
    order_size = State()
    order_comment = State()
    order_confirm = State()

    edit_field = State()

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
            [KeyboardButton(text="📣 Telegram kanal"), KeyboardButton(text="📸 Katalog")],
            [KeyboardButton(text="🧾 Narxlar"), KeyboardButton(text="📏 O‘lcham")],
            [KeyboardButton(text="🧺 Savat"), KeyboardButton(text="📜 Buyurtmalar")],
            [KeyboardButton(text="✅ Buyurtma"), KeyboardButton(text="📞 Aloqa")],
            [KeyboardButton(text="🌐 Til"), KeyboardButton(text="❌ Bekor qilish")],
        ]
    else:
        rows = [
            [KeyboardButton(text="📣 Telegram канал"), KeyboardButton(text="📸 Каталог")],
            [KeyboardButton(text="🧾 Прайс"), KeyboardButton(text="📏 Размер")],
            [KeyboardButton(text="🧺 Корзина"), KeyboardButton(text="📜 История")],
            [KeyboardButton(text="✅ Заказ"), KeyboardButton(text="📞 Связаться")],
            [KeyboardButton(text="🌐 Язык"), KeyboardButton(text="❌ Отмена")],
        ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def kb_channel_only(lang: str) -> InlineKeyboardMarkup:
    channel_text = "📣 Telegram канал" if lang == "ru" else "📣 Telegram kanal"
    menu_text = "⬅️ Меню" if lang == "ru" else "⬅️ Menyu"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=channel_text, url=TELEGRAM_CHANNEL_URL)],
        [InlineKeyboardButton(text=menu_text, callback_data="back:menu")],
    ])

def kb_social_end(lang: str) -> InlineKeyboardMarkup:
    menu_text = "⬅️ Меню" if lang == "ru" else "⬅️ Menyu"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📣 Telegram", url=TELEGRAM_CHANNEL_URL)],
        [InlineKeyboardButton(text="📸 Instagram", url=INSTAGRAM_URL)],
        [InlineKeyboardButton(text="▶️ YouTube", url=YOUTUBE_URL)],
        [InlineKeyboardButton(text=menu_text, callback_data="back:menu")],
    ])

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

def kb_cart_actions(lang: str) -> InlineKeyboardMarkup:
    if lang == "uz":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Savatga qo‘shish", callback_data="cart:add_manual")],
            [InlineKeyboardButton(text="✅ Buyurtma qilish", callback_data="cart:checkout")],
            [InlineKeyboardButton(text="🧹 Tozalash", callback_data="cart:clear")],
            [InlineKeyboardButton(text="⬅️ Menyu", callback_data="back:menu")],
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить в корзину", callback_data="cart:add_manual")],
        [InlineKeyboardButton(text="✅ Оформить заказ", callback_data="cart:checkout")],
        [InlineKeyboardButton(text="🧹 Очистить", callback_data="cart:clear")],
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="back:menu")],
    ])

# =========================
# ORDER REVIEW
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

async def send_subscribe_hint(message: Message, lang: str):
    await safe_answer(message, TEXT[lang]["subscribe_hint"], reply_markup=kb_channel_only(lang))

# =========================
# COMMANDS / START / LANG
# =========================
async def cmd_start(message: Message, state: FSMContext):
    data = await state.get_data()
    if "lang" not in data:
        await safe_answer(message, TEXT["ru"]["hello_ask_lang"], reply_markup=kb_lang())
        return
    lang = await get_lang(state)
    await set_lang_keep(state, lang)
    await safe_answer(message, TEXT[lang]["hello"], reply_markup=kb_menu(lang))
    await send_subscribe_hint(message, lang)

async def cmd_menu(message: Message, state: FSMContext):
    lang = await get_lang(state)
    await safe_answer(message, TEXT[lang]["menu_title"], reply_markup=kb_menu(lang))

async def pick_lang(call: CallbackQuery, state: FSMContext):
    lang = call.data.split(":")[1]
    await set_lang_keep(state, lang)
    await safe_answer_call(call, TEXT[lang]["hello"], reply_markup=kb_menu(lang))
    await call.message.answer(TEXT[lang]["subscribe_hint"], reply_markup=kb_channel_only(lang))
    await call.answer()

async def back_menu(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    await set_lang_keep(state, lang)
    await safe_answer_call(call, TEXT[lang]["menu_title"], reply_markup=kb_menu(lang))
    await call.answer()

# =========================
# MENU BY TEXT
# =========================
def is_cancel(lang: str, txt: str) -> bool:
    return (lang == "ru" and txt == "❌ Отмена") or (lang == "uz" and txt == "❌ Bekor qilish")

def is_telegram_btn(lang: str, txt: str) -> bool:
    return (lang == "ru" and txt == "📣 Telegram канал") or (lang == "uz" and txt == "📣 Telegram kanal")

async def menu_by_text(message: Message, state: FSMContext):
    lang = await get_lang(state)
    txt = (message.text or "").strip()

    # ✅ Telegram кнопка разрешена даже во время оформления заказа
    if txt in ("📣 Telegram канал", "📣 Telegram kanal"):
        msg = (
            "📣 <b>Наш Telegram-канал</b>\n"
            f"👉 <b>@{TELEGRAM_CHANNEL_USERNAME}</b>\n\n"
            "Там все коллекции, фото и новинки. Подпишитесь 😊✨"
        ) if lang == "ru" else (
            "📣 <b>Telegram kanalimiz</b>\n"
            f"👉 <b>@{TELEGRAM_CHANNEL_USERNAME}</b>\n\n"
            "Kolleksiyalar, rasmlar va yangiliklar shu yerda. Obuna bo‘ling 😊✨"
        )
        await safe_answer(message, msg, reply_markup=kb_channel_only(lang))
        return

    if is_cancel(lang, txt):
        await set_lang_keep(state, lang)
        await safe_answer(message, TEXT[lang]["cancelled"], reply_markup=kb_menu(lang))
        await safe_answer(message, TEXT[lang]["social_end"], reply_markup=kb_social_end(lang))
        return

    # ✅ блокировка только для кнопок меню (но не для Telegram)
    st = await state.get_state()
    if st and st.startswith("Flow:order_") and txt in (
        "🧾 Прайс","📸 Каталог","📏 Размер","📞 Связаться","🌐 Язык","🧺 Корзина","📜 История",
        "🧾 Narxlar","📸 Katalog","📏 O‘lcham","📞 Aloqa","🌐 Til","🧺 Savat","📜 Buyurtmalar"
    ):
        await safe_answer(message, TEXT[lang]["flow_locked"], reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➡️ Продолжить" if lang == "ru" else "➡️ Davom etish", callback_data="order:back_confirm")],
            [InlineKeyboardButton(text="❌ Отмена" if lang == "ru" else "❌ Bekor qilish", callback_data="order:cancel")],
            [InlineKeyboardButton(text="⬅️ Меню" if lang == "ru" else "⬅️ Menyu", callback_data="back:menu")],
        ]))
        return

    if txt in ("🌐 Язык","🌐 Til"):
        await safe_answer(message, TEXT[lang]["hello_ask_lang"], reply_markup=kb_lang())
        return

    if txt in ("🧾 Прайс","🧾 Narxlar"):
        await safe_answer(message, TEXT[lang]["price_title"], reply_markup=kb_price(lang))
        return

    if txt in ("📸 Каталог","📸 Katalog"):
        await safe_answer(message, TEXT[lang]["photos_title"], reply_markup=kb_photos(lang))
        return

    if txt in ("📏 Размер","📏 O‘lcham"):
        await safe_answer(message, TEXT[lang]["size_title"], reply_markup=kb_size_mode(lang))
        return

    if txt in ("✅ Заказ","✅ Buyurtma"):
        await start_order(message, state)
        return

    if txt in ("📞 Связаться","📞 Aloqa"):
        msg = TEXT[lang]["contact_title"]
        if MANAGER_USERNAME:
            msg += (f"\n👩‍💼 Menejer: @{MANAGER_USERNAME}" if lang == "uz" else f"\n👩‍💼 Менеджер: @{MANAGER_USERNAME}")
        await safe_answer(message, msg, reply_markup=kb_menu(lang))
        await safe_answer(message, TEXT[lang]["contact_offer_leave"], reply_markup=kb_contact_actions(lang))
        return

    if txt in ("🧺 Корзина","🧺 Savat"):
        items = cart_list(message.from_user.id)
        if not items:
            await safe_answer(message, TEXT[lang]["cart_empty"], reply_markup=kb_menu(lang))
            await safe_answer(message, "👇", reply_markup=kb_cart_actions(lang))
            return
        lines = []
        for i, it in enumerate(items, 1):
            lines.append(f"{i}) {esc(it['item'])} × {it['qty']}")
        text = TEXT[lang]["cart_title"] + "\n\n" + "\n".join(lines)
        await safe_answer(message, text, reply_markup=kb_cart_actions(lang))
        return

    if txt in ("📜 История","📜 Buyurtmalar"):
        hist = orders_list(message.from_user.id, limit=10)
        if not hist:
            await safe_answer(message, TEXT[lang]["history_empty"], reply_markup=kb_menu(lang))
            return
        lines = []
        for o in hist:
            lines.append(f"#{o['id']} • {esc(o['item'])} • {esc(o['city'])} • {esc(o['status'])} • {esc(o['created_at'])}")
        await safe_answer(message, TEXT[lang]["history_title"] + "\n\n" + "\n".join(lines), reply_markup=kb_menu(lang))
        return

    await safe_answer(message, TEXT[lang]["unknown"], reply_markup=kb_menu(lang))

# =========================
# PRICE
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
# CATALOG (IMPORTANT: always "no photos" + channel button)
# =========================
async def photo_section(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    key = call.data.split(":")[1]
    block = PHOTO_CATALOG.get(key)
    title = (block["uz"] if lang == "uz" else block["ru"]) if block else ("Каталог" if lang == "ru" else "Katalog")

    msg = f"📸 <b>{esc(title)}</b>\n\n" + TEXT[lang]["photos_no"]
    await safe_edit_call(call, msg, reply_markup=kb_channel_only(lang))
    await call.answer()

# =========================
# SIZE
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
    await safe_answer(message, TEXT[lang]["size_result_by_age"].format(age=age, age_rec=age_rec), reply_markup=kb_menu(lang))

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
    await safe_answer(message, TEXT[lang]["size_result_by_height"].format(height=height, height_rec=height_rec), reply_markup=kb_menu(lang))

# =========================
# CONTACT FLOW (lead -> DB + manager)
# =========================
async def contact_leave(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    await state.set_state(Flow.contact_phone)
    await safe_answer_call(call, TEXT[lang]["contact_phone_ask"], reply_markup=kb_contact_request(lang))
    await call.answer()

async def contact_phone(message: Message, state: FSMContext):
    lang = await get_lang(state)

    if message.contact and message.contact.phone_number:
        phone = message.contact.phone_number
    else:
        phone = (message.text or "").strip()

    if is_cancel(lang, phone):
        await set_lang_keep(state, lang)
        await safe_answer(message, TEXT[lang]["cancelled"], reply_markup=kb_menu(lang))
        await safe_answer(message, TEXT[lang]["social_end"], reply_markup=kb_social_end(lang))
        return

    phone = clean_phone(phone)
    if not looks_like_phone(phone):
        await safe_answer(message, TEXT[lang]["contact_phone_ask"], reply_markup=kb_contact_request(lang))
        return

    # save lead
    leads_insert(message.from_user.id, message.from_user.username or "", phone)

    ts = now_local().strftime("%Y-%m-%d %H:%M")
    lead_text = (
        f"📩 <b>Лид (контакт)</b> ({esc(ts)})\n"
        f"Телефон: <b>{esc(phone)}</b>\n"
        f"user_id: <code>{message.from_user.id}</code>\n"
        f"username: <code>@{esc(message.from_user.username) if message.from_user.username else '-'}</code>"
    )
    try:
        await message.bot.send_message(chat_id=MANAGER_CHAT_ID, text=lead_text)
    except Exception as e:
        print(f"Manager lead send error: {e}")

    await set_lang_keep(state, lang)
    await safe_answer(message, TEXT[lang]["contact_thanks"], reply_markup=kb_channel_only(lang))
    await safe_answer(message, "😊✨", reply_markup=kb_menu(lang))

# =========================
# CART FLOW
# =========================
async def cart_add_manual(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    await state.set_state(Flow.cart_add_item)
    await safe_answer_call(call, TEXT[lang]["cart_add_ask"], reply_markup=kb_menu(lang))
    await call.answer()

async def cart_add_item(message: Message, state: FSMContext):
    lang = await get_lang(state)
    txt = (message.text or "").strip()
    if is_cancel(lang, txt):
        await set_lang_keep(state, lang)
        await safe_answer(message, TEXT[lang]["cancelled"], reply_markup=kb_menu(lang))
        return
    if not txt:
        await safe_answer(message, TEXT[lang]["cart_add_ask"], reply_markup=kb_menu(lang))
        return
    cart_add(message.from_user.id, txt, 1)
    await set_lang_keep(state, lang)
    await safe_answer(message, TEXT[lang]["cart_added"], reply_markup=kb_menu(lang))

async def cart_clear_cb(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    cart_clear(call.from_user.id)
    await safe_answer_call(call, TEXT[lang]["cart_cleared"], reply_markup=kb_menu(lang))
    await call.answer()

async def cart_checkout_cb(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    items = cart_list(call.from_user.id)
    if not items:
        await safe_answer_call(call, TEXT[lang]["cart_empty"], reply_markup=kb_menu(lang))
        await call.answer()
        return
    order_text = "; ".join([f"{it['item']}×{it['qty']}" for it in items])
    await state.update_data(order_item=order_text, _from_cart=True)
    await state.set_state(Flow.order_name)
    await safe_answer_call(call, TEXT[lang]["order_start"], reply_markup=kb_menu(lang))
    await call.answer()

# =========================
# ORDER FLOW
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
        await set_lang_keep(state, lang)
        await safe_answer(message, TEXT[lang]["cancelled"], reply_markup=kb_menu(lang))
        await safe_answer(message, TEXT[lang]["social_end"], reply_markup=kb_social_end(lang))
        return

    phone = clean_phone(phone)
    if not looks_like_phone(phone):
        await safe_answer(message, TEXT[lang]["order_phone"], reply_markup=kb_contact_request(lang))
        return

    await state.update_data(order_phone=phone)
    await state.set_state(Flow.order_city)
    await safe_answer(message, TEXT[lang]["order_city"], reply_markup=kb_menu(lang))

async def order_city(message: Message, state: FSMContext):
    lang = await get_lang(state)
    city = (message.text or "").strip()
    if is_cancel(lang, city):
        await set_lang_keep(state, lang)
        await safe_answer(message, TEXT[lang]["cancelled"], reply_markup=kb_menu(lang))
        await safe_answer(message, TEXT[lang]["social_end"], reply_markup=kb_social_end(lang))
        return
    if not city:
        await safe_answer(message, TEXT[lang]["order_city"], reply_markup=kb_menu(lang))
        return
    await state.update_data(order_city=city)

    data = await state.get_data()
    # если заказ из корзины — item уже заполнен
    if data.get("order_item"):
        await state.set_state(Flow.order_size)
        await safe_answer(message, TEXT[lang]["order_size"], reply_markup=kb_menu(lang))
    else:
        await state.set_state(Flow.order_item)
        await safe_answer(message, TEXT[lang]["order_item"], reply_markup=kb_menu(lang))

async def order_item(message: Message, state: FSMContext):
    lang = await get_lang(state)
    item = (message.text or "").strip()
    if is_cancel(lang, item):
        await set_lang_keep(state, lang)
        await safe_answer(message, TEXT[lang]["cancelled"], reply_markup=kb_menu(lang))
        await safe_answer(message, TEXT[lang]["social_end"], reply_markup=kb_social_end(lang))
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
        await set_lang_keep(state, lang)
        await safe_answer(message, TEXT[lang]["cancelled"], reply_markup=kb_menu(lang))
        await safe_answer(message, TEXT[lang]["social_end"], reply_markup=kb_social_end(lang))
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
        await set_lang_keep(state, lang)
        await safe_answer(message, TEXT[lang]["cancelled"], reply_markup=kb_menu(lang))
        await safe_answer(message, TEXT[lang]["social_end"], reply_markup=kb_social_end(lang))
        return
    if not comment:
        comment = "нет" if lang == "ru" else "yo‘q"
    await state.update_data(order_comment=comment)
    await state.set_state(Flow.order_confirm)
    await show_order_review(message, state, lang)

async def order_cancel(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    await set_lang_keep(state, lang)
    await safe_answer_call(call, TEXT[lang]["cancelled"], reply_markup=kb_menu(lang))
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
    value = (message.text or "").strip()

    if is_cancel(lang, value):
        await set_lang_keep(state, lang)
        await safe_answer(message, TEXT[lang]["cancelled"], reply_markup=kb_menu(lang))
        await safe_answer(message, TEXT[lang]["social_end"], reply_markup=kb_social_end(lang))
        return

    if field == "phone":
        if message.contact and message.contact.phone_number:
            value = message.contact.phone_number
        value = clean_phone(value)
        if not looks_like_phone(value):
            await safe_answer(message, TEXT[lang]["order_phone"], reply_markup=kb_contact_request(lang))
            return
    else:
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

    # save order to DB (history)
    orders_insert(
        user_id=call.from_user.id,
        username=call.from_user.username or "",
        name=data.get("order_name", ""),
        phone=data.get("order_phone", ""),
        city=data.get("order_city", ""),
        item=data.get("order_item", ""),
        size=data.get("order_size", ""),
        comment=data.get("order_comment", ""),
    )

    # if order from cart -> clear cart
    if data.get("_from_cart"):
        cart_clear(call.from_user.id)

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

    # auto-reply to client
    await safe_answer_call(call, TEXT[lang]["order_sent"], reply_markup=kb_menu(lang))
    await safe_answer_call(call, TEXT[lang]["payment_info"], reply_markup=kb_menu(lang))
    await safe_answer_call(call, TEXT[lang]["worktime_in"] if in_work_time(now_local()) else TEXT[lang]["worktime_out"], reply_markup=kb_menu(lang))
    await safe_answer_call(call, TEXT[lang]["social_end"], reply_markup=kb_social_end(lang))

    await set_lang_keep(state, lang)
    await call.answer()

# =========================
# CALLBACKS: CART
# =========================
async def cart_clear_cb_wrap(call: CallbackQuery, state: FSMContext):
    await cart_clear_cb(call, state)

async def cart_checkout_cb_wrap(call: CallbackQuery, state: FSMContext):
    await cart_checkout_cb(call, state)

# =========================
# AUTOMATIONS: DAILY REPORT + MANAGER REMINDERS
# =========================
async def send_daily_report(bot: Bot):
    d = now_local().strftime("%Y-%m-%d")
    orders_cnt, leads_cnt = daily_counts(d)
    text = (
        f"📊 <b>Отчёт за {esc(d)}</b>\n"
        f"Заказы: <b>{orders_cnt}</b>\n"
        f"Лиды (контакты): <b>{leads_cnt}</b>\n"
    )
    await bot.send_message(MANAGER_CHAT_ID, text)

async def reminder_tick(bot: Bot):
    # remind about "new" orders older than 30 minutes, not reminded recently
    con = db_conn()
    cur = con.cursor()
    cur.execute("""
        SELECT id, name, phone, item, created_at, created_ts, reminded_ts
        FROM orders
        WHERE status='new'
        ORDER BY id DESC
        LIMIT 50
    """)
    rows = cur.fetchall()

    now_ = now_ts()
    remind_after = 30 * 60     # 30 min
    repeat_every = 60 * 60     # repeat each 60 min if still new

    to_remind = []
    for r in rows:
        order_id, name, phone, item, created_at, created_ts, reminded_ts = r
        if now_ - int(created_ts) >= remind_after:
            if int(reminded_ts) == 0 or (now_ - int(reminded_ts) >= repeat_every):
                to_remind.append((order_id, name, phone, item, created_at))

    if to_remind:
        lines = []
        for (order_id, name, phone, item, created_at) in to_remind[:10]:
            lines.append(f"#{order_id} • {esc(name)} • {esc(phone)} • {esc(item)} • {esc(created_at)}")
        text = "🔔 <b>Напоминание менеджеру</b>\nНеобработанные заказы:\n" + "\n".join(lines)
        try:
            await bot.send_message(MANAGER_CHAT_ID, text)
            # update reminded_ts
            cur2 = con.cursor()
            for (order_id, *_rest) in to_remind:
                cur2.execute("UPDATE orders SET reminded_ts=? WHERE id=?", (now_, order_id))
            con.commit()
        except Exception as e:
            print("reminder send error:", e)

    con.close()

async def scheduler_loop(bot: Bot):
    last_report_date = None
    while True:
        dt = now_local()

        # daily report at 21:05
        if dt.hour == 21 and dt.minute == 5:
            d = dt.strftime("%Y-%m-%d")
            if last_report_date != d:
                try:
                    await send_daily_report(bot)
                    last_report_date = d
                except Exception as e:
                    print("daily report error:", e)

        # manager reminder every 2 minutes
        try:
            await reminder_tick(bot)
        except Exception as e:
            print("reminder tick error:", e)

        await asyncio.sleep(120)

# =========================
# RENDER HEALTH SERVER (HEAD OK)
# =========================
class _HealthHandler(BaseHTTPRequestHandler):
    def _ok(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()

    def do_GET(self):
        self._ok()
        self.wfile.write(b"OK")

    def do_HEAD(self):
        self._ok()

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
    dp.message.register(cmd_menu, Command("menu"))

    dp.callback_query.register(pick_lang, F.data.startswith("lang:"))
    dp.callback_query.register(back_menu, F.data == "back:menu")

    dp.callback_query.register(price_section, F.data.startswith("price:"))
    dp.callback_query.register(go_order, F.data == "go:order")

    dp.callback_query.register(photo_section, F.data.startswith("photo:"))

    dp.callback_query.register(size_mode, F.data.startswith("size:"))
    dp.message.register(size_age, Flow.size_age)
    dp.message.register(size_height, Flow.size_height)

    # contact flow
    dp.callback_query.register(contact_leave, F.data == "contact:leave")
    dp.message.register(contact_phone, Flow.contact_phone)

    # cart flow
    dp.callback_query.register(cart_add_manual, F.data == "cart:add_manual")
    dp.message.register(cart_add_item, Flow.cart_add_item)
    dp.callback_query.register(cart_clear_cb_wrap, F.data == "cart:clear")
    dp.callback_query.register(cart_checkout_cb_wrap, F.data == "cart:checkout")

    # order states
    dp.message.register(order_name, Flow.order_name)
    dp.message.register(order_phone, Flow.order_phone)
    dp.message.register(order_city, Flow.order_city)
    dp.message.register(order_item, Flow.order_item)
    dp.message.register(order_size, Flow.order_size)
    dp.message.register(order_comment, Flow.order_comment)

    dp.callback_query.register(order_cancel, F.data == "order:cancel")
    dp.callback_query.register(order_confirm, F.data == "order:confirm")
    dp.callback_query.register(order_edit, F.data == "order:edit")
    dp.callback_query.register(order_back_confirm, F.data == "order:back_confirm")

    dp.callback_query.register(edit_pick, F.data.startswith("edit:"))
    dp.message.register(edit_field_value, Flow.edit_field)

    dp.message.register(menu_by_text, F.text)

    return dp

async def main():
    start_health_server()
    db_init()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dp()

    # background scheduler (daily report + reminders)
    asyncio.create_task(scheduler_loop(bot))

    print("✅ ZARY & CO assistant started (polling).")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
