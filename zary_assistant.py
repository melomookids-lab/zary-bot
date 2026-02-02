import os
import re
import html
import asyncio
import threading
import sqlite3
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
)

# =========================
# CONFIG
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env is empty. Set it in Render Environment Variables")

BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip()  # without @
if not BOT_USERNAME:
    print("⚠️ BOT_USERNAME is empty. Deep-links under channel posts will NOT work until you set BOT_USERNAME env.")

CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))  # -100xxxxxxxxxx
if CHANNEL_ID == 0:
    print("⚠️ CHANNEL_ID is 0. Autoposting will NOT work until you set CHANNEL_ID env.")

DB_PATH = os.getenv("DB_PATH", "bot.db")

# Manager settings
MANAGER_CHAT_ID = 7195737024
MANAGER_PHONE = "+998771202255"
MANAGER_USERNAME = ""  # without @ (optional)

# Timezone & schedules
TZ = ZoneInfo("Asia/Tashkent")
POST_TIME = time(18, 0)  # daily autopost at 18:00

# Links
INSTAGRAM_URL = "https://www.instagram.com/zary.co/"
YOUTUBE_URL = "https://www.youtube.com/@ZARYCOOFFICIAL"
TELEGRAM_CHANNEL_USERNAME = "zaryco_official"
TELEGRAM_CHANNEL_URL = f"https://t.me/{TELEGRAM_CHANNEL_USERNAME}"

# Deep links
BOT_URL = f"https://t.me/{BOT_USERNAME}" if BOT_USERNAME else ""

def start_link(payload: str) -> str:
    if not BOT_URL:
        return TELEGRAM_CHANNEL_URL
    return f"{BOT_URL}?start={payload}"

def is_admin(user_id: int) -> bool:
    return user_id == MANAGER_CHAT_ID

# =========================
# PROMO
# =========================
PROMO_CODES = {
    "PROMO10": 10,   # 10% discount
}

def promo_normalize(s: str) -> str:
    return (s or "").strip().upper().replace(" ", "")

def promo_discount(code: str) -> int:
    return PROMO_CODES.get(promo_normalize(code), 0)

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

def clean_phone(raw: str) -> str:
    return (raw or "").strip().replace(" ", "").replace("-", "")

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

# =========================
# DATABASE
# =========================
def db_conn():
    return sqlite3.connect(DB_PATH)

def _ensure_column(con: sqlite3.Connection, table: str, col: str, col_def: str):
    cur = con.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    if col not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
        con.commit()

def db_init():
    con = db_conn()
    cur = con.cursor()

    # users: store lang per user
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            lang TEXT NOT NULL DEFAULT 'ru',
            updated_at TEXT NOT NULL,
            updated_ts INTEGER NOT NULL
        )
    """)

    # cart
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

    # orders
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
            promo_code TEXT DEFAULT '',
            promo_discount INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            created_ts INTEGER NOT NULL,
            reminded_ts INTEGER NOT NULL DEFAULT 0
        )
    """)

    # leads
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

    # autopost templates
    cur.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            media_type TEXT NOT NULL,
            file_id TEXT,
            text TEXT,
            used INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            created_ts INTEGER NOT NULL
        )
    """)

    con.commit()

    _ensure_column(con, "orders", "promo_code", "TEXT DEFAULT ''")
    _ensure_column(con, "orders", "promo_discount", "INTEGER NOT NULL DEFAULT 0")

    con.close()

def user_upsert(user_id: int, username: str, lang: str):
    con = db_conn()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO users (user_id, username, lang, updated_at, updated_ts)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username=excluded.username,
            lang=excluded.lang,
            updated_at=excluded.updated_at,
            updated_ts=excluded.updated_ts
    """, (user_id, username or "", lang or "ru", now_local().strftime("%Y-%m-%d %H:%M:%S"), now_ts()))
    con.commit()
    con.close()

def user_get_lang(user_id: int) -> str:
    con = db_conn()
    cur = con.cursor()
    cur.execute("SELECT lang FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    con.close()
    if row and row[0] in ("ru", "uz"):
        return row[0]
    return "ru"

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

def orders_insert(user_id: int, username: str, name: str, phone: str, city: str, item: str, size: str, comment: str,
                  promo_code: str, promo_disc: int):
    con = db_conn()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO orders (user_id, username, name, phone, city, item, size, comment, status,
                            promo_code, promo_discount, created_at, created_ts, reminded_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, ?, ?, 0)
    """, (
        user_id, username or "", name or "", phone or "", city or "", item or "", size or "", comment or "",
        promo_code or "", int(promo_disc or 0),
        now_local().strftime("%Y-%m-%d %H:%M:%S"), now_ts()
    ))
    con.commit()
    order_id = cur.lastrowid
    con.close()
    return order_id

def orders_list_by_user(user_id: int, limit: int = 10):
    con = db_conn()
    cur = con.cursor()
    cur.execute("""
        SELECT id, item, city, status, promo_code, promo_discount, created_at
        FROM orders
        WHERE user_id=?
        ORDER BY id DESC LIMIT ?
    """, (user_id, limit))
    rows = cur.fetchall()
    con.close()
    return [{
        "id": r[0], "item": r[1], "city": r[2], "status": r[3],
        "promo_code": r[4], "promo_discount": r[5], "created_at": r[6]
    } for r in rows]

def orders_list_all(limit: int = 30):
    con = db_conn()
    cur = con.cursor()
    cur.execute("""
        SELECT id, user_id, name, phone, city, item, status, promo_code, promo_discount, created_at
        FROM orders
        ORDER BY id DESC LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    con.close()
    return rows

def order_set_status(order_id: int, status: str):
    con = db_conn()
    cur = con.cursor()
    cur.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    con.commit()
    con.close()

def order_get(order_id: int):
    con = db_conn()
    cur = con.cursor()
    cur.execute("SELECT user_id, name, status FROM orders WHERE id=?", (order_id,))
    row = cur.fetchone()
    con.close()
    return row  # (user_id, name, status) or None

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
    con = db_conn()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM orders WHERE substr(created_at,1,10)=?", (date_str,))
    orders_cnt = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM leads WHERE substr(created_at,1,10)=?", (date_str,))
    leads_cnt = cur.fetchone()[0]
    con.close()
    return orders_cnt, leads_cnt

def post_add(media_type: str, file_id: str | None, text: str | None):
    con = db_conn()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO posts (media_type, file_id, text, used, created_at, created_ts)
        VALUES (?, ?, ?, 0, ?, ?)
    """, (media_type, file_id or "", text or "", now_local().strftime("%Y-%m-%d %H:%M:%S"), now_ts()))
    con.commit()
    con.close()

def post_pick_next():
    con = db_conn()
    cur = con.cursor()
    cur.execute("""
        SELECT id, media_type, file_id, text
        FROM posts
        WHERE used=0
        ORDER BY id ASC
        LIMIT 1
    """)
    row = cur.fetchone()

    # если закончились — начинаем сначала
    if not row:
        cur.execute("UPDATE posts SET used=0")
        con.commit()
        cur.execute("""
            SELECT id, media_type, file_id, text
            FROM posts
            WHERE used=0
            ORDER BY id ASC
            LIMIT 1
        """)
        row = cur.fetchone()

    if not row:
        con.close()
        return None

    post_id, media_type, file_id, text = row
    cur.execute("UPDATE posts SET used=1 WHERE id=?", (post_id,))
    con.commit()
    con.close()
    return {"id": post_id, "media_type": media_type, "file_id": file_id, "text": text}

# =========================
# FAQ TEXTS
# =========================
FAQ_RU = (
    "❓ <b>FAQ — Частые вопросы</b>\n\n"
    "🚚 <b>Доставка</b>\n"
    "• Доставляем по Узбекистану\n"
    "• Стоимость и сроки зависят от города\n\n"
    "💳 <b>Оплата</b>\n"
    "• После подтверждения заказа менеджер отправит реквизиты\n"
    "• После оплаты отправьте чек/скрин\n\n"
    "↩️ <b>Возврат/обмен</b>\n"
    "• Возврат/обмен обсуждается с менеджером\n"
    "• Важно сохранить товарный вид\n\n"
    "⏳ <b>Сроки пошива</b>\n"
    "• Если модель в наличии — отправка быстрее\n"
    "• Если индивидуальный пошив — менеджер уточнит сроки\n"
)

FAQ_UZ = (
    "❓ <b>FAQ — Ko‘p so‘raladigan savollar</b>\n\n"
    "🚚 <b>Yetkazib berish</b>\n"
    "• O‘zbekiston bo‘ylab yetkazamiz\n"
    "• Narx va muddat shaharga bog‘liq\n\n"
    "💳 <b>To‘lov</b>\n"
    "• Buyurtma tasdiqlangach menejer rekvizit yuboradi\n"
    "• To‘lovdan keyin чек/skrinni yuboring\n\n"
    "↩️ <b>Qaytarish/almashtirish</b>\n"
    "• Menejer bilan kelishiladi\n"
    "• Mahsulot ko‘rinishi saqlanishi kerak\n\n"
    "⏳ <b>Tikish muddati</b>\n"
    "• Tayyor bo‘lsa — tezroq yuboriladi\n"
    "• Individual tikuv — muddatni menejer aytadi\n"
)

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
        "from_post_hint": "✨ Вы пришли из поста в канале. Чем помочь? 👇",

        "photos_title": "📸 <b>Каталог (разделы)</b>\nВыберите раздел:",
        "photos_no": (
            "Извините, сейчас в этом разделе фото нет.\n"
            "Все фото-коллекции и новинки мы выкладываем в Telegram-канале 👇\n"
            f"👉 <b>@{TELEGRAM_CHANNEL_USERNAME}</b>\n\n"
            "Нажмите кнопку ниже, чтобы перейти и подписаться 😊✨"
        ),

        "size_title": "📏 <b>Подбор размера (1–15 лет)</b>\nВыберите способ:",
        "size_age_ask": "Напишите возраст ребёнка (1–15). Пример: <code>7</code>",
        "size_height_ask": "Напишите рост в см. Пример: <code>125</code>",
        "size_bad_age": "Введите возраст цифрой от 1 до 15. Пример: <code>7</code>",
        "size_bad_height": "Введите рост цифрой (например: 125).",
        "size_result_by_age": (
            "📏 <b>Рекомендация по возрасту</b>\n"
            "Возраст: {age}\n"
            "Примерный размер: <b>{age_rec}</b>\n\n"
            "ℹ️ Точный размер подтверждает менеджер 😊"
        ),
        "size_result_by_height": (
            "📏 <b>Рекомендация по росту</b>\n"
            "Рост: {height} см\n"
            "Рекомендуем размер: <b>{height_rec}</b>\n\n"
            "ℹ️ Точный размер подтверждает менеджер 😊"
        ),

        "faq_text": FAQ_RU,

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

        "order_start": "🧾 <b>Оформляем заказ</b>\nКак вас зовут? 😊",
        "order_phone": "📲 Отправьте номер телефона (или нажмите кнопку «📲 Отправить контакт»).",
        "order_city": "🏙 Ваш город/район?",
        "order_item": "👕 Что хотите заказать? (например: куртка / худи / костюм / школьная форма)",
        "order_size": "👶 Возраст и рост одним сообщением.\nПример: <code>7 лет, 125 см</code>",
        "order_size_bad": "Напишите <b>и возраст, и рост</b> одним сообщением.\nПример: <code>7 лет, 125 см</code>",
        "order_promo": "🏷 Есть промокод? Напишите (например: <code>PROMO10</code>) или напишите <b>нет</b>.",
        "order_promo_ok": "✅ Промокод принят: <b>{code}</b> (скидка {disc}%)",
        "order_promo_bad": "⚠️ Такой промокод не найден. Напишите другой или <b>нет</b>.",
        "order_comment": "✍️ Комментарий (цвет/кол-во) или напишите «нет»",
        "order_sent": (
            "✅ Спасибо! Заказ принят 😊\n"
            "Менеджер свяжется с вами, чтобы уточнить детали заказа и доставки."
        ),
        "payment_info": (
            "💳 <b>Оплата</b>\n"
            "После подтверждения заказа менеджер отправит реквизиты/карту.\n\n"
            "✅ После оплаты отправьте чек/скрин менеджеру — и мы оформим доставку 😊"
        ),
        "after_order": (
            "📣 Пока менеджер готовит ответ — зайдите в наш Telegram-канал и посмотрите коллекции 👇\n"
            "Там все фото и новинки 😊✨"
        ),

        "client_processing": "✅ Ваш заказ #{order_id} принят в работу. Менеджер уже занимается вашим заказом 😊",
        "client_done": "🎉 Ваш заказ #{order_id} готов / обработан! Если нужно — менеджер уточнит доставку 😊",
        "client_new": "ℹ️ Статус заказа #{order_id} обновлён: <b>new</b>.",

        "cancelled": "❌ Отменено. Возвращаю в меню 👇",
        "unknown": "Пожалуйста, используйте кнопки меню 👇",

        "social_end": (
            "📌 <b>Наши ссылки:</b>\n"
            f"📣 Telegram: {TELEGRAM_CHANNEL_URL}\n"
            f"📸 Instagram: {INSTAGRAM_URL}\n"
            f"▶️ YouTube: {YOUTUBE_URL}\n\n"
            "Спасибо, что вы с нами 😊✨"
        ),

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
        "from_post_hint": "✨ Siz kanal postidan kirdingiz. Qanday yordam beray? 👇",

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

        "faq_text": FAQ_UZ,

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
        "order_promo": "🏷 Promokod bormi? (masalan: <code>PROMO10</code>) yoki <b>yo‘q</b> deb yozing.",
        "order_promo_ok": "✅ Promokod qabul qilindi: <b>{code}</b> (chegirma {disc}%)",
        "order_promo_bad": "⚠️ Bunday promokod yo‘q. Boshqasini yozing yoki <b>yo‘q</b> deb yozing.",
        "order_comment": "✍️ Izoh (rang/soni) yoki «yo‘q» deb yozing",
        "order_sent": (
            "✅ Rahmat! Buyurtma qabul qilindi 😊\n"
            "Menejer bog‘lanib, buyurtma va yetkazib berish tafsilotlarini aniqlashtiradi."
        ),
        "payment_info": (
            "💳 <b>To‘lov</b>\n"
            "Buyurtma tasdiqlangandan so‘ng menejer karta/revizitlarni yuboradi.\n\n"
            "✅ To‘lovdan keyin чек/skrinni menejerga yuboring 😊"
        ),
        "after_order": (
            "📣 Menejer javob tayyorlayotgan paytda — Telegram kanalimizga o‘ting va kolleksiyalarni ko‘ring 👇\n"
            "U yerda barcha rasmlar va yangiliklar bor 😊✨"
        ),

        "client_processing": "✅ Buyurtmangiz #{order_id} ishga olindi. Menejer buyurtmangizni ko‘rib chiqmoqda 😊",
        "client_done": "🎉 Buyurtmangiz #{order_id} tayyor / bajarildi! Yetkazib berish bo‘yicha menejer aniqlashtiradi 😊",
        "client_new": "ℹ️ Buyurtma #{order_id} holati yangilandi: <b>new</b>.",

        "cancelled": "❌ Bekor qilindi. Menyuga qaytdik 👇",
        "unknown": "Iltimos, menyu tugmalaridan foydalaning 👇",

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
    order_promo = State()
    order_comment = State()

# =========================
# LANGUAGE helpers (FSM + DB)
# =========================
async def get_lang(state: FSMContext, user_id: int) -> str:
    data = await state.get_data()
    if data.get("lang") in ("ru", "uz"):
        return data["lang"]
    # fallback to DB
    lang = user_get_lang(user_id)
    await state.update_data(lang=lang)
    return lang

async def set_lang_keep(state: FSMContext, user_id: int, username: str, lang: str):
    await state.clear()
    await state.update_data(lang=lang)
    user_upsert(user_id, username or "", lang)

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
            [KeyboardButton(text="📏 O‘lcham"), KeyboardButton(text="❓ FAQ")],
            [KeyboardButton(text="🧺 Savat"), KeyboardButton(text="📜 Buyurtmalar")],
            [KeyboardButton(text="✅ Buyurtma"), KeyboardButton(text="📞 Aloqa")],
            [KeyboardButton(text="🌐 Til"), KeyboardButton(text="❌ Bekor qilish")],
        ]
    else:
        rows = [
            [KeyboardButton(text="📣 Telegram канал"), KeyboardButton(text="📸 Каталог")],
            [KeyboardButton(text="📏 Размер"), KeyboardButton(text="❓ FAQ")],
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

def kb_after_order(lang: str) -> InlineKeyboardMarkup:
    channel_text = "📣 Перейти в канал" if lang == "ru" else "📣 Kanalga o‘tish"
    menu_text = "⬅️ Меню" if lang == "ru" else "⬅️ Menyu"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=channel_text, url=TELEGRAM_CHANNEL_URL)],
        [InlineKeyboardButton(text=menu_text, callback_data="back:menu")]
    ])

def kb_social_end(lang: str) -> InlineKeyboardMarkup:
    menu_text = "⬅️ Меню" if lang == "ru" else "⬅️ Menyu"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📣 Telegram", url=TELEGRAM_CHANNEL_URL)],
        [InlineKeyboardButton(text="📸 Instagram", url=INSTAGRAM_URL)],
        [InlineKeyboardButton(text="▶️ YouTube", url=YOUTUBE_URL)],
        [InlineKeyboardButton(text=menu_text, callback_data="back:menu")],
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

def kb_write_manager(lang: str) -> InlineKeyboardMarkup:
    menu_text = "⬅️ Меню" if lang == "ru" else "⬅️ Menyu"
    if not MANAGER_USERNAME:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=menu_text, callback_data="back:menu")]
        ])
    btn_text = "✍️ Написать менеджеру" if lang == "ru" else "✍️ Menejerga yozish"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_text, url=f"https://t.me/{MANAGER_USERNAME}")],
        [InlineKeyboardButton(text=menu_text, callback_data="back:menu")],
    ])

def kb_post_cta(lang: str) -> InlineKeyboardMarkup:
    # buttons under channel posts
    if lang == "uz":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Buyurtma", url=start_link("order")),
             InlineKeyboardButton(text="📏 O‘lcham", url=start_link("size"))],
            [InlineKeyboardButton(text="📸 Katalog", url=start_link("catalog")),
             InlineKeyboardButton(text="📞 Aloqa", url=start_link("contact"))],
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Заказать", url=start_link("order")),
         InlineKeyboardButton(text="📏 Выбрать размер", url=start_link("size"))],
        [InlineKeyboardButton(text="📸 Каталог", url=start_link("catalog")),
         InlineKeyboardButton(text="📞 Связаться", url=start_link("contact"))],
    ])

def kb_admin_status(order_id: int, current_status: str = "new") -> InlineKeyboardMarkup:
    # callback: adm:status:<id>:<status>
    btns = []
    if current_status != "processing":
        btns.append(InlineKeyboardButton(text="✅ processing", callback_data=f"adm:status:{order_id}:processing"))
    if current_status != "done":
        btns.append(InlineKeyboardButton(text="✅ done", callback_data=f"adm:status:{order_id}:done"))
    if current_status != "new":
        btns.append(InlineKeyboardButton(text="↩️ new", callback_data=f"adm:status:{order_id}:new"))

    rows = []
    if len(btns) <= 2:
        rows.append(btns)
    else:
        rows.append(btns[:2])
        rows.append(btns[2:])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# =========================
# START / LANG + deep-link routing
# =========================
def parse_start_payload(message: Message) -> str:
    txt = (message.text or "").strip()
    parts = txt.split(maxsplit=1)
    if len(parts) == 2:
        return parts[1].strip()
    return ""

async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or ""

    data = await state.get_data()
    if "lang" not in data:
        # If user already has lang in DB - we can skip language ask
        saved = user_get_lang(user_id)
        if saved in ("ru", "uz"):
            await state.update_data(lang=saved)
        else:
            await safe_answer(message, TEXT["ru"]["hello_ask_lang"], reply_markup=kb_lang())
            return

    lang = await get_lang(state, user_id)
    await set_lang_keep(state, user_id, username, lang)

    payload = parse_start_payload(message)

    if payload in ("order", "size", "catalog", "contact"):
        await safe_answer(message, TEXT[lang]["from_post_hint"], reply_markup=kb_menu(lang))
        if payload == "order":
            await start_order(message, state)
            return
        if payload == "size":
            await safe_answer(message, TEXT[lang]["size_title"], reply_markup=kb_size_mode(lang))
            return
        if payload == "catalog":
            await safe_answer(message, TEXT[lang]["photos_title"], reply_markup=kb_photos(lang))
            return
        if payload == "contact":
            await show_contact(message, state)
            return

    await safe_answer(message, TEXT[lang]["hello"], reply_markup=kb_menu(lang))
    await safe_answer(message, TEXT[lang]["subscribe_hint"], reply_markup=kb_channel_only(lang))

async def cmd_menu(message: Message, state: FSMContext):
    lang = await get_lang(state, message.from_user.id)
    await safe_answer(message, TEXT[lang]["menu_title"], reply_markup=kb_menu(lang))

async def pick_lang(call: CallbackQuery, state: FSMContext):
    lang = call.data.split(":")[1]
    user_id = call.from_user.id
    username = call.from_user.username or ""
    await set_lang_keep(state, user_id, username, lang)
    await safe_answer_call(call, TEXT[lang]["hello"], reply_markup=kb_menu(lang))
    await call.message.answer(TEXT[lang]["subscribe_hint"], reply_markup=kb_channel_only(lang))
    await call.answer()

async def back_menu(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state, call.from_user.id)
    await set_lang_keep(state, call.from_user.id, call.from_user.username or "", lang)
    await safe_answer_call(call, TEXT[lang]["menu_title"], reply_markup=kb_menu(lang))
    await call.answer()

# =========================
# MENU BY TEXT
# =========================
def is_cancel(lang: str, txt: str) -> bool:
    return (lang == "ru" and txt == "❌ Отмена") or (lang == "uz" and txt == "❌ Bekor qilish")

async def show_contact(message: Message, state: FSMContext):
    lang = await get_lang(state, message.from_user.id)
    msg = TEXT[lang]["contact_title"]
    if MANAGER_USERNAME:
        msg += (f"\n👩‍💼 Menejer: @{MANAGER_USERNAME}" if lang == "uz" else f"\n👩‍💼 Менеджер: @{MANAGER_USERNAME}")
    await safe_answer(message, msg, reply_markup=kb_write_manager(lang))
    await safe_answer(message, TEXT[lang]["contact_offer_leave"], reply_markup=kb_contact_actions(lang))

async def menu_by_text(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = await get_lang(state, user_id)
    txt = (message.text or "").strip()

    if is_cancel(lang, txt):
        await set_lang_keep(state, user_id, message.from_user.username or "", lang)
        await safe_answer(message, TEXT[lang]["cancelled"], reply_markup=kb_menu(lang))
        await safe_answer(message, TEXT[lang]["social_end"], reply_markup=kb_social_end(lang))
        return

    if txt in ("🌐 Язык","🌐 Til"):
        await safe_answer(message, TEXT[lang]["hello_ask_lang"], reply_markup=kb_lang())
        return

    if txt in ("❓ FAQ",):
        await safe_answer(message, TEXT[lang]["faq_text"], reply_markup=kb_menu(lang))
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
        await show_contact(message, state)
        return

    if txt in ("🧺 Корзина","🧺 Savat"):
        items = cart_list(user_id)
        if not items:
            await safe_answer(message, TEXT[lang]["cart_empty"], reply_markup=kb_menu(lang))
            await safe_answer(message, "👇", reply_markup=kb_cart_actions(lang))
            return
        lines = [f"{i}) {esc(it['item'])} × {it['qty']}" for i, it in enumerate(items, 1)]
        await safe_answer(message, TEXT[lang]["cart_title"] + "\n\n" + "\n".join(lines), reply_markup=kb_cart_actions(lang))
        return

    if txt in ("📜 История","📜 Buyurtmalar"):
        hist = orders_list_by_user(user_id, limit=10)  # ✅ ONLY USER ORDERS
        if not hist:
            await safe_answer(message, TEXT[lang]["history_empty"], reply_markup=kb_menu(lang))
            return
        lines = []
        for o in hist:
            promo_line = ""
            if o["promo_code"] and o["promo_discount"]:
                promo_line = f" • promo {esc(o['promo_code'])} (-{o['promo_discount']}%)"
            lines.append(f"#{o['id']} • {esc(o['item'])} • {esc(o['city'])} • {esc(o['status'])}{promo_line} • {esc(o['created_at'])}")
        await safe_answer(message, TEXT[lang]["history_title"] + "\n\n" + "\n".join(lines), reply_markup=kb_menu(lang))
        return

    if txt in ("📣 Telegram канал","📣 Telegram kanal"):
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

    await safe_answer(message, TEXT[lang]["unknown"], reply_markup=kb_menu(lang))

# =========================
# CATALOG
# =========================
async def photo_section(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state, call.from_user.id)
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
    lang = await get_lang(state, call.from_user.id)
    mode = call.data.split(":")[1]
    if mode == "age":
        await state.set_state(Flow.size_age)
        await safe_answer_call(call, TEXT[lang]["size_age_ask"], reply_markup=kb_menu(lang))
    else:
        await state.set_state(Flow.size_height)
        await safe_answer_call(call, TEXT[lang]["size_height_ask"], reply_markup=kb_menu(lang))
    await call.answer()

async def size_age(message: Message, state: FSMContext):
    lang = await get_lang(state, message.from_user.id)
    txt = (message.text or "").strip()
    if not txt.isdigit():
        await safe_answer(message, TEXT[lang]["size_bad_age"], reply_markup=kb_menu(lang))
        return
    age = int(txt)
    if not (1 <= age <= 15):
        await safe_answer(message, TEXT[lang]["size_bad_age"], reply_markup=kb_menu(lang))
        return
    age_rec = age_to_size_range(age)
    await set_lang_keep(state, message.from_user.id, message.from_user.username or "", lang)
    await safe_answer(message, TEXT[lang]["size_result_by_age"].format(age=age, age_rec=age_rec), reply_markup=kb_menu(lang))

async def size_height(message: Message, state: FSMContext):
    lang = await get_lang(state, message.from_user.id)
    txt = (message.text or "").strip()
    if not txt.isdigit():
        await safe_answer(message, TEXT[lang]["size_bad_height"], reply_markup=kb_menu(lang))
        return
    height = int(txt)
    if height < 70 or height > 190:
        await safe_answer(message, TEXT[lang]["size_bad_height"], reply_markup=kb_menu(lang))
        return
    height_rec = height_to_size(height)
    await set_lang_keep(state, message.from_user.id, message.from_user.username or "", lang)
    await safe_answer(message, TEXT[lang]["size_result_by_height"].format(height=height, height_rec=height_rec), reply_markup=kb_menu(lang))

# =========================
# CONTACT FLOW
# =========================
async def contact_leave(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state, call.from_user.id)
    await state.set_state(Flow.contact_phone)
    await safe_answer_call(call, TEXT[lang]["contact_phone_ask"], reply_markup=kb_contact_request(lang))
    await call.answer()

async def contact_phone(message: Message, state: FSMContext):
    lang = await get_lang(state, message.from_user.id)

    if message.contact and message.contact.phone_number:
        phone = message.contact.phone_number
    else:
        phone = (message.text or "").strip()

    if is_cancel(lang, phone):
        await set_lang_keep(state, message.from_user.id, message.from_user.username or "", lang)
        await safe_answer(message, TEXT[lang]["cancelled"], reply_markup=kb_menu(lang))
        await safe_answer(message, TEXT[lang]["social_end"], reply_markup=kb_social_end(lang))
        return

    phone = clean_phone(phone)
    if not looks_like_phone(phone):
        await safe_answer(message, TEXT[lang]["contact_phone_ask"], reply_markup=kb_contact_request(lang))
        return

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

    await set_lang_keep(state, message.from_user.id, message.from_user.username or "", lang)
    await safe_answer(message, TEXT[lang]["contact_thanks"], reply_markup=kb_channel_only(lang))
    await safe_answer(message, "😊✨", reply_markup=kb_menu(lang))

# =========================
# CART FLOW
# =========================
async def cart_add_manual(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state, call.from_user.id)
    await state.set_state(Flow.cart_add_item)
    await safe_answer_call(call, TEXT[lang]["cart_add_ask"], reply_markup=kb_menu(lang))
    await call.answer()

async def cart_add_item(message: Message, state: FSMContext):
    lang = await get_lang(state, message.from_user.id)
    txt = (message.text or "").strip()
    if is_cancel(lang, txt):
        await set_lang_keep(state, message.from_user.id, message.from_user.username or "", lang)
        await safe_answer(message, TEXT[lang]["cancelled"], reply_markup=kb_menu(lang))
        return
    if not txt:
        await safe_answer(message, TEXT[lang]["cart_add_ask"], reply_markup=kb_menu(lang))
        return
    cart_add(message.from_user.id, txt, 1)
    await set_lang_keep(state, message.from_user.id, message.from_user.username or "", lang)
    await safe_answer(message, TEXT[lang]["cart_added"], reply_markup=kb_menu(lang))

async def cart_clear_cb(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state, call.from_user.id)
    cart_clear(call.from_user.id)
    await safe_answer_call(call, TEXT[lang]["cart_cleared"], reply_markup=kb_menu(lang))
    await call.answer()

async def cart_checkout_cb(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state, call.from_user.id)
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
    lang = await get_lang(state, message.from_user.id)
    await state.set_state(Flow.order_name)
    await safe_answer(message, TEXT[lang]["order_start"], reply_markup=kb_menu(lang))

async def order_name(message: Message, state: FSMContext):
    lang = await get_lang(state, message.from_user.id)
    name = (message.text or "").strip()
    if not name or is_cancel(lang, name):
        await safe_answer(message, TEXT[lang]["order_start"], reply_markup=kb_menu(lang))
        return
    await state.update_data(order_name=name)
    await state.set_state(Flow.order_phone)
    await safe_answer(message, TEXT[lang]["order_phone"], reply_markup=kb_contact_request(lang))

async def order_phone(message: Message, state: FSMContext):
    lang = await get_lang(state, message.from_user.id)
    if message.contact and message.contact.phone_number:
        phone = message.contact.phone_number
    else:
        phone = (message.text or "").strip()

    if is_cancel(lang, phone):
        await set_lang_keep(state, message.from_user.id, message.from_user.username or "", lang)
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
    lang = await get_lang(state, message.from_user.id)
    city = (message.text or "").strip()
    if is_cancel(lang, city):
        await set_lang_keep(state, message.from_user.id, message.from_user.username or "", lang)
        await safe_answer(message, TEXT[lang]["cancelled"], reply_markup=kb_menu(lang))
        await safe_answer(message, TEXT[lang]["social_end"], reply_markup=kb_social_end(lang))
        return
    if not city:
        await safe_answer(message, TEXT[lang]["order_city"], reply_markup=kb_menu(lang))
        return
    await state.update_data(order_city=city)

    data = await state.get_data()
    if data.get("order_item"):
        await state.set_state(Flow.order_size)
        await safe_answer(message, TEXT[lang]["order_size"], reply_markup=kb_menu(lang))
    else:
        await state.set_state(Flow.order_item)
        await safe_answer(message, TEXT[lang]["order_item"], reply_markup=kb_menu(lang))

async def order_item(message: Message, state: FSMContext):
    lang = await get_lang(state, message.from_user.id)
    item = (message.text or "").strip()
    if is_cancel(lang, item):
        await set_lang_keep(state, message.from_user.id, message.from_user.username or "", lang)
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
    lang = await get_lang(state, message.from_user.id)
    raw = (message.text or "").strip()
    if is_cancel(lang, raw):
        await set_lang_keep(state, message.from_user.id, message.from_user.username or "", lang)
        await safe_answer(message, TEXT[lang]["cancelled"], reply_markup=kb_menu(lang))
        await safe_answer(message, TEXT[lang]["social_end"], reply_markup=kb_social_end(lang))
        return

    age, height = extract_two_numbers_any_order(raw)
    if age is None or height is None:
        await safe_answer(message, TEXT[lang]["order_size_bad"], reply_markup=kb_menu(lang))
        return

    normalized = f"{age} лет, {height} см" if lang == "ru" else f"{age} yosh, {height} sm"
    await state.update_data(order_size=normalized)
    await state.set_state(Flow.order_promo)
    await safe_answer(message, TEXT[lang]["order_promo"], reply_markup=kb_menu(lang))

async def order_promo(message: Message, state: FSMContext):
    lang = await get_lang(state, message.from_user.id)
    raw = (message.text or "").strip()

    if is_cancel(lang, raw):
        await set_lang_keep(state, message.from_user.id, message.from_user.username or "", lang)
        await safe_answer(message, TEXT[lang]["cancelled"], reply_markup=kb_menu(lang))
        await safe_answer(message, TEXT[lang]["social_end"], reply_markup=kb_social_end(lang))
        return

    none_words = {"нет", "yo‘q", "yo'q", "yoq", "нету", "no"}
    if promo_normalize(raw).lower() in none_words:
        await state.update_data(promo_code="", promo_discount=0)
        await state.set_state(Flow.order_comment)
        await safe_answer(message, TEXT[lang]["order_comment"], reply_markup=kb_menu(lang))
        return

    code = promo_normalize(raw)
    disc = promo_discount(code)
    if disc <= 0:
        await safe_answer(message, TEXT[lang]["order_promo_bad"], reply_markup=kb_menu(lang))
        return

    await state.update_data(promo_code=code, promo_discount=disc)
    await safe_answer(message, TEXT[lang]["order_promo_ok"].format(code=esc(code), disc=disc), reply_markup=kb_menu(lang))
    await state.set_state(Flow.order_comment)
    await safe_answer(message, TEXT[lang]["order_comment"], reply_markup=kb_menu(lang))

async def order_comment(message: Message, state: FSMContext):
    lang = await get_lang(state, message.from_user.id)
    comment = (message.text or "").strip()

    if is_cancel(lang, comment):
        await set_lang_keep(state, message.from_user.id, message.from_user.username or "", lang)
        await safe_answer(message, TEXT[lang]["cancelled"], reply_markup=kb_menu(lang))
        await safe_answer(message, TEXT[lang]["social_end"], reply_markup=kb_social_end(lang))
        return

    if not comment:
        comment = "нет" if lang == "ru" else "yo‘q"

    data = await state.get_data()
    promo_code = data.get("promo_code", "") or ""
    promo_disc = int(data.get("promo_discount", 0) or 0)

    order_id = orders_insert(
        user_id=message.from_user.id,
        username=message.from_user.username or "",
        name=data.get("order_name", ""),
        phone=data.get("order_phone", ""),
        city=data.get("order_city", ""),
        item=data.get("order_item", ""),
        size=data.get("order_size", ""),
        comment=comment,
        promo_code=promo_code,
        promo_disc=promo_disc,
    )

    if data.get("_from_cart"):
        cart_clear(message.from_user.id)

    # ✅ send to manager + status buttons
    ts = now_local().strftime("%Y-%m-%d %H:%M")
    promo_line = ""
    if promo_code and promo_disc:
        promo_line = f"\n🏷 Promo: <b>{esc(promo_code)}</b> (-{promo_disc}%)"

    manager_text = (
        f"🛎 <b>Новый заказ</b> #{order_id} ({esc(ts)})\n\n"
        f"• Имя: <b>{esc(data.get('order_name','-'))}</b>\n"
        f"• Телефон: <b>{esc(data.get('order_phone','-'))}</b>\n"
        f"• Город: <b>{esc(data.get('order_city','-'))}</b>\n"
        f"• Товар: <b>{esc(data.get('order_item','-'))}</b>\n"
        f"• Возраст/рост: <b>{esc(data.get('order_size','-'))}</b>\n"
        f"• Комментарий: <b>{esc(comment)}</b>"
        f"{promo_line}\n\n"
        f"Статус: <b>new</b>\n"
        f"👤 user_id: <code>{message.from_user.id}</code>\n"
        f"👤 username: <code>@{esc(message.from_user.username) if message.from_user.username else '-'}</code>"
    )
    try:
        await message.bot.send_message(
            chat_id=MANAGER_CHAT_ID,
            text=manager_text,
            reply_markup=kb_admin_status(order_id, "new")
        )
    except Exception as e:
        print(f"Manager send error: {e}")

    await set_lang_keep(state, message.from_user.id, message.from_user.username or "", lang)

    await safe_answer(message, TEXT[lang]["order_sent"], reply_markup=kb_menu(lang))
    await safe_answer(message, TEXT[lang]["payment_info"], reply_markup=kb_menu(lang))
    await safe_answer(message, TEXT[lang]["after_order"], reply_markup=kb_after_order(lang))

# =========================
# ADMIN CALLBACK: status buttons + notify client
# =========================
async def admin_set_status(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    # adm:status:<id>:<status>
    try:
        _, _, sid, st = call.data.split(":", 3)
    except Exception:
        await call.answer("Ошибка данных", show_alert=True)
        return

    if not sid.isdigit():
        await call.answer("Неверный ID", show_alert=True)
        return

    st = (st or "").lower().strip()
    if st not in ("new", "processing", "done"):
        await call.answer("Неверный статус", show_alert=True)
        return

    order_id = int(sid)
    order_set_status(order_id, st)

    # update manager message text
    try:
        old = call.message.text or ""
        new_text = re.sub(r"Статус:\s*<b>.*?</b>", f"Статус: <b>{st}</b>", old)
        await call.message.edit_text(new_text, reply_markup=kb_admin_status(order_id, st))
    except Exception:
        pass

    # notify client in THEIR language (from DB)
    row = order_get(order_id)
    if row:
        client_id, _name, _old_status = row
        client_lang = user_get_lang(client_id)
        if st == "processing":
            text_client = TEXT[client_lang]["client_processing"].format(order_id=order_id)
            try:
                await call.bot.send_message(client_id, text_client)
            except Exception:
                pass
        elif st == "done":
            text_client = TEXT[client_lang]["client_done"].format(order_id=order_id)
            try:
                await call.bot.send_message(client_id, text_client, reply_markup=kb_after_order(client_lang))
            except Exception:
                pass
        else:  # new
            text_client = TEXT[client_lang]["client_new"].format(order_id=order_id)
            try:
                await call.bot.send_message(client_id, text_client)
            except Exception:
                pass

    await call.answer(f"✅ Статус: {st}")

# =========================
# ADMIN COMMANDS
# =========================
async def cmd_orders(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    rows = orders_list_all(limit=20)
    if not rows:
        await safe_answer(message, "Заказов нет.")
        return
    lines = ["📋 <b>Последние заказы</b>:"]
    for r in rows:
        (oid, uid, name, phone, city, item, status, pcode, pdisc, created_at) = r
        promo = f" • {pcode}(-{pdisc}%)" if pcode and pdisc else ""
        lines.append(f"#{oid} • {esc(name)} • {esc(phone)} • {esc(city)} • {esc(status)}{promo} • {esc(created_at)}")
    await safe_answer(message, "\n".join(lines))

async def cmd_status(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) != 3:
        await safe_answer(message, "Формат: /status <id> <new|processing|done>")
        return
    _, sid, st = parts
    if not sid.isdigit():
        await safe_answer(message, "ID должен быть числом.")
        return
    st = st.lower().strip()
    if st not in ("new", "processing", "done"):
        await safe_answer(message, "Статус только: new / processing / done")
        return
    order_set_status(int(sid), st)
    await safe_answer(message, f"✅ Статус заказа #{sid} обновлён: <b>{st}</b>")

# ✅ add post templates into queue: /addpost
async def cmd_addpost(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    txt = (message.text or "")
    payload = ""
    if txt.startswith("/addpost"):
        payload = txt.replace("/addpost", "", 1).strip()

    if payload:
        post_add("text", None, payload)
        await safe_answer(message, "✅ Заготовка (текст) добавлена в очередь.")
        return

    if message.photo:
        file_id = message.photo[-1].file_id
        cap = (message.caption or "").replace("/addpost", "", 1).strip()
        post_add("photo", file_id, cap)
        await safe_answer(message, "✅ Заготовка (фото) добавлена в очередь.")
        return

    if message.video:
        file_id = message.video.file_id
        cap = (message.caption or "").replace("/addpost", "", 1).strip()
        post_add("video", file_id, cap)
        await safe_answer(message, "✅ Заготовка (видео) добавлена в очередь.")
        return

    await safe_answer(
        message,
        "Формат:\n"
        "1) /addpost ТЕКСТ\n"
        "2) Отправь фото/видео с подписью, где в первой строке /addpost\n\n"
        "Пример:\n"
        "/addpost Новинка! Школьная форма 🔥\n"
        "Размеры 122–164"
    )

# =========================
# AUTOPOSTING (18:00 daily)
# =========================
async def post_to_channel(bot: Bot):
    if CHANNEL_ID == 0:
        return

    # posts in RU by default (you can change to "uz" if need)
    lang = "ru"
    cta = kb_post_cta(lang)

    post = post_pick_next()
    if not post:
        await bot.send_message(CHANNEL_ID, "⚠️ Нет заготовок для автопоста. Добавь через /addpost", reply_markup=cta)
        return

    media_type = post["media_type"]
    file_id = (post["file_id"] or "").strip()
    text = (post["text"] or "").strip()

    try:
        if media_type == "photo" and file_id:
            await bot.send_photo(chat_id=CHANNEL_ID, photo=file_id, caption=text[:1024] if text else None, reply_markup=cta)
        elif media_type == "video" and file_id:
            await bot.send_video(chat_id=CHANNEL_ID, video=file_id, caption=text[:1024] if text else None, reply_markup=cta)
        else:
            await bot.send_message(chat_id=CHANNEL_ID, text=text or "✨ ZARY & CO", reply_markup=cta)
    except Exception as e:
        print("post_to_channel error:", e)

async def autopost_scheduler(bot: Bot):
    last_date = None
    while True:
        dt = now_local()
        if dt.hour == POST_TIME.hour and dt.minute == POST_TIME.minute:
            d = dt.strftime("%Y-%m-%d")
            if last_date != d:
                await post_to_channel(bot)
                last_date = d
        await asyncio.sleep(20)

# =========================
# DAILY REPORT (manager)
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

async def daily_report_scheduler(bot: Bot):
    last_report_date = None
    while True:
        dt = now_local()
        if dt.hour == 21 and dt.minute == 5:
            d = dt.strftime("%Y-%m-%d")
            if last_report_date != d:
                try:
                    await send_daily_report(bot)
                    last_report_date = d
                except Exception as e:
                    print("daily report error:", e)
        await asyncio.sleep(30)

# =========================
# RENDER HEALTH SERVER
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
# CALLBACKS & HANDLERS
# =========================
async def admin_noop(call: CallbackQuery):
    await call.answer("OK")

async def size_mode_cb(call: CallbackQuery, state: FSMContext):
    await size_mode(call, state)

async def cart_clear_cb_wrap(call: CallbackQuery, state: FSMContext):
    await cart_clear_cb(call, state)

async def cart_checkout_cb_wrap(call: CallbackQuery, state: FSMContext):
    await cart_checkout_cb(call, state)

# =========================
# DISPATCHER
# =========================
def build_dp() -> Dispatcher:
    dp = Dispatcher()

    dp.message.register(cmd_start, CommandStart())
    dp.message.register(cmd_menu, Command("menu"))

    dp.callback_query.register(pick_lang, F.data.startswith("lang:"))
    dp.callback_query.register(back_menu, F.data == "back:menu")

    dp.callback_query.register(photo_section, F.data.startswith("photo:"))

    dp.callback_query.register(size_mode_cb, F.data.startswith("size:"))
    dp.message.register(size_age, Flow.size_age)
    dp.message.register(size_height, Flow.size_height)

    dp.callback_query.register(contact_leave, F.data == "contact:leave")
    dp.message.register(contact_phone, Flow.contact_phone)

    dp.callback_query.register(cart_add_manual, F.data == "cart:add_manual")
    dp.message.register(cart_add_item, Flow.cart_add_item)
    dp.callback_query.register(cart_clear_cb_wrap, F.data == "cart:clear")
    dp.callback_query.register(cart_checkout_cb_wrap, F.data == "cart:checkout")

    dp.message.register(order_name, Flow.order_name)
    dp.message.register(order_phone, Flow.order_phone)
    dp.message.register(order_city, Flow.order_city)
    dp.message.register(order_item, Flow.order_item)
    dp.message.register(order_size, Flow.order_size)
    dp.message.register(order_promo, Flow.order_promo)
    dp.message.register(order_comment, Flow.order_comment)

    # admin
    dp.message.register(cmd_addpost, Command("addpost"))
    dp.message.register(cmd_orders, Command("orders"))
    dp.message.register(cmd_status, Command("status"))

    dp.callback_query.register(admin_set_status, F.data.startswith("adm:status:"))
    dp.callback_query.register(admin_noop, F.data == "adm:noop")

    dp.message.register(menu_by_text, F.text)

    return dp

async def main():
    start_health_server()
    db_init()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dp()

    asyncio.create_task(autopost_scheduler(bot))
    asyncio.create_task(daily_report_scheduler(bot))

    print("✅ ZARY & CO assistant started (polling).")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
