"""
ZARY & CO — Retail Bot v3.0 (FULL)
✅ aiogram 3.x
✅ SQLite (bot.db)
✅ Admins only (ADMIN_ID_1..3)
✅ Channel notifications (CHANNEL_ID)
✅ Orders + Cart + Admin panel
✅ Excel export (manual)
✅ Render HTTP endpoints for Cron:
   - /cron/monthly?secret=...
   - /cron/daily?secret=...
✅ Weekly scheduled posts (Mon–Sat 18:00 Tashkent):
   Admin uploads photo/video+caption into bot → stored by Telegram file_id → bot posts to channel by schedule
✅ Sunday: reminder to admin to upload new weekly posts
"""

import os
import html
import asyncio
import json
from datetime import datetime, timedelta
from calendar import monthrange
from typing import Optional, Dict, List
from pathlib import Path
import sqlite3
import threading

# =========================
# ENV
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN не установлен!")

ADMIN_IDS: List[int] = []
for i in range(1, 4):
    v = os.getenv(f"ADMIN_ID_{i}", "").strip()
    if v and v.lstrip("-").isdigit():
        ADMIN_IDS.append(int(v))

if not ADMIN_IDS:
    old_admin = os.getenv("MANAGER_CHAT_ID", "").strip()
    if old_admin and old_admin.lstrip("-").isdigit():
        ADMIN_IDS.append(int(old_admin))

if not ADMIN_IDS:
    raise RuntimeError("❌ Нужен хотя бы один ADMIN_ID_1 (личный Telegram ID)")

PRIMARY_ADMIN = ADMIN_IDS[0]

_channel_id = os.getenv("CHANNEL_ID", "").strip()
CHANNEL_ID = int(_channel_id) if _channel_id and _channel_id.lstrip("-").isdigit() else None

CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "zaryco_official").strip().lstrip("@")
TG_CHANNEL_URL = f"https://t.me/{CHANNEL_USERNAME}"

PHONE = os.getenv("MANAGER_PHONE", "+998771202255").strip()
MANAGER_USERNAME = os.getenv("MANAGER_USERNAME", "zaryco_official").strip().lstrip("@")

INSTAGRAM_URL = "https://www.instagram.com/zary.co/"
YOUTUBE_URL = "https://www.youtube.com/@ZARYCOOFFICIAL"

PORT = int(os.getenv("PORT", "10000"))
DB_PATH = os.getenv("DB_PATH", "bot.db")

# Cron secret for /cron/*
CRON_SECRET = os.getenv("CRON_SECRET", "").strip()

# =========================
# DB
# =========================
class Database:
    def __init__(self):
        self.db_path = DB_PATH
        self._local = threading.local()
        self._init_db()

    def _get_conn(self):
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                lang TEXT DEFAULT 'ru',
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS carts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                product_name TEXT,
                qty INTEGER DEFAULT 1,
                size TEXT,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                name TEXT,
                phone TEXT,
                city TEXT,
                items TEXT,
                total_amount INTEGER DEFAULT 0,
                delivery_type TEXT,
                delivery_address TEXT,
                comment TEXT,
                status TEXT DEFAULT 'new',
                manager_seen INTEGER DEFAULT 0,
                manager_id INTEGER,
                created_at TEXT,
                reminded_at TEXT
            );

            CREATE TABLE IF NOT EXISTS monthly_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                year INTEGER,
                month INTEGER,
                sent_at TEXT,
                filename TEXT,
                total_orders INTEGER,
                total_amount INTEGER,
                status TEXT DEFAULT 'pending'
            );

            CREATE TABLE IF NOT EXISTS scheduled_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dow INTEGER,                 -- 1=Mon ... 6=Sat, 7=Sun
                media_type TEXT,             -- photo|video|none
                file_id TEXT,                -- Telegram file_id
                caption TEXT,
                week_key TEXT,               -- e.g. 2026-W09
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                posted_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
            CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
            CREATE INDEX IF NOT EXISTS idx_carts_user ON carts(user_id);
            CREATE INDEX IF NOT EXISTS idx_sched_week_dow ON scheduled_posts(week_key, dow);
        """)
        conn.commit()
        conn.close()

    # --- users
    def user_upsert(self, user_id: int, username: str, lang: str):
        conn = self._get_conn()
        cur = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,))
        if cur.fetchone():
            cur.execute("UPDATE users SET username=?, lang=? WHERE user_id=?", (username, lang, user_id))
        else:
            cur.execute("INSERT INTO users (user_id, username, lang, created_at) VALUES (?,?,?,?)",
                        (user_id, username, lang, now))
        conn.commit()

    def user_get(self, user_id: int) -> Optional[Dict]:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    # --- cart
    def cart_add(self, user_id: int, product_name: str, qty: int = 1, size: str = ""):
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("INSERT INTO carts (user_id, product_name, qty, size) VALUES (?,?,?,?)",
                    (user_id, product_name, qty, size))
        conn.commit()

    def cart_get(self, user_id: int) -> List[Dict]:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM carts WHERE user_id=? ORDER BY id DESC", (user_id,))
        return [dict(r) for r in cur.fetchall()]

    def cart_clear(self, user_id: int):
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM carts WHERE user_id=?", (user_id,))
        conn.commit()

    def cart_remove(self, cart_id: int):
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM carts WHERE id=?", (cart_id,))
        conn.commit()

    # --- orders
    def order_create(self, data: Dict) -> int:
        conn = self._get_conn()
        cur = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("""
            INSERT INTO orders (
                user_id, username, name, phone, city, items,
                total_amount, delivery_type, delivery_address,
                comment, status, created_at
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            data["user_id"], data.get("username", ""), data["name"],
            data["phone"], data["city"], data["items"],
            data.get("total_amount", 0),
            data.get("delivery_type", ""),
            data.get("delivery_address", ""),
            data.get("comment", ""),
            "new",
            now
        ))
        conn.commit()
        return cur.lastrowid

    def order_get(self, order_id: int) -> Optional[Dict]:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM orders WHERE id=?", (order_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def orders_get_by_status(self, status: str, limit: int = 50) -> List[Dict]:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM orders WHERE status=? ORDER BY created_at DESC LIMIT ?",
                    (status, limit))
        return [dict(r) for r in cur.fetchall()]

    def orders_get_user(self, user_id: int, limit: int = 10) -> List[Dict]:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT ?",
                    (user_id, limit))
        return [dict(r) for r in cur.fetchall()]

    def order_update_status(self, order_id: int, status: str, manager_id: int = None):
        conn = self._get_conn()
        cur = conn.cursor()
        if manager_id is not None:
            cur.execute("UPDATE orders SET status=?, manager_id=?, manager_seen=1 WHERE id=?",
                        (status, manager_id, order_id))
        else:
            cur.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
        conn.commit()

    def order_mark_seen(self, order_id: int, manager_id: int):
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("UPDATE orders SET manager_seen=1, manager_id=? WHERE id=?",
                    (manager_id, order_id))
        conn.commit()

    def orders_get_for_reminder(self) -> List[Dict]:
        conn = self._get_conn()
        cur = conn.cursor()
        cutoff = (datetime.now() - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("""
            SELECT * FROM orders
            WHERE status='new' AND manager_seen=0
              AND created_at < ?
              AND (reminded_at IS NULL OR reminded_at < ?)
            ORDER BY created_at DESC
        """, (cutoff, cutoff))
        return [dict(r) for r in cur.fetchall()]

    def order_update_reminded(self, order_id: int):
        conn = self._get_conn()
        cur = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("UPDATE orders SET reminded_at=? WHERE id=?", (now, order_id))
        conn.commit()

    def orders_get_monthly(self, year: int, month: int) -> List[Dict]:
        conn = self._get_conn()
        cur = conn.cursor()
        start = f"{year}-{month:02d}-01 00:00:00"
        last_day = monthrange(year, month)[1]
        end = f"{year}-{month:02d}-{last_day} 23:59:59"
        cur.execute("SELECT * FROM orders WHERE created_at BETWEEN ? AND ? ORDER BY id",
                    (start, end))
        return [dict(r) for r in cur.fetchall()]

    def report_mark_sent(self, year: int, month: int, filename: str, total_orders: int, total_amount: int):
        conn = self._get_conn()
        cur = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("""
            INSERT INTO monthly_reports (year, month, sent_at, filename, total_orders, total_amount, status)
            VALUES (?,?,?,?,?,?,?)
        """, (year, month, now, filename, total_orders, total_amount, "sent"))
        conn.commit()

    def report_is_sent(self, year: int, month: int) -> bool:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM monthly_reports WHERE year=? AND month=? AND status='sent'",
                    (year, month))
        return cur.fetchone() is not None

    def get_stats(self) -> Dict:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status='new' THEN 1 ELSE 0 END) as new,
                SUM(CASE WHEN status='processing' THEN 1 ELSE 0 END) as processing,
                SUM(CASE WHEN status='delivered' THEN 1 ELSE 0 END) as delivered,
                COUNT(DISTINCT user_id) as unique_users
            FROM orders
        """)
        row = cur.fetchone()
        return dict(row) if row else {"total": 0, "new": 0, "processing": 0, "delivered": 0, "unique_users": 0}

    # --- weekly scheduled posts
    def week_key_now(self, dt: datetime) -> str:
        iso = dt.isocalendar()  # year, week, weekday
        return f"{iso[0]}-W{iso[1]:02d}"

    def sched_add(self, dow: int, media_type: str, file_id: str, caption: str, week_key: str):
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO scheduled_posts (dow, media_type, file_id, caption, week_key)
            VALUES (?,?,?,?,?)
        """, (dow, media_type, file_id, caption, week_key))
        conn.commit()

    def sched_get_for_day(self, dow: int, week_key: str) -> Optional[Dict]:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM scheduled_posts
            WHERE dow=? AND week_key=? AND posted_at IS NULL
            ORDER BY id ASC
            LIMIT 1
        """, (dow, week_key))
        row = cur.fetchone()
        return dict(row) if row else None

    def sched_mark_posted(self, post_id: int):
        conn = self._get_conn()
        cur = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("UPDATE scheduled_posts SET posted_at=? WHERE id=?", (now, post_id))
        conn.commit()

    def sched_count_week(self, week_key: str) -> int:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as c FROM scheduled_posts WHERE week_key=?", (week_key,))
        r = cur.fetchone()
        return int(r["c"]) if r else 0

db = Database()

# =========================
# aiogram
# =========================
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)
from aiogram.types.input_file import FSInputFile

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

# =========================
# TEXTS
# =========================
TEXT = {
    "ru": {
        "welcome": "👋 Добро пожаловать в <b>ZARY & CO</b>!\n\n🧸 Детская одежда премиум качества\n📦 Доставка по Узбекистану 1-5 дней\n\nВыберите действие 👇",
        "menu": "📍 Главное меню",
        "catalog": "📸 <b>Каталог</b>\n\nВыберите категорию:",
        "price": "🧾 <b>Прайс-лист</b>\n\n👶 Мальчики — от 150 000 сум\n👧 Девочки — от 140 000 сум\n🧒 Унисекс — от 130 000 сум\n🎒 Школьная форма — от 200 000 сум\n\n✅ Нажмите «Заказ» для оформления",
        "size": "📏 <b>Подбор размера</b>\n\nВыберите способ:",
        "size_age": "Введите возраст (1-15 лет):\nПример: 7",
        "size_height": "Введите рост в см:\nПример: 125",
        "size_result": "📏 Рекомендуемый размер: <b>{size}</b>",
        "cart": "🛒 <b>Корзина</b>\n\n{items}\n\n💰 Итого: <b>{total} сум</b>",
        "cart_empty": "🛒 Корзина пуста\n\nДобавьте товары из каталога",
        "cart_added": "✅ Добавлено в корзину",
        "delivery": "🚚 <b>Доставка</b>\n\n1️⃣ <b>B2B Почта</b> — 2-5 дней, весь Узбекистан\n2️⃣ <b>Яндекс Курьер</b> — 1-3 дня, крупные города\n3️⃣ <b>Яндекс ПВЗ</b> — 1-3 дня, пункты выдачи\n\n💰 Стоимость: от 15 000 сум (зависит от города)",
        "faq": "❓ <b>FAQ</b>\n\n<b>Доставка?</b>\n— По всему Узбекистану, 1-5 дней\n\n<b>Оплата?</b>\n— Наличными или переводом\n\n<b>Возврат?</b>\n— 14 дней при сохранении вида\n\n<b>Размеры?</b>\n— Используйте подбор в боте",
        "contact": "📞 <b>Связаться</b>\n\n☎️ {phone}\n⏰ Пн-Пт: 09:00-21:00\n📱 @{username}\n\nИли оставьте номер — мы перезвоним",
        "order_start": "📝 <b>Оформление заказа</b>\n\nВведите ваше имя:",
        "order_phone": "📱 Отправьте номер телефона:",
        "order_city": "🏙 Введите город:",
        "order_delivery": "🚚 Выберите способ доставки:",
        "order_address": "📍 Введите адрес доставки:",
        "order_comment": "💬 Комментарий (необязательно):",
        "order_confirm": "📝 <b>Проверьте заказ:</b>\n\n👤 {name}\n📱 {phone}\n🏙 {city}\n🚚 {delivery}\n📍 {address}\n💬 {comment}\n\n🛒 Товары:\n{items}\n\n💰 Итого: {total} сум",
        "order_success": "✅ Заказ #{order_id} принят!\n\nМенеджер свяжется в течение 15 минут\n⏰ Рабочее время: 09:00-21:00",
        "history": "📜 <b>История заказов</b>\n\n{orders}",
        "history_empty": "📜 У вас пока нет заказов",
        "admin_menu": "🛠 <b>Админ панель</b>\n\nВыберите действие:",
        "admin_stats": "📊 <b>Статистика</b>\n\n📦 Всего: {total}\n🆕 Новых: {new}\n⚙️ В обработке: {processing}\n✅ Доставлено: {delivered}\n👥 Клиентов: {unique_users}",
        "cancelled": "❌ Отменено",
    },
    "uz": {
        "welcome": "👋 <b>ZARY & CO</b> ga xush kelibsiz!\n\n🧸 Bolalar kiyimi premium sifat\n📦 O'zbekiston bo'ylab yetkazib berish 1-5 kun\n\nAmalni tanlang 👇",
        "menu": "📍 Asosiy menyu",
        "catalog": "📸 <b>Katalog</b>\n\nKategoriyani tanlang:",
        "price": "🧾 <b>Narxlar</b>\n\n👶 O'g'il bolalar — 150 000 so'mdan\n👧 Qiz bolalar — 140 000 so'mdan\n🧒 Uniseks — 130 000 so'mdan\n🎒 Maktab formasi — 200 000 so'mdan\n\n✅ «Buyurtma» ni bosing",
        "size": "📏 <b>O'lcham tanlash</b>\n\nUsulni tanlang:",
        "size_age": "Yoshini kiriting (1-15 yosh):\nMisol: 7",
        "size_height": "Bo'yni sm da kiriting:\nMisol: 125",
        "size_result": "📏 Tavsiya etilgan o'lcham: <b>{size}</b>",
        "cart": "🛒 <b>Savat</b>\n\n{items}\n\n💰 Jami: <b>{total} so'm</b>",
        "cart_empty": "🛒 Savat bo'sh\n\nKatalogdan mahsulot qo'shing",
        "cart_added": "✅ Savatga qo'shildi",
        "delivery": "🚚 <b>Yetkazib berish</b>\n\n1️⃣ <b>B2B Pochta</b> — 2-5 kun, butun O'zbekiston\n2️⃣ <b>Yandex Kuryer</b> — 1-3 kun, yirik shaharlarga\n3️⃣ <b>Yandex PVZ</b> — 1-3 kun, topshirish punktlari\n\n💰 Narxi: 15 000 so'mdan (shahar qarab)",
        "faq": "❓ <b>FAQ</b>\n\n<b>Yetkazib berish?</b>\n— Butun O'zbekiston, 1-5 kun\n\n<b>To'lov?</b>\n— Naqd yoki o'tkazma\n\n<b>Qaytarish?</b>\n— 14 kun ichida tovar ko'rinishi saqlangan bo'lsa\n\n<b>O'lchamlar?</b>\n— Botdagi o'lcham tanlashdan foydalaning",
        "contact": "📞 <b>Aloqa</b>\n\n☎️ {phone}\n⏰ Du-Sha: 09:00-21:00\n📱 @{username}\n\nYoki raqam qoldiring — qo'ng'iroq qilamiz",
        "order_start": "📝 <b>Buyurtma berish</b>\n\nIsmingizni kiriting:",
        "order_phone": "📱 Telefon raqamingizni yuboring:",
        "order_city": "🏙 Shaharni kiriting:",
        "order_delivery": "🚚 Yetkazib berish usulini tanlang:",
        "order_address": "📍 Yetkazib berish manzilini kiriting:",
        "order_comment": "💬 Izoh (ixtiyoriy):",
        "order_confirm": "📝 <b>Buyurtmani tekshiring:</b>\n\n👤 {name}\n📱 {phone}\n🏙 {city}\n🚚 {delivery}\n📍 {address}\n💬 {comment}\n\n🛒 Tovarlar:\n{items}\n\n💰 Jami: {total} so'm",
        "order_success": "✅ Buyurtma #{order_id} qabul qilindi!\n\nMenejer 15 daqiqa ichida bog'lanadi\n⏰ Ish vaqti: 09:00-21:00",
        "history": "📜 <b>Buyurtmalar tarixi</b>\n\n{orders}",
        "history_empty": "📜 Hozircha buyurtmalar yo'q",
        "admin_menu": "🛠 <b>Admin paneli</b>\n\nAmalni tanlang:",
        "admin_stats": "📊 <b>Statistika</b>\n\n📦 Jami: {total}\n🆕 Yangi: {new}\n⚙️ Ishlanmoqda: {processing}\n✅ Yetkazildi: {delivered}\n👥 Mijozlar: {unique_users}",
        "cancelled": "❌ Bekor qilindi",
    }
}

# =========================
# KEYBOARDS
# =========================
def kb_main(lang: str, is_admin_flag: bool = False) -> ReplyKeyboardMarkup:
    if lang == "uz":
        rows = [
            [KeyboardButton(text="📸 Katalog"), KeyboardButton(text="🧾 Narxlar")],
            [KeyboardButton(text="📏 O'lcham"), KeyboardButton(text="🛒 Savat")],
            [KeyboardButton(text="🚚 Yetkazib berish"), KeyboardButton(text="❓ FAQ")],
            [KeyboardButton(text="📞 Aloqa"), KeyboardButton(text="✅ Buyurtma")],
            [KeyboardButton(text="📜 Buyurtmalar"), KeyboardButton(text="🌐 Til")],
        ]
    else:
        rows = [
            [KeyboardButton(text="📸 Каталог"), KeyboardButton(text="🧾 Прайс")],
            [KeyboardButton(text="📏 Размер"), KeyboardButton(text="🛒 Корзина")],
            [KeyboardButton(text="🚚 Доставка"), KeyboardButton(text="❓ FAQ")],
            [KeyboardButton(text="📞 Связаться"), KeyboardButton(text="✅ Заказ")],
            [KeyboardButton(text="📜 История"), KeyboardButton(text="🌐 Язык")],
        ]
    if is_admin_flag:
        rows.append([KeyboardButton(text="🛠 Админ" if lang == "ru" else "🛠 Admin")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def kb_catalog(lang: str) -> InlineKeyboardMarkup:
    cats = [
        [("👶 Мальчики", "cat:boys"), ("👧 Девочки", "cat:girls")],
        [("🧒 Унисекс", "cat:unisex"), ("🎒 Школа", "cat:school")],
        [("🔥 Новинки", "cat:new"), ("💰 Акции", "cat:sale")],
    ]
    buttons = []
    for row in cats:
        buttons.append([
            InlineKeyboardButton(text=row[0][0], callback_data=row[0][1]),
            InlineKeyboardButton(text=row[1][0], callback_data=row[1][1])
        ])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад" if lang == "ru" else "⬅️ Orqaga", callback_data="back:menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_size(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👶 По возрасту" if lang == "ru" else "👶 Yosh bo'yicha", callback_data="size:age")],
        [InlineKeyboardButton(text="📏 По росту" if lang == "ru" else "📏 Bo'y bo'yicha", callback_data="size:height")],
        [InlineKeyboardButton(text="⬅️ Назад" if lang == "ru" else "⬅️ Orqaga", callback_data="back:menu")],
    ])

def kb_delivery(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 B2B Почта", callback_data="delivery:b2b")],
        [InlineKeyboardButton(text="🚚 Яндекс Курьер", callback_data="delivery:yandex_courier")],
        [InlineKeyboardButton(text="🏪 Яндекс ПВЗ", callback_data="delivery:yandex_pvz")],
        [InlineKeyboardButton(text="⬅️ Назад" if lang == "ru" else "⬅️ Orqaga", callback_data="back:menu")],
    ])

def kb_cart(items: List[Dict], lang: str) -> InlineKeyboardMarkup:
    buttons = []
    for item in items:
        name = item["product_name"][:20]
        btn_text = f"❌ {name} ({item['qty']}x)"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"cart_remove:{item['id']}")])

    buttons.extend([
        [InlineKeyboardButton(text="✅ Оформить" if lang == "ru" else "✅ Rasmiylashtirish", callback_data="cart:checkout")],
        [InlineKeyboardButton(text="🧹 Очистить" if lang == "ru" else "🧹 Tozalash", callback_data="cart:clear")],
        [InlineKeyboardButton(text="⬅️ Назад" if lang == "ru" else "⬅️ Orqaga", callback_data="back:menu")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_order_confirm(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить" if lang == "ru" else "✅ Tasdiqlash", callback_data="order:confirm")],
        [InlineKeyboardButton(text="❌ Отмена" if lang == "ru" else "❌ Bekor", callback_data="order:cancel")],
    ])

def kb_admin(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Новые заказы" if lang == "ru" else "📋 Yangi buyurtmalar", callback_data="admin:new")],
        [InlineKeyboardButton(text="⚙️ В обработке" if lang == "ru" else "⚙️ Ishlanmoqda", callback_data="admin:processing")],
        [InlineKeyboardButton(text="📊 Статистика" if lang == "ru" else "📊 Statistika", callback_data="admin:stats")],
        [InlineKeyboardButton(text="📤 Excel отчет" if lang == "ru" else "📤 Excel hisobot", callback_data="admin:export")],
        [InlineKeyboardButton(text="📰 Посты недели" if lang == "ru" else "📰 Haftalik postlar", callback_data="admin:posts")],
        [InlineKeyboardButton(text="⬅️ Назад" if lang == "ru" else "⬅️ Orqaga", callback_data="back:menu")],
    ])

def kb_admin_order(order_id: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👁 Просмотрено", callback_data=f"order_seen:{order_id}"),
            InlineKeyboardButton(text="⚙️ В работу", callback_data=f"order_process:{order_id}")
        ],
        [
            InlineKeyboardButton(text="🚚 Отправлен", callback_data=f"order_ship:{order_id}"),
            InlineKeyboardButton(text="✅ Доставлен", callback_data=f"order_deliver:{order_id}")
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"order_cancel:{order_id}")],
    ])

def kb_contact(lang: str) -> ReplyKeyboardMarkup:
    if lang == "uz":
        btn = KeyboardButton(text="📱 Raqamni yuborish", request_contact=True)
        cancel = KeyboardButton(text="❌ Bekor qilish")
    else:
        btn = KeyboardButton(text="📱 Отправить номер", request_contact=True)
        cancel = KeyboardButton(text="❌ Отмена")
    return ReplyKeyboardMarkup(keyboard=[[btn], [cancel]], resize_keyboard=True, one_time_keyboard=True)

def kb_channel(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📣 Канал" if lang == "ru" else "📣 Kanal", url=TG_CHANNEL_URL)],
        [InlineKeyboardButton(text="⬅️ Меню" if lang == "ru" else "⬅️ Menyu", callback_data="back:menu")],
    ])

def kb_dow(lang: str) -> InlineKeyboardMarkup:
    if lang == "uz":
        names = [(1, "Dushanba"), (2, "Seshanba"), (3, "Chorshanba"), (4, "Payshanba"), (5, "Juma"), (6, "Shanba")]
        title = "Kun tanlang (Du–Sha):"
    else:
        names = [(1, "Понедельник"), (2, "Вторник"), (3, "Среда"), (4, "Четверг"), (5, "Пятница"), (6, "Суббота")]
        title = "Выберите день (Пн–Сб):"

    rows = []
    for i in range(0, 6, 2):
        a = names[i]
        b = names[i + 1]
        rows.append([
            InlineKeyboardButton(text=a[1], callback_data=f"dow:{a[0]}"),
            InlineKeyboardButton(text=b[1], callback_data=f"dow:{b[0]}")
        ])
    rows.append([InlineKeyboardButton(text="⬅️ Назад" if lang == "ru" else "⬅️ Orqaga", callback_data="admin:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# =========================
# HELPERS
# =========================
def esc(s: str) -> str:
    return html.escape(str(s) if s else "")

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def format_price(price: int) -> str:
    return f"{int(price):,}".replace(",", " ")

def size_by_age(age: int) -> str:
    mapping = {1: "86", 2: "92", 3: "98", 4: "104", 5: "110", 6: "116",
               7: "122", 8: "128", 9: "134", 10: "140", 11: "146",
               12: "152", 13: "158", 14: "164", 15: "164"}
    return mapping.get(age, "122-128")

def size_by_height(height: int) -> str:
    sizes = [86, 92, 98, 104, 110, 116, 122, 128, 134, 140, 146, 152, 158, 164]
    closest = min(sizes, key=lambda x: abs(x - height))
    return str(closest)

def prev_month(dt: datetime) -> tuple[int, int]:
    first = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    prev_last = first - timedelta(days=1)
    return prev_last.year, prev_last.month

def cron_allowed(secret: str) -> bool:
    return bool(CRON_SECRET) and secret == CRON_SECRET

# =========================
# FSM
# =========================
class States(StatesGroup):
    size_age = State()
    size_height = State()
    order_name = State()
    order_phone = State()
    order_city = State()
    order_delivery = State()
    order_address = State()
    order_comment = State()
    cart_add = State()

    # weekly posts
    admin_post_dow = State()
    admin_post_media = State()

# =========================
# BOT INIT
# =========================
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# =========================
# HANDLERS
# =========================
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username or ""
    lang = "uz" if (message.from_user.language_code == "uz") else "ru"
    db.user_upsert(user_id, username, lang)
    await message.answer(TEXT[lang]["welcome"], reply_markup=kb_main(lang, is_admin(user_id)))
    await message.answer(TEXT[lang]["menu"], reply_markup=kb_main(lang, is_admin(user_id)))

@dp.message(F.text.in_(["🌐 Язык", "🌐 Til"]))
async def cmd_lang(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = "uz" if user and user.get("lang") == "ru" else "ru"
    db.user_upsert(message.from_user.id, message.from_user.username or "", lang)
    await message.answer(TEXT[lang]["welcome"], reply_markup=kb_main(lang, is_admin(message.from_user.id)))

@dp.callback_query(F.data == "back:menu")
async def back_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    user = db.user_get(call.from_user.id)
    lang = user["lang"] if user else "ru"
    await call.message.answer(TEXT[lang]["menu"], reply_markup=kb_main(lang, is_admin(call.from_user.id)))
    await call.answer()

# Catalog
@dp.message(F.text.in_(["📸 Каталог", "📸 Katalog"]))
async def cmd_catalog(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"
    await message.answer(TEXT[lang]["catalog"], reply_markup=kb_catalog(lang))

@dp.callback_query(F.data.startswith("cat:"))
async def cat_select(call: CallbackQuery, state: FSMContext):
    user = db.user_get(call.from_user.id)
    lang = user["lang"] if user else "ru"
    cat = call.data.split(":")[1]
    await call.message.answer(
        f"📸 {cat.upper()}\n\nСмотрите полный каталог в канале 👇" if lang == "ru"
        else f"📸 {cat.upper()}\n\nTo'liq katalog kanalimizda 👇",
        reply_markup=kb_channel(lang)
    )
    await call.answer()

# Price
@dp.message(F.text.in_(["🧾 Прайс", "🧾 Narxlar"]))
async def cmd_price(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"
    await message.answer(TEXT[lang]["price"], reply_markup=kb_main(lang, is_admin(message.from_user.id)))

# Size
@dp.message(F.text.in_(["📏 Размер", "📏 O'lcham"]))
async def cmd_size(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"
    await message.answer(TEXT[lang]["size"], reply_markup=kb_size(lang))

@dp.callback_query(F.data.startswith("size:"))
async def size_select(call: CallbackQuery, state: FSMContext):
    user = db.user_get(call.from_user.id)
    lang = user["lang"] if user else "ru"
    mode = call.data.split(":")[1]
    if mode == "age":
        await state.set_state(States.size_age)
        await call.message.answer(TEXT[lang]["size_age"])
    else:
        await state.set_state(States.size_height)
        await call.message.answer(TEXT[lang]["size_height"])
    await call.answer()

@dp.message(States.size_age)
async def size_age_input(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"
    if not message.text or not message.text.isdigit():
        await message.answer(TEXT[lang]["size_age"])
        return
    age = int(message.text)
    if not (1 <= age <= 15):
        await message.answer(TEXT[lang]["size_age"])
        return
    size = size_by_age(age)
    await message.answer(TEXT[lang]["size_result"].format(size=size), reply_markup=kb_main(lang, is_admin(message.from_user.id)))
    await state.clear()

@dp.message(States.size_height)
async def size_height_input(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"
    if not message.text or not message.text.isdigit():
        await message.answer(TEXT[lang]["size_height"])
        return
    height = int(message.text)
    if not (50 <= height <= 180):
        await message.answer(TEXT[lang]["size_height"])
        return
    size = size_by_height(height)
    await message.answer(TEXT[lang]["size_result"].format(size=size), reply_markup=kb_main(lang, is_admin(message.from_user.id)))
    await state.clear()

# Cart
@dp.message(F.text.in_(["🛒 Корзина", "🛒 Savat"]))
async def cmd_cart(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"

    items = db.cart_get(message.from_user.id)
    if not items:
        await message.answer(TEXT[lang]["cart_empty"], reply_markup=kb_main(lang, is_admin(message.from_user.id)))
        return

    items_text = "\n".join([f"• {esc(it['product_name'])} x{it['qty']}" for it in items])
    total = sum(it["qty"] * 150000 for it in items)  # заглушка цены

    text = TEXT[lang]["cart"].format(items=items_text, total=format_price(total))
    await message.answer(text, reply_markup=kb_cart(items, lang))

@dp.callback_query(F.data.startswith("cart_remove:"))
async def cart_remove(call: CallbackQuery, state: FSMContext):
    cart_id = int(call.data.split(":")[1])
    db.cart_remove(cart_id)

    user = db.user_get(call.from_user.id)
    lang = user["lang"] if user else "ru"

    items = db.cart_get(call.from_user.id)
    if not items:
        await call.message.edit_text(TEXT[lang]["cart_empty"])
    else:
        items_text = "\n".join([f"• {esc(it['product_name'])} x{it['qty']}" for it in items])
        total = sum(it["qty"] * 150000 for it in items)
        text = TEXT[lang]["cart"].format(items=items_text, total=format_price(total))
        await call.message.edit_text(text, reply_markup=kb_cart(items, lang))

    await call.answer("❌ Удалено" if lang == "ru" else "❌ O'chirildi")

@dp.callback_query(F.data == "cart:clear")
async def cart_clear(call: CallbackQuery, state: FSMContext):
    db.cart_clear(call.from_user.id)
    user = db.user_get(call.from_user.id)
    lang = user["lang"] if user else "ru"
    await call.message.edit_text(TEXT[lang]["cart_empty"])
    await call.answer()

@dp.callback_query(F.data == "cart:checkout")
async def cart_checkout(call: CallbackQuery, state: FSMContext):
    user = db.user_get(call.from_user.id)
    lang = user["lang"] if user else "ru"

    items = db.cart_get(call.from_user.id)
    if not items:
        await call.answer("Корзина пуста!" if lang == "ru" else "Savat bo'sh!")
        return

    await state.set_state(States.order_name)
    await call.message.answer(TEXT[lang]["order_start"])
    await call.answer()

# Delivery + FAQ + Contact
@dp.message(F.text.in_(["🚚 Доставка", "🚚 Yetkazib berish"]))
async def cmd_delivery(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"
    await message.answer(TEXT[lang]["delivery"], reply_markup=kb_delivery(lang))

@dp.message(F.text.in_(["❓ FAQ"]))
async def cmd_faq(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"
    await message.answer(TEXT[lang]["faq"], reply_markup=kb_main(lang, is_admin(message.from_user.id)))

@dp.message(F.text.in_(["📞 Связаться", "📞 Aloqa"]))
async def cmd_contact(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"
    text = TEXT[lang]["contact"].format(phone=PHONE, username=MANAGER_USERNAME or CHANNEL_USERNAME)
    await message.answer(text, reply_markup=kb_contact(lang))

# Order flow
@dp.message(F.text.in_(["✅ Заказ", "✅ Buyurtma"]))
async def cmd_order(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"

    items = db.cart_get(message.from_user.id)
    if not items:
        await state.set_state(States.cart_add)
        await message.answer("📝 Введите название товара:" if lang == "ru" else "📝 Mahsulot nomini kiriting:")
        return

    await state.set_state(States.order_name)
    await message.answer(TEXT[lang]["order_start"])

@dp.message(States.cart_add)
async def cart_add_manual(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"
    if not message.text:
        await message.answer("Введите название товара:" if lang == "ru" else "Mahsulot nomini kiriting:")
        return
    db.cart_add(message.from_user.id, message.text, 1)
    await message.answer(TEXT[lang]["cart_added"], reply_markup=kb_main(lang, is_admin(message.from_user.id)))
    await state.clear()

@dp.message(States.order_name)
async def order_name(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"
    if not message.text:
        await message.answer(TEXT[lang]["order_start"])
        return
    await state.update_data(name=message.text)
    await state.set_state(States.order_phone)
    await message.answer(TEXT[lang]["order_phone"], reply_markup=kb_contact(lang))

@dp.message(States.order_phone)
async def order_phone(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"
    phone = message.contact.phone_number if message.contact else message.text
    if not phone:
        await message.answer(TEXT[lang]["order_phone"], reply_markup=kb_contact(lang))
        return
    await state.update_data(phone=phone)
    await state.set_state(States.order_city)
    await message.answer(TEXT[lang]["order_city"], reply_markup=kb_main(lang, is_admin(message.from_user.id)))

@dp.message(States.order_city)
async def order_city(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"
    if not message.text:
        await message.answer(TEXT[lang]["order_city"])
        return
    await state.update_data(city=message.text)
    await state.set_state(States.order_delivery)
    await message.answer(TEXT[lang]["order_delivery"], reply_markup=kb_delivery(lang))

@dp.callback_query(F.data.startswith("delivery:"))
async def order_delivery(call: CallbackQuery, state: FSMContext):
    delivery_type = call.data.split(":")[1]
    await state.update_data(delivery=delivery_type)

    user = db.user_get(call.from_user.id)
    lang = user["lang"] if user else "ru"
    delivery_names = {
        "b2b": "B2B Почта" if lang == "ru" else "B2B Pochta",
        "yandex_courier": "Яндекс Курьер" if lang == "ru" else "Yandex Kuryer",
        "yandex_pvz": "Яндекс ПВЗ" if lang == "ru" else "Yandex PVZ"
    }
    await state.update_data(delivery_name=delivery_names.get(delivery_type, delivery_type))

    await state.set_state(States.order_address)
    await call.message.answer(TEXT[lang]["order_address"])
    await call.answer()

@dp.message(States.order_address)
async def order_address(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"
    if not message.text:
        await message.answer(TEXT[lang]["order_address"])
        return
    await state.update_data(address=message.text)
    await state.set_state(States.order_comment)
    await message.answer(TEXT[lang]["order_comment"], reply_markup=kb_main(lang, is_admin(message.from_user.id)))

@dp.message(States.order_comment)
async def order_comment(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"

    comment = message.text or ""
    if comment in ["📜 История", "📜 Buyurtmalar", "🛠 Админ", "🛠 Admin"]:
        comment = ""
    await state.update_data(comment=(comment.strip() or "—"))

    data = await state.get_data()
    items = db.cart_get(message.from_user.id)

    items_text = "\n".join([f"• {esc(it['product_name'])} x{it['qty']}" for it in items])
    total = sum(it["qty"] * 150000 for it in items)

    await state.update_data(
        total=total,
        items_json=json.dumps([{"name": it["product_name"], "qty": it["qty"]} for it in items], ensure_ascii=False)
    )

    text = TEXT[lang]["order_confirm"].format(
        name=esc(data["name"]),
        phone=esc(data["phone"]),
        city=esc(data["city"]),
        delivery=esc(data.get("delivery_name", "—")),
        address=esc(data["address"]),
        comment=esc(data["comment"]),
        items=items_text,
        total=format_price(total)
    )
    await message.answer(text, reply_markup=kb_order_confirm(lang))

@dp.callback_query(F.data == "order:confirm")
async def order_confirm(call: CallbackQuery, state: FSMContext):
    user = db.user_get(call.from_user.id)
    lang = user["lang"] if user else "ru"
    data = await state.get_data()

    order_data = {
        "user_id": call.from_user.id,
        "username": call.from_user.username or "",
        "name": data["name"],
        "phone": data["phone"],
        "city": data["city"],
        "items": data["items_json"],
        "total_amount": data["total"],
        "delivery_type": data.get("delivery", ""),
        "delivery_address": data["address"],
        "comment": data["comment"],
    }

    order_id = db.order_create(order_data)

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🆕 Новый заказ #{order_id}\n\n"
                f"👤 {esc(data['name'])}\n"
                f"📱 {esc(data['phone'])}\n"
                f"🏙 {esc(data['city'])}\n"
                f"💰 {format_price(data['total'])} сум",
                reply_markup=kb_admin_order(order_id, "ru")
            )
        except Exception as e:
            print(f"Failed to notify admin {admin_id}: {e}")

    if CHANNEL_ID:
        try:
            await bot.send_message(
                CHANNEL_ID,
                f"🆕 Новый заказ #{order_id}\n"
                f"👤 {esc(data['name'])}\n"
                f"📱 {esc(data['phone'])}\n"
                f"🏙 {esc(data['city'])}\n"
                f"💰 {format_price(data['total'])} сум"
            )
        except Exception as e:
            print(f"Failed to send to channel {CHANNEL_ID}: {e}")

    db.cart_clear(call.from_user.id)
    await state.clear()

    await call.message.answer(TEXT[lang]["order_success"].format(order_id=order_id),
                              reply_markup=kb_main(lang, is_admin(call.from_user.id)))
    await call.answer()

@dp.callback_query(F.data == "order:cancel")
async def order_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    user = db.user_get(call.from_user.id)
    lang = user["lang"] if user else "ru"
    await call.message.answer(TEXT[lang]["cancelled"], reply_markup=kb_main(lang, is_admin(call.from_user.id)))
    await call.answer()

# History
@dp.message(F.text.in_(["📜 История", "📜 Buyurtmalar"]))
async def cmd_history(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"
    orders = db.orders_get_user(message.from_user.id)
    if not orders:
        await message.answer(TEXT[lang]["history_empty"], reply_markup=kb_main(lang, is_admin(message.from_user.id)))
        return
    lines = []
    for o in orders[:5]:
        status_icon = {"new": "🆕", "processing": "⚙️", "shipped": "🚚", "delivered": "✅", "cancelled": "❌"}.get(o["status"], "❓")
        lines.append(f"{status_icon} #{o['id']} • {format_price(o['total_amount'])} сум • {o['created_at'][:10]}")
    await message.answer(TEXT[lang]["history"].format(orders="\n".join(lines)),
                         reply_markup=kb_main(lang, is_admin(message.from_user.id)))

# Admin panel
@dp.message(F.text.in_(["🛠 Админ", "🛠 Admin"]))
async def cmd_admin(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"
    await message.answer(TEXT[lang]["admin_menu"], reply_markup=kb_admin(lang))

@dp.callback_query(F.data == "admin:back")
async def admin_back(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.clear()
    user = db.user_get(call.from_user.id)
    lang = user["lang"] if user else "ru"
    await call.message.answer(TEXT[lang]["admin_menu"], reply_markup=kb_admin(lang))
    await call.answer()

@dp.callback_query(F.data.startswith("admin:"))
async def admin_action(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Access denied")
        return

    action = call.data.split(":")[1]
    user = db.user_get(call.from_user.id)
    lang = user["lang"] if user else "ru"

    if action == "stats":
        stats = db.get_stats()
        await call.message.answer(TEXT[lang]["admin_stats"].format(**stats), reply_markup=kb_admin(lang))

    elif action == "new":
        orders = db.orders_get_by_status("new")
        if not orders:
            await call.message.answer("Нет новых заказов" if lang == "ru" else "Yangi buyurtmalar yo'q")
        else:
            for order in orders[:5]:
                items = json.loads(order["items"]) if order.get("items") else []
                items_text = ", ".join([f"{it.get('name','')} x{it.get('qty',1)}" for it in items[:3]])
                text = (
                    f"🆕 Заказ #{order['id']}\n"
                    f"👤 {esc(order['name'])}\n"
                    f"📱 {esc(order['phone'])}\n"
                    f"🏙 {esc(order['city'])}\n"
                    f"🛒 {esc(items_text)}\n"
                    f"💰 {format_price(order['total_amount'])} сум"
                )
                await call.message.answer(text, reply_markup=kb_admin_order(order["id"], lang))

    elif action == "processing":
        orders = db.orders_get_by_status("processing")
        await call.message.answer(
            (f"В обработке: {len(orders)} заказов") if lang == "ru" else (f"Ishlanmoqda: {len(orders)} ta")
        )

    elif action == "export":
        await generate_monthly_report(call.message, lang)

    elif action == "posts":
        # Start weekly posts flow
        await state.set_state(States.admin_post_dow)
        await call.message.answer("Выберите день публикации (Пн–Сб):" if lang == "ru" else "Kun tanlang (Du–Sha):",
                                  reply_markup=kb_dow(lang))

    await call.answer()

# Admin: choose day-of-week
@dp.callback_query(F.data.startswith("dow:"))
async def admin_choose_dow(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    user = db.user_get(call.from_user.id)
    lang = user["lang"] if user else "ru"
    dow = int(call.data.split(":")[1])  # 1..6
    await state.update_data(post_dow=dow)
    await state.set_state(States.admin_post_media)
    await call.message.answer(
        "Теперь отправьте ОДНО сообщение: фото/видео + описание (caption)."
        if lang == "ru" else
        "Endi BITTA xabar yuboring: foto/video + matn (caption)."
    )
    await call.answer()

# Admin: receive media+caption
@dp.message(States.admin_post_media)
async def admin_receive_week_post(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"

    data = await state.get_data()
    dow = int(data.get("post_dow", 0))
    if dow not in (1, 2, 3, 4, 5, 6):
        await state.clear()
        await message.answer("Сначала выберите день." if lang == "ru" else "Avval kunni tanlang.")
        return

    caption = (message.caption or message.text or "").strip()
    if not caption:
        await message.answer("⚠️ Добавьте описание (текст) к фото/видео." if lang == "ru" else "⚠️ Matn (izoh) qo'shing.")
        return

    media_type = "none"
    file_id = ""

    if message.photo:
        media_type = "photo"
        file_id = message.photo[-1].file_id
    elif message.video:
        media_type = "video"
        file_id = message.video.file_id
    else:
        media_type = "none"
        file_id = ""

    week_key = db.week_key_now(datetime.now())
    db.sched_add(dow=dow, media_type=media_type, file_id=file_id, caption=caption, week_key=week_key)
    cnt = db.sched_count_week(week_key)

    await message.answer(
        (f"✅ Добавлено в план недели: <b>{week_key}</b>\n"
         f"📌 День: {dow} (1=Пн ... 6=Сб)\n"
         f"🧾 Сейчас постов в этой неделе: <b>{cnt}</b>\n\n"
         "Чтобы добавить ещё — снова нажми: 🛠 Админ → 📰 Посты недели.")
        if lang == "ru" else
        (f"✅ Haftalik reja: <b>{week_key}</b>\n"
         f"📌 Kun: {dow} (1=Du ... 6=Sha)\n"
         f"🧾 Postlar soni: <b>{cnt}</b>\n\n"
         "Yana qo‘shish uchun: 🛠 Admin → 📰 Haftalik postlar.")
    )
    await state.clear()

# Order status buttons
@dp.callback_query(F.data.startswith("order_seen:"))
async def order_seen(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    order_id = int(call.data.split(":")[1])
    db.order_mark_seen(order_id, call.from_user.id)
    await call.answer("✅ Просмотрено")

@dp.callback_query(F.data.startswith("order_process:"))
async def order_process(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    order_id = int(call.data.split(":")[1])
    db.order_update_status(order_id, "processing", call.from_user.id)

    order = db.order_get(order_id)
    if order:
        user_row = db.user_get(order["user_id"])
        lang = user_row["lang"] if user_row else "ru"
        try:
            await bot.send_message(
                order["user_id"],
                ("⚙️ Заказ #{0} в обработке!\nМенеджер скоро свяжется.".format(order_id))
                if lang == "ru"
                else ("⚙️ Buyurtma #{0} ishlanmoqda!\nMenejer tez orada bog'lanadi.".format(order_id)),
                reply_markup=kb_main(lang, is_admin(order["user_id"]))
            )
        except Exception as e:
            print(f"Failed to notify user: {e}")

    await call.answer("✅ В работе!")

@dp.callback_query(F.data.startswith("order_ship:"))
async def order_ship(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    order_id = int(call.data.split(":")[1])
    db.order_update_status(order_id, "shipped", call.from_user.id)
    await call.answer("✅ Отправлен!")

@dp.callback_query(F.data.startswith("order_deliver:"))
async def order_deliver(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    order_id = int(call.data.split(":")[1])
    db.order_update_status(order_id, "delivered", call.from_user.id)
    await call.answer("✅ Доставлен!")

@dp.callback_query(F.data.startswith("order_cancel:"))
async def order_cancel_admin(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    order_id = int(call.data.split(":")[1])
    db.order_update_status(order_id, "cancelled", call.from_user.id)
    await call.answer("❌ Отменен!")

# =========================
# REPORTS
# =========================
async def generate_monthly_report(message: Message, lang: str):
    """Manual export: current month"""
    now = datetime.now()
    year, month = now.year, now.month

    if db.report_is_sent(year, month):
        await message.answer("Отчет за этот месяц уже отправлен!" if lang == "ru" else "Bu oy hisobot yuborilgan!")
        return

    orders = db.orders_get_monthly(year, month)
    if not orders:
        await message.answer("Нет заказов за этот месяц" if lang == "ru" else "Bu oy buyurtmalar yo'q")
        return

    Path("reports").mkdir(exist_ok=True)
    filename = f"reports/report_{year}_{month:02d}.xlsx"
    total_amount = build_excel_report(filename, orders)

    text = (
        f"📊 <b>Отчет за {month:02d}.{year}</b>\n\n"
        f"📦 Заказов: {len(orders)}\n"
        f"💰 Сумма: {format_price(total_amount)} сум"
    ) if lang == "ru" else (
        f"📊 <b>Hisobot {month:02d}.{year}</b>\n\n"
        f"📦 Buyurtmalar: {len(orders)}\n"
        f"💰 Summa: {format_price(total_amount)} so'm"
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
            await bot.send_document(admin_id, FSInputFile(filename))
        except Exception as e:
            print(f"Failed to send report to {admin_id}: {e}")

    db.report_mark_sent(year, month, filename, len(orders), total_amount)
    await message.answer("✅ Отчет отправлен!" if lang == "ru" else "✅ Hisobot yuborildi!")

def build_excel_report(filename: str, orders: List[Dict]) -> int:
    wb = Workbook()
    ws = wb.active
    ws.title = "Report"

    headers = ["ID", "Дата", "Клиент", "Телефон", "Город", "Товары", "Сумма", "Статус"]
    ws.append(headers)

    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")

    total_amount = 0
    for order in orders:
        items = json.loads(order["items"]) if order.get("items") else []
        items_str = ", ".join([f"{it.get('name','')} x{it.get('qty',1)}" for it in items])

        ws.append([
            order["id"],
            order["created_at"],
            order["name"],
            order["phone"],
            order["city"],
            items_str[:80],
            int(order["total_amount"] or 0),
            order["status"]
        ])
        total_amount += int(order["total_amount"] or 0)

    wb.save(filename)
    return total_amount

async def cron_send_prev_month_report():
    """Auto: previous month report (closed month)"""
    now = datetime.now()
    year, month = prev_month(now)

    if db.report_is_sent(year, month):
        return

    orders = db.orders_get_monthly(year, month)
    if not orders:
        return

    Path("reports").mkdir(exist_ok=True)
    filename = f"reports/report_{year}_{month:02d}.xlsx"
    total_amount = build_excel_report(filename, orders)

    text = (
        f"📊 <b>Автоотчет за {month:02d}.{year}</b>\n\n"
        f"📦 Заказов: {len(orders)}\n"
        f"💰 Сумма: {format_price(total_amount)} сум"
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
            await bot.send_document(admin_id, FSInputFile(filename))
        except Exception as e:
            print(f"Auto report failed for {admin_id}: {e}")

    db.report_mark_sent(year, month, filename, len(orders), total_amount)

# =========================
# DAILY WEEKLY POST (Mon–Sat)
# =========================
async def cron_post_daily_to_channel():
    if not CHANNEL_ID:
        return

    now = datetime.now()
    dow = now.isoweekday()  # 1..7

    # Sunday: remind admin
    if dow == 7:
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, "📌 Воскресенье: загрузите посты на новую неделю (Пн–Сб) → 🛠 Админ → 📰 Посты недели.")
            except Exception:
                pass
        return

    week_key = db.week_key_now(now)
    post = db.sched_get_for_day(dow=dow, week_key=week_key)

    if not post:
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, f"⚠️ Нет поста на сегодня (день={dow}) для недели {week_key}. Загрузите: 🛠 Админ → 📰 Посты недели.")
            except Exception:
                pass
        return

    caption = (post.get("caption") or "").strip() or "🔥 ZARY & CO"
    media_type = post.get("media_type") or "none"
    file_id = post.get("file_id") or ""

    try:
        if media_type == "video" and file_id:
            await bot.send_video(CHANNEL_ID, file_id, caption=caption)
        elif media_type == "photo" and file_id:
            await bot.send_photo(CHANNEL_ID, file_id, caption=caption)
        else:
            await bot.send_message(CHANNEL_ID, caption)

        db.sched_mark_posted(post["id"])

    except Exception as e:
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, f"❌ Ошибка публикации в канал: {e}")
            except Exception:
                pass

# =========================
# REMINDERS
# =========================
async def check_reminders():
    orders = db.orders_get_for_reminder()
    if not orders:
        return

    for admin_id in ADMIN_IDS:
        try:
            lines = [f"🆕 #{o['id']} | {esc(o['name'])} | {esc(o['phone'])}" for o in orders[:10]]
            text = "🔔 <b>Напоминание: новые заказы!</b>\n\n" + "\n".join(lines)
            await bot.send_message(admin_id, text)
        except Exception as e:
            print(f"Reminder failed for {admin_id}: {e}")

    for o in orders:
        db.order_update_reminded(o["id"])

# =========================
# SCHEDULER (only reminders)
# =========================
async def scheduler():
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    sch = AsyncIOScheduler()
    sch.add_job(check_reminders, "interval", minutes=30)
    sch.start()

# =========================
# WEB SERVER + CRON ENDPOINTS
# =========================
from aiohttp import web

async def health_server():
    app = web.Application()

    async def health(request):
        return web.Response(text="OK", status=200)

    async def cron_monthly(request: web.Request):
        secret = request.query.get("secret", "")
        if not cron_allowed(secret):
            return web.Response(text="Forbidden", status=403)
        await cron_send_prev_month_report()
        return web.Response(text="OK", status=200)

    async def cron_daily(request: web.Request):
        secret = request.query.get("secret", "")
        if not cron_allowed(secret):
            return web.Response(text="Forbidden", status=403)
        await cron_post_daily_to_channel()
        return web.Response(text="OK", status=200)

    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    app.router.add_get("/cron/monthly", cron_monthly)
    app.router.add_get("/cron/daily", cron_daily)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"✅ Health server on port {PORT}")

# =========================
# MAIN
# =========================
async def main():
    await health_server()
    await scheduler()
    print(f"✅ Bot started with {len(ADMIN_IDS)} admins: {ADMIN_IDS}")
    if CHANNEL_ID:
        print(f"✅ Channel enabled: {CHANNEL_ID}")
    if CRON_SECRET:
        print("✅ Cron endpoints enabled: /cron/monthly /cron/daily")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
