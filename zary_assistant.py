"""
ZARY SHOP BOT — FINAL FULL VERSION
PART 1/4

Что внутри этой части:
- imports
- env
- helpers
- texts RU/UZ
- database
- bot init
- states
- keyboards
"""

import os
import html
import json
import asyncio
import sqlite3
import secrets
import threading
from datetime import datetime, timedelta
from calendar import monthrange
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
from urllib.parse import quote

from zoneinfo import ZoneInfo
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ContentType
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    ReplyKeyboardRemove,
)
from aiogram.types.input_file import FSInputFile

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill


# =========================================================
# BASIC APP / TZ
# =========================================================
TZ = ZoneInfo("Asia/Tashkent")
web_app = web.Application()


# =========================================================
# ENV
# =========================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN не установлен")

PORT = int(os.getenv("PORT", "10000"))
DB_PATH = os.getenv("DB_PATH", "bot.db")

BASE_URL = os.getenv("BASE_URL", "").strip().rstrip("/")
if not BASE_URL:
    print("⚠️ BASE_URL не установлен. WebApp может работать некорректно.")

CRON_SECRET = os.getenv("CRON_SECRET", "").strip()
ADMIN_PANEL_TOKEN = os.getenv("ADMIN_PANEL_TOKEN", "").strip()
WEBAPP_SECRET = os.getenv("WEBAPP_SECRET", secrets.token_hex(16)).strip()

CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "zaryco_official").strip().lstrip("@")
TG_CHANNEL_URL = f"https://t.me/{CHANNEL_USERNAME}"

FOLLOW_TG = "https://t.me/zaryco_official"
FOLLOW_IG = "https://www.instagram.com/zary.co/"
FOLLOW_YT = "https://www.youtube.com/@ZARYCOOFFICIAL"

PHONE = os.getenv("MANAGER_PHONE", "+998771202255").strip()
MANAGER_USERNAME = os.getenv("MANAGER_USERNAME", "zaryco_official").strip().lstrip("@")

CLICK_MERCHANT_ID = os.getenv("CLICK_MERCHANT_ID", "").strip()
CLICK_SERVICE_ID = os.getenv("CLICK_SERVICE_ID", "").strip()
CLICK_SECRET_KEY = os.getenv("CLICK_SECRET_KEY", "").strip()

PAYME_MERCHANT_ID = os.getenv("PAYME_MERCHANT_ID", "").strip()
PAYME_SECRET_KEY = os.getenv("PAYME_SECRET_KEY", "").strip()

_channel_id = os.getenv("CHANNEL_ID", "").strip()
CHANNEL_ID = int(_channel_id) if _channel_id and _channel_id.lstrip("-").isdigit() else None

ADMIN_IDS: List[int] = []
for i in range(1, 6):
    raw = os.getenv(f"ADMIN_ID_{i}", "").strip()
    if raw and raw.lstrip("-").isdigit():
        ADMIN_IDS.append(int(raw))

if not ADMIN_IDS:
    fallback_admin = os.getenv("MANAGER_CHAT_ID", "").strip()
    if fallback_admin and fallback_admin.lstrip("-").isdigit():
        ADMIN_IDS.append(int(fallback_admin))

if not ADMIN_IDS:
    raise RuntimeError("❌ Нужен хотя бы один ADMIN_ID_1")

PRIMARY_ADMIN = ADMIN_IDS[0]

if not ADMIN_PANEL_TOKEN:
    print("⚠️ ADMIN_PANEL_TOKEN не установлен. /admin будет без защиты.")


# =========================================================
# CONSTANTS
# =========================================================
SHOP_CATEGORIES = ("new", "hits", "sale", "limited", "school", "casual")
DELIVERY_TYPES = ("yandex_courier", "b2b_post", "yandex_pvz")
PAYMENT_METHODS = ("click", "payme")
PAYMENT_STATUSES = ("pending", "paid", "failed", "cancelled", "refunded")
ORDER_STATUSES = ("new", "processing", "confirmed", "paid", "shipped", "delivered", "cancelled")


# =========================================================
# HELPERS
# =========================================================
def now_tz() -> datetime:
    return datetime.now(TZ)


def now_str() -> str:
    return now_tz().strftime("%Y-%m-%d %H:%M:%S")


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def money_fmt(amount: int | float | str) -> str:
    try:
        return f"{int(float(amount)):,}".replace(",", " ")
    except Exception:
        return "0"


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def cron_allowed(secret: str) -> bool:
    return bool(CRON_SECRET) and secret == CRON_SECRET


def admin_panel_allowed(token: str) -> bool:
    if not ADMIN_PANEL_TOKEN:
        return True
    return token == ADMIN_PANEL_TOKEN


def product_public_photo_url(file_id: str) -> str:
    if not file_id:
        return ""
    return f"/media/{quote(file_id)}"


def prev_month(dt: datetime) -> tuple[int, int]:
    first_day = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    prev_last_day = first_day - timedelta(days=1)
    return prev_last_day.year, prev_last_day.month


def size_by_age(age: int) -> str:
    mapping = {
        1: "86",
        2: "92",
        3: "98",
        4: "104",
        5: "110",
        6: "116",
        7: "122",
        8: "128",
        9: "134",
        10: "140",
        11: "146",
        12: "152",
        13: "158",
        14: "164",
        15: "164",
    }
    return mapping.get(age, "122-128")


def size_by_height(height: int) -> str:
    sizes = [86, 92, 98, 104, 110, 116, 122, 128, 134, 140, 146, 152, 158, 164]
    closest = min(sizes, key=lambda x: abs(x - height))
    return str(closest)


def normalize_phone(phone: str) -> str:
    if not phone:
        return ""
    cleaned = "".join(ch for ch in phone if ch.isdigit() or ch == "+")
    if cleaned.startswith("998") and not cleaned.startswith("+998"):
        cleaned = "+" + cleaned
    if cleaned.startswith("8") and len(cleaned) == 9:
        cleaned = "+998" + cleaned
    return cleaned


def phone_is_valid(phone: str) -> bool:
    phone = normalize_phone(phone)
    digits = "".join(ch for ch in phone if ch.isdigit())
    return len(digits) >= 9


def parse_sizes_text(sizes: str) -> List[str]:
    if not sizes:
        return []
    raw = sizes.replace(";", ",").replace("|", ",")
    return [x.strip() for x in raw.split(",") if x.strip()]


def user_lang_or_default(user_row: Optional[Dict]) -> str:
    if user_row and user_row.get("lang") in ("ru", "uz"):
        return user_row["lang"]
    return "ru"


# =========================================================
# TEXTS
# =========================================================
TEXTS: Dict[str, Dict[str, str]] = {
    "welcome": {
        "ru": (
            "👋 Добро пожаловать в <b>ZARY & CO</b>\n\n"
            "Стильная одежда для детей и семьи.\n"
            "Выберите действие ниже 👇"
        ),
        "uz": (
            "👋 <b>ZARY & CO</b> ga xush kelibsiz\n\n"
            "Bolalar va oila uchun zamonaviy kiyimlar.\n"
            "Quyidan kerakli bo‘limni tanlang 👇"
        ),
    },
    "shop_open": {
        "ru": "🛍 Откройте магазин по кнопке ниже:",
        "uz": "🛍 Do‘konni quyidagi tugma orqali oching:",
    },
    "cart_empty": {
        "ru": "🛒 Корзина пустая.",
        "uz": "🛒 Savatcha bo‘sh.",
    },
    "cart_title": {
        "ru": "🛒 <b>Ваша корзина</b>",
        "uz": "🛒 <b>Sizning savatchangiz</b>",
    },
    "checkout_start_name": {
        "ru": "Введите ваше имя:",
        "uz": "Ismingizni kiriting:",
    },
    "checkout_phone": {
        "ru": "Введите номер телефона:",
        "uz": "Telefon raqamingizni kiriting:",
    },
    "checkout_delivery": {
        "ru": "Выберите способ доставки:",
        "uz": "Yetkazib berish usulini tanlang:",
    },
    "checkout_address_type": {
        "ru": "Выберите способ указания адреса:",
        "uz": "Manzilni ko‘rsatish usulini tanlang:",
    },
    "checkout_city": {
        "ru": "Введите город:",
        "uz": "Shaharni kiriting:",
    },
    "checkout_address_manual": {
        "ru": "Введите адрес вручную:",
        "uz": "Manzilni qo‘lda kiriting:",
    },
    "checkout_location_wait": {
        "ru": "Отправьте вашу геолокацию кнопкой ниже.",
        "uz": "Quyidagi tugma orqali lokatsiyangizni yuboring.",
    },
    "checkout_pvz": {
        "ru": "Введите адрес или код ПВЗ:",
        "uz": "PVZ manzili yoki kodini kiriting:",
    },
    "checkout_payment": {
        "ru": "Выберите способ оплаты:",
        "uz": "To‘lov usulini tanlang:",
    },
    "checkout_comment": {
        "ru": "Комментарий к заказу (или отправьте -):",
        "uz": "Buyurtmaga izoh kiriting (yoki - yuboring):",
    },
    "checkout_confirm": {
        "ru": "Проверьте заказ и подтвердите:",
        "uz": "Buyurtmani tekshirib, tasdiqlang:",
    },
    "orders_empty": {
        "ru": "📦 У вас пока нет заказов.",
        "uz": "📦 Sizda hali buyurtmalar yo‘q.",
    },
    "size_help": {
        "ru": (
            "📏 <b>Подбор размера</b>\n\n"
            "Отправьте:\n"
            "• возраст ребёнка числом, например: <b>6</b>\n"
            "или\n"
            "• рост, например: <b>128</b>"
        ),
        "uz": (
            "📏 <b>Razmer tanlash</b>\n\n"
            "Yuboring:\n"
            "• bolaning yoshini, masalan: <b>6</b>\n"
            "yoki\n"
            "• bo‘yini, masalan: <b>128</b>"
        ),
    },
    "contacts": {
        "ru": (
            "📞 <b>Контакты</b>\n\n"
            f"Телефон: {PHONE}\n"
            f"Telegram: @{MANAGER_USERNAME}\n\n"
            f"Telegram канал:\n{FOLLOW_TG}\n\n"
            f"Instagram:\n{FOLLOW_IG}\n\n"
            f"YouTube:\n{FOLLOW_YT}"
        ),
        "uz": (
            "📞 <b>Aloqa</b>\n\n"
            f"Telefon: {PHONE}\n"
            f"Telegram: @{MANAGER_USERNAME}\n\n"
            f"Telegram kanal:\n{FOLLOW_TG}\n\n"
            f"Instagram:\n{FOLLOW_IG}\n\n"
            f"YouTube:\n{FOLLOW_YT}"
        ),
    },
    "thanks_order": {
        "ru": (
            "💛 Спасибо за заказ!\n\n"
            "Мы очень рады, что вы с нами.\n"
            "Пусть покупки от <b>ZARY & CO</b> приносят радость и комфорт.\n"
            "Носите с удовольствием.\n\n"
            "Чтобы не потерять нас и следить за новинками, подпишитесь:\n"
            f"Telegram: {FOLLOW_TG}\n"
            f"Instagram: {FOLLOW_IG}\n"
            f"YouTube: {FOLLOW_YT}"
        ),
        "uz": (
            "💛 Buyurtmangiz uchun rahmat!\n\n"
            "Biz siz biz bilan ekaningizdan juda xursandmiz.\n"
            "<b>ZARY & CO</b> sizga qulaylik va xursandchilik olib kelsin.\n"
            "Mamnuniyat bilan kiying.\n\n"
            "Bizni yo‘qotib qo‘ymaslik va yangiliklarni kuzatish uchun obuna bo‘ling:\n"
            f"Telegram: {FOLLOW_TG}\n"
            f"Instagram: {FOLLOW_IG}\n"
            f"YouTube: {FOLLOW_YT}"
        ),
    },
}


def t(lang: str, key: str) -> str:
    lang = "uz" if lang == "uz" else "ru"
    return TEXTS.get(key, {}).get(lang, TEXTS.get(key, {}).get("ru", key))


# =========================================================
# DATABASE
# =========================================================
class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=20)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA temp_store=MEMORY;")
            conn.execute("PRAGMA foreign_keys=ON;")
        except Exception:
            pass
        return conn

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = self._connect()
        return self._local.conn

    def _init_db(self) -> None:
        conn = self._connect()
        cur = conn.cursor()

        cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT DEFAULT '',
            lang TEXT DEFAULT 'ru',
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS carts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER,
            product_name TEXT NOT NULL,
            price INTEGER DEFAULT 0,
            qty INTEGER DEFAULT 1,
            size TEXT DEFAULT '',
            photo_file_id TEXT DEFAULT '',
            added_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT DEFAULT '',
            customer_name TEXT DEFAULT '',
            customer_phone TEXT DEFAULT '',
            city TEXT DEFAULT '',
            items TEXT DEFAULT '[]',
            total_qty INTEGER DEFAULT 0,
            total_amount INTEGER DEFAULT 0,

            delivery_service TEXT DEFAULT '',
            delivery_type TEXT DEFAULT '',
            delivery_address TEXT DEFAULT '',
            latitude REAL,
            longitude REAL,
            pvz_code TEXT DEFAULT '',
            pvz_address TEXT DEFAULT '',

            payment_method TEXT DEFAULT '',
            payment_status TEXT DEFAULT 'pending',
            payment_provider_invoice_id TEXT DEFAULT '',
            payment_provider_url TEXT DEFAULT '',

            comment TEXT DEFAULT '',
            status TEXT DEFAULT 'new',
            manager_seen INTEGER DEFAULT 0,
            manager_id INTEGER,
            source TEXT DEFAULT 'bot',
            created_at TEXT,
            updated_at TEXT,
            reminded_at TEXT
        );

        CREATE TABLE IF NOT EXISTS monthly_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            year INTEGER,
            month INTEGER,
            sent_at TEXT,
            filename TEXT,
            total_orders INTEGER DEFAULT 0,
            total_amount INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending'
        );

        CREATE TABLE IF NOT EXISTS scheduled_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dow INTEGER,
            media_type TEXT,
            file_id TEXT,
            caption TEXT,
            week_key TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            posted_at TEXT
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            event_type TEXT,
            meta TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS shop_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            photo_file_id TEXT DEFAULT '',
            title_ru TEXT NOT NULL,
            title_uz TEXT NOT NULL,
            description_ru TEXT DEFAULT '',
            description_uz TEXT DEFAULT '',
            sizes TEXT DEFAULT '',
            category_slug TEXT DEFAULT 'casual',
            price INTEGER DEFAULT 0,
            old_price INTEGER DEFAULT 0,
            price_on_request INTEGER DEFAULT 0,
            stock_qty INTEGER DEFAULT 0,
            is_published INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
        CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
        CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);
        CREATE INDEX IF NOT EXISTS idx_carts_user ON carts(user_id);
        CREATE INDEX IF NOT EXISTS idx_events_type_time ON events(event_type, created_at);
        CREATE INDEX IF NOT EXISTS idx_sched_week_dow ON scheduled_posts(week_key, dow);
        CREATE INDEX IF NOT EXISTS idx_products_pub_cat ON shop_products(is_published, category_slug, sort_order, id);
        """)

        conn.commit()
        self._migrate_orders(conn)
        self._migrate_products(conn)
        conn.close()

    def _migrate_orders(self, conn: sqlite3.Connection) -> None:
        existing = {r["name"] for r in conn.execute("PRAGMA table_info(orders)").fetchall()}
        columns_to_add = {
            "customer_name": "TEXT DEFAULT ''",
            "customer_phone": "TEXT DEFAULT ''",
            "total_qty": "INTEGER DEFAULT 0",
            "delivery_service": "TEXT DEFAULT ''",
            "delivery_type": "TEXT DEFAULT ''",
            "latitude": "REAL",
            "longitude": "REAL",
            "pvz_code": "TEXT DEFAULT ''",
            "pvz_address": "TEXT DEFAULT ''",
            "payment_method": "TEXT DEFAULT ''",
            "payment_status": "TEXT DEFAULT 'pending'",
            "payment_provider_invoice_id": "TEXT DEFAULT ''",
            "payment_provider_url": "TEXT DEFAULT ''",
            "updated_at": "TEXT",
            "source": "TEXT DEFAULT 'bot'",
        }
        for col, sql_type in columns_to_add.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE orders ADD COLUMN {col} {sql_type}")
        conn.commit()

    def _migrate_products(self, conn: sqlite3.Connection) -> None:
        existing = {r["name"] for r in conn.execute("PRAGMA table_info(shop_products)").fetchall()}
        columns_to_add = {
            "old_price": "INTEGER DEFAULT 0",
            "stock_qty": "INTEGER DEFAULT 0",
        }
        for col, sql_type in columns_to_add.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE shop_products ADD COLUMN {col} {sql_type}")
        conn.commit()

    # -------------------------
    # Users
    # -------------------------
    def user_upsert(self, user_id: int, username: str = "", full_name: str = "", lang: str = "ru") -> None:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,))
        if cur.fetchone():
            cur.execute("""
                UPDATE users
                SET username=?, full_name=?, lang=?, updated_at=?
                WHERE user_id=?
            """, (username, full_name, lang, now_str(), user_id))
        else:
            cur.execute("""
                INSERT INTO users (user_id, username, full_name, lang, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, username, full_name, lang, now_str(), now_str()))
        conn.commit()

    def user_get(self, user_id: int) -> Optional[Dict]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row else None

    def user_set_lang(self, user_id: int, lang: str) -> None:
        conn = self._get_conn()
        conn.execute("UPDATE users SET lang=?, updated_at=? WHERE user_id=?", (lang, now_str(), user_id))
        conn.commit()

    # -------------------------
    # Events
    # -------------------------
    def event_add(self, user_id: Optional[int], event_type: str, meta: Optional[Dict] = None) -> None:
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO events (user_id, event_type, meta, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            user_id,
            event_type,
            json.dumps(meta or {}, ensure_ascii=False),
            now_str(),
        ))
        conn.commit()

    # -------------------------
    # Cart
    # -------------------------
    def cart_add(
        self,
        user_id: int,
        product_id: Optional[int],
        product_name: str,
        price: int,
        qty: int = 1,
        size: str = "",
        photo_file_id: str = "",
    ) -> int:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO carts (user_id, product_id, product_name, price, qty, size, photo_file_id, added_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            product_id,
            product_name,
            safe_int(price),
            max(1, safe_int(qty, 1)),
            size,
            photo_file_id,
            now_str(),
        ))
        conn.commit()
        cart_id = cur.lastrowid
        self.event_add(user_id, "cart_add", {
            "product_id": product_id,
            "product_name": product_name,
            "qty": qty,
            "size": size,
        })
        return cart_id

    def cart_get(self, user_id: int) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT * FROM carts
            WHERE user_id=?
            ORDER BY id DESC
        """, (user_id,)).fetchall()
        return [dict(r) for r in rows]

    def cart_clear(self, user_id: int) -> None:
        conn = self._get_conn()
        conn.execute("DELETE FROM carts WHERE user_id=?", (user_id,))
        conn.commit()

    def cart_remove(self, cart_id: int, user_id: Optional[int] = None) -> None:
        conn = self._get_conn()
        if user_id is None:
            conn.execute("DELETE FROM carts WHERE id=?", (cart_id,))
        else:
            conn.execute("DELETE FROM carts WHERE id=? AND user_id=?", (cart_id, user_id))
        conn.commit()

    def cart_update_qty(self, cart_id: int, qty: int, user_id: Optional[int] = None) -> None:
        qty = max(1, safe_int(qty, 1))
        conn = self._get_conn()
        if user_id is None:
            conn.execute("UPDATE carts SET qty=? WHERE id=?", (qty, cart_id))
        else:
            conn.execute("UPDATE carts SET qty=? WHERE id=? AND user_id=?", (qty, cart_id, user_id))
        conn.commit()

    def cart_totals(self, user_id: int) -> Dict[str, int]:
        cart = self.cart_get(user_id)
        total_qty = sum(safe_int(x.get("qty"), 1) for x in cart)
        total_amount = sum(safe_int(x.get("price"), 0) * safe_int(x.get("qty"), 1) for x in cart)
        return {"total_qty": total_qty, "total_amount": total_amount}

    # -------------------------
    # Orders
    # -------------------------
    def order_create(self, data: Dict[str, Any]) -> int:
        conn = self._get_conn()
        cur = conn.cursor()

        items_raw = data.get("items", [])
        if isinstance(items_raw, str):
            try:
                items_list = json.loads(items_raw)
            except Exception:
                items_list = []
        else:
            items_list = items_raw

        total_qty = data.get("total_qty")
        if total_qty is None:
            total_qty = sum(safe_int(x.get("qty"), 1) for x in items_list)

        total_amount = data.get("total_amount")
        if total_amount is None:
            total_amount = sum(
                safe_int(x.get("price"), 0) * safe_int(x.get("qty"), 1)
                for x in items_list
            )

        created = now_str()

        cur.execute("""
            INSERT INTO orders (
                user_id, username, customer_name, customer_phone, city,
                items, total_qty, total_amount,
                delivery_service, delivery_type, delivery_address,
                latitude, longitude, pvz_code, pvz_address,
                payment_method, payment_status, payment_provider_invoice_id, payment_provider_url,
                comment, status, manager_seen, manager_id, source,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("user_id"),
            data.get("username", ""),
            data.get("customer_name", ""),
            normalize_phone(data.get("customer_phone", "")),
            data.get("city", ""),
            json.dumps(items_list, ensure_ascii=False),
            safe_int(total_qty),
            safe_int(total_amount),

            data.get("delivery_service", ""),
            data.get("delivery_type", ""),
            data.get("delivery_address", ""),
            data.get("latitude"),
            data.get("longitude"),
            data.get("pvz_code", ""),
            data.get("pvz_address", ""),

            data.get("payment_method", ""),
            data.get("payment_status", "pending"),
            data.get("payment_provider_invoice_id", ""),
            data.get("payment_provider_url", ""),

            data.get("comment", ""),
            data.get("status", "new"),
            safe_int(data.get("manager_seen", 0)),
            data.get("manager_id"),
            data.get("source", "bot"),
            created,
            created,
        ))
        conn.commit()

        order_id = cur.lastrowid
        self.event_add(data.get("user_id"), "order_created", {
            "order_id": order_id,
            "source": data.get("source", "bot"),
            "payment_method": data.get("payment_method", ""),
            "delivery_type": data.get("delivery_type", ""),
        })
        return order_id

    def order_get(self, order_id: int) -> Optional[Dict]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        return dict(row) if row else None

    def orders_get_user(self, user_id: int, limit: int = 10) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT * FROM orders
            WHERE user_id=?
            ORDER BY id DESC
            LIMIT ?
        """, (user_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def orders_get_by_status(self, status: str, limit: int = 50) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT * FROM orders
            WHERE status=?
            ORDER BY id DESC
            LIMIT ?
        """, (status, limit)).fetchall()
        return [dict(r) for r in rows]

    def order_update_status(self, order_id: int, status: str, manager_id: Optional[int] = None) -> None:
        conn = self._get_conn()
        if manager_id is None:
            conn.execute("""
                UPDATE orders
                SET status=?, updated_at=?
                WHERE id=?
            """, (status, now_str(), order_id))
        else:
            conn.execute("""
                UPDATE orders
                SET status=?, manager_id=?, manager_seen=1, updated_at=?
                WHERE id=?
            """, (status, manager_id, now_str(), order_id))
        conn.commit()

    def order_update_payment(
        self,
        order_id: int,
        payment_status: str,
        payment_provider_invoice_id: str = "",
        payment_provider_url: str = "",
    ) -> None:
        conn = self._get_conn()
        conn.execute("""
            UPDATE orders
            SET payment_status=?, payment_provider_invoice_id=?, payment_provider_url=?, updated_at=?
            WHERE id=?
        """, (
            payment_status,
            payment_provider_invoice_id,
            payment_provider_url,
            now_str(),
            order_id,
        ))
        conn.commit()

    def order_mark_seen(self, order_id: int, manager_id: int) -> None:
        conn = self._get_conn()
        conn.execute("""
            UPDATE orders
            SET manager_seen=1, manager_id=?, updated_at=?
            WHERE id=?
        """, (manager_id, now_str(), order_id))
        conn.commit()

    def orders_filter(
        self,
        status: str = "",
        city: str = "",
        phone_q: str = "",
        limit: int = 200,
    ) -> List[Dict]:
        conn = self._get_conn()
        q = "SELECT * FROM orders WHERE 1=1"
        args: List[Any] = []

        if status:
            q += " AND status=?"
            args.append(status)

        if city:
            q += " AND city LIKE ?"
            args.append(f"%{city}%")

        if phone_q:
            q += " AND customer_phone LIKE ?"
            args.append(f"%{phone_q}%")

        q += " ORDER BY id DESC LIMIT ?"
        args.append(limit)

        rows = conn.execute(q, tuple(args)).fetchall()
        return [dict(r) for r in rows]

    def find_orders_by_phone(self, phone_part: str, limit: int = 20) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT * FROM orders
            WHERE customer_phone LIKE ?
            ORDER BY id DESC
            LIMIT ?
        """, (f"%{phone_part}%", limit)).fetchall()
        return [dict(r) for r in rows]

    def orders_get_for_reminder(self) -> List[Dict]:
        conn = self._get_conn()
        cutoff = (now_tz() - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
        rows = conn.execute("""
            SELECT * FROM orders
            WHERE status='new'
              AND manager_seen=0
              AND created_at < ?
              AND (reminded_at IS NULL OR reminded_at < ?)
            ORDER BY id DESC
        """, (cutoff, cutoff)).fetchall()
        return [dict(r) for r in rows]

    def order_update_reminded(self, order_id: int) -> None:
        conn = self._get_conn()
        conn.execute("""
            UPDATE orders
            SET reminded_at=?, updated_at=?
            WHERE id=?
        """, (now_str(), now_str(), order_id))
        conn.commit()

    def orders_get_monthly(self, year: int, month: int) -> List[Dict]:
        conn = self._get_conn()
        start = f"{year}-{month:02d}-01 00:00:00"
        last_day = monthrange(year, month)[1]
        end = f"{year}-{month:02d}-{last_day} 23:59:59"
        rows = conn.execute("""
            SELECT * FROM orders
            WHERE created_at BETWEEN ? AND ?
            ORDER BY id ASC
        """, (start, end)).fetchall()
        return [dict(r) for r in rows]

    # -------------------------
    # Reports / stats
    # -------------------------
    def report_mark_sent(self, year: int, month: int, filename: str, total_orders: int, total_amount: int) -> None:
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO monthly_reports (year, month, sent_at, filename, total_orders, total_amount, status)
            VALUES (?, ?, ?, ?, ?, ?, 'sent')
        """, (year, month, now_str(), filename, total_orders, total_amount))
        conn.commit()

    def report_is_sent(self, year: int, month: int) -> bool:
        conn = self._get_conn()
        row = conn.execute("""
            SELECT 1 FROM monthly_reports
            WHERE year=? AND month=? AND status='sent'
        """, (year, month)).fetchone()
        return row is not None

    def get_stats_all(self) -> Dict[str, int]:
        conn = self._get_conn()
        row = conn.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status='new' THEN 1 ELSE 0 END) AS new_count,
                SUM(CASE WHEN status='processing' THEN 1 ELSE 0 END) AS processing,
                SUM(CASE WHEN status='confirmed' THEN 1 ELSE 0 END) AS confirmed,
                SUM(CASE WHEN status='paid' THEN 1 ELSE 0 END) AS paid_count,
                SUM(CASE WHEN status='shipped' THEN 1 ELSE 0 END) AS shipped,
                SUM(CASE WHEN status='delivered' THEN 1 ELSE 0 END) AS delivered,
                SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END) AS cancelled,
                COUNT(DISTINCT user_id) AS unique_users
            FROM orders
        """).fetchone()

        if not row:
            return {
                "total": 0,
                "new_count": 0,
                "processing": 0,
                "confirmed": 0,
                "paid_count": 0,
                "shipped": 0,
                "delivered": 0,
                "cancelled": 0,
                "unique_users": 0,
            }
        return dict(row)

    def stats_range(self, start: str, end: str) -> Dict[str, int]:
        conn = self._get_conn()
        row = conn.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status='new' THEN 1 ELSE 0 END) AS new_count,
                SUM(CASE WHEN status='processing' THEN 1 ELSE 0 END) AS processing,
                SUM(CASE WHEN status='confirmed' THEN 1 ELSE 0 END) AS confirmed,
                SUM(CASE WHEN status='paid' THEN 1 ELSE 0 END) AS paid_count,
                SUM(CASE WHEN status='shipped' THEN 1 ELSE 0 END) AS shipped,
                SUM(CASE WHEN status='delivered' THEN 1 ELSE 0 END) AS delivered,
                SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END) AS cancelled
            FROM orders
            WHERE created_at BETWEEN ? AND ?
        """, (start, end)).fetchone()
        return dict(row) if row else {}

    def top_products_range(self, start: str, end: str, limit: int = 10) -> List[Tuple[str, int]]:
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT items FROM orders
            WHERE created_at BETWEEN ? AND ?
        """, (start, end)).fetchall()

        counter: Dict[str, int] = {}
        for row in rows:
            try:
                items = json.loads(row["items"] or "[]")
            except Exception:
                items = []
            for item in items:
                name = (item.get("product_name") or item.get("name") or "").strip()
                qty = safe_int(item.get("qty"), 1)
                if name:
                    counter[name] = counter.get(name, 0) + qty

        return sorted(counter.items(), key=lambda x: x[1], reverse=True)[:limit]

    def top_cities_range(self, start: str, end: str, limit: int = 10) -> List[Tuple[str, int]]:
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT city, COUNT(*) AS c
            FROM orders
            WHERE created_at BETWEEN ? AND ?
            GROUP BY city
            ORDER BY c DESC
            LIMIT ?
        """, (start, end, limit)).fetchall()
        return [(r["city"] or "—", safe_int(r["c"])) for r in rows]

    def funnel_range(self, start: str, end: str) -> Dict[str, float]:
        conn = self._get_conn()
        row = conn.execute("""
            SELECT
                SUM(CASE WHEN event_type='cart_add' THEN 1 ELSE 0 END) AS cart_add,
                SUM(CASE WHEN event_type='order_created' THEN 1 ELSE 0 END) AS order_created
            FROM events
            WHERE created_at BETWEEN ? AND ?
        """, (start, end)).fetchone()

        cart_add = safe_int(row["cart_add"] if row else 0)
        order_created = safe_int(row["order_created"] if row else 0)
        conversion = round((order_created / cart_add * 100.0), 2) if cart_add > 0 else 0.0

        return {
            "cart_add": cart_add,
            "order_created": order_created,
            "conversion": conversion,
        }

    # -------------------------
    # Scheduled posts
    # -------------------------
    def week_key_now(self, dt: datetime) -> str:
        iso = dt.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"

    def sched_add(self, dow: int, media_type: str, file_id: str, caption: str, week_key: str) -> int:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO scheduled_posts (dow, media_type, file_id, caption, week_key)
            VALUES (?, ?, ?, ?, ?)
        """, (dow, media_type, file_id, caption, week_key))
        conn.commit()
        return cur.lastrowid

    def sched_get_for_day(self, dow: int, week_key: str) -> Optional[Dict]:
        conn = self._get_conn()
        row = conn.execute("""
            SELECT * FROM scheduled_posts
            WHERE dow=? AND week_key=? AND posted_at IS NULL
            ORDER BY id ASC
            LIMIT 1
        """, (dow, week_key)).fetchone()
        return dict(row) if row else None

    def sched_mark_posted(self, post_id: int) -> None:
        conn = self._get_conn()
        conn.execute("""
            UPDATE scheduled_posts
            SET posted_at=?
            WHERE id=?
        """, (now_str(), post_id))
        conn.commit()

    def sched_count_week(self, week_key: str) -> int:
        conn = self._get_conn()
        row = conn.execute("""
            SELECT COUNT(*) AS c
            FROM scheduled_posts
            WHERE week_key=?
        """, (week_key,)).fetchone()
        return safe_int(row["c"] if row else 0)

    # -------------------------
    # Shop products
    # -------------------------
    def shop_product_add(
        self,
        photo_file_id: str,
        title_ru: str,
        title_uz: str,
        description_ru: str,
        description_uz: str,
        sizes: str,
        category_slug: str,
        price: int,
        old_price: int = 0,
        price_on_request: int = 0,
        stock_qty: int = 0,
        is_published: int = 1,
        sort_order: int = 0,
    ) -> int:
        if category_slug not in SHOP_CATEGORIES:
            category_slug = "casual"

        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO shop_products (
                photo_file_id, title_ru, title_uz,
                description_ru, description_uz,
                sizes, category_slug,
                price, old_price, price_on_request, stock_qty,
                is_published, sort_order,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            photo_file_id,
            title_ru.strip(),
            title_uz.strip(),
            description_ru.strip(),
            description_uz.strip(),
            sizes.strip(),
            category_slug,
            safe_int(price),
            safe_int(old_price),
            safe_int(price_on_request),
            safe_int(stock_qty),
            safe_int(is_published, 1),
            safe_int(sort_order),
            now_str(),
            now_str(),
        ))
        conn.commit()
        return cur.lastrowid

    def shop_product_get(self, product_id: int) -> Optional[Dict]:
        conn = self._get_conn()
        row = conn.execute("""
            SELECT * FROM shop_products
            WHERE id=?
        """, (product_id,)).fetchone()
        return dict(row) if row else None

    def shop_products_list(self, published_only: bool = True, limit: int = 500) -> List[Dict]:
        conn = self._get_conn()
        if published_only:
            rows = conn.execute("""
                SELECT * FROM shop_products
                WHERE is_published=1
                ORDER BY sort_order ASC, id DESC
                LIMIT ?
            """, (limit,)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM shop_products
                ORDER BY sort_order ASC, id DESC
                LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def shop_products_count(self) -> int:
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) AS c FROM shop_products").fetchone()
        return safe_int(row["c"] if row else 0)

    def shop_product_delete(self, product_id: int) -> None:
        conn = self._get_conn()
        conn.execute("DELETE FROM shop_products WHERE id=?", (product_id,))
        conn.commit()

    def shop_product_update_publish(self, product_id: int, is_published: int) -> None:
        conn = self._get_conn()
        conn.execute("""
            UPDATE shop_products
            SET is_published=?, updated_at=?
            WHERE id=?
        """, (safe_int(is_published), now_str(), product_id))
        conn.commit()

    def shop_product_update_field(self, product_id: int, field_name: str, value: Any) -> None:
        allowed = {
            "photo_file_id", "title_ru", "title_uz",
            "description_ru", "description_uz",
            "sizes", "category_slug", "price", "old_price",
            "price_on_request", "stock_qty", "is_published", "sort_order",
        }
        if field_name not in allowed:
            raise ValueError("Недопустимое поле для обновления")

        conn = self._get_conn()
        conn.execute(
            f"UPDATE shop_products SET {field_name}=?, updated_at=? WHERE id=?",
            (value, now_str(), product_id)
        )
        conn.commit()

    def shop_seed_demo_if_empty(self) -> None:
        if self.shop_products_count() > 0:
            return

        demo_products = [
            {
                "photo_file_id": "",
                "title_ru": "Kids Hoodie",
                "title_uz": "Bolalar hudi",
                "description_ru": "Тёплый и стильный худи для повседневной носки.",
                "description_uz": "Kundalik kiyish uchun issiq va zamonaviy hudi.",
                "sizes": "98,104,110,116",
                "category_slug": "new",
                "price": 250000,
                "old_price": 290000,
                "price_on_request": 0,
                "stock_qty": 15,
            },
            {
                "photo_file_id": "",
                "title_ru": "Mini Boss Suit",
                "title_uz": "Mini Boss kostyum",
                "description_ru": "Стильный комплект для особых дней.",
                "description_uz": "Maxsus kunlar uchun zamonaviy to‘plam.",
                "sizes": "104,110,116,122",
                "category_slug": "hits",
                "price": 390000,
                "old_price": 0,
                "price_on_request": 0,
                "stock_qty": 8,
            },
            {
                "photo_file_id": "",
                "title_ru": "School Set",
                "title_uz": "Maktab formasi",
                "description_ru": "Школьная форма премиум качества.",
                "description_uz": "Premium sifatdagi maktab formasi.",
                "sizes": "110,116,122,128,134",
                "category_slug": "school",
                "price": 320000,
                "old_price": 350000,
                "price_on_request": 0,
                "stock_qty": 20,
            },
        ]

        for item in demo_products:
            self.shop_product_add(**item)


db = Database(DB_PATH)
db.shop_seed_demo_if_empty()


# =========================================================
# BOT INIT
# =========================================================
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher(storage=MemoryStorage())


# =========================================================
# STATES
# =========================================================
class LangStates(StatesGroup):
    waiting_lang = State()


class SizeStates(StatesGroup):
    waiting_input = State()


class OrderStates(StatesGroup):
    waiting_name = State()
    waiting_phone = State()
    waiting_delivery = State()
    waiting_address_type = State()
    waiting_city = State()
    waiting_manual_address = State()
    waiting_location = State()
    waiting_pvz = State()
    waiting_payment = State()
    waiting_comment = State()
    waiting_confirm = State()


class AdminAddProductStates(StatesGroup):
    waiting_photo = State()
    waiting_title_ru = State()
    waiting_title_uz = State()
    waiting_desc_ru = State()
    waiting_desc_uz = State()
    waiting_sizes = State()
    waiting_category = State()
    waiting_price = State()
    waiting_old_price = State()
    waiting_stock_qty = State()
    waiting_publish = State()


class AdminEditProductStates(StatesGroup):
    waiting_product_id = State()
    waiting_field = State()
    waiting_new_value = State()


# =========================================================
# KEYBOARDS
# =========================================================
def main_menu(lang: str, user_id: int) -> ReplyKeyboardMarkup:
    if lang == "uz":
        keyboard = [
            [KeyboardButton(text="🛍 Do'kon"), KeyboardButton(text="🛒 Savatcha")],
            [KeyboardButton(text="📦 Buyurtmalarim"), KeyboardButton(text="📏 Razmer tanlash")],
            [KeyboardButton(text="📞 Aloqa"), KeyboardButton(text="🌐 Til")],
        ]
        if is_admin(user_id):
            keyboard.append([KeyboardButton(text="🛠 Admin")])
    else:
        keyboard = [
            [KeyboardButton(text="🛍 Магазин"), KeyboardButton(text="🛒 Корзина")],
            [KeyboardButton(text="📦 Мои заказы"), KeyboardButton(text="📏 Подбор размера")],
            [KeyboardButton(text="📞 Контакты"), KeyboardButton(text="🌐 Язык")],
        ]
        if is_admin(user_id):
            keyboard.append([KeyboardButton(text="🛠 Админ")])

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
                InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang_uz"),
            ]
        ]
    )


def shop_keyboard(lang: str) -> InlineKeyboardMarkup:
    text = "🛍 Открыть магазин" if lang == "ru" else "🛍 Do'konni ochish"
    url = f"{BASE_URL}/" if BASE_URL else "https://t.me"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url))]
        ]
    )


def cart_keyboard(lang: str) -> InlineKeyboardMarkup:
    if lang == "uz":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Buyurtma berish", callback_data="checkout_start")],
                [InlineKeyboardButton(text="🗑 Savatchani tozalash", callback_data="cart_clear")],
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Оформить заказ", callback_data="checkout_start")],
            [InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="cart_clear")],
        ]
    )


def admin_panel_keyboard(lang: str) -> InlineKeyboardMarkup:
    if lang == "uz":
        rows = [
            [InlineKeyboardButton(text="📦 Yangi buyurtmalar", callback_data="admin_orders_new")],
            [InlineKeyboardButton(text="📋 Barcha buyurtmalar", callback_data="admin_orders_all")],
            [InlineKeyboardButton(text="➕ Tovar qo‘shish", callback_data="admin_add_product")],
            [InlineKeyboardButton(text="📝 Tovarni tahrirlash", callback_data="admin_edit_product")],
            [InlineKeyboardButton(text="🗑 Tovarni o‘chirish", callback_data="admin_delete_product_menu")],
            [InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats")],
        ]
    else:
        rows = [
            [InlineKeyboardButton(text="📦 Новые заказы", callback_data="admin_orders_new")],
            [InlineKeyboardButton(text="📋 Все заказы", callback_data="admin_orders_all")],
            [InlineKeyboardButton(text="➕ Добавить товар", callback_data="admin_add_product")],
            [InlineKeyboardButton(text="📝 Редактировать товар", callback_data="admin_edit_product")],
            [InlineKeyboardButton(text="🗑 Удалить товар", callback_data="admin_delete_product_menu")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def delivery_keyboard(lang: str) -> InlineKeyboardMarkup:
    if lang == "uz":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🚚 Yandex kuryer", callback_data="delivery:yandex_courier")],
                [InlineKeyboardButton(text="📦 B2B pochta", callback_data="delivery:b2b_post")],
                [InlineKeyboardButton(text="🏪 Yandex PVZ", callback_data="delivery:yandex_pvz")],
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚚 Яндекс курьер", callback_data="delivery:yandex_courier")],
            [InlineKeyboardButton(text="📦 B2B почта", callback_data="delivery:b2b_post")],
            [InlineKeyboardButton(text="🏪 Яндекс ПВЗ", callback_data="delivery:yandex_pvz")],
        ]
    )


def address_type_keyboard(lang: str) -> InlineKeyboardMarkup:
    if lang == "uz":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📍 Lokatsiya yuborish", callback_data="addrtype:location")],
                [InlineKeyboardButton(text="✍️ Qo‘lda kiritish", callback_data="addrtype:manual")],
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📍 Отправить локацию", callback_data="addrtype:location")],
            [InlineKeyboardButton(text="✍️ Ввести вручную", callback_data="addrtype:manual")],
        ]
    )


def payment_keyboard(lang: str) -> InlineKeyboardMarkup:
    if lang == "uz":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💳 Click", callback_data="pay:click")],
                [InlineKeyboardButton(text="💳 Payme", callback_data="pay:payme")],
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Click", callback_data="pay:click")],
            [InlineKeyboardButton(text="💳 Payme", callback_data="pay:payme")],
        ]
    )


def confirm_order_keyboard(lang: str) -> InlineKeyboardMarkup:
    if lang == "uz":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="confirm_order_yes")],
                [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="confirm_order_no")],
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_order_yes")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="confirm_order_no")],
        ]
    )


def location_request_keyboard(lang: str) -> ReplyKeyboardMarkup:
    if lang == "uz":
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📍 Lokatsiyani yuborish", request_location=True)],
                [KeyboardButton(text="⬅️ Bekor qilish")],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Отправить геолокацию", request_location=True)],
            [KeyboardButton(text="⬅️ Отмена")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def order_admin_keyboard(order_id: int, user_id: Optional[int]) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="🟡 В работу", callback_data=f"order_status:{order_id}:processing"),
            InlineKeyboardButton(text="🟢 Подтвердить", callback_data=f"order_status:{order_id}:confirmed"),
        ],
        [
            InlineKeyboardButton(text="💳 Оплачен", callback_data=f"order_status:{order_id}:paid"),
            InlineKeyboardButton(text="🚚 Отправлен", callback_data=f"order_status:{order_id}:shipped"),
        ],
        [
            InlineKeyboardButton(text="✅ Доставлен", callback_data=f"order_status:{order_id}:delivered"),
            InlineKeyboardButton(text="❌ Отменён", callback_data=f"order_status:{order_id}:cancelled"),
        ],
    ]
    if user_id:
        rows.append([InlineKeyboardButton(text="📞 Написать клиенту", url=f"tg://user?id={user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_products_list_keyboard(products: List[Dict], action: str) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    for product in products[:20]:
        title = product.get("title_ru") or f"ID {product['id']}"
        rows.append([
            InlineKeyboardButton(
                text=f"{product['id']} • {title[:35]}",
                callback_data=f"{action}:{product['id']}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# =========================================================
# PART 1/4 END
# =========================================================

# =========================================================
# PART 2/4
# Что внутри:
# - common helpers for bot messages
# - start / language
# - main menu handlers
# - contacts / size picker / my orders
# - cart handlers
# - checkout FSM
# - client order confirmation
# =========================================================


# =========================================================
# BOT HELPERS
# =========================================================
def get_user_lang(user_id: int) -> str:
    user = db.user_get(user_id)
    return user_lang_or_default(user)


def get_full_name_from_user(message: Message) -> str:
    first_name = (message.from_user.first_name or "").strip()
    last_name = (message.from_user.last_name or "").strip()
    full_name = f"{first_name} {last_name}".strip()
    return full_name


def status_label(status: str, lang: str) -> str:
    ru_map = {
        "new": "Новый",
        "processing": "В обработке",
        "confirmed": "Подтверждён",
        "paid": "Оплачен",
        "shipped": "Отправлен",
        "delivered": "Доставлен",
        "cancelled": "Отменён",
    }
    uz_map = {
        "new": "Yangi",
        "processing": "Jarayonda",
        "confirmed": "Tasdiqlangan",
        "paid": "To‘langan",
        "shipped": "Yuborilgan",
        "delivered": "Yetkazilgan",
        "cancelled": "Bekor qilingan",
    }
    if lang == "uz":
        return uz_map.get(status, status)
    return ru_map.get(status, status)


def payment_label(method: str, lang: str) -> str:
    labels = {
        "click": "Click",
        "payme": "Payme",
    }
    return labels.get(method, method or ("—" if lang == "ru" else "—"))


def payment_status_label(status: str, lang: str) -> str:
    ru_map = {
        "pending": "Ожидает оплаты",
        "paid": "Оплачен",
        "failed": "Ошибка оплаты",
        "cancelled": "Отменён",
        "refunded": "Возврат",
    }
    uz_map = {
        "pending": "To‘lov kutilmoqda",
        "paid": "To‘langan",
        "failed": "To‘lovda xato",
        "cancelled": "Bekor qilingan",
        "refunded": "Qaytarilgan",
    }
    if lang == "uz":
        return uz_map.get(status, status)
    return ru_map.get(status, status)


def delivery_label(delivery_type: str, lang: str) -> str:
    ru_map = {
        "yandex_courier": "Яндекс курьер",
        "b2b_post": "B2B почта",
        "yandex_pvz": "Яндекс ПВЗ",
    }
    uz_map = {
        "yandex_courier": "Yandex kuryer",
        "b2b_post": "B2B pochta",
        "yandex_pvz": "Yandex PVZ",
    }
    if lang == "uz":
        return uz_map.get(delivery_type, delivery_type)
    return ru_map.get(delivery_type, delivery_type)


def cart_to_order_items(cart: List[Dict]) -> List[Dict]:
    items: List[Dict] = []
    for row in cart:
        items.append({
            "cart_id": row.get("id"),
            "product_id": row.get("product_id"),
            "product_name": row.get("product_name", ""),
            "name": row.get("product_name", ""),
            "price": safe_int(row.get("price"), 0),
            "qty": safe_int(row.get("qty"), 1),
            "size": row.get("size", ""),
            "photo_file_id": row.get("photo_file_id", ""),
        })
    return items


def format_cart_text(cart: List[Dict], lang: str) -> str:
    title = t(lang, "cart_title")
    if not cart:
        return t(lang, "cart_empty")

    lines = [title, ""]
    total_qty = 0
    total_amount = 0

    for idx, item in enumerate(cart, start=1):
        name = item.get("product_name", "—")
        qty = safe_int(item.get("qty"), 1)
        price = safe_int(item.get("price"), 0)
        size = item.get("size", "")
        line_total = qty * price

        total_qty += qty
        total_amount += line_total

        if lang == "uz":
            lines.append(
                f"{idx}. <b>{esc(name)}</b>\n"
                f"   Soni: {qty}\n"
                f"   Razmer: {esc(size or '—')}\n"
                f"   Narx: {money_fmt(price)} so'm\n"
                f"   Jami: {money_fmt(line_total)} so'm"
            )
        else:
            lines.append(
                f"{idx}. <b>{esc(name)}</b>\n"
                f"   Кол-во: {qty}\n"
                f"   Размер: {esc(size or '—')}\n"
                f"   Цена: {money_fmt(price)} сум\n"
                f"   Итого: {money_fmt(line_total)} сум"
            )

    lines.append("")
    if lang == "uz":
        lines.append(f"Jami soni: <b>{total_qty}</b>")
        lines.append(f"Umumiy summa: <b>{money_fmt(total_amount)} so'm</b>")
    else:
        lines.append(f"Всего позиций: <b>{total_qty}</b>")
        lines.append(f"Общая сумма: <b>{money_fmt(total_amount)} сум</b>")

    return "\n".join(lines)


def format_order_items(items_raw: str | List[Dict], lang: str) -> str:
    if isinstance(items_raw, str):
        try:
            items = json.loads(items_raw or "[]")
        except Exception:
            items = []
    else:
        items = items_raw

    if not items:
        return "—"

    lines = []
    for item in items:
        name = item.get("product_name") or item.get("name") or "item"
        qty = safe_int(item.get("qty"), 1)
        size = item.get("size", "")
        price = safe_int(item.get("price"), 0)
        if lang == "uz":
            lines.append(
                f"• {esc(name)} x{qty}"
                + (f" | {esc(size)}" if size else "")
                + (f" | {money_fmt(price)} so'm" if price else "")
            )
        else:
            lines.append(
                f"• {esc(name)} x{qty}"
                + (f" | {esc(size)}" if size else "")
                + (f" | {money_fmt(price)} сум" if price else "")
            )
    return "\n".join(lines)


def format_my_orders_text(orders: List[Dict], lang: str) -> str:
    if not orders:
        return t(lang, "orders_empty")

    if lang == "uz":
        lines = ["📦 <b>Buyurtmalaringiz</b>", ""]
    else:
        lines = ["📦 <b>Ваши заказы</b>", ""]

    for o in orders:
        created_at = (o.get("created_at") or "")[:16]
        order_id = o.get("id")
        total_amount = safe_int(o.get("total_amount"), 0)
        delivery = delivery_label(o.get("delivery_type", ""), lang)
        payment = payment_label(o.get("payment_method", ""), lang)
        status = status_label(o.get("status", ""), lang)
        pay_status = payment_status_label(o.get("payment_status", ""), lang)

        if lang == "uz":
            lines.append(
                f"№<b>{order_id}</b> | {created_at}\n"
                f"Holat: <b>{status}</b>\n"
                f"To‘lov: {payment} ({pay_status})\n"
                f"Yetkazish: {delivery}\n"
                f"Summa: <b>{money_fmt(total_amount)} so'm</b>"
            )
        else:
            lines.append(
                f"№<b>{order_id}</b> | {created_at}\n"
                f"Статус: <b>{status}</b>\n"
                f"Оплата: {payment} ({pay_status})\n"
                f"Доставка: {delivery}\n"
                f"Сумма: <b>{money_fmt(total_amount)} сум</b>"
            )
        lines.append("")

    return "\n".join(lines).strip()


def build_checkout_preview(data: Dict[str, Any], cart: List[Dict], lang: str) -> str:
    items_text = format_order_items(cart_to_order_items(cart), lang)
    totals = db.cart_totals(data["user_id"])
    delivery = delivery_label(data.get("delivery_type", ""), lang)
    payment = payment_label(data.get("payment_method", ""), lang)

    address = data.get("delivery_address", "")
    if data.get("delivery_type") == "yandex_pvz":
        address = data.get("pvz_address") or data.get("pvz_code") or address

    if data.get("latitude") and data.get("longitude"):
        geo_text = f"{data.get('latitude')}, {data.get('longitude')}"
    else:
        geo_text = "—"

    if lang == "uz":
        lines = [
            t(lang, "checkout_confirm"),
            "",
            f"👤 Ism: <b>{esc(data.get('customer_name', ''))}</b>",
            f"📞 Telefon: <b>{esc(data.get('customer_phone', ''))}</b>",
            f"🏙 Shahar: <b>{esc(data.get('city', ''))}</b>",
            f"🚚 Yetkazish: <b>{esc(delivery)}</b>",
            f"💳 To‘lov: <b>{esc(payment)}</b>",
            f"📍 Manzil: <b>{esc(address or '—')}</b>",
            f"🗺 Lokatsiya: <b>{esc(geo_text)}</b>",
            f"💬 Izoh: <b>{esc(data.get('comment', '—') or '—')}</b>",
            "",
            "🛍 <b>Tovarlar:</b>",
            items_text,
            "",
            f"📦 Jami soni: <b>{totals['total_qty']}</b>",
            f"💰 Jami summa: <b>{money_fmt(totals['total_amount'])} so'm</b>",
        ]
    else:
        lines = [
            t(lang, "checkout_confirm"),
            "",
            f"👤 Имя: <b>{esc(data.get('customer_name', ''))}</b>",
            f"📞 Телефон: <b>{esc(data.get('customer_phone', ''))}</b>",
            f"🏙 Город: <b>{esc(data.get('city', ''))}</b>",
            f"🚚 Доставка: <b>{esc(delivery)}</b>",
            f"💳 Оплата: <b>{esc(payment)}</b>",
            f"📍 Адрес: <b>{esc(address or '—')}</b>",
            f"🗺 Локация: <b>{esc(geo_text)}</b>",
            f"💬 Комментарий: <b>{esc(data.get('comment', '—') or '—')}</b>",
            "",
            "🛍 <b>Товары:</b>",
            items_text,
            "",
            f"📦 Всего: <b>{totals['total_qty']}</b>",
            f"💰 Сумма: <b>{money_fmt(totals['total_amount'])} сум</b>",
        ]
    return "\n".join(lines)


def build_admin_order_text(order: Dict, lang: str = "ru") -> str:
    items_text = format_order_items(order.get("items", "[]"), "ru")
    delivery = delivery_label(order.get("delivery_type", ""), "ru")
    payment = payment_label(order.get("payment_method", ""), "ru")
    pay_status = payment_status_label(order.get("payment_status", ""), "ru")
    status = status_label(order.get("status", ""), "ru")

    location_part = "—"
    if order.get("latitude") and order.get("longitude"):
        location_part = f"{order.get('latitude')}, {order.get('longitude')}"

    username = order.get("username") or ""
    username_line = f"@{username}" if username else "—"

    address = order.get("delivery_address") or ""
    if order.get("delivery_type") == "yandex_pvz":
        address = order.get("pvz_address") or order.get("pvz_code") or address

    return (
        f"🆕 <b>Новый заказ #{order.get('id')}</b>\n\n"
        f"👤 Имя: <b>{esc(order.get('customer_name') or '')}</b>\n"
        f"📞 Телефон: <b>{esc(order.get('customer_phone') or '')}</b>\n"
        f"👨‍💻 Username: <b>{esc(username_line)}</b>\n"
        f"🆔 User ID: <b>{esc(order.get('user_id') or '—')}</b>\n"
        f"🏙 Город: <b>{esc(order.get('city') or '—')}</b>\n"
        f"🚚 Доставка: <b>{esc(delivery)}</b>\n"
        f"📍 Адрес: <b>{esc(address or '—')}</b>\n"
        f"🗺 Локация: <b>{esc(location_part)}</b>\n"
        f"💳 Оплата: <b>{esc(payment)}</b>\n"
        f"💰 Статус оплаты: <b>{esc(pay_status)}</b>\n"
        f"📦 Статус заказа: <b>{esc(status)}</b>\n"
        f"💬 Комментарий: <b>{esc(order.get('comment') or '—')}</b>\n"
        f"🌐 Источник: <b>{esc(order.get('source') or 'bot')}</b>\n"
        f"🕒 Дата: <b>{esc(order.get('created_at') or '')}</b>\n\n"
        f"🛍 <b>Товары:</b>\n{items_text}\n\n"
        f"📦 Кол-во: <b>{safe_int(order.get('total_qty'), 0)}</b>\n"
        f"💵 Сумма: <b>{money_fmt(order.get('total_amount'))} сум</b>"
    )


async def ensure_user_record(message: Message) -> str:
    lang = get_user_lang(message.from_user.id)
    db.user_upsert(
        user_id=message.from_user.id,
        username=message.from_user.username or "",
        full_name=get_full_name_from_user(message),
        lang=lang,
    )
    return lang


async def send_order_to_admins(order_id: int) -> None:
    order = db.order_get(order_id)
    if not order:
        return

    text = build_admin_order_text(order)
    kb = order_admin_keyboard(order_id, order.get("user_id"))

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, reply_markup=kb)
        except Exception as e:
            print(f"Failed to send order to admin {admin_id}: {e}")


async def send_payment_stub(order: Dict, lang: str) -> None:
    """
    Пока это заглушка под Click / Payme.
    Архитектура уже готова, позже можно подключить реальные ссылки/API.
    """
    order_id = order.get("id")
    payment_method = order.get("payment_method")

    if payment_method == "click":
        fake_url = f"{BASE_URL}/pay/click/{order_id}" if BASE_URL else f"https://t.me/{CHANNEL_USERNAME}"
        db.order_update_payment(order_id, "pending", payment_provider_url=fake_url)
        if order.get("user_id"):
            if lang == "uz":
                text = (
                    f"💳 Click to‘lovi uchun havola:\n{fake_url}\n\n"
                    "To‘lovdan keyin status yangilanadi."
                )
            else:
                text = (
                    f"💳 Ссылка на оплату Click:\n{fake_url}\n\n"
                    "После оплаты статус будет обновлён."
                )
            try:
                await bot.send_message(order["user_id"], text)
            except Exception:
                pass

    elif payment_method == "payme":
        fake_url = f"{BASE_URL}/pay/payme/{order_id}" if BASE_URL else f"https://t.me/{CHANNEL_USERNAME}"
        db.order_update_payment(order_id, "pending", payment_provider_url=fake_url)
        if order.get("user_id"):
            if lang == "uz":
                text = (
                    f"💳 Payme to‘lovi uchun havola:\n{fake_url}\n\n"
                    "To‘lovdan keyin status yangilanadi."
                )
            else:
                text = (
                    f"💳 Ссылка на оплату Payme:\n{fake_url}\n\n"
                    "После оплаты статус будет обновлён."
                )
            try:
                await bot.send_message(order["user_id"], text)
            except Exception:
                pass


# =========================================================
# START / LANGUAGE
# =========================================================
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()

    user_id = message.from_user.id
    user = db.user_get(user_id)
    lang = user_lang_or_default(user)

    db.user_upsert(
        user_id=user_id,
        username=message.from_user.username or "",
        full_name=get_full_name_from_user(message),
        lang=lang,
    )

    await message.answer(
        t(lang, "welcome"),
        reply_markup=main_menu(lang, user_id),
    )


@dp.message(F.text.in_(["🌐 Язык", "🌐 Til"]))
async def choose_language(message: Message):
    lang = await ensure_user_record(message)
    text = "Выберите язык:" if lang == "ru" else "Tilni tanlang:"
    await message.answer(text, reply_markup=language_keyboard())


@dp.callback_query(F.data.in_(["lang_ru", "lang_uz"]))
async def set_language(cb: CallbackQuery):
    lang = "uz" if cb.data == "lang_uz" else "ru"

    db.user_upsert(
        user_id=cb.from_user.id,
        username=cb.from_user.username or "",
        full_name=f"{cb.from_user.first_name or ''} {cb.from_user.last_name or ''}".strip(),
        lang=lang,
    )
    db.user_set_lang(cb.from_user.id, lang)

    text = "✅ Язык изменён." if lang == "ru" else "✅ Til o‘zgartirildi."
    await cb.message.edit_text(text)
    await cb.message.answer(
        t(lang, "welcome"),
        reply_markup=main_menu(lang, cb.from_user.id),
    )
    await cb.answer()


# =========================================================
# MAIN MENU
# =========================================================
@dp.message(F.text.in_(["🛍 Магазин", "🛍 Do'kon"]))
async def open_shop(message: Message):
    lang = await ensure_user_record(message)
    await message.answer(
        t(lang, "shop_open"),
        reply_markup=shop_keyboard(lang),
    )


@dp.message(F.text.in_(["📞 Контакты", "📞 Aloqa"]))
async def show_contacts(message: Message):
    lang = await ensure_user_record(message)
    await message.answer(t(lang, "contacts"))


@dp.message(F.text.in_(["📦 Мои заказы", "📦 Buyurtmalarim"]))
async def show_my_orders(message: Message):
    lang = await ensure_user_record(message)
    orders = db.orders_get_user(message.from_user.id, limit=10)
    await message.answer(format_my_orders_text(orders, lang))


@dp.message(F.text.in_(["📏 Подбор размера", "📏 Razmer tanlash"]))
async def size_picker_start(message: Message, state: FSMContext):
    lang = await ensure_user_record(message)
    await state.set_state(SizeStates.waiting_input)
    await message.answer(t(lang, "size_help"))


@dp.message(SizeStates.waiting_input)
async def size_picker_process(message: Message, state: FSMContext):
    lang = await ensure_user_record(message)
    text = (message.text or "").strip()

    if not text.isdigit():
        if lang == "uz":
            await message.answer("Iltimos, faqat raqam yuboring. Masalan: 6 yoki 128")
        else:
            await message.answer("Пожалуйста, отправьте только число. Например: 6 или 128")
        return

    value = int(text)

    if 1 <= value <= 15:
        size = size_by_age(value)
        if lang == "uz":
            reply = f"✅ Tavsiya etilgan razmer: <b>{size}</b>\n(Yosh bo‘yicha: {value})"
        else:
            reply = f"✅ Рекомендуемый размер: <b>{size}</b>\n(По возрасту: {value})"
    elif 80 <= value <= 170:
        size = size_by_height(value)
        if lang == "uz":
            reply = f"✅ Tavsiya etilgan razmer: <b>{size}</b>\n(Bo‘y bo‘yicha: {value} sm)"
        else:
            reply = f"✅ Рекомендуемый размер: <b>{size}</b>\n(По росту: {value} см)"
    else:
        if lang == "uz":
            reply = "Mos qiymat kiriting: yosh uchun 1–15, bo‘y uchun 80–170."
        else:
            reply = "Введите подходящее значение: возраст 1–15, рост 80–170."
        await message.answer(reply)
        return

    await message.answer(reply, reply_markup=main_menu(lang, message.from_user.id))
    await state.clear()


# =========================================================
# CART
# =========================================================
@dp.message(F.text.in_(["🛒 Корзина", "🛒 Savatcha"]))
async def open_cart(message: Message):
    lang = await ensure_user_record(message)
    cart = db.cart_get(message.from_user.id)

    if not cart:
        await message.answer(t(lang, "cart_empty"))
        return

    await message.answer(
        format_cart_text(cart, lang),
        reply_markup=cart_keyboard(lang),
    )


@dp.callback_query(F.data == "cart_clear")
async def cart_clear_handler(cb: CallbackQuery):
    lang = get_user_lang(cb.from_user.id)
    db.cart_clear(cb.from_user.id)

    if lang == "uz":
        await cb.message.edit_text("🗑 Savatcha tozalandi.")
    else:
        await cb.message.edit_text("🗑 Корзина очищена.")
    await cb.answer()


# =========================================================
# CHECKOUT FSM
# =========================================================
@dp.callback_query(F.data == "checkout_start")
async def checkout_start(cb: CallbackQuery, state: FSMContext):
    lang = get_user_lang(cb.from_user.id)
    cart = db.cart_get(cb.from_user.id)

    if not cart:
        await cb.answer("Корзина пустая" if lang == "ru" else "Savatcha bo‘sh", show_alert=True)
        return

    await state.clear()
    await state.update_data(user_id=cb.from_user.id, lang=lang)

    await cb.message.answer(t(lang, "checkout_start_name"))
    await state.set_state(OrderStates.waiting_name)
    await cb.answer()


@dp.message(OrderStates.waiting_name)
async def checkout_name(message: Message, state: FSMContext):
    lang = await ensure_user_record(message)
    name = (message.text or "").strip()

    if len(name) < 2:
        if lang == "uz":
            await message.answer("Iltimos, ismingizni to‘liqroq kiriting.")
        else:
            await message.answer("Пожалуйста, введите имя корректно.")
        return

    await state.update_data(customer_name=name)
    await message.answer(t(lang, "checkout_phone"))
    await state.set_state(OrderStates.waiting_phone)


@dp.message(OrderStates.waiting_phone)
async def checkout_phone(message: Message, state: FSMContext):
    lang = await ensure_user_record(message)
    phone = normalize_phone((message.text or "").strip())

    if not phone_is_valid(phone):
        if lang == "uz":
            await message.answer("Telefon raqamini to‘g‘ri kiriting. Masalan: +998901234567")
        else:
            await message.answer("Введите телефон корректно. Например: +998901234567")
        return

    await state.update_data(customer_phone=phone)
    await message.answer(
        t(lang, "checkout_delivery"),
        reply_markup=delivery_keyboard(lang),
    )
    await state.set_state(OrderStates.waiting_delivery)


@dp.callback_query(OrderStates.waiting_delivery, F.data.startswith("delivery:"))
async def checkout_delivery(cb: CallbackQuery, state: FSMContext):
    lang = get_user_lang(cb.from_user.id)
    delivery_type = cb.data.split(":", 1)[1]

    if delivery_type not in DELIVERY_TYPES:
        await cb.answer("Ошибка")
        return

    await state.update_data(delivery_type=delivery_type, delivery_service=delivery_type)

    if delivery_type == "yandex_pvz":
        await cb.message.answer(t(lang, "checkout_city"))
        await state.set_state(OrderStates.waiting_city)
    else:
        await cb.message.answer(
            t(lang, "checkout_address_type"),
            reply_markup=address_type_keyboard(lang),
        )
        await state.set_state(OrderStates.waiting_address_type)

    await cb.answer()


@dp.callback_query(OrderStates.waiting_address_type, F.data.startswith("addrtype:"))
async def checkout_address_type(cb: CallbackQuery, state: FSMContext):
    lang = get_user_lang(cb.from_user.id)
    address_type = cb.data.split(":", 1)[1]

    await state.update_data(address_type=address_type)

    if address_type == "manual":
        await cb.message.answer(t(lang, "checkout_city"))
        await state.set_state(OrderStates.waiting_city)
    elif address_type == "location":
        await cb.message.answer(
            t(lang, "checkout_location_wait"),
            reply_markup=location_request_keyboard(lang),
        )
        await state.set_state(OrderStates.waiting_location)
    else:
        await cb.answer("Ошибка")
        return

    await cb.answer()


@dp.message(OrderStates.waiting_location, F.location)
async def checkout_location_received(message: Message, state: FSMContext):
    lang = await ensure_user_record(message)

    latitude = message.location.latitude
    longitude = message.location.longitude

    await state.update_data(latitude=latitude, longitude=longitude)
    await message.answer(
        t(lang, "checkout_city"),
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(OrderStates.waiting_city)


@dp.message(OrderStates.waiting_location)
async def checkout_location_text_fallback(message: Message, state: FSMContext):
    lang = await ensure_user_record(message)

    cancel_texts = ["⬅️ Отмена", "⬅️ Bekor qilish"]
    if (message.text or "").strip() in cancel_texts:
        await state.clear()
        if lang == "uz":
            await message.answer("Bekor qilindi.", reply_markup=main_menu(lang, message.from_user.id))
        else:
            await message.answer("Отменено.", reply_markup=main_menu(lang, message.from_user.id))
        return

    if lang == "uz":
        await message.answer("Iltimos, lokatsiyani tugma orqali yuboring.")
    else:
        await message.answer("Пожалуйста, отправьте геолокацию кнопкой.")


@dp.message(OrderStates.waiting_city)
async def checkout_city(message: Message, state: FSMContext):
    lang = await ensure_user_record(message)
    city = (message.text or "").strip()

    if len(city) < 2:
        if lang == "uz":
            await message.answer("Shahar nomini kiriting.")
        else:
            await message.answer("Введите город.")
        return

    await state.update_data(city=city)
    data = await state.get_data()
    delivery_type = data.get("delivery_type")

    if delivery_type == "yandex_pvz":
        await message.answer(t(lang, "checkout_pvz"))
        await state.set_state(OrderStates.waiting_pvz)
        return

    address_type = data.get("address_type")
    if address_type == "manual":
        await message.answer(t(lang, "checkout_address_manual"))
        await state.set_state(OrderStates.waiting_manual_address)
    elif address_type == "location":
        await state.update_data(delivery_address="Локация отправлена" if lang == "ru" else "Lokatsiya yuborildi")
        await message.answer(t(lang, "checkout_payment"), reply_markup=payment_keyboard(lang))
        await state.set_state(OrderStates.waiting_payment)
    else:
        await message.answer(t(lang, "checkout_address_type"), reply_markup=address_type_keyboard(lang))
        await state.set_state(OrderStates.waiting_address_type)


@dp.message(OrderStates.waiting_manual_address)
async def checkout_manual_address(message: Message, state: FSMContext):
    lang = await ensure_user_record(message)
    address = (message.text or "").strip()

    if len(address) < 4:
        if lang == "uz":
            await message.answer("Manzilni to‘liqroq kiriting.")
        else:
            await message.answer("Введите адрес подробнее.")
        return

    await state.update_data(delivery_address=address)
    await message.answer(t(lang, "checkout_payment"), reply_markup=payment_keyboard(lang))
    await state.set_state(OrderStates.waiting_payment)


@dp.message(OrderStates.waiting_pvz)
async def checkout_pvz(message: Message, state: FSMContext):
    lang = await ensure_user_record(message)
    pvz = (message.text or "").strip()

    if len(pvz) < 2:
        if lang == "uz":
            await message.answer("PVZ manzili yoki kodini kiriting.")
        else:
            await message.answer("Введите адрес или код ПВЗ.")
        return

    await state.update_data(
        pvz_code=pvz,
        pvz_address=pvz,
        delivery_address=pvz,
    )
    await message.answer(t(lang, "checkout_payment"), reply_markup=payment_keyboard(lang))
    await state.set_state(OrderStates.waiting_payment)


@dp.callback_query(OrderStates.waiting_payment, F.data.startswith("pay:"))
async def checkout_payment(cb: CallbackQuery, state: FSMContext):
    lang = get_user_lang(cb.from_user.id)
    payment_method = cb.data.split(":", 1)[1]

    if payment_method not in PAYMENT_METHODS:
        await cb.answer("Ошибка")
        return

    await state.update_data(payment_method=payment_method, payment_status="pending")
    await cb.message.answer(t(lang, "checkout_comment"))
    await state.set_state(OrderStates.waiting_comment)
    await cb.answer()


@dp.message(OrderStates.waiting_comment)
async def checkout_comment(message: Message, state: FSMContext):
    lang = await ensure_user_record(message)
    comment = (message.text or "").strip()
    if comment == "-":
        comment = ""

    await state.update_data(comment=comment)

    data = await state.get_data()
    cart = db.cart_get(message.from_user.id)
    if not cart:
        if lang == "uz":
            await message.answer("Savatcha bo‘sh.")
        else:
            await message.answer("Корзина пустая.")
        await state.clear()
        return

    preview = build_checkout_preview(data, cart, lang)
    await message.answer(
        preview,
        reply_markup=confirm_order_keyboard(lang),
    )
    await state.set_state(OrderStates.waiting_confirm)


@dp.callback_query(OrderStates.waiting_confirm, F.data == "confirm_order_no")
async def checkout_cancel(cb: CallbackQuery, state: FSMContext):
    lang = get_user_lang(cb.from_user.id)
    await state.clear()

    if lang == "uz":
        await cb.message.edit_text("❌ Buyurtma bekor qilindi.")
    else:
        await cb.message.edit_text("❌ Заказ отменён.")

    await cb.message.answer(
        t(lang, "welcome"),
        reply_markup=main_menu(lang, cb.from_user.id),
    )
    await cb.answer()


@dp.callback_query(OrderStates.waiting_confirm, F.data == "confirm_order_yes")
async def checkout_confirm(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang") or get_user_lang(cb.from_user.id)

    cart = db.cart_get(cb.from_user.id)
    if not cart:
        await state.clear()
        await cb.answer("Корзина пуста" if lang == "ru" else "Savatcha bo‘sh", show_alert=True)
        return

    items = cart_to_order_items(cart)
    totals = db.cart_totals(cb.from_user.id)

    order_id = db.order_create({
        "user_id": cb.from_user.id,
        "username": cb.from_user.username or "",
        "customer_name": data.get("customer_name", ""),
        "customer_phone": data.get("customer_phone", ""),
        "city": data.get("city", ""),
        "items": items,
        "total_qty": totals["total_qty"],
        "total_amount": totals["total_amount"],
        "delivery_service": data.get("delivery_type", ""),
        "delivery_type": data.get("delivery_type", ""),
        "delivery_address": data.get("delivery_address", ""),
        "latitude": data.get("latitude"),
        "longitude": data.get("longitude"),
        "pvz_code": data.get("pvz_code", ""),
        "pvz_address": data.get("pvz_address", ""),
        "payment_method": data.get("payment_method", ""),
        "payment_status": "pending",
        "comment": data.get("comment", ""),
        "status": "new",
        "source": "bot",
    })

    order = db.order_get(order_id)
    db.cart_clear(cb.from_user.id)

    if lang == "uz":
        text = (
            f"✅ Buyurtmangiz №<b>{order_id}</b> qabul qilindi.\n\n"
            + t(lang, "thanks_order")
        )
    else:
        text = (
            f"✅ Ваш заказ №<b>{order_id}</b> принят.\n\n"
            + t(lang, "thanks_order")
        )

    await cb.message.edit_text(text)
    await cb.message.answer(
        t(lang, "welcome"),
        reply_markup=main_menu(lang, cb.from_user.id),
    )

    await send_order_to_admins(order_id)

    if order:
        await send_payment_stub(order, lang)

    await state.clear()
    await cb.answer()


# =========================================================
# FALLBACK HELPERS
# =========================================================
@dp.message(F.text.in_(["/menu", "меню", "menu"]))
async def menu_command(message: Message, state: FSMContext):
    lang = await ensure_user_record(message)
    await state.clear()
    await message.answer(
        t(lang, "welcome"),
        reply_markup=main_menu(lang, message.from_user.id),
    )


@dp.message(Command("cancel"))
async def universal_cancel(message: Message, state: FSMContext):
    lang = await ensure_user_record(message)
    await state.clear()

    if lang == "uz":
        await message.answer("Bekor qilindi.", reply_markup=main_menu(lang, message.from_user.id))
    else:
        await message.answer("Отменено.", reply_markup=main_menu(lang, message.from_user.id))


# =========================================================
# PART 2/4 END
# =========================================================

# =========================================================
# PART 3/4
# ADMIN PANEL
# PRODUCT MANAGEMENT
# ORDER MANAGEMENT
# =========================================================

# ================================
# ADMIN PANEL
# ================================

@dp.message(F.text.in_(["🛠 Админ","🛠 Admin"]))
async def admin_panel(message: Message):
    
    if message.from_user.id not in ADMIN_IDS:
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Заказы", callback_data="admin_orders")],
        [InlineKeyboardButton(text="🛍 Товары", callback_data="admin_products")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")]
    ])

    await message.answer("🛠 Админ панель", reply_markup=kb)


# ================================
# ADMIN ORDERS
# ================================

@dp.callback_query(F.data=="admin_orders")
async def admin_orders(cb: CallbackQuery):

    if cb.from_user.id not in ADMIN_IDS:
        return

    orders = db.orders_recent()

    if not orders:
        await cb.message.answer("Нет заказов")
        return

    for o in orders:

        text = build_admin_order_text(o)

        kb = order_admin_keyboard(o["id"], o["user_id"])

        await cb.message.answer(text, reply_markup=kb)

    await cb.answer()


# ================================
# ORDER STATUS CHANGE
# ================================

@dp.callback_query(F.data.startswith("order_status:"))
async def order_status_update(cb: CallbackQuery):

    if cb.from_user.id not in ADMIN_IDS:
        return

    _,order_id,status = cb.data.split(":")

    db.order_update_status(int(order_id),status)

    await cb.answer("Статус обновлен")


# ================================
# PRODUCT MENU
# ================================

@dp.callback_query(F.data=="admin_products")
async def admin_products(cb: CallbackQuery):

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить товар", callback_data="add_product")],
        [InlineKeyboardButton(text="📋 Список товаров", callback_data="list_products")]
    ])

    await cb.message.answer("🛍 Управление товарами",reply_markup=kb)

    await cb.answer()


# ================================
# ADD PRODUCT
# ================================

@dp.callback_query(F.data=="add_product")
async def add_product_start(cb: CallbackQuery,state:FSMContext):

    await state.set_state(AdminProductStates.wait_photo)

    await cb.message.answer("Отправьте фото товара")

    await cb.answer()


@dp.message(AdminProductStates.wait_photo, F.photo)
async def add_product_photo(message:Message,state:FSMContext):

    photo = message.photo[-1].file_id

    await state.update_data(photo=photo)

    await message.answer("Введите название RU")

    await state.set_state(AdminProductStates.wait_title_ru)


@dp.message(AdminProductStates.wait_title_ru)
async def add_product_title_ru(message:Message,state:FSMContext):

    await state.update_data(title_ru=message.text)

    await message.answer("Введите название UZ")

    await state.set_state(AdminProductStates.wait_title_uz)


@dp.message(AdminProductStates.wait_title_uz)
async def add_product_title_uz(message:Message,state:FSMContext):

    await state.update_data(title_uz=message.text)

    await message.answer("Введите цену")

    await state.set_state(AdminProductStates.wait_price)


@dp.message(AdminProductStates.wait_price)
async def add_product_price(message:Message,state:FSMContext):

    price=int(message.text)

    await state.update_data(price=price)

    await message.answer("Введите описание")

    await state.set_state(AdminProductStates.wait_description)


@dp.message(AdminProductStates.wait_description)
async def add_product_description(message:Message,state:FSMContext):

    data=await state.get_data()

    db.product_add({
        "photo_file_id":data["photo"],
        "title_ru":data["title_ru"],
        "title_uz":data["title_uz"],
        "price":data["price"],
        "description_ru":message.text,
        "description_uz":message.text
    })

    await message.answer("✅ Товар добавлен")

    await state.clear()


# ================================
# PRODUCT LIST
# ================================

@dp.callback_query(F.data=="list_products")
async def list_products(cb:CallbackQuery):

    products=db.products_all()

    if not products:

        await cb.message.answer("Нет товаров")

        return

    kb=admin_products_list_keyboard(products,"delete_product")

    await cb.message.answer("Выберите товар",reply_markup=kb)


# ================================
# DELETE PRODUCT
# ================================

@dp.callback_query(F.data.startswith("delete_product:"))
async def delete_product(cb:CallbackQuery):

    _,pid=cb.data.split(":")

    db.product_delete(int(pid))

    await cb.answer("Товар удален")

# ================================
# ADMIN STATS
# ================================

@dp.callback_query(F.data=="admin_stats")
async def admin_stats(cb:CallbackQuery):

    stats=db.stats()

    text=(
        f"📊 Статистика\n\n"
        f"Заказы: {stats['orders']}\n"
        f"Пользователи: {stats['users']}\n"
        f"Товары: {stats['products']}"
    )

    await cb.message.answer(text)

    await cb.answer()


# =========================================================
# PART 3/4 END
# =========================================================

# =========================================================
# PART 3/4
# - admin panel
# - admin orders
# - admin products add/edit/delete/publish
# - stats
# - reminders
# - reports
# - scheduled posts
# =========================================================


# =========================================================
# EXTRA TEXT HELPERS
# =========================================================
def admin_text(lang: str, ru_text: str, uz_text: str) -> str:
    return uz_text if lang == "uz" else ru_text


def product_card_text(product: Dict, lang: str = "ru") -> str:
    title = product.get("title_uz") if lang == "uz" else product.get("title_ru")
    desc = product.get("description_uz") if lang == "uz" else product.get("description_ru")
    sizes = product.get("sizes") or "—"
    category = product.get("category_slug") or "casual"
    price = safe_int(product.get("price"), 0)
    old_price = safe_int(product.get("old_price"), 0)
    stock_qty = safe_int(product.get("stock_qty"), 0)
    is_published = safe_int(product.get("is_published"), 1)

    if lang == "uz":
        lines = [
            f"🆔 ID: <b>{product.get('id')}</b>",
            f"🛍 Nomi: <b>{esc(title or '')}</b>",
            f"📝 Tavsif: {esc(desc or '—')}",
            f"📏 Razmerlar: <b>{esc(sizes)}</b>",
            f"🏷 Kategoriya: <b>{esc(category)}</b>",
            f"💰 Narx: <b>{money_fmt(price)} so'm</b>",
            f"💸 Eski narx: <b>{money_fmt(old_price)} so'm</b>" if old_price else "💸 Eski narx: —",
            f"📦 Qoldiq: <b>{stock_qty}</b>",
            f"👁 Holat: <b>{'Ko‘rinadi' if is_published else 'Yashirin'}</b>",
        ]
    else:
        lines = [
            f"🆔 ID: <b>{product.get('id')}</b>",
            f"🛍 Название: <b>{esc(title or '')}</b>",
            f"📝 Описание: {esc(desc or '—')}",
            f"📏 Размеры: <b>{esc(sizes)}</b>",
            f"🏷 Категория: <b>{esc(category)}</b>",
            f"💰 Цена: <b>{money_fmt(price)} сум</b>",
            f"💸 Старая цена: <b>{money_fmt(old_price)} сум</b>" if old_price else "💸 Старая цена: —",
            f"📦 Остаток: <b>{stock_qty}</b>",
            f"👁 Статус: <b>{'Опубликован' if is_published else 'Скрыт'}</b>",
        ]
    return "\n".join(lines)


def admin_product_actions_keyboard(product_id: int, is_published: int) -> InlineKeyboardMarkup:
    publish_text = "🙈 Скрыть" if is_published else "👁 Опубликовать"
    publish_value = 0 if is_published else 1

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏ Изменить поле", callback_data=f"admin_edit_pick:{product_id}"),
                InlineKeyboardButton(text=publish_text, callback_data=f"admin_publish:{product_id}:{publish_value}"),
            ],
            [
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_delete_product:{product_id}"),
            ]
        ]
    )


def admin_edit_fields_keyboard(product_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🖼 Фото", callback_data=f"edit_field:{product_id}:photo_file_id")],
            [InlineKeyboardButton(text="🇷🇺 Название RU", callback_data=f"edit_field:{product_id}:title_ru")],
            [InlineKeyboardButton(text="🇺🇿 Название UZ", callback_data=f"edit_field:{product_id}:title_uz")],
            [InlineKeyboardButton(text="📝 Описание RU", callback_data=f"edit_field:{product_id}:description_ru")],
            [InlineKeyboardButton(text="📝 Описание UZ", callback_data=f"edit_field:{product_id}:description_uz")],
            [InlineKeyboardButton(text="📏 Размеры", callback_data=f"edit_field:{product_id}:sizes")],
            [InlineKeyboardButton(text="🏷 Категория", callback_data=f"edit_field:{product_id}:category_slug")],
            [InlineKeyboardButton(text="💰 Цена", callback_data=f"edit_field:{product_id}:price")],
            [InlineKeyboardButton(text="💸 Старая цена", callback_data=f"edit_field:{product_id}:old_price")],
            [InlineKeyboardButton(text="📦 Остаток", callback_data=f"edit_field:{product_id}:stock_qty")],
            [InlineKeyboardButton(text="↕ Сортировка", callback_data=f"edit_field:{product_id}:sort_order")],
        ]
    )


def format_orders_short_list(orders: List[Dict]) -> str:
    if not orders:
        return "Нет заказов."
    lines = []
    for o in orders[:30]:
        lines.append(
            f"#{o['id']} | {esc((o.get('created_at') or '')[:16])} | "
            f"{esc(o.get('customer_name') or '')} | "
            f"{esc(o.get('customer_phone') or '')} | "
            f"{status_label(o.get('status') or '', 'ru')}"
        )
    return "\n".join(lines)


# =========================================================
# ADMIN ACCESS
# =========================================================
def admin_only(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# =========================================================
# ADMIN MENU
# =========================================================
@dp.message(F.text.in_(["🛠 Админ", "🛠 Admin"]))
async def admin_panel_open(message: Message):
    if not admin_only(message.from_user.id):
        return

    lang = get_user_lang(message.from_user.id)
    text = admin_text(lang, "🛠 Админ панель", "🛠 Admin panel")
    await message.answer(text, reply_markup=admin_panel_keyboard(lang))


# =========================================================
# ADMIN ORDERS
# =========================================================
@dp.callback_query(F.data == "admin_orders_new")
async def admin_orders_new(cb: CallbackQuery):
    if not admin_only(cb.from_user.id):
        await cb.answer()
        return

    orders = db.orders_get_by_status("new", limit=20)
    if not orders:
        await cb.message.answer("Новых заказов нет.")
        await cb.answer()
        return

    for order in orders:
        db.order_mark_seen(order["id"], cb.from_user.id)
        await cb.message.answer(
            build_admin_order_text(order),
            reply_markup=order_admin_keyboard(order["id"], order.get("user_id")),
        )

    await cb.answer()


@dp.callback_query(F.data == "admin_orders_all")
async def admin_orders_all(cb: CallbackQuery):
    if not admin_only(cb.from_user.id):
        await cb.answer()
        return

    orders = db.orders_filter(limit=30)
    if not orders:
        await cb.message.answer("Заказов пока нет.")
        await cb.answer()
        return

    await cb.message.answer("📋 Последние заказы:\n\n" + format_orders_short_list(orders))
    await cb.answer()


@dp.message(Command("find"))
async def admin_find_orders(message: Message):
    if not admin_only(message.from_user.id):
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /find 90 или /find 901234")
        return

    phone_part = parts[1].strip()
    rows = db.find_orders_by_phone(phone_part, limit=20)
    if not rows:
        await message.answer("Ничего не найдено.")
        return

    for order in rows:
        await message.answer(
            build_admin_order_text(order),
            reply_markup=order_admin_keyboard(order["id"], order.get("user_id")),
        )


@dp.callback_query(F.data.startswith("order_status:"))
async def order_status_update(cb: CallbackQuery):
    if not admin_only(cb.from_user.id):
        await cb.answer()
        return

    try:
        _, order_id_str, new_status = cb.data.split(":")
        order_id = int(order_id_str)
    except Exception:
        await cb.answer("Ошибка")
        return

    if new_status not in ORDER_STATUSES:
        await cb.answer("Неверный статус")
        return

    db.order_update_status(order_id, new_status, manager_id=cb.from_user.id)
    order = db.order_get(order_id)

    await cb.answer("Статус обновлён")

    if order and order.get("user_id"):
        user_lang = get_user_lang(order["user_id"])
        if user_lang == "uz":
            text = f"📦 Buyurtmangiz №{order_id} holati yangilandi: <b>{status_label(new_status, 'uz')}</b>"
        else:
            text = f"📦 Статус вашего заказа №{order_id} обновлён: <b>{status_label(new_status, 'ru')}</b>"

        try:
            await bot.send_message(order["user_id"], text)
        except Exception:
            pass

    try:
        await cb.message.edit_reply_markup(reply_markup=order_admin_keyboard(order_id, order.get("user_id") if order else None))
    except Exception:
        pass


# =========================================================
# ADMIN PRODUCT MENU
# =========================================================
@dp.callback_query(F.data == "admin_add_product")
async def admin_add_product_start(cb: CallbackQuery, state: FSMContext):
    if not admin_only(cb.from_user.id):
        await cb.answer()
        return

    await state.clear()
    await state.set_state(AdminAddProductStates.waiting_photo)
    await cb.message.answer("📸 Отправьте фото товара.")
    await cb.answer()


@dp.callback_query(F.data == "admin_edit_product")
async def admin_edit_product_menu(cb: CallbackQuery):
    if not admin_only(cb.from_user.id):
        await cb.answer()
        return

    products = db.shop_products_list(published_only=False, limit=50)
    if not products:
        await cb.message.answer("Товаров пока нет.")
        await cb.answer()
        return

    await cb.message.answer(
        "Выберите товар для редактирования:",
        reply_markup=admin_products_list_keyboard(products, "admin_edit_pick"),
    )
    await cb.answer()


@dp.callback_query(F.data == "admin_delete_product_menu")
async def admin_delete_product_menu(cb: CallbackQuery):
    if not admin_only(cb.from_user.id):
        await cb.answer()
        return

    products = db.shop_products_list(published_only=False, limit=50)
    if not products:
        await cb.message.answer("Товаров пока нет.")
        await cb.answer()
        return

    await cb.message.answer(
        "Выберите товар для удаления:",
        reply_markup=admin_products_list_keyboard(products, "admin_delete_product"),
    )
    await cb.answer()


# =========================================================
# ADD PRODUCT FSM
# =========================================================
@dp.message(AdminAddProductStates.waiting_photo, F.photo)
async def add_product_photo(message: Message, state: FSMContext):
    if not admin_only(message.from_user.id):
        return

    photo_file_id = message.photo[-1].file_id
    await state.update_data(photo_file_id=photo_file_id)
    await state.set_state(AdminAddProductStates.waiting_title_ru)
    await message.answer("🇷🇺 Введите название товара на русском:")


@dp.message(AdminAddProductStates.waiting_photo)
async def add_product_photo_invalid(message: Message):
    if not admin_only(message.from_user.id):
        return
    await message.answer("Нужно отправить именно фото товара.")


@dp.message(AdminAddProductStates.waiting_title_ru)
async def add_product_title_ru(message: Message, state: FSMContext):
    await state.update_data(title_ru=(message.text or "").strip())
    await state.set_state(AdminAddProductStates.waiting_title_uz)
    await message.answer("🇺🇿 Введите название товара на узбекском:")


@dp.message(AdminAddProductStates.waiting_title_uz)
async def add_product_title_uz(message: Message, state: FSMContext):
    await state.update_data(title_uz=(message.text or "").strip())
    await state.set_state(AdminAddProductStates.waiting_desc_ru)
    await message.answer("📝 Введите описание на русском:")


@dp.message(AdminAddProductStates.waiting_desc_ru)
async def add_product_desc_ru(message: Message, state: FSMContext):
    await state.update_data(description_ru=(message.text or "").strip())
    await state.set_state(AdminAddProductStates.waiting_desc_uz)
    await message.answer("📝 Введите описание на узбекском:")


@dp.message(AdminAddProductStates.waiting_desc_uz)
async def add_product_desc_uz(message: Message, state: FSMContext):
    await state.update_data(description_uz=(message.text or "").strip())
    await state.set_state(AdminAddProductStates.waiting_sizes)
    await message.answer("📏 Введите размеры через запятую. Например: 98,104,110,116")


@dp.message(AdminAddProductStates.waiting_sizes)
async def add_product_sizes(message: Message, state: FSMContext):
    await state.update_data(sizes=(message.text or "").strip())
    await state.set_state(AdminAddProductStates.waiting_category)
    await message.answer(
        "🏷 Введите категорию:\n"
        "new / hits / sale / limited / school / casual"
    )


@dp.message(AdminAddProductStates.waiting_category)
async def add_product_category(message: Message, state: FSMContext):
    category = (message.text or "").strip().lower()
    if category not in SHOP_CATEGORIES:
        await message.answer("Неверная категория. Введите одну из: new, hits, sale, limited, school, casual")
        return

    await state.update_data(category_slug=category)
    await state.set_state(AdminAddProductStates.waiting_price)
    await message.answer("💰 Введите цену товара цифрами. Например: 250000")


@dp.message(AdminAddProductStates.waiting_price)
async def add_product_price(message: Message, state: FSMContext):
    text = (message.text or "").strip().replace(" ", "")
    if not text.isdigit():
        await message.answer("Цена должна быть числом.")
        return

    await state.update_data(price=int(text))
    await state.set_state(AdminAddProductStates.waiting_old_price)
    await message.answer("💸 Введите старую цену цифрами или 0 если её нет.")


@dp.message(AdminAddProductStates.waiting_old_price)
async def add_product_old_price(message: Message, state: FSMContext):
    text = (message.text or "").strip().replace(" ", "")
    if not text.isdigit():
        await message.answer("Старая цена должна быть числом.")
        return

    await state.update_data(old_price=int(text))
    await state.set_state(AdminAddProductStates.waiting_stock_qty)
    await message.answer("📦 Введите остаток товара. Например: 10")


@dp.message(AdminAddProductStates.waiting_stock_qty)
async def add_product_stock_qty(message: Message, state: FSMContext):
    text = (message.text or "").strip().replace(" ", "")
    if not text.isdigit():
        await message.answer("Остаток должен быть числом.")
        return

    await state.update_data(stock_qty=int(text))
    await state.set_state(AdminAddProductStates.waiting_publish)
    await message.answer("👁 Опубликовать товар сразу? Напишите: да или нет")


@dp.message(AdminAddProductStates.waiting_publish)
async def add_product_publish(message: Message, state: FSMContext):
    answer = ((message.text or "").strip().lower())
    is_published = 1 if answer in ("да", "ha", "yes", "y", "1") else 0

    data = await state.get_data()

    product_id = db.shop_product_add(
        photo_file_id=data.get("photo_file_id", ""),
        title_ru=data.get("title_ru", ""),
        title_uz=data.get("title_uz", ""),
        description_ru=data.get("description_ru", ""),
        description_uz=data.get("description_uz", ""),
        sizes=data.get("sizes", ""),
        category_slug=data.get("category_slug", "casual"),
        price=safe_int(data.get("price"), 0),
        old_price=safe_int(data.get("old_price"), 0),
        price_on_request=0,
        stock_qty=safe_int(data.get("stock_qty"), 0),
        is_published=is_published,
        sort_order=0,
    )

    product = db.shop_product_get(product_id)
    await state.clear()

    await message.answer("✅ Товар добавлен.")
    if product:
        caption = product_card_text(product, "ru")
        if product.get("photo_file_id"):
            try:
                await message.answer_photo(
                    product["photo_file_id"],
                    caption=caption,
                    reply_markup=admin_product_actions_keyboard(product_id, safe_int(product.get("is_published"), 1)),
                )
            except Exception:
                await message.answer(
                    caption,
                    reply_markup=admin_product_actions_keyboard(product_id, safe_int(product.get("is_published"), 1)),
                )
        else:
            await message.answer(
                caption,
                reply_markup=admin_product_actions_keyboard(product_id, safe_int(product.get("is_published"), 1)),
            )


# =========================================================
# EDIT PRODUCT
# =========================================================
@dp.callback_query(F.data.startswith("admin_edit_pick:"))
async def admin_edit_pick(cb: CallbackQuery):
    if not admin_only(cb.from_user.id):
        await cb.answer()
        return

    try:
        product_id = int(cb.data.split(":")[1])
    except Exception:
        await cb.answer("Ошибка")
        return

    product = db.shop_product_get(product_id)
    if not product:
        await cb.message.answer("Товар не найден.")
        await cb.answer()
        return

    await cb.message.answer(
        product_card_text(product, "ru"),
        reply_markup=admin_edit_fields_keyboard(product_id),
    )
    await cb.answer()


@dp.callback_query(F.data.startswith("edit_field:"))
async def admin_edit_field_select(cb: CallbackQuery, state: FSMContext):
    if not admin_only(cb.from_user.id):
        await cb.answer()
        return

    try:
        _, product_id_str, field_name = cb.data.split(":")
        product_id = int(product_id_str)
    except Exception:
        await cb.answer("Ошибка")
        return

    await state.clear()
    await state.update_data(product_id=product_id, field_name=field_name)
    await state.set_state(AdminEditProductStates.waiting_new_value)

    prompts = {
        "photo_file_id": "Отправьте новое фото товара.",
        "title_ru": "Введите новое название RU.",
        "title_uz": "Введите новое название UZ.",
        "description_ru": "Введите новое описание RU.",
        "description_uz": "Введите новое описание UZ.",
        "sizes": "Введите новые размеры. Например: 98,104,110",
        "category_slug": "Введите категорию: new / hits / sale / limited / school / casual",
        "price": "Введите новую цену цифрами.",
        "old_price": "Введите новую старую цену цифрами.",
        "stock_qty": "Введите новый остаток цифрами.",
        "sort_order": "Введите новую сортировку цифрами.",
    }
    await cb.message.answer(prompts.get(field_name, "Введите новое значение."))
    await cb.answer()


@dp.message(AdminEditProductStates.waiting_new_value, F.photo)
async def admin_edit_new_photo(message: Message, state: FSMContext):
    if not admin_only(message.from_user.id):
        return

    data = await state.get_data()
    field_name = data.get("field_name")
    product_id = safe_int(data.get("product_id"))

    if field_name != "photo_file_id":
        await message.answer("Сейчас ожидается текстовое значение, а не фото.")
        return

    new_value = message.photo[-1].file_id
    db.shop_product_update_field(product_id, "photo_file_id", new_value)
    product = db.shop_product_get(product_id)
    await state.clear()

    await message.answer("✅ Фото обновлено.")
    if product:
        await message.answer(
            product_card_text(product, "ru"),
            reply_markup=admin_product_actions_keyboard(product_id, safe_int(product.get("is_published"), 1)),
        )


@dp.message(AdminEditProductStates.waiting_new_value)
async def admin_edit_new_value(message: Message, state: FSMContext):
    if not admin_only(message.from_user.id):
        return

    data = await state.get_data()
    field_name = data.get("field_name")
    product_id = safe_int(data.get("product_id"))
    raw_value = (message.text or "").strip()

    if field_name in ("price", "old_price", "stock_qty", "sort_order"):
        if not raw_value.replace(" ", "").isdigit():
            await message.answer("Нужно ввести число.")
            return
        value: Any = int(raw_value.replace(" ", ""))
    elif field_name == "category_slug":
        value = raw_value.lower()
        if value not in SHOP_CATEGORIES:
            await message.answer("Неверная категория. Используйте: new, hits, sale, limited, school, casual")
            return
    else:
        value = raw_value

    db.shop_product_update_field(product_id, field_name, value)
    product = db.shop_product_get(product_id)
    await state.clear()

    await message.answer("✅ Поле обновлено.")
    if product:
        await message.answer(
            product_card_text(product, "ru"),
            reply_markup=admin_product_actions_keyboard(product_id, safe_int(product.get("is_published"), 1)),
        )


# =========================================================
# DELETE / PUBLISH PRODUCT
# =========================================================
@dp.callback_query(F.data.startswith("admin_delete_product:"))
async def admin_delete_product(cb: CallbackQuery):
    if not admin_only(cb.from_user.id):
        await cb.answer()
        return

    try:
        product_id = int(cb.data.split(":")[1])
    except Exception:
        await cb.answer("Ошибка")
        return

    db.shop_product_delete(product_id)
    await cb.message.answer(f"🗑 Товар ID {product_id} удалён.")
    await cb.answer("Удалено")


@dp.callback_query(F.data.startswith("admin_publish:"))
async def admin_publish_product(cb: CallbackQuery):
    if not admin_only(cb.from_user.id):
        await cb.answer()
        return

    try:
        _, product_id_str, publish_str = cb.data.split(":")
        product_id = int(product_id_str)
        publish_value = int(publish_str)
    except Exception:
        await cb.answer("Ошибка")
        return

    db.shop_product_update_publish(product_id, publish_value)
    product = db.shop_product_get(product_id)
    if not product:
        await cb.answer("Товар не найден")
        return

    text = "✅ Статус публикации обновлён.\n\n" + product_card_text(product, "ru")
    await cb.message.answer(
        text,
        reply_markup=admin_product_actions_keyboard(product_id, safe_int(product.get("is_published"), 1)),
    )
    await cb.answer("Готово")


# =========================================================
# ADMIN STATS
# =========================================================
@dp.callback_query(F.data == "admin_stats")
async def admin_stats(cb: CallbackQuery):
    if not admin_only(cb.from_user.id):
        await cb.answer()
        return

    stats = db.get_stats_all()
    products_count = db.shop_products_count()

    text = (
        "📊 <b>Статистика</b>\n\n"
        f"Всего заказов: <b>{safe_int(stats.get('total'), 0)}</b>\n"
        f"Новые: <b>{safe_int(stats.get('new_count'), 0)}</b>\n"
        f"В обработке: <b>{safe_int(stats.get('processing'), 0)}</b>\n"
        f"Подтверждены: <b>{safe_int(stats.get('confirmed'), 0)}</b>\n"
        f"Оплачены: <b>{safe_int(stats.get('paid_count'), 0)}</b>\n"
        f"Отправлены: <b>{safe_int(stats.get('shipped'), 0)}</b>\n"
        f"Доставлены: <b>{safe_int(stats.get('delivered'), 0)}</b>\n"
        f"Отменены: <b>{safe_int(stats.get('cancelled'), 0)}</b>\n"
        f"Уникальных клиентов: <b>{safe_int(stats.get('unique_users'), 0)}</b>\n"
        f"Товаров в базе: <b>{products_count}</b>"
    )
    await cb.message.answer(text)
    await cb.answer()


# =========================================================
# REMINDERS
# =========================================================
async def check_reminders():
    orders = db.orders_get_for_reminder()
    if not orders:
        return

    lines = []
    for o in orders[:10]:
        lines.append(
            f"🆕 #{o['id']} | {esc(o.get('customer_name') or '')} | "
            f"{esc(o.get('customer_phone') or '')}"
        )

    text = "🔔 <b>Напоминание: есть новые заказы</b>\n\n" + "\n".join(lines)

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception as e:
            print(f"Reminder failed for {admin_id}: {e}")

    for o in orders:
        db.order_update_reminded(o["id"])


async def reminders_loop():
    while True:
        try:
            await check_reminders()
        except Exception as e:
            print("reminders_loop error:", e)
        await asyncio.sleep(30 * 60)


# =========================================================
# EXCEL REPORTS
# =========================================================
def build_excel_report(filename: str, orders: List[Dict]) -> int:
    wb = Workbook()
    ws = wb.active
    ws.title = "Orders"

    headers = [
        "ID", "Дата", "Имя", "Телефон", "Город", "Товары",
        "Сумма", "Статус", "Оплата", "Статус оплаты", "Источник"
    ]
    ws.append(headers)

    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")

    total_amount = 0

    for o in orders:
        try:
            items = json.loads(o.get("items") or "[]")
        except Exception:
            items = []

        items_text = ", ".join([
            f"{(it.get('product_name') or it.get('name') or 'item')} x{it.get('qty', 1)}"
            for it in items
        ])

        order_sum = safe_int(o.get("total_amount"), 0)
        total_amount += order_sum

        ws.append([
            o.get("id"),
            o.get("created_at"),
            o.get("customer_name"),
            o.get("customer_phone"),
            o.get("city"),
            items_text,
            order_sum,
            o.get("status"),
            o.get("payment_method"),
            o.get("payment_status"),
            o.get("source", "bot"),
        ])

    wb.save(filename)
    return total_amount


async def generate_monthly_report_to_admins():
    year, month = prev_month(now_tz())

    if db.report_is_sent(year, month):
        return

    orders = db.orders_get_monthly(year, month)
    if not orders:
        return

    Path("reports").mkdir(exist_ok=True)
    filename = f"reports/report_{year}_{month:02d}.xlsx"
    total_amount = build_excel_report(filename, orders)

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"📊 Отчёт {month:02d}.{year}\n"
                f"📦 Заказов: {len(orders)}\n"
                f"💰 Сумма: {money_fmt(total_amount)} сум"
            )
            await bot.send_document(admin_id, FSInputFile(filename))
        except Exception as e:
            print(f"Failed to send report to {admin_id}: {e}")

    db.report_mark_sent(year, month, filename, len(orders), total_amount)


# =========================================================
# SCHEDULED POSTS
# =========================================================
async def cron_post_daily_to_channel():
    if not CHANNEL_ID:
        return

    now = now_tz()
    dow = now.isoweekday()

    if dow == 7:
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, "📌 Воскресенье: загрузите посты на новую неделю.")
            except Exception:
                pass
        return

    week_key = db.week_key_now(now)
    post = db.sched_get_for_day(dow, week_key)
    if not post:
        return

    caption = (post.get("caption") or "").strip() or "🔥 ZARY & CO"
    media_type = post.get("media_type") or "none"
    file_id = post.get("file_id") or ""

    try:
        if media_type == "photo" and file_id:
            await bot.send_photo(CHANNEL_ID, file_id, caption=caption)
        elif media_type == "video" and file_id:
            await bot.send_video(CHANNEL_ID, file_id, caption=caption)
        else:
            await bot.send_message(CHANNEL_ID, caption)

        db.sched_mark_posted(post["id"])
    except Exception as e:
        print("Post error:", e)


# =========================================================
# CRON COMMANDS IN BOT
# =========================================================
@dp.message(Command("monthly_report"))
async def manual_monthly_report(message: Message):
    if not admin_only(message.from_user.id):
        return
    await message.answer("Генерирую отчёт...")
    await generate_monthly_report_to_admins()
    await message.answer("Готово.")


# =========================================================
# PART 3/4 END
# =========================================================

# =========================================================
# PART 4/4
# - web shop
# - payment stub pages
# - api
# - media proxy
# - web admin
# - health/cron
# - main()
# =========================================================


# =========================================================
# WEB HELPERS
# =========================================================
def parse_web_lang(request: web.Request) -> str:
    lang = (request.query.get("lang") or "ru").strip().lower()
    return "uz" if lang == "uz" else "ru"


def product_to_web_dict(product: Dict, lang: str) -> Dict[str, Any]:
    return {
        "id": product.get("id"),
        "title": product.get("title_uz") if lang == "uz" else product.get("title_ru"),
        "title_ru": product.get("title_ru"),
        "title_uz": product.get("title_uz"),
        "description": product.get("description_uz") if lang == "uz" else product.get("description_ru"),
        "description_ru": product.get("description_ru"),
        "description_uz": product.get("description_uz"),
        "sizes": parse_sizes_text(product.get("sizes") or ""),
        "sizes_text": product.get("sizes") or "",
        "category_slug": product.get("category_slug") or "casual",
        "price": safe_int(product.get("price"), 0),
        "old_price": safe_int(product.get("old_price"), 0),
        "price_on_request": safe_int(product.get("price_on_request"), 0),
        "stock_qty": safe_int(product.get("stock_qty"), 0),
        "photo": product_public_photo_url(product.get("photo_file_id") or ""),
        "is_published": safe_int(product.get("is_published"), 1),
    }


def admin_orders_html_rows(rows: List[Dict]) -> str:
    html_rows = []
    for o in rows:
        try:
            items = json.loads(o.get("items") or "[]")
        except Exception:
            items = []

        items_preview = ", ".join([
            f"{esc((it.get('product_name') or it.get('name') or 'item'))} x{safe_int(it.get('qty'), 1)}"
            for it in items[:3]
        ])

        html_rows.append(
            "<tr>"
            f"<td>#{o['id']}</td>"
            f"<td>{esc((o.get('created_at') or '')[:16])}</td>"
            f"<td>{esc(o.get('customer_name') or '')}</td>"
            f"<td>{esc(o.get('customer_phone') or '')}</td>"
            f"<td>{esc(o.get('city') or '')}</td>"
            f"<td>{esc(delivery_label(o.get('delivery_type') or '', 'ru'))}</td>"
            f"<td>{esc(payment_label(o.get('payment_method') or '', 'ru'))}</td>"
            f"<td>{esc(items_preview)}</td>"
            f"<td>{money_fmt(o.get('total_amount') or 0)}</td>"
            f"<td>{esc(status_label(o.get('status') or '', 'ru'))}</td>"
            "</tr>"
        )
    return "\n".join(html_rows)


def admin_products_html_rows(rows: List[Dict]) -> str:
    html_rows = []
    for p in rows:
        html_rows.append(
            "<tr>"
            f"<td>{p['id']}</td>"
            f"<td>{esc(p.get('title_ru') or '')}</td>"
            f"<td>{esc(p.get('category_slug') or '')}</td>"
            f"<td>{money_fmt(p.get('price') or 0)}</td>"
            f"<td>{money_fmt(p.get('old_price') or 0)}</td>"
            f"<td>{safe_int(p.get('stock_qty'), 0)}</td>"
            f"<td>{'Да' if safe_int(p.get('is_published'), 1) else 'Нет'}</td>"
            "</tr>"
        )
    return "\n".join(html_rows)


# =========================================================
# WEB PAGES
# =========================================================
async def shop_index(request: web.Request) -> web.Response:
    lang = parse_web_lang(request)
    is_uz = lang == "uz"

    title = "ZARY SHOP" if not is_uz else "ZARY DO'KON"
    shop_label = "Магазин" if not is_uz else "Do'kon"
    cart_label = "Корзина" if not is_uz else "Savatcha"
    order_label = "Оформить заказ" if not is_uz else "Buyurtma berish"
    empty_cart_label = "Корзина пуста" if not is_uz else "Savatcha bo'sh"
    name_label = "Имя" if not is_uz else "Ism"
    phone_label = "Телефон" if not is_uz else "Telefon"
    city_label = "Город" if not is_uz else "Shahar"
    address_label = "Адрес" if not is_uz else "Manzil"
    comment_label = "Комментарий" if not is_uz else "Izoh"
    delivery_label_title = "Доставка" if not is_uz else "Yetkazish"
    payment_label_title = "Оплата" if not is_uz else "To'lov"
    success_label = "Заказ отправлен" if not is_uz else "Buyurtma yuborildi"
    sizes_label = "Размеры" if not is_uz else "Razmerlar"
    total_label = "Итого" if not is_uz else "Jami"
    add_to_cart_label = "В корзину" if not is_uz else "Savatchaga"
    old_price_label = "Старая цена" if not is_uz else "Eski narx"
    stock_label = "Остаток" if not is_uz else "Qoldiq"
    delivery_1 = "Яндекс курьер" if not is_uz else "Yandex kuryer"
    delivery_2 = "B2B почта" if not is_uz else "B2B pochta"
    delivery_3 = "Яндекс ПВЗ" if not is_uz else "Yandex PVZ"

    html_page = f"""
<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{title}</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;font-family:Arial,sans-serif;background:#f6f6f6;color:#111}}
header{{background:#111;color:#fff;padding:18px 16px;position:sticky;top:0;z-index:9}}
.wrap{{max-width:1180px;margin:0 auto;padding:18px}}
.topbar{{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}}
.brand{{font-size:24px;font-weight:700;letter-spacing:.5px}}
.langs a{{color:#fff;text-decoration:none;margin-left:10px;padding:6px 10px;border:1px solid rgba(255,255,255,.2);border-radius:8px}}
.layout{{display:grid;grid-template-columns:1fr 360px;gap:18px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:16px}}
.card{{background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 6px 18px rgba(0,0,0,.06)}}
.card img{{width:100%;height:250px;object-fit:cover;background:#ececec}}
.card .ph{{width:100%;height:250px;background:#ececec;display:flex;align-items:center;justify-content:center;color:#777}}
.card-body{{padding:14px}}
.card h3{{margin:0 0 8px;font-size:18px}}
.muted{{color:#666;font-size:14px}}
.price{{font-size:20px;font-weight:700;margin:10px 0 4px}}
.old{{text-decoration:line-through;color:#999;font-size:14px}}
.sizes{{font-size:13px;color:#555;margin:8px 0}}
.stock{{font-size:13px;color:#555;margin:8px 0}}
.btn{{display:inline-block;width:100%;padding:11px 12px;border:none;border-radius:10px;background:#111;color:#fff;cursor:pointer;font-size:15px}}
.btn.secondary{{background:#e9e9e9;color:#111}}
.side{{background:#fff;border-radius:16px;padding:16px;box-shadow:0 6px 18px rgba(0,0,0,.06);position:sticky;top:90px;height:max-content}}
.field{{margin-bottom:10px}}
.field label{{display:block;font-size:13px;margin-bottom:6px;color:#555}}
.field input,.field select,.field textarea{{width:100%;padding:10px;border:1px solid #ddd;border-radius:10px;font-size:14px}}
.cart-list{{max-height:240px;overflow:auto;margin-bottom:14px}}
.cart-item{{padding:10px 0;border-bottom:1px solid #eee;font-size:14px}}
.row{{display:flex;justify-content:space-between;gap:8px}}
.badge{{display:inline-block;padding:4px 8px;border-radius:999px;background:#f1f1f1;font-size:12px;margin-right:6px;margin-bottom:6px}}
.notice{{padding:10px 12px;border-radius:10px;background:#f8f3d8;color:#6a5800;font-size:13px;margin-bottom:12px}}
.footer{{padding:30px 0 10px;color:#777;font-size:13px}}
@media (max-width: 920px) {{
  .layout{{grid-template-columns:1fr}}
  .side{{position:static}}
}}
</style>
</head>
<body>
<header>
  <div class="wrap topbar">
    <div class="brand">ZARY & CO</div>
    <div class="langs">
      <a href="/?lang=ru">RU</a>
      <a href="/?lang=uz">UZ</a>
    </div>
  </div>
</header>

<div class="wrap">
  <div class="layout">
    <section>
      <h2 style="margin:0 0 14px">{shop_label}</h2>
      <div id="products" class="grid"></div>
      <div class="footer">
        Telegram: {FOLLOW_TG}<br/>
        Instagram: {FOLLOW_IG}<br/>
        YouTube: {FOLLOW_YT}
      </div>
    </section>

    <aside class="side">
      <h3 style="margin-top:0">{cart_label}</h3>
      <div id="cartList" class="cart-list"></div>
      <div class="row" style="margin:12px 0 16px">
        <strong>{total_label}</strong>
        <strong id="cartTotal">0</strong>
      </div>

      <div class="notice">
        Click / Payme integration ready structure. Real API can be connected later.
      </div>

      <div class="field">
        <label>{name_label}</label>
        <input id="name" />
      </div>
      <div class="field">
        <label>{phone_label}</label>
        <input id="phone" />
      </div>
      <div class="field">
        <label>{city_label}</label>
        <input id="city" />
      </div>
      <div class="field">
        <label>{delivery_label_title}</label>
        <select id="delivery">
          <option value="yandex_courier">{delivery_1}</option>
          <option value="b2b_post">{delivery_2}</option>
          <option value="yandex_pvz">{delivery_3}</option>
        </select>
      </div>
      <div class="field">
        <label>{payment_label_title}</label>
        <select id="payment">
          <option value="click">Click</option>
          <option value="payme">Payme</option>
        </select>
      </div>
      <div class="field">
        <label>{address_label}</label>
        <input id="address" />
      </div>
      <div class="field">
        <label>{comment_label}</label>
        <textarea id="comment" rows="3"></textarea>
      </div>

      <button class="btn" onclick="submitOrder()">{order_label}</button>
      <button class="btn secondary" style="margin-top:10px" onclick="clearCart()">{empty_cart_label}</button>
    </aside>
  </div>
</div>

<script>
const LANG = "{lang}";
let PRODUCTS = [];
let CART = JSON.parse(localStorage.getItem("zary_cart") || "[]");

function money(v) {{
  try {{
    return Number(v || 0).toLocaleString("ru-RU");
  }} catch(e) {{
    return String(v || 0);
  }}
}}

function saveCart() {{
  localStorage.setItem("zary_cart", JSON.stringify(CART));
}}

function renderCart() {{
  const box = document.getElementById("cartList");
  const totalEl = document.getElementById("cartTotal");

  if (!CART.length) {{
    box.innerHTML = '<div class="muted">{empty_cart_label}</div>';
    totalEl.textContent = '0';
    return;
  }}

  let total = 0;
  box.innerHTML = CART.map((item, idx) => {{
    const line = (Number(item.price || 0) * Number(item.qty || 1));
    total += line;
    return `
      <div class="cart-item">
        <div><b>${{item.title}}</b></div>
        <div class="muted">${{item.size || '—'}} | x${{item.qty || 1}}</div>
        <div class="row">
          <span>${{money(item.price)}} сум</span>
          <button class="btn secondary" style="width:auto;padding:4px 8px" onclick="removeCartItem(${{idx}})">✕</button>
        </div>
      </div>
    `;
  }}).join("");

  totalEl.textContent = money(total) + " сум";
}}

function removeCartItem(idx) {{
  CART.splice(idx, 1);
  saveCart();
  renderCart();
}}

function clearCart() {{
  CART = [];
  saveCart();
  renderCart();
}}

function addToCart(productId) {{
  const product = PRODUCTS.find(p => Number(p.id) === Number(productId));
  if (!product) return;

  let chosenSize = "";
  if (product.sizes && product.sizes.length) {{
    chosenSize = prompt("{sizes_label}: " + product.sizes.join(", "), product.sizes[0]) || product.sizes[0];
  }}

  CART.push({{
    id: product.id,
    product_id: product.id,
    title: product.title,
    product_name: product.title,
    qty: 1,
    price: product.price || 0,
    size: chosenSize
  }});

  saveCart();
  renderCart();
}}

function renderProducts() {{
  const box = document.getElementById("products");
  box.innerHTML = PRODUCTS.map(p => `
    <div class="card">
      ${
        "`${p.photo ? `<img src=\"${p.photo}\" alt=\"\">` : `<div class=\"ph\">No photo</div>`}`"
      }
      <div class="card-body">
        <h3>${"${p.title || ''}"}</h3>
        <div class="muted">${"${p.description || ''}"}</div>
        <div class="sizes"><b>{sizes_label}:</b> ${"${(p.sizes || []).join(', ') || '—'}"}</div>
        <div class="stock"><b>{stock_label}:</b> ${"${p.stock_qty || 0}"}</div>
        ${"${p.old_price ? `<div class=\"old\">{old_price_label}: ${money(p.old_price)} сум</div>` : ''}"}
        <div class="price">${"${money(p.price || 0)}"} сум</div>
        <button class="btn" onclick="addToCart(${ "${p.id}" })">{add_to_cart_label}</button>
      </div>
    </div>
  `).join("");
}}

async function loadProducts() {{
  const res = await fetch("/api/shop/products?lang=" + LANG);
  const data = await res.json();
  PRODUCTS = data.products || [];
  renderProducts();
}}

async function submitOrder() {{
  if (!CART.length) {{
    alert("{empty_cart_label}");
    return;
  }}

  const payload = {{
    name: document.getElementById("name").value.trim(),
    phone: document.getElementById("phone").value.trim(),
    city: document.getElementById("city").value.trim(),
    delivery_type: document.getElementById("delivery").value,
    payment_method: document.getElementById("payment").value,
    address: document.getElementById("address").value.trim(),
    comment: document.getElementById("comment").value.trim(),
    items: CART
  }};

  if (!payload.name || !payload.phone) {{
    alert("Fill name and phone");
    return;
  }}

  const res = await fetch("/api/shop/order", {{
    method: "POST",
    headers: {{"Content-Type": "application/json"}},
    body: JSON.stringify(payload)
  }});

  const data = await res.json();
  if (data.status === "ok") {{
    alert("{success_label} #" + data.order_id);
    clearCart();
    document.getElementById("name").value = "";
    document.getElementById("phone").value = "";
    document.getElementById("city").value = "";
    document.getElementById("address").value = "";
    document.getElementById("comment").value = "";
  }} else {{
    alert(data.message || "Error");
  }}
}}

loadProducts();
renderCart();
</script>
</body>
</html>
"""
    return web.Response(text=html_page, content_type="text/html")


# =========================================================
# PAYMENT STUB PAGES
# =========================================================
async def pay_click_page(request: web.Request) -> web.Response:
    order_id = safe_int(request.match_info.get("order_id"))
    order = db.order_get(order_id)

    if not order:
        return web.Response(text="Order not found", status=404)

    html_page = f"""
    <html>
    <head><meta charset="utf-8"><title>Click Payment</title></head>
    <body style="font-family:Arial;padding:40px">
      <h1>Click payment stub</h1>
      <p>Order: #{order_id}</p>
      <p>Amount: {money_fmt(order.get('total_amount') or 0)} сум</p>
      <p>This is a placeholder page. Real Click API can be connected later.</p>
      <form method="post" action="/pay/click/{order_id}/success">
        <button type="submit" style="padding:12px 18px">Mark as paid</button>
      </form>
    </body>
    </html>
    """
    return web.Response(text=html_page, content_type="text/html")


async def pay_click_success(request: web.Request) -> web.Response:
    order_id = safe_int(request.match_info.get("order_id"))
    order = db.order_get(order_id)
    if not order:
        return web.Response(text="Order not found", status=404)

    db.order_update_payment(order_id, "paid")
    db.order_update_status(order_id, "paid")

    if order.get("user_id"):
        user_lang = get_user_lang(order["user_id"])
        try:
            if user_lang == "uz":
                await bot.send_message(order["user_id"], f"💳 Buyurtmangiz #{order_id} bo'yicha to'lov tasdiqlandi.")
            else:
                await bot.send_message(order["user_id"], f"💳 Оплата по заказу #{order_id} подтверждена.")
        except Exception:
            pass

    return web.Response(text="Payment marked as paid", content_type="text/plain")


async def pay_payme_page(request: web.Request) -> web.Response:
    order_id = safe_int(request.match_info.get("order_id"))
    order = db.order_get(order_id)

    if not order:
        return web.Response(text="Order not found", status=404)

    html_page = f"""
    <html>
    <head><meta charset="utf-8"><title>Payme Payment</title></head>
    <body style="font-family:Arial;padding:40px">
      <h1>Payme payment stub</h1>
      <p>Order: #{order_id}</p>
      <p>Amount: {money_fmt(order.get('total_amount') or 0)} сум</p>
      <p>This is a placeholder page. Real Payme API can be connected later.</p>
      <form method="post" action="/pay/payme/{order_id}/success">
        <button type="submit" style="padding:12px 18px">Mark as paid</button>
      </form>
    </body>
    </html>
    """
    return web.Response(text=html_page, content_type="text/html")


async def pay_payme_success(request: web.Request) -> web.Response:
    order_id = safe_int(request.match_info.get("order_id"))
    order = db.order_get(order_id)
    if not order:
        return web.Response(text="Order not found", status=404)

    db.order_update_payment(order_id, "paid")
    db.order_update_status(order_id, "paid")

    if order.get("user_id"):
        user_lang = get_user_lang(order["user_id"])
        try:
            if user_lang == "uz":
                await bot.send_message(order["user_id"], f"💳 Buyurtmangiz #{order_id} bo'yicha to'lov tasdiqlandi.")
            else:
                await bot.send_message(order["user_id"], f"💳 Оплата по заказу #{order_id} подтверждена.")
        except Exception:
            pass

    return web.Response(text="Payment marked as paid", content_type="text/plain")


# =========================================================
# API
# =========================================================
async def api_shop_products(request: web.Request) -> web.Response:
    lang = parse_web_lang(request)
    products = db.shop_products_list(published_only=True, limit=500)

    result = [product_to_web_dict(p, lang) for p in products if safe_int(p.get("is_published"), 1) == 1]
    return web.json_response({"status": "ok", "products": result})


async def api_shop_order(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"status": "error", "message": "Invalid JSON"}, status=400)

    name = (data.get("name") or "").strip()
    phone = normalize_phone((data.get("phone") or "").strip())
    city = (data.get("city") or "").strip()
    address = (data.get("address") or "").strip()
    comment = (data.get("comment") or "").strip()
    delivery_type = (data.get("delivery_type") or "yandex_courier").strip()
    payment_method = (data.get("payment_method") or "click").strip()
    items = data.get("items") or []

    if not name or not phone_is_valid(phone):
        return web.json_response({"status": "error", "message": "Invalid name or phone"}, status=400)

    if delivery_type not in DELIVERY_TYPES:
        delivery_type = "yandex_courier"

    if payment_method not in PAYMENT_METHODS:
        payment_method = "click"

    normalized_items: List[Dict[str, Any]] = []
    total_qty = 0
    total_amount = 0

    for item in items:
        product_id = safe_int(item.get("product_id") or item.get("id"), 0)
        product = db.shop_product_get(product_id) if product_id else None

        title = (
            (product.get("title_ru") if product else None)
            or item.get("product_name")
            or item.get("title")
            or "Item"
        )
        price = safe_int(product.get("price"), 0) if product else safe_int(item.get("price"), 0)
        qty = max(1, safe_int(item.get("qty"), 1))
        size = (item.get("size") or "").strip()

        normalized_items.append({
            "product_id": product_id or None,
            "product_name": title,
            "name": title,
            "price": price,
            "qty": qty,
            "size": size,
        })

        total_qty += qty
        total_amount += price * qty

    order_id = db.order_create({
        "user_id": None,
        "username": "",
        "customer_name": name,
        "customer_phone": phone,
        "city": city,
        "items": normalized_items,
        "total_qty": total_qty,
        "total_amount": total_amount,
        "delivery_service": delivery_type,
        "delivery_type": delivery_type,
        "delivery_address": address,
        "payment_method": payment_method,
        "payment_status": "pending",
        "comment": comment,
        "status": "new",
        "source": "web",
    })

    order = db.order_get(order_id)
    await send_order_to_admins(order_id)

    if order:
        await send_payment_stub(order, "ru")

    return web.json_response({"status": "ok", "order_id": order_id})


# =========================================================
# MEDIA PROXY
# =========================================================
async def media_proxy(request: web.Request) -> web.Response:
    """
    Placeholder for Telegram file proxy.
    Сейчас возвращает заглушку, чтобы не ломать магазин без реального file download.
    Позже можно подключить bot.get_file + CDN/proxy.
    """
    file_id = request.match_info.get("file_id", "")
    if not file_id:
        return web.Response(text="No file", status=404)

    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="600" height="600">
      <rect width="100%" height="100%" fill="#eeeeee"/>
      <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle"
            font-family="Arial" font-size="28" fill="#777777">ZARY PHOTO</text>
    </svg>
    """
    return web.Response(text=svg, content_type="image/svg+xml")


# =========================================================
# WEB ADMIN
# =========================================================
async def admin_dashboard(request: web.Request) -> web.Response:
    token = request.query.get("token", "")
    if not admin_panel_allowed(token):
        return web.Response(text="Access denied", status=403)

    stats = db.get_stats_all()
    products_count = db.shop_products_count()

    html_page = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>ZARY ADMIN</title>
<style>
body{{font-family:Arial,sans-serif;background:#f5f5f5;padding:30px;color:#111}}
.wrap{{max-width:1100px;margin:0 auto}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin-bottom:24px}}
.card{{background:#fff;padding:18px;border-radius:16px;box-shadow:0 6px 18px rgba(0,0,0,.06)}}
.num{{font-size:30px;font-weight:700;margin-top:8px}}
a.btn{{display:inline-block;padding:12px 16px;background:#111;color:#fff;text-decoration:none;border-radius:10px;margin-right:10px;margin-bottom:10px}}
</style>
</head>
<body>
<div class="wrap">
  <h1>ZARY ADMIN</h1>
  <div class="cards">
    <div class="card"><div>Всего заказов</div><div class="num">{safe_int(stats.get('total'), 0)}</div></div>
    <div class="card"><div>Новые</div><div class="num">{safe_int(stats.get('new_count'), 0)}</div></div>
    <div class="card"><div>В обработке</div><div class="num">{safe_int(stats.get('processing'), 0)}</div></div>
    <div class="card"><div>Доставлены</div><div class="num">{safe_int(stats.get('delivered'), 0)}</div></div>
    <div class="card"><div>Клиенты</div><div class="num">{safe_int(stats.get('unique_users'), 0)}</div></div>
    <div class="card"><div>Товары</div><div class="num">{products_count}</div></div>
  </div>

  <a class="btn" href="/admin/orders?token={esc(token)}">Заказы</a>
  <a class="btn" href="/admin/products?token={esc(token)}">Товары</a>
  <a class="btn" href="/health">Health</a>
</div>
</body>
</html>
"""
    return web.Response(text=html_page, content_type="text/html")


async def admin_orders_page(request: web.Request) -> web.Response:
    token = request.query.get("token", "")
    if not admin_panel_allowed(token):
        return web.Response(text="Access denied", status=403)

    status = (request.query.get("status") or "").strip()
    city = (request.query.get("city") or "").strip()
    phone_q = (request.query.get("phone") or "").strip()

    rows = db.orders_filter(status=status, city=city, phone_q=phone_q, limit=300)

    html_page = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>ZARY Orders</title>
<style>
body{{font-family:Arial,sans-serif;background:#f5f5f5;padding:30px}}
.wrap{{max-width:1300px;margin:0 auto}}
table{{width:100%;border-collapse:collapse;background:#fff}}
th,td{{border:1px solid #ddd;padding:10px;text-align:left;font-size:14px;vertical-align:top}}
th{{background:#111;color:#fff}}
input,select{{padding:10px;border:1px solid #ddd;border-radius:8px}}
button{{padding:10px 14px;border:none;background:#111;color:#fff;border-radius:8px;cursor:pointer}}
a{{display:inline-block;margin-bottom:20px}}
.form{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px}}
</style>
</head>
<body>
<div class="wrap">
<a href="/admin?token={esc(token)}">← Назад</a>
<h1>Orders</h1>

<form class="form" method="get" action="/admin/orders">
  <input type="hidden" name="token" value="{esc(token)}"/>
  <select name="status">
    <option value="">Все статусы</option>
    <option value="new" {"selected" if status=="new" else ""}>new</option>
    <option value="processing" {"selected" if status=="processing" else ""}>processing</option>
    <option value="confirmed" {"selected" if status=="confirmed" else ""}>confirmed</option>
    <option value="paid" {"selected" if status=="paid" else ""}>paid</option>
    <option value="shipped" {"selected" if status=="shipped" else ""}>shipped</option>
    <option value="delivered" {"selected" if status=="delivered" else ""}>delivered</option>
    <option value="cancelled" {"selected" if status=="cancelled" else ""}>cancelled</option>
  </select>
  <input name="city" placeholder="Город" value="{esc(city)}"/>
  <input name="phone" placeholder="Телефон" value="{esc(phone_q)}"/>
  <button type="submit">Фильтр</button>
</form>

<table>
<tr>
<th>ID</th>
<th>Дата</th>
<th>Имя</th>
<th>Телефон</th>
<th>Город</th>
<th>Доставка</th>
<th>Оплата</th>
<th>Товары</th>
<th>Сумма</th>
<th>Статус</th>
</tr>
{admin_orders_html_rows(rows)}
</table>
</div>
</body>
</html>
"""
    return web.Response(text=html_page, content_type="text/html")


async def admin_products_page(request: web.Request) -> web.Response:
    token = request.query.get("token", "")
    if not admin_panel_allowed(token):
        return web.Response(text="Access denied", status=403)

    rows = db.shop_products_list(published_only=False, limit=500)

    html_page = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>ZARY Products</title>
<style>
body{{font-family:Arial,sans-serif;background:#f5f5f5;padding:30px}}
.wrap{{max-width:1200px;margin:0 auto}}
table{{width:100%;border-collapse:collapse;background:#fff}}
th,td{{border:1px solid #ddd;padding:10px;text-align:left;font-size:14px}}
th{{background:#111;color:#fff}}
a{{display:inline-block;margin-bottom:20px}}
</style>
</head>
<body>
<div class="wrap">
<a href="/admin?token={esc(token)}">← Назад</a>
<h1>Products</h1>
<table>
<tr>
<th>ID</th>
<th>Название</th>
<th>Категория</th>
<th>Цена</th>
<th>Старая цена</th>
<th>Остаток</th>
<th>Опубликован</th>
</tr>
{admin_products_html_rows(rows)}
</table>
</div>
</body>
</html>
"""
    return web.Response(text=html_page, content_type="text/html")


# =========================================================
# HEALTH / CRON
# =========================================================
async def health(request: web.Request) -> web.Response:
    return web.Response(text="OK", status=200)


async def cron_daily(request: web.Request) -> web.Response:
    secret = request.query.get("secret", "")
    if not cron_allowed(secret):
        return web.Response(text="Forbidden", status=403)

    await cron_post_daily_to_channel()
    await check_reminders()
    return web.Response(text="daily ok", status=200)


async def cron_monthly(request: web.Request) -> web.Response:
    secret = request.query.get("secret", "")
    if not cron_allowed(secret):
        return web.Response(text="Forbidden", status=403)

    await generate_monthly_report_to_admins()
    return web.Response(text="monthly ok", status=200)


# =========================================================
# ROUTES
# =========================================================
web_app.router.add_get("/", shop_index)
web_app.router.add_get("/health", health)

web_app.router.add_get("/api/shop/products", api_shop_products)
web_app.router.add_post("/api/shop/order", api_shop_order)

web_app.router.add_get("/media/{file_id}", media_proxy)

web_app.router.add_get("/pay/click/{order_id}", pay_click_page)
web_app.router.add_post("/pay/click/{order_id}/success", pay_click_success)
web_app.router.add_get("/pay/payme/{order_id}", pay_payme_page)
web_app.router.add_post("/pay/payme/{order_id}/success", pay_payme_success)

web_app.router.add_get("/admin", admin_dashboard)
web_app.router.add_get("/admin/orders", admin_orders_page)
web_app.router.add_get("/admin/products", admin_products_page)

web_app.router.add_get("/cron/daily", cron_daily)
web_app.router.add_get("/cron/monthly", cron_monthly)


# =========================================================
# STARTUP
# =========================================================
async def on_startup():
    print("Starting reminders loop...")
    asyncio.create_task(reminders_loop())


async def main():
    print("Starting bot and web server...")

    await on_startup()

    runner = web.AppRunner(web_app)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    print(f"Web server started on port {PORT}")
    print("Bot polling started")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())


# =========================================================
# PART 4/4 END
# =========================================================
