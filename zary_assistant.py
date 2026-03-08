"""
ZARY & CO — Retail Bot v4.0 FIXED (PART 1/3)
✅ aiogram 3.x
✅ SQLite (bot.db)
✅ Admins only
✅ Channel notifications
✅ Orders + Cart + Admin panel
✅ Excel export (manual)
✅ Render HTTP endpoints for Cron
✅ Weekly scheduled posts
✅ Web analytics panel
✅ Telegram WebApp store inside bot
"""

import os
import html
import asyncio
import json
import secrets
from datetime import datetime, timedelta
from calendar import monthrange
from typing import Optional, Dict, List, Tuple
from pathlib import Path
import sqlite3
import threading
from urllib.parse import quote

from zoneinfo import ZoneInfo
from aiohttp import web

TZ = ZoneInfo("Asia/Tashkent")
web_app = web.Application()


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

PORT = int(os.getenv("PORT", "10000"))
DB_PATH = os.getenv("DB_PATH", "bot.db")

CRON_SECRET = os.getenv("CRON_SECRET", "").strip()
ADMIN_PANEL_TOKEN = os.getenv("ADMIN_PANEL_TOKEN", "").strip()
WEBAPP_SECRET = os.getenv("WEBAPP_SECRET", secrets.token_hex(16)).strip()

BASE_URL = os.getenv("BASE_URL", "").strip().rstrip("/")
if not BASE_URL:
    print("⚠️ BASE_URL не установлен. WebApp кнопка магазина может работать некорректно, пока не задашь BASE_URL.")

if not ADMIN_PANEL_TOKEN:
    print("⚠️ ADMIN_PANEL_TOKEN не установлен! /admin будет без защиты. Лучше установить.")

FOLLOW_TG = "https://t.me/zaryco_official"
FOLLOW_YT = "https://www.youtube.com/@ZARYCOOFFICIAL"
FOLLOW_IG = "https://www.instagram.com/zary.co/"


# =========================
# PRODUCTS (legacy quick order list)
# =========================
PRODUCTS_RU = [
    "Худи детское", "Свитшот", "Футболка", "Рубашка", "Джинсы",
    "Брюки классические", "Юбка", "Платье", "Куртка демисезонная",
    "Костюм спортивный", "Школьная форма (комплект)", "Жилет школьный",
    "Кардиган", "Пижама", "Комплект (кофта+брюки)"
]
PRODUCTS_UZ = [
    "Bolalar hudi", "Sviter", "Futbolka", "Ko'ylak", "Jinsi",
    "Klassik shim", "Yubka", "Ko'ylak (dress)", "Demisezon kurtka",
    "Sport kostyum", "Maktab formasi (komplekt)", "Maktab jileti",
    "Kardigan", "Pijama", "Komplekt (kofta+shim)"
]

SHOP_CATEGORIES = ("new", "hits", "sale", "limited", "school", "casual")


# =========================
# HELPERS
# =========================
def now_tz() -> datetime:
    return datetime.now(TZ)

def esc(s: str) -> str:
    return html.escape(str(s) if s else "")

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def size_by_age(age: int) -> str:
    mapping = {
        1: "86", 2: "92", 3: "98", 4: "104", 5: "110", 6: "116",
        7: "122", 8: "128", 9: "134", 10: "140", 11: "146",
        12: "152", 13: "158", 14: "164", 15: "164"
    }
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

def admin_panel_allowed(token: str) -> bool:
    if not ADMIN_PANEL_TOKEN:
        return True
    return token == ADMIN_PANEL_TOKEN

def webapp_allowed(token: str) -> bool:
    return bool(token) and token == WEBAPP_SECRET

def product_public_photo_url(file_id: str) -> str:
    if not file_id:
        return ""
    return f"/media/{quote(file_id)}"

def shop_category_title(lang: str, slug: str) -> str:
    titles = {
        "ru": {
            "new": "Новинки",
            "hits": "Хиты",
            "sale": "Акции",
            "limited": "Limited",
            "school": "Школа",
            "casual": "Повседневная",
        },
        "uz": {
            "new": "Yangilar",
            "hits": "Xitlar",
            "sale": "Aksiyalar",
            "limited": "Limited",
            "school": "Maktab",
            "casual": "Kundalik",
        },
    }
    return titles.get(lang, titles["ru"]).get(slug, slug)

def shop_delivery_title(lang: str, key: str) -> str:
    data = {
        "ru": {
            "courier": "Курьер",
            "post": "Почта",
            "pickup": "Самовывоз",
            "webapp": "WebApp",
        },
        "uz": {
            "courier": "Kuryer",
            "post": "Pochta",
            "pickup": "Olib ketish",
            "webapp": "WebApp",
        },
    }
    return data.get(lang, data["ru"]).get(key, key)

def order_status_human(lang: str, status: str) -> str:
    ru = {
        "new": "Новый",
        "processing": "В обработке",
        "shipped": "Отправлен",
        "delivered": "Доставлен",
        "cancelled": "Отменён",
    }
    uz = {
        "new": "Yangi",
        "processing": "Ishlanmoqda",
        "shipped": "Jo'natildi",
        "delivered": "Yetkazildi",
        "cancelled": "Bekor qilindi",
    }
    return (uz if lang == "uz" else ru).get(status, status)

def parse_sizes_text(s: str) -> List[str]:
    if not s:
        return []
    raw = [x.strip() for x in s.replace(";", ",").replace("/", ",").split(",")]
    return [x for x in raw if x]

def money_fmt(amount: int) -> str:
    try:
        return f"{int(amount):,}".replace(",", " ")
    except Exception:
        return "0"


# =========================
# DB
# =========================
class Database:
    def __init__(self):
        self.db_path = DB_PATH
        self._local = threading.local()
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA temp_store=MEMORY;")
        except Exception:
            pass
        return conn

    def _get_conn(self):
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = self._connect()
        return self._local.conn

    def _init_db(self):
        conn = self._connect()
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
                photo_file_id TEXT,
                title_ru TEXT NOT NULL,
                title_uz TEXT NOT NULL,
                description_ru TEXT DEFAULT '',
                description_uz TEXT DEFAULT '',
                sizes TEXT DEFAULT '',
                category_slug TEXT DEFAULT 'casual',
                price INTEGER DEFAULT 0,
                price_on_request INTEGER DEFAULT 0,
                is_published INTEGER DEFAULT 1,
                sort_order INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
            CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
            CREATE INDEX IF NOT EXISTS idx_carts_user ON carts(user_id);
            CREATE INDEX IF NOT EXISTS idx_sched_week_dow ON scheduled_posts(week_key, dow);
            CREATE INDEX IF NOT EXISTS idx_events_type_time ON events(event_type, created_at);
            CREATE INDEX IF NOT EXISTS idx_shop_products_pub ON shop_products(is_published, category_slug, sort_order, id);
        """)
        conn.commit()

        existing_cols = {r["name"] for r in conn.execute("PRAGMA table_info(orders)").fetchall()}
        if "latitude" not in existing_cols:
            conn.execute("ALTER TABLE orders ADD COLUMN latitude REAL")
        if "longitude" not in existing_cols:
            conn.execute("ALTER TABLE orders ADD COLUMN longitude REAL")
        if "source" not in existing_cols:
            conn.execute("ALTER TABLE orders ADD COLUMN source TEXT DEFAULT 'bot'")
        conn.commit()
        conn.close()

    def event_add(self, user_id: int, event_type: str, meta: Optional[Dict] = None):
        conn = self._get_conn()
        cur = conn.cursor()
        ts = now_tz().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            "INSERT INTO events (user_id, event_type, meta, created_at) VALUES (?,?,?,?)",
            (user_id, event_type, json.dumps(meta or {}, ensure_ascii=False), ts)
        )
        conn.commit()

    def user_upsert(self, user_id: int, username: str, lang: str):
        conn = self._get_conn()
        cur = conn.cursor()
        ts = now_tz().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,))
        if cur.fetchone():
            cur.execute("UPDATE users SET username=?, lang=? WHERE user_id=?", (username, lang, user_id))
        else:
            cur.execute(
                "INSERT INTO users (user_id, username, lang, created_at) VALUES (?,?,?,?)",
                (user_id, username, lang, ts)
            )
        conn.commit()

    def user_get(self, user_id: int) -> Optional[Dict]:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def cart_add(self, user_id: int, product_name: str, qty: int = 1, size: str = ""):
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO carts (user_id, product_name, qty, size) VALUES (?,?,?,?)",
            (user_id, product_name, qty, size)
        )
        conn.commit()
        self.event_add(user_id, "cart_add", {"product": product_name, "qty": qty})

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

    def order_create(self, data: Dict) -> int:
        conn = self._get_conn()
        cur = conn.cursor()
        ts = now_tz().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("""
            INSERT INTO orders (
                user_id, username, name, phone, city, items,
                total_amount, delivery_type, delivery_address,
                comment, status, created_at, latitude, longitude, source
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            data.get("user_id"),
            data.get("username", ""),
            data.get("name", ""),
            data.get("phone", ""),
            data.get("city", ""),
            data.get("items", "[]"),
            data.get("total_amount", 0),
            data.get("delivery_type", ""),
            data.get("delivery_address", ""),
            data.get("comment", "—"),
            "new",
            ts,
            data.get("latitude"),
            data.get("longitude"),
            data.get("source", "bot"),
        ))
        conn.commit()
        order_id = cur.lastrowid

        if data.get("user_id"):
            self.event_add(data["user_id"], "order_created", {"order_id": order_id, "source": data.get("source", "bot")})

        return order_id

    def order_get(self, order_id: int) -> Optional[Dict]:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM orders WHERE id=?", (order_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def orders_get_by_status(self, status: str, limit: int = 50) -> List[Dict]:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM orders WHERE status=? ORDER BY created_at DESC LIMIT ?", (status, limit))
        return [dict(r) for r in cur.fetchall()]

    def orders_get_user(self, user_id: int, limit: int = 10) -> List[Dict]:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit))
        return [dict(r) for r in cur.fetchall()]

    def order_update_status(self, order_id: int, status: str, manager_id: int = None):
        conn = self._get_conn()
        cur = conn.cursor()
        if manager_id is not None:
            cur.execute("UPDATE orders SET status=?, manager_id=?, manager_seen=1 WHERE id=?", (status, manager_id, order_id))
        else:
            cur.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
        conn.commit()

    def order_mark_seen(self, order_id: int, manager_id: int):
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("UPDATE orders SET manager_seen=1, manager_id=? WHERE id=?", (manager_id, order_id))
        conn.commit()

    def orders_get_for_reminder(self) -> List[Dict]:
        conn = self._get_conn()
        cur = conn.cursor()
        cutoff = (now_tz() - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
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
        ts = now_tz().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("UPDATE orders SET reminded_at=? WHERE id=?", (ts, order_id))
        conn.commit()

    def orders_get_monthly(self, year: int, month: int) -> List[Dict]:
        conn = self._get_conn()
        cur = conn.cursor()
        start = f"{year}-{month:02d}-01 00:00:00"
        last_day = monthrange(year, month)[1]
        end = f"{year}-{month:02d}-{last_day} 23:59:59"
        cur.execute("SELECT * FROM orders WHERE created_at BETWEEN ? AND ? ORDER BY id", (start, end))
        return [dict(r) for r in cur.fetchall()]

    def report_mark_sent(self, year: int, month: int, filename: str, total_orders: int, total_amount: int):
        conn = self._get_conn()
        cur = conn.cursor()
        ts = now_tz().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("""
            INSERT INTO monthly_reports (year, month, sent_at, filename, total_orders, total_amount, status)
            VALUES (?,?,?,?,?,?,?)
        """, (year, month, ts, filename, total_orders, total_amount, "sent"))
        conn.commit()

    def report_is_sent(self, year: int, month: int) -> bool:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM monthly_reports WHERE year=? AND month=? AND status='sent'", (year, month))
        return cur.fetchone() is not None

    def get_stats_all(self) -> Dict:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status='new' THEN 1 ELSE 0 END) as new,
                SUM(CASE WHEN status='processing' THEN 1 ELSE 0 END) as processing,
                SUM(CASE WHEN status='shipped' THEN 1 ELSE 0 END) as shipped,
                SUM(CASE WHEN status='delivered' THEN 1 ELSE 0 END) as delivered,
                SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END) as cancelled,
                COUNT(DISTINCT user_id) as unique_users
            FROM orders
        """)
        row = cur.fetchone()
        return dict(row) if row else {
            "total": 0, "new": 0, "processing": 0, "shipped": 0,
            "delivered": 0, "cancelled": 0, "unique_users": 0
        }

    def week_key_now(self, dt: datetime) -> str:
        iso = dt.isocalendar()
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
        ts = now_tz().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("UPDATE scheduled_posts SET posted_at=? WHERE id=?", (ts, post_id))
        conn.commit()

    def sched_count_week(self, week_key: str) -> int:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as c FROM scheduled_posts WHERE week_key=?", (week_key,))
        r = cur.fetchone()
        return int(r["c"]) if r else 0

    def stats_range(self, start: str, end: str) -> Dict:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status='new' THEN 1 ELSE 0 END) as new,
                SUM(CASE WHEN status='processing' THEN 1 ELSE 0 END) as processing,
                SUM(CASE WHEN status='shipped' THEN 1 ELSE 0 END) as shipped,
                SUM(CASE WHEN status='delivered' THEN 1 ELSE 0 END) as delivered,
                SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END) as cancelled
            FROM orders
            WHERE created_at BETWEEN ? AND ?
        """, (start, end))
        row = cur.fetchone()
        return dict(row) if row else {
            "total": 0, "new": 0, "processing": 0, "shipped": 0, "delivered": 0, "cancelled": 0
        }

    def top_products_range(self, start: str, end: str, limit: int = 10) -> List[Tuple[str, int]]:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT items FROM orders WHERE created_at BETWEEN ? AND ?", (start, end))
        counter: Dict[str, int] = {}
        for r in cur.fetchall():
            try:
                items = json.loads(r["items"] or "[]")
            except Exception:
                items = []
            for it in items:
                name = (it.get("name") or it.get("product_name") or "").strip()
                qty = int(it.get("qty") or 1)
                if not name:
                    continue
                counter[name] = counter.get(name, 0) + qty
        return sorted(counter.items(), key=lambda x: x[1], reverse=True)[:limit]

    def top_cities_range(self, start: str, end: str, limit: int = 10) -> List[Tuple[str, int]]:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT city, COUNT(*) as c
            FROM orders
            WHERE created_at BETWEEN ? AND ?
            GROUP BY city
            ORDER BY c DESC
            LIMIT ?
        """, (start, end, limit))
        return [(r["city"] or "—", int(r["c"])) for r in cur.fetchall()]

    def ru_vs_uz_range(self, start: str, end: str) -> Dict:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT u.lang as lang, COUNT(o.id) as c
            FROM orders o
            LEFT JOIN users u ON u.user_id = o.user_id
            WHERE o.created_at BETWEEN ? AND ?
            GROUP BY u.lang
        """, (start, end))
        res = {"ru": 0, "uz": 0, "unknown": 0}
        for r in cur.fetchall():
            lang = (r["lang"] or "unknown").lower()
            if lang not in res:
                lang = "unknown"
            res[lang] += int(r["c"])
        return res

    def funnel_range(self, start: str, end: str) -> Dict:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT
              SUM(CASE WHEN event_type='cart_add' THEN 1 ELSE 0 END) as cart_add,
              SUM(CASE WHEN event_type='order_created' THEN 1 ELSE 0 END) as order_created
            FROM events
            WHERE created_at BETWEEN ? AND ?
        """, (start, end))
        r = cur.fetchone()
        cart_add = int(r["cart_add"] or 0) if r else 0
        order_created = int(r["order_created"] or 0) if r else 0
        conv = (order_created / cart_add * 100.0) if cart_add > 0 else 0.0
        return {"cart_add": cart_add, "order_created": order_created, "conversion": round(conv, 2)}

    def orders_filter(self, status: str = "", city: str = "", phone_q: str = "", limit: int = 200) -> List[Dict]:
        conn = self._get_conn()
        cur = conn.cursor()
        q = "SELECT * FROM orders WHERE 1=1"
        args: List = []
        if status:
            q += " AND status=?"
            args.append(status)
        if city:
            q += " AND city LIKE ?"
            args.append(f"%{city}%")
        if phone_q:
            q += " AND phone LIKE ?"
            args.append(f"%{phone_q}%")
        q += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        cur.execute(q, tuple(args))
        return [dict(r) for r in cur.fetchall()]

    def find_orders_by_phone(self, phone_part: str, limit: int = 20) -> List[Dict]:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM orders
            WHERE phone LIKE ?
            ORDER BY id DESC
            LIMIT ?
        """, (f"%{phone_part}%", limit))
        return [dict(r) for r in cur.fetchall()]

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
        price_on_request: int,
        is_published: int = 1,
        sort_order: int = 0,
    ) -> int:
        if category_slug not in SHOP_CATEGORIES:
            category_slug = "casual"

        conn = self._get_conn()
        cur = conn.cursor()
        ts = now_tz().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("""
            INSERT INTO shop_products (
                photo_file_id, title_ru, title_uz,
                description_ru, description_uz,
                sizes, category_slug, price, price_on_request,
                is_published, sort_order, created_at, updated_at
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            photo_file_id, title_ru, title_uz,
            description_ru, description_uz,
            sizes, category_slug, int(price or 0), int(price_on_request or 0),
            int(is_published), int(sort_order),
            ts, ts
        ))
        conn.commit()
        return cur.lastrowid

    def shop_product_update_publish(self, product_id: int, is_published: int):
        conn = self._get_conn()
        cur = conn.cursor()
        ts = now_tz().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("UPDATE shop_products SET is_published=?, updated_at=? WHERE id=?", (int(is_published), ts, product_id))
        conn.commit()

    def shop_product_delete(self, product_id: int):
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM shop_products WHERE id=?", (product_id,))
        conn.commit()

    def shop_product_get(self, product_id: int) -> Optional[Dict]:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM shop_products WHERE id=?", (product_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def shop_products_list(self, published_only: bool = True, limit: int = 500) -> List[Dict]:
        conn = self._get_conn()
        cur = conn.cursor()
        if published_only:
            cur.execute("""
                SELECT * FROM shop_products
                WHERE is_published=1
                ORDER BY sort_order ASC, id DESC
                LIMIT ?
            """, (limit,))
        else:
            cur.execute("""
                SELECT * FROM shop_products
                ORDER BY sort_order ASC, id DESC
                LIMIT ?
            """, (limit,))
        return [dict(r) for r in cur.fetchall()]

    def shop_products_by_category(self, category_slug: str, published_only: bool = True, limit: int = 200) -> List[Dict]:
        conn = self._get_conn()
        cur = conn.cursor()
        if published_only:
            cur.execute("""
                SELECT * FROM shop_products
                WHERE category_slug=? AND is_published=1
                ORDER BY sort_order ASC, id DESC
                LIMIT ?
            """, (category_slug, limit))
        else:
            cur.execute("""
                SELECT * FROM shop_products
                WHERE category_slug=?
                ORDER BY sort_order ASC, id DESC
                LIMIT ?
            """, (category_slug, limit))
        return [dict(r) for r in cur.fetchall()]

    def shop_products_count(self) -> int:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS c FROM shop_products")
        row = cur.fetchone()
        return int(row["c"]) if row else 0

    def shop_seed_demo_if_empty(self):
        if self.shop_products_count() > 0:
            return
        demo = [
            {
                "photo_file_id": "",
                "title_ru": "Kids Hoodie",
                "title_uz": "Bolalar hudi",
                "description_ru": "Тёплый худи из хлопка для повседневной носки.",
                "description_uz": "Kundalik kiyish uchun issiq paxtali hudi.",
                "sizes": "98,104,110,116",
                "category_slug": "new",
                "price": 250000,
                "price_on_request": 0,
            },
            {
                "photo_file_id": "",
                "title_ru": "Mini Boss Suit",
                "title_uz": "Mini Boss kostyum",
                "description_ru": "Стильный костюм для особых дней.",
                "description_uz": "Maxsus kunlar uchun zamonaviy kostyum.",
                "sizes": "98,104,110,116,122",
                "category_slug": "hits",
                "price": 390000,
                "price_on_request": 0,
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
                "price_on_request": 0,
            },
            {
                "photo_file_id": "",
                "title_ru": "Daily Comfort",
                "title_uz": "Kundalik kiyim",
                "description_ru": "Комфортный комплект на каждый день.",
                "description_uz": "Har kun uchun qulay kiyim to‘plami.",
                "sizes": "98,104,110",
                "category_slug": "casual",
                "price": 0,
                "price_on_request": 1,
            },
        ]
        for item in demo:
            self.shop_product_add(**item)


db = Database()
db.shop_seed_demo_if_empty()


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
    WebAppInfo,
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
        "catalog_hint": "Чтобы быстро оформить — нажмите <b>✅ Заказ</b> (выбор товаров внутри бота).",
        "price": "🧾 <b>Прайс-лист</b>\n\n💬 Цена — по договоренности (зависит от модели/размера).\n\n✅ Нажмите «Заказ» для оформления",
        "size": "📏 <b>Подбор размера</b>\n\nВыберите способ:",
        "size_age": "Введите возраст (1-15 лет):\nПример: 7",
        "size_height": "Введите рост в см:\nПример: 125",
        "size_result": "📏 Рекомендуемый размер: <b>{size}</b>\n\n✅ Если определились — нажмите <b>✅ Заказ</b> или вернитесь в меню.",
        "cart": "🛒 <b>Корзина</b>\n\n{items}\n\n💬 Цена: <b>по договоренности</b>\nНажмите <b>✅ Оформить</b>, чтобы продолжить.",
        "cart_empty": "🛒 Корзина пуста\n\nПерейдите в <b>✅ Заказ</b> и выберите товар (или напишите свой).",
        "cart_added": "✅ Добавлено в корзину",
        "delivery": "🚚 <b>Доставка</b>\n\n1️⃣ <b>B2B Почта</b> — 2-5 дней, весь Узбекистан\n2️⃣ <b>Яндекс Курьер</b> — 1-3 дня, крупные города\n3️⃣ <b>Яндекс ПВЗ</b> — 1-3 дня, пункты выдачи\n\n💬 Стоимость доставки зависит от города.",
        "faq": "❓ <b>FAQ</b>\n\n<b>Доставка?</b>\n— По всему Узбекистану, 1-5 дней\n\n<b>Оплата?</b>\n— Наличными или переводом\n\n<b>Возврат?</b>\n— 14 дней при сохранении вида\n\n<b>Размеры?</b>\n— Используйте подбор в боте",
        "contact": "📞 <b>Связаться</b>\n\n☎️ {phone}\n⏰ Пн-Пт: 09:00-21:00\n📱 @{username}",
        "order_start": "🛍 <b>Выберите товар</b>\n\nНажмите на кнопку товара ниже 👇\nЕсли вашего товара нет — нажмите <b>✍️ Ввести вручную</b>",
        "order_manual": "📝 Введите название товара (например: худи, джинсы, школьная форма):",
        "order_phone": "📱 Отправьте номер телефона:",
        "order_city": "🏙 Введите город:",
        "order_delivery": "🚚 Выберите способ доставки (нажмите кнопку):",
        "order_address": "📍 Введите адрес доставки:",
        "order_confirm": "📝 <b>Проверьте заказ:</b>\n\n👤 {name}\n📱 {phone}\n🏙 {city}\n🚚 {delivery}\n📍 {address}\n\n🛒 Товары:\n{items}\n\n💬 Цена: <b>по договоренности</b>\nМенеджер уточнит размер и итоговую сумму.\n\nПодтвердить?",
        "order_success": "✅ Заказ #{order_id} принят!\n\nУважаемый покупатель, вам поступят уведомления о статусе.\nМенеджер скоро свяжется и уточнит детали.\n⏰ 09:00-21:00",
        "thanks_new": "🙏 Спасибо за заказ! Мы рады, что вы с нами 🤍\n\nЧтобы нас не потерять — подпишитесь на наши каналы:",
        "thanks_delivered": (
            "🤍 Спасибо, что выбрали ZARY & CO!\n\n"
            "Надеемся, одежда принесёт радость и комфорт.\n"
            "Носите с удовольствием и на здоровье ✨\n\n"
            "Будем рады видеть вас снова!\n"
            "Чтобы не пропустить новинки — подпишитесь на наши каналы 👇"
        ),
        "history": "📜 <b>История заказов</b>\n\n{orders}",
        "history_empty": "📜 У вас пока нет заказов",
        "admin_menu": "🛠 <b>Админ панель</b>\n\nВыберите действие:",
        "admin_stats": "📊 <b>Статистика</b>\n\n📦 Всего: {total}\n🆕 Новых: {new}\n⚙️ В обработке: {processing}\n🚚 Отправлено: {shipped}\n✅ Доставлено: {delivered}\n❌ Отменено: {cancelled}\n👥 Клиентов: {unique_users}",
        "cancelled": "❌ Отменено",
        "shop_open_text": (
            "🛍 <b>ZARY & CO Store</b>\n\n"
            "Откройте магазин внутри Telegram:\n"
            "• Hero-экран\n• Категории\n• Сетка товаров\n• Корзина\n• Оформление заказа\n• Геолокация"
        ),
        "shop_open_btn": "Смотреть коллекцию",
        "shop_products_admin": "🛍 <b>Управление магазином</b>\n\nВыберите действие:",
        "shop_add_start": "1️⃣ Отправьте фото товара одним сообщением.",
        "shop_add_title_ru": "2️⃣ Введите название товара на русском.",
        "shop_add_title_uz": "3️⃣ Введите название товара на узбекском.",
        "shop_add_desc_ru": "4️⃣ Введите описание товара на русском.",
        "shop_add_desc_uz": "5️⃣ Введите описание товара на узбекском.",
        "shop_add_sizes": "6️⃣ Введите размеры через запятую.\nНапример: 98,104,110,116",
        "shop_add_category": "7️⃣ Введите категорию:\nnew / hits / sale / limited / school / casual",
        "shop_add_price": "8️⃣ Введите цену цифрами.\nИли напишите <code>request</code>, если <b>Цена по запросу</b>.",
        "shop_add_done": "✅ Товар магазина успешно добавлен.",
        "shop_empty": "Пока нет товаров магазина.",
        "shop_select_product": "Выберите товар:",
        "shop_product_hidden": "✅ Статус публикации изменён.",
        "shop_product_deleted": "🗑 Товар удалён.",
        "shop_invalid_category": "Неверная категория. Допустимо: new / hits / sale / limited / school / casual",
        "shop_invalid_price": "Введите цену цифрами или слово <code>request</code>.",
    },
    "uz": {
        "welcome": "👋 <b>ZARY & CO</b> ga xush kelibsiz!\n\n🧸 Bolalar kiyimi premium sifat\n📦 O'zbekiston bo'ylab yetkazib berish 1-5 kun\n\nAmalni tanlang 👇",
        "menu": "📍 Asosiy menyu",
        "catalog": "📸 <b>Katalog</b>\n\nKategoriyani tanlang:",
        "catalog_hint": "Tez buyurtma uchun <b>✅ Buyurtma</b> ni bosing (bot ichida tanlash).",
        "price": "🧾 <b>Narxlar</b>\n\n💬 Narx — kelishuv bo'yicha (model/o'lchamga qarab).\n\n✅ «Buyurtma» ni bosing",
        "size": "📏 <b>O'lcham tanlash</b>\n\nUsulni tanlang:",
        "size_age": "Yoshini kiriting (1-15 yosh):\nMisol: 7",
        "size_height": "Bo'yni sm da kiriting:\nMisol: 125",
        "size_result": "📏 Tavsiya etilgan o'lcham: <b>{size}</b>\n\n✅ Tayyor bo'lsangiz <b>✅ Buyurtma</b> ni bosing yoki menyuga qayting.",
        "cart": "🛒 <b>Savat</b>\n\n{items}\n\n💬 Narx: <b>kelishuv bo'yicha</b>\n<b>✅ Rasmiylashtirish</b> ni bosing.",
        "cart_empty": "🛒 Savat bo'sh\n\n<b>✅ Buyurtma</b> ga kiring va tovar tanlang (yoki o'zingiz yozing).",
        "cart_added": "✅ Savatga qo'shildi",
        "delivery": "🚚 <b>Yetkazib berish</b>\n\n1️⃣ <b>B2B Pochta</b> — 2-5 kun\n2️⃣ <b>Yandex Kuryer</b> — 1-3 kun\n3️⃣ <b>Yandex PVZ</b> — 1-3 kun\n\n💬 Yetkazib berish narxi shahar bo'yicha.",
        "faq": "❓ <b>FAQ</b>\n\n<b>Yetkazib berish?</b>\n— Butun O'zbekiston, 1-5 kun\n\n<b>To'lov?</b>\n— Naqd yoki o'tkazma\n\n<b>Qaytarish?</b>\n— 14 kun ichida (tovar ko'rinishi saqlangan bo'lsa)\n\n<b>O'lchamlar?</b>\n— Botdagi o'lcham tanlashdan foydalaning",
        "contact": "📞 <b>Aloqa</b>\n\n☎️ {phone}\n⏰ Du-Sha: 09:00-21:00\n📱 @{username}",
        "order_start": "🛍 <b>Tovar tanlang</b>\n\nQuyidagi tugmalardan birini bosing 👇\nAgar kerakli tovar bo'lmasa — <b>✍️ Qo'lda kiritish</b> ni bosing",
        "order_manual": "📝 Mahsulot nomini kiriting (masalan: hudi, jinsi, maktab formasi):",
        "order_phone": "📱 Telefon raqamingizni yuboring:",
        "order_city": "🏙 Shaharni kiriting:",
        "order_delivery": "🚚 Yetkazib berish usulini tanlang (tugmani bosing):",
        "order_address": "📍 Manzilni kiriting:",
        "order_confirm": "📝 <b>Buyurtmani tekshiring:</b>\n\n👤 {name}\n📱 {phone}\n🏙 {city}\n🚚 {delivery}\n📍 {address}\n\n🛒 Tovarlar:\n{items}\n\n💬 Narx: <b>kelishuv bo'yicha</b>\nMenejer o'lcham va yakuniy summani aniqlaydi.\n\nTasdiqlaysizmi?",
        "order_success": "✅ Buyurtma #{order_id} qabul qilindi!\n\nHurmatli mijoz, status bo'yicha xabarlar yuboriladi.\nMenejer tez orada bog'lanadi.\n⏰ 09:00-21:00",
        "thanks_new": "🙏 Buyurtmangiz uchun rahmat! Siz biz bilan ekaningizdan xursandmiz 🤍\n\nBizni yo‘qotib qo‘ymaslik uchun kanallarimizga obuna bo‘ling:",
        "thanks_delivered": (
            "🤍 ZARY & CO ni tanlaganingiz uchun rahmat!\n\n"
            "Kiyim sizga qulaylik va xursandchilik olib kelsin.\n"
            "Yaxshi kayfiyat bilan kiying ✨\n\n"
            "Yana sizni ko‘rishdan xursand bo‘lamiz!\n"
            "Yangiliklarni o‘tkazib yubormaslik uchun kanallarimizga obuna bo‘ling 👇"
        ),
        "history": "📜 <b>Buyurtmalar tarixi</b>\n\n{orders}",
        "history_empty": "Hozircha buyurtmalar yo'q",
        "admin_menu": "🛠 <b>Admin paneli</b>\n\nAmalni tanlang:",
        "admin_stats": "📊 <b>Statistika</b>\n\n📦 Jami: {total}\n🆕 Yangi: {new}\n⚙️ Ishlanmoqda: {processing}\n🚚 Jo'natildi: {shipped}\n✅ Yetkazildi: {delivered}\n❌ Bekor: {cancelled}\n👥 Mijozlar: {unique_users}",
        "cancelled": "❌ Bekor qilindi",
        "shop_open_text": (
            "🛍 <b>ZARY & CO Do‘kon</b>\n\n"
            "Telegram ichida do‘konni oching:\n"
            "• Hero-ekran\n• Kategoriyalar\n• Tovarlar setkasi\n• Savat\n• Buyurtma berish\n• Geolokatsiya"
        ),
        "shop_open_btn": "Kolleksiyani ko‘rish",
        "shop_products_admin": "🛍 <b>Do‘kon boshqaruvi</b>\n\nAmalni tanlang:",
        "shop_add_start": "1️⃣ Tovar rasmini bitta xabar bilan yuboring.",
        "shop_add_title_ru": "2️⃣ Tovar nomini rus tilida kiriting.",
        "shop_add_title_uz": "3️⃣ Tovar nomini o‘zbek tilida kiriting.",
        "shop_add_desc_ru": "4️⃣ Tovar tavsifini rus tilida kiriting.",
        "shop_add_desc_uz": "5️⃣ Tovar tavsifini o‘zbek tilida kiriting.",
        "shop_add_sizes": "6️⃣ Razmerlarni vergul bilan kiriting.\nMasalan: 98,104,110,116",
        "shop_add_category": "7️⃣ Kategoriya kiriting:\nnew / hits / sale / limited / school / casual",
        "shop_add_price": "8️⃣ Narxni raqam bilan kiriting.\nYoki <code>request</code> deb yozing, agar <b>Narx so‘rov bo‘yicha</b> bo‘lsa.",
        "shop_add_done": "✅ Do‘kon mahsuloti muvaffaqiyatli qo‘shildi.",
        "shop_empty": "Hozircha do‘kon tovarlari yo‘q.",
        "shop_select_product": "Tovarni tanlang:",
        "shop_product_hidden": "✅ E’lon holati o‘zgartirildi.",
        "shop_product_deleted": "🗑 Tovar o‘chirildi.",
        "shop_invalid_category": "Noto‘g‘ri kategoriya. Faqat: new / hits / sale / limited / school / casual",
        "shop_invalid_price": "Narxni raqam bilan yoki <code>request</code> deb yuboring.",
    }
}


def kb_main(lang: str, is_admin_flag: bool = False) -> ReplyKeyboardMarkup:
    if lang == "uz":
        rows = [
            [KeyboardButton(text="🛍 Do'kon"), KeyboardButton(text="📸 Katalog")],
            [KeyboardButton(text="🧾 Narxlar"), KeyboardButton(text="📏 O'lcham")],
            [KeyboardButton(text="🛒 Savat"), KeyboardButton(text="🚚 Yetkazib berish")],
            [KeyboardButton(text="❓ FAQ"), KeyboardButton(text="📞 Aloqa")],
            [KeyboardButton(text="✅ Buyurtma"), KeyboardButton(text="📜 Buyurtmalar")],
            [KeyboardButton(text="🌐 Til")],
        ]
    else:
        rows = [
            [KeyboardButton(text="🛍 Магазин"), KeyboardButton(text="📸 Каталог")],
            [KeyboardButton(text="🧾 Прайс"), KeyboardButton(text="📏 Размер")],
            [KeyboardButton(text="🛒 Корзина"), KeyboardButton(text="🚚 Доставка")],
            [KeyboardButton(text="❓ FAQ"), KeyboardButton(text="📞 Связаться")],
            [KeyboardButton(text="✅ Заказ"), KeyboardButton(text="📜 История")],
            [KeyboardButton(text="🌐 Язык")],
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
    buttons.append([InlineKeyboardButton(text="✅ Быстрый заказ" if lang == "ru" else "✅ Tez buyurtma", callback_data="quick_order")])
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
        [InlineKeyboardButton(text="📦 B2B Почта" if lang == "ru" else "📦 B2B Pochta", callback_data="delivery:b2b")],
        [InlineKeyboardButton(text="🚚 Яндекс Курьер" if lang == "ru" else "🚚 Yandex Kuryer", callback_data="delivery:yandex_courier")],
        [InlineKeyboardButton(text="🏪 Яндекс ПВЗ" if lang == "ru" else "🏪 Yandex PVZ", callback_data="delivery:yandex_pvz")],
        [InlineKeyboardButton(text="⬅️ Назад" if lang == "ru" else "⬅️ Orqaga", callback_data="back:menu")],
    ])

def kb_cart(items: List[Dict], lang: str) -> InlineKeyboardMarkup:
    buttons = []
    for item in items:
        name = item["product_name"][:22]
        btn_text = f"❌ {name} (x{item['qty']})"
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
    rows = [
        [InlineKeyboardButton(text="📋 Новые заказы" if lang == "ru" else "📋 Yangi buyurtmalar", callback_data="admin:new")],
        [InlineKeyboardButton(text="⚙️ В обработке" if lang == "ru" else "⚙️ Ishlanmoqda", callback_data="admin:processing")],
        [InlineKeyboardButton(text="📊 Статистика" if lang == "ru" else "📊 Statistika", callback_data="admin:stats")],
        [InlineKeyboardButton(text="📤 Excel отчет" if lang == "ru" else "📤 Excel hisobot", callback_data="admin:export")],
        [InlineKeyboardButton(text="📰 Посты недели" if lang == "ru" else "📰 Haftalik postlar", callback_data="admin:posts")],
        [InlineKeyboardButton(text="🛍 Магазин: добавить" if lang == "ru" else "🛍 Do'kon: qo'shish", callback_data="shop_admin:add")],
        [InlineKeyboardButton(text="🙈 Магазин: скрыть/показать" if lang == "ru" else "🙈 Do'kon: yashirish/ko'rsatish", callback_data="shop_admin:toggle")],
        [InlineKeyboardButton(text="🗑 Магазин: удалить" if lang == "ru" else "🗑 Do'kon: o'chirish", callback_data="shop_admin:delete")],
        [InlineKeyboardButton(text="⬅️ Назад" if lang == "ru" else "⬅️ Orqaga", callback_data="back:menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_admin_order(order_id: int, user_id: Optional[int], lang: str) -> InlineKeyboardMarkup:
    rows = []
    if user_id:
        rows.append([InlineKeyboardButton(text="📞 Написать клиенту" if lang == "ru" else "📞 Mijozga yozish", url=f"tg://user?id={user_id}")])

    rows.extend([
        [
            InlineKeyboardButton(text="👁 Просмотрено" if lang == "ru" else "👁 Ko'rildi", callback_data=f"order_seen:{order_id}"),
            InlineKeyboardButton(text="⚙️ В работу" if lang == "ru" else "⚙️ Ishga", callback_data=f"order_process:{order_id}")
        ],
        [
            InlineKeyboardButton(text="🚚 Отправлен" if lang == "ru" else "🚚 Jo'natildi", callback_data=f"order_ship:{order_id}"),
            InlineKeyboardButton(text="✅ Доставлен" if lang == "ru" else "✅ Yetkazildi", callback_data=f"order_deliver:{order_id}")
        ],
        [InlineKeyboardButton(text="❌ Отмена" if lang == "ru" else "❌ Bekor", callback_data=f"order_cancel:{order_id}")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_contact(lang: str) -> ReplyKeyboardMarkup:
    if lang == "uz":
        btn = KeyboardButton(text="📱 Raqamni yuborish", request_contact=True)
        cancel = KeyboardButton(text="❌ Bekor qilish")
    else:
        btn = KeyboardButton(text="📱 Отправить номер", request_contact=True)
        cancel = KeyboardButton(text="❌ Отмена")
    return ReplyKeyboardMarkup(keyboard=[[btn], [cancel]], resize_keyboard=True, one_time_keyboard=True)

def kb_channel_and_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📣 Канал" if lang == "ru" else "📣 Kanal", url=TG_CHANNEL_URL)],
        [InlineKeyboardButton(text="⬅️ Меню" if lang == "ru" else "⬅️ Menyu", callback_data="back:menu")],
    ])

def kb_follow_links(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📣 Telegram канал", url=FOLLOW_TG)],
        [InlineKeyboardButton(text="📺 YouTube", url=FOLLOW_YT)],
        [InlineKeyboardButton(text="📸 Instagram", url=FOLLOW_IG)],
    ])

def kb_quick_products(lang: str) -> InlineKeyboardMarkup:
    items = PRODUCTS_RU if lang == "ru" else PRODUCTS_UZ
    rows = []
    for i in range(0, min(len(items), 12), 2):
        a = items[i]
        b = items[i + 1] if i + 1 < min(len(items), 12) else None
        row = [InlineKeyboardButton(text=a, callback_data=f"prod:{i}")]
        if b:
            row.append(InlineKeyboardButton(text=b, callback_data=f"prod:{i+1}"))
        rows.append(row)

    rows.append([InlineKeyboardButton(text="✍️ Ввести вручную" if lang == "ru" else "✍️ Qo'lda kiritish", callback_data="prod_manual")])
    rows.append([InlineKeyboardButton(text="🛒 Корзина" if lang == "ru" else "🛒 Savat", callback_data="go_cart")])
    rows.append([InlineKeyboardButton(text="⬅️ Меню" if lang == "ru" else "⬅️ Menyu", callback_data="back:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_after_add(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить ещё" if lang == "ru" else "➕ Yana qo‘shish", callback_data="quick_order")],
        [InlineKeyboardButton(text="🛒 Перейти в корзину" if lang == "ru" else "🛒 Savatga o‘tish", callback_data="go_cart")],
        [InlineKeyboardButton(text="✅ Оформить заказ" if lang == "ru" else "✅ Buyurtmani rasmiylashtirish", callback_data="cart:checkout")],
        [InlineKeyboardButton(text="⬅️ Меню" if lang == "ru" else "⬅️ Menyu", callback_data="back:menu")],
    ])

def kb_dow(lang: str) -> InlineKeyboardMarkup:
    if lang == "uz":
        names = [(1, "Dushanba"), (2, "Seshanba"), (3, "Chorshanba"), (4, "Payshanba"), (5, "Juma"), (6, "Shanba")]
    else:
        names = [(1, "Понедельник"), (2, "Вторник"), (3, "Среда"), (4, "Четверг"), (5, "Пятница"), (6, "Суббота")]

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

def kb_shop_open(lang: str) -> InlineKeyboardMarkup:
    shop_url = f"{BASE_URL}/shop?lang={lang}&token={WEBAPP_SECRET}" if BASE_URL else f"/shop?lang={lang}&token={WEBAPP_SECRET}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=TEXT[lang]["shop_open_btn"], web_app=WebAppInfo(url=shop_url))],
        [InlineKeyboardButton(text="⬅️ Меню" if lang == "ru" else "⬅️ Menyu", callback_data="back:menu")],
    ])

def kb_shop_products_manage(rows: List[Dict], action: str, lang: str) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = []
    for row in rows[:30]:
        title = row["title_ru"] if lang == "ru" else row["title_uz"]
        if action == "toggle":
            status = "✅" if int(row.get("is_published", 1)) == 1 else "🙈"
            txt = f"{status} #{row['id']} {title[:24]}"
        else:
            txt = f"#{row['id']} {title[:24]}"
        buttons.append([InlineKeyboardButton(text=txt, callback_data=f"shop_admin_{action}:{row['id']}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад" if lang == "ru" else "⬅️ Orqaga", callback_data="admin:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


class States(StatesGroup):
    size_age = State()
    size_height = State()
    order_name = State()
    order_phone = State()
    order_city = State()
    order_delivery = State()
    order_address = State()
    prod_manual = State()
    admin_post_dow = State()
    admin_post_media = State()
    shop_add_photo = State()
    shop_add_title_ru = State()
    shop_add_title_uz = State()
    shop_add_desc_ru = State()
    shop_add_desc_uz = State()
    shop_add_sizes = State()
    shop_add_category = State()
    shop_add_price = State()


bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())


def get_user_lang(user_id: int, default: str = "ru") -> str:
    user = db.user_get(user_id)
    if user and user.get("lang") in ("ru", "uz"):
        return user["lang"]
    return default

async def send_order_to_admins(order_id: int, order_data: Dict, items: List[Dict], lang_for_customer: str, delivery_name: str):
    items_text = ", ".join([f"{esc(it.get('product_name') or it.get('name') or it.get('title') or '')} x{it.get('qty', 1)}" for it in items]) or "—"
    location_note = ""
    if order_data.get("latitude") is not None and order_data.get("longitude") is not None:
        location_note = f"\n🗺 Геолокация: {order_data['latitude']}, {order_data['longitude']}"

    text = (
        f"🆕 Новый заказ #{order_id}\n\n"
        f"👤 {esc(order_data.get('name', '—'))}\n"
        f"📱 {esc(order_data.get('phone', '—'))}\n"
        f"🏙 {esc(order_data.get('city', '—'))}\n"
        f"🚚 {esc(delivery_name or '—')}\n"
        f"📍 {esc(order_data.get('delivery_address', '—'))}{location_note}\n"
        f"🛒 {items_text}\n"
        f"💰 Сумма: {money_fmt(order_data.get('total_amount', 0))}\n"
        f"🧾 Источник: {esc(order_data.get('source', 'bot'))}"
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                text,
                reply_markup=kb_admin_order(order_id, order_data.get("user_id"), "ru")
            )
            if order_data.get("latitude") is not None and order_data.get("longitude") is not None:
                try:
                    await bot.send_location(admin_id, float(order_data["latitude"]), float(order_data["longitude"]))
                except Exception:
                    pass
        except Exception as e:
            print(f"Failed to notify admin {admin_id}: {e}")

    if CHANNEL_ID:
        try:
            await bot.send_message(
                CHANNEL_ID,
                (
                    f"🆕 Новый заказ #{order_id}\n"
                    f"👤 {esc(order_data.get('name', '—'))}\n"
                    f"📱 {esc(order_data.get('phone', '—'))}\n"
                    f"🏙 {esc(order_data.get('city', '—'))}\n"
                    f"🛒 {items_text}\n"
                    f"💰 Сумма: {money_fmt(order_data.get('total_amount', 0))}\n"
                    f"🧾 Источник: {esc(order_data.get('source', 'bot'))}"
                )
            )
        except Exception as e:
            print(f"Failed to send to channel {CHANNEL_ID}: {e}")

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

@dp.message(F.text.in_(["🛍 Магазин", "🛍 Do'kon"]))
async def cmd_shop_open(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"
    await state.clear()
    await message.answer(TEXT[lang]["shop_open_text"], reply_markup=kb_shop_open(lang))

@dp.message(F.text.in_(["📸 Каталог", "📸 Katalog"]))
async def cmd_catalog(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"
    await message.answer(TEXT[lang]["catalog"], reply_markup=kb_catalog(lang))
    await message.answer(TEXT[lang]["catalog_hint"], reply_markup=kb_main(lang, is_admin(message.from_user.id)))

@dp.callback_query(F.data.startswith("cat:"))
async def cat_select(call: CallbackQuery, state: FSMContext):
    user = db.user_get(call.from_user.id)
    lang = user["lang"] if user else "ru"
    cat = call.data.split(":")[1]
    await call.message.answer(
        f"📸 {cat.upper()}\n\nСмотрите полный каталог в канале 👇" if lang == "ru"
        else f"📸 {cat.upper()}\n\nTo'liq katalog kanalimizda 👇",
        reply_markup=kb_channel_and_menu(lang)
    )
    await call.answer()

@dp.callback_query(F.data == "quick_order")
async def quick_order(call: CallbackQuery, state: FSMContext):
    user = db.user_get(call.from_user.id)
    lang = user["lang"] if user else "ru"
    await state.clear()
    await call.message.answer(TEXT[lang]["order_start"], reply_markup=kb_quick_products(lang))
    await call.answer()

@dp.message(F.text.in_(["🧾 Прайс", "🧾 Narxlar"]))
async def cmd_price(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"
    await message.answer(TEXT[lang]["price"], reply_markup=kb_main(lang, is_admin(message.from_user.id)))

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

@dp.message(F.text.in_(["❓ FAQ"]))
async def cmd_faq(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"
    await message.answer(TEXT[lang]["faq"], reply_markup=kb_channel_and_menu(lang))
    await message.answer(TEXT[lang]["menu"], reply_markup=kb_main(lang, is_admin(message.from_user.id)))

@dp.message(F.text.in_(["🚚 Доставка", "🚚 Yetkazib berish"]))
async def cmd_delivery(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"
    await message.answer(TEXT[lang]["delivery"], reply_markup=kb_delivery(lang))

@dp.message(F.text.in_(["📞 Связаться", "📞 Aloqa"]))
async def cmd_contact(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"
    text = TEXT[lang]["contact"].format(phone=PHONE, username=MANAGER_USERNAME or CHANNEL_USERNAME)
    await message.answer(text, reply_markup=kb_main(lang, is_admin(message.from_user.id)))

@dp.message(F.text.in_(["🛒 Корзина", "🛒 Savat"]))
async def cmd_cart(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"

    items = db.cart_get(message.from_user.id)
    if not items:
        await message.answer(TEXT[lang]["cart_empty"], reply_markup=kb_main(lang, is_admin(message.from_user.id)))
        return

    items_text = "\n".join([f"• {esc(it['product_name'])} x{it['qty']}" for it in items])
    text = TEXT[lang]["cart"].format(items=items_text)
    await message.answer(text, reply_markup=kb_cart(items, lang))

@dp.callback_query(F.data == "go_cart")
async def go_cart(call: CallbackQuery, state: FSMContext):
    user = db.user_get(call.from_user.id)
    lang = user["lang"] if user else "ru"
    items = db.cart_get(call.from_user.id)
    if not items:
        await call.message.answer(TEXT[lang]["cart_empty"], reply_markup=kb_main(lang, is_admin(call.from_user.id)))
    else:
        items_text = "\n".join([f"• {esc(it['product_name'])} x{it['qty']}" for it in items])
        text = TEXT[lang]["cart"].format(items=items_text)
        await call.message.answer(text, reply_markup=kb_cart(items, lang))
    await call.answer()

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
        text = TEXT[lang]["cart"].format(items=items_text)
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
    await call.message.answer("Введите ваше имя:" if lang == "ru" else "Ismingizni kiriting:")
    await call.answer()

@dp.callback_query(F.data.startswith("prod:"))
async def prod_select(call: CallbackQuery, state: FSMContext):
    user = db.user_get(call.from_user.id)
    lang = user["lang"] if user else "ru"
    idx = int(call.data.split(":")[1])

    items = PRODUCTS_RU if lang == "ru" else PRODUCTS_UZ
    if 0 <= idx < len(items):
        db.cart_add(call.from_user.id, items[idx], 1)

        await call.message.answer(TEXT[lang]["cart_added"])
        await call.message.answer(
            ("🛒 Товар добавлен!\n\nЕсли хотите — добавьте ещё товары.\nЕсли достаточно — перейдите в корзину и оформите заказ 👇")
            if lang == "ru" else
            ("🛒 Mahsulot savatga qo‘shildi!\n\nXohlasangiz yana qo‘shing.\nYetarli bo‘lsa savatga o‘ting va buyurtmani rasmiylashtiring 👇"),
            reply_markup=kb_after_add(lang)
        )

    await call.answer()

@dp.callback_query(F.data == "prod_manual")
async def prod_manual_start(call: CallbackQuery, state: FSMContext):
    user = db.user_get(call.from_user.id)
    lang = user["lang"] if user else "ru"
    await state.set_state(States.prod_manual)
    await call.message.answer(TEXT[lang]["order_manual"])
    await call.answer()

@dp.message(States.prod_manual)
async def prod_manual_input(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"
    if not message.text or len(message.text.strip()) < 2:
        await message.answer(TEXT[lang]["order_manual"])
        return
    db.cart_add(message.from_user.id, message.text.strip(), 1)
    await message.answer(TEXT[lang]["cart_added"], reply_markup=kb_main(lang, is_admin(message.from_user.id)))
    await state.clear()

@dp.message(F.text.in_(["✅ Заказ", "✅ Buyurtma"]))
async def cmd_order(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"
    await state.clear()
    await message.answer(TEXT[lang]["order_start"], reply_markup=kb_quick_products(lang))

@dp.message(F.text.startswith("/find"))
async def admin_find(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or len(parts[1].strip()) < 3:
        await message.answer("Пример: /find 99877\nИщу по номеру телефона (часть номера).")
        return
    q = parts[1].strip()
    rows = db.find_orders_by_phone(q, limit=20)
    if not rows:
        await message.answer(f"Ничего не найдено по: {esc(q)}")
        return
    lines = []
    for o in rows[:10]:
        lines.append(f"#{o['id']} • {o['created_at'][:16]} • {esc(o['name'])} • {esc(o['phone'])} • {esc(o['city'])} • {o['status']}")
    await message.answer("🔎 Найдено:\n" + "\n".join(lines))

@dp.message(States.order_name)
async def order_name(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"
    if not message.text or len(message.text.strip()) < 2:
        await message.answer("Введите ваше имя:" if lang == "ru" else "Ismingizni kiriting:")
        return
    await state.update_data(name=message.text.strip())
    await state.set_state(States.order_phone)
    await message.answer(TEXT[lang]["order_phone"], reply_markup=kb_contact(lang))

@dp.message(States.order_phone)
async def order_phone(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"
    phone = message.contact.phone_number if message.contact else (message.text or "").strip()
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
    if not message.text or len(message.text.strip()) < 2:
        await message.answer(TEXT[lang]["order_city"])
        return
    await state.update_data(city=message.text.strip())
    await state.set_state(States.order_delivery)
    await message.answer(TEXT[lang]["order_delivery"], reply_markup=kb_delivery(lang))

@dp.message(States.order_delivery)
async def order_delivery_text_guard(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"
    await message.answer(TEXT[lang]["order_delivery"], reply_markup=kb_delivery(lang))

@dp.callback_query(F.data.startswith("delivery:"))
async def order_delivery_callback(call: CallbackQuery, state: FSMContext):
    delivery_type = call.data.split(":")[1]
    user = db.user_get(call.from_user.id)
    lang = user["lang"] if user else "ru"

    delivery_names = {
        "b2b": "B2B Почта" if lang == "ru" else "B2B Pochta",
        "yandex_courier": "Яндекс Курьер" if lang == "ru" else "Yandex Kuryer",
        "yandex_pvz": "Яндекс ПВЗ" if lang == "ru" else "Yandex PVZ"
    }

    await state.update_data(delivery=delivery_type, delivery_name=delivery_names.get(delivery_type, delivery_type))
    await state.set_state(States.order_address)
    await call.message.answer(TEXT[lang]["order_address"])
    await call.answer()

@dp.message(States.order_address)
async def order_address(message: Message, state: FSMContext):
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"
    if not message.text or len(message.text.strip()) < 3:
        await message.answer(TEXT[lang]["order_address"])
        return

    await state.update_data(address=message.text.strip())

    data = await state.get_data()
    items = db.cart_get(message.from_user.id)
    if not items:
        await state.clear()
        await message.answer(TEXT[lang]["cart_empty"], reply_markup=kb_main(lang, is_admin(message.from_user.id)))
        return

    items_text = "\n".join([f"• {esc(it['product_name'])} x{it['qty']}" for it in items])

    text = TEXT[lang]["order_confirm"].format(
        name=esc(data["name"]),
        phone=esc(data["phone"]),
        city=esc(data["city"]),
        delivery=esc(data.get("delivery_name", "—")),
        address=esc(data["address"]),
        items=items_text
    )
    await message.answer(text, reply_markup=kb_order_confirm(lang))

@dp.callback_query(F.data == "order:confirm")
async def order_confirm(call: CallbackQuery, state: FSMContext):
    user_row = db.user_get(call.from_user.id)
    lang = user_row["lang"] if user_row else "ru"
    data = await state.get_data()

    items = db.cart_get(call.from_user.id)
    if not items:
        await state.clear()
        await call.message.answer(TEXT[lang]["cart_empty"], reply_markup=kb_main(lang, is_admin(call.from_user.id)))
        await call.answer()
        return

    items_json = json.dumps([{"name": it["product_name"], "qty": it["qty"]} for it in items], ensure_ascii=False)

    order_data = {
        "user_id": call.from_user.id,
        "username": call.from_user.username or "",
        "name": data.get("name", "—"),
        "phone": data.get("phone", "—"),
        "city": data.get("city", "—"),
        "items": items_json,
        "total_amount": 0,
        "delivery_type": data.get("delivery", ""),
        "delivery_address": data.get("address", ""),
        "comment": "—",
        "source": "bot",
        "latitude": None,
        "longitude": None,
    }

    order_id = db.order_create(order_data)
    await send_order_to_admins(order_id, order_data, items, lang, data.get("delivery_name", "—"))

    db.cart_clear(call.from_user.id)
    await state.clear()

    await call.message.answer(
        TEXT[lang]["order_success"].format(order_id=order_id),
        reply_markup=kb_main(lang, is_admin(call.from_user.id))
    )
    await call.message.answer(TEXT[lang]["thanks_new"], reply_markup=kb_follow_links(lang))
    await call.answer()

@dp.callback_query(F.data == "order:cancel")
async def order_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    user = db.user_get(call.from_user.id)
    lang = user["lang"] if user else "ru"
    await call.message.answer(TEXT[lang]["cancelled"], reply_markup=kb_main(lang, is_admin(call.from_user.id)))
    await call.answer()

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
        source = o.get("source") or "bot"
        lines.append(f"{status_icon} #{o['id']} • {o['created_at'][:10]} • {source}")
    await message.answer(
        TEXT[lang]["history"].format(orders="\n".join(lines)),
        reply_markup=kb_main(lang, is_admin(message.from_user.id))
    )

@dp.message(F.text.in_(["🛠 Админ", "🛠 Admin"]))
async def cmd_admin(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    user = db.user_get(message.from_user.id)
    lang = user["lang"] if user else "ru"
    await state.clear()
    await message.answer(TEXT[lang]["admin_menu"], reply_markup=kb_admin(lang))

@dp.callback_query(F.data == "admin:back")
async def admin_back(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer()
        return
    user = db.user_get(call.from_user.id)
    lang = user["lang"] if user else "ru"
    await state.clear()
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
        stats = db.get_stats_all()
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
                    f"💰 Сумма: {money_fmt(order.get('total_amount', 0))}\n"
                    f"🧾 Источник: {esc(order.get('source', 'bot'))}"
                )
                await call.message.answer(text, reply_markup=kb_admin_order(order["id"], order["user_id"], lang))

    elif action == "processing":
        orders = db.orders_get_by_status("processing")
        await call.message.answer(
            (f"В обработке: {len(orders)} заказов") if lang == "ru" else (f"Ishlanmoqda: {len(orders)} ta")
        )

    elif action == "export":
        await generate_monthly_report(call.message, lang)

    elif action == "posts":
        await state.set_state(States.admin_post_dow)
        await call.message.answer(
            "Выберите день публикации (Пн–Сб):" if lang == "ru" else "Kun tanlang (Du–Sha):",
            reply_markup=kb_dow(lang)
        )

    await call.answer()

# =========================
# REPORTS / CRON / WEB
# =========================

async def generate_monthly_report(message: Message, lang: str):
    now = now_tz()
    y, m = prev_month(now)

    if db.report_is_sent(y, m):
        await message.answer("Отчет уже отправлен." if lang == "ru" else "Hisobot allaqachon yuborilgan.")
        return

    orders = db.orders_get_monthly(y, m)

    wb = Workbook()
    ws = wb.active
    ws.title = "Orders"

    headers = ["ID", "Дата", "Имя", "Телефон", "Город", "Статус"]
    ws.append(headers)

    for c in range(1, len(headers) + 1):
        ws.cell(row=1, column=c).font = Font(bold=True)

    total_amount = 0

    for o in orders:
        ws.append([
            o["id"],
            o["created_at"],
            o["name"],
            o["phone"],
            o["city"],
            o["status"]
        ])
        total_amount += o.get("total_amount", 0)

    filename = f"report_{y}_{m}.xlsx"
    wb.save(filename)

    await message.answer_document(FSInputFile(filename))

    db.report_mark_sent(y, m, filename, len(orders), total_amount)


async def cron_post_daily_to_channel():
    if not CHANNEL_ID:
        return

    now = now_tz()
    dow = now.isoweekday()
    week_key = db.week_key_now(now)

    post = db.sched_get_for_day(dow, week_key)
    if not post:
        return

    try:
        if post["media_type"] == "photo":
            await bot.send_photo(CHANNEL_ID, post["file_id"], caption=post["caption"])
        elif post["media_type"] == "video":
            await bot.send_video(CHANNEL_ID, post["file_id"], caption=post["caption"])
        else:
            await bot.send_message(CHANNEL_ID, post["caption"])

        db.sched_mark_posted(post["id"])
    except Exception as e:
        print("Post error:", e)


async def cron_send_prev_month_report():
    if not ADMIN_IDS:
        return

    y, m = prev_month(now_tz())
    if db.report_is_sent(y, m):
        return

    orders = db.orders_get_monthly(y, m)

    wb = Workbook()
    ws = wb.active
    ws.title = "Orders"

    headers = ["ID", "Дата", "Имя", "Телефон", "Город", "Статус"]
    ws.append(headers)

    for c in range(1, len(headers) + 1):
        ws.cell(row=1, column=c).font = Font(bold=True)

    for o in orders:
        ws.append([
            o["id"],
            o["created_at"],
            o["name"],
            o["phone"],
            o["city"],
            o["status"]
        ])

    filename = f"report_{y}_{m}.xlsx"
    wb.save(filename)

    for admin in ADMIN_IDS:
        try:
            await bot.send_document(admin, FSInputFile(filename))
        except:
            pass

    db.report_mark_sent(y, m, filename, len(orders), 0)


async def reminders_loop():
    while True:
        await asyncio.sleep(60)
        orders = db.orders_get_for_reminder()

        for o in orders:
            for admin in ADMIN_IDS:
                try:
                    await bot.send_message(
                        admin,
                        f"⏰ Напоминание\nЗаказ #{o['id']} ожидает обработки"
                    )
                except:
                    pass

            db.order_update_reminded(o["id"])


# =========================
# SHOP WEB API
# =========================

@web_app.get("/api/shop/products")
async def api_shop_products(request):
    lang = request.query.get("lang", "ru")
    category = request.query.get("category")

    rows = db.shop_products_list(published_only=True, limit=200)

    products = []
    for r in rows:
        if category and r["category_slug"] != category:
            continue

        title = r["title_ru"] if lang == "ru" else r["title_uz"]
        desc = r["description_ru"] if lang == "ru" else r["description_uz"]

        products.append({
            "id": r["id"],
            "title": title,
            "description": desc,
            "sizes": r["sizes"],
            "price": r["price"],
            "price_on_request": r["price_on_request"],
            "photo": f"/media/{r['photo_file_id']}"
        })

    return web.json_response(products)


@web_app.post("/api/shop/order")
async def api_shop_order(request):
    data = await request.json()

    items_json = json.dumps(data.get("items", []), ensure_ascii=False)

    order_data = {
        "user_id": data.get("user_id"),
        "username": "",
        "name": data.get("name"),
        "phone": data.get("phone"),
        "city": data.get("city"),
        "items": items_json,
        "total_amount": 0,
        "delivery_type": "webapp",
        "delivery_address": data.get("address"),
        "comment": "",
        "source": "webapp",
        "latitude": data.get("latitude"),
        "longitude": data.get("longitude")
    }

    order_id = db.order_create(order_data)

    await send_order_to_admins(order_id, order_data, data.get("items", []), "ru", "WebApp")

    return web.json_response({"success": True, "order_id": order_id})


# =========================
# MEDIA PROXY
# =========================

@web_app.get("/media/{file_id}")
async def media_proxy(request):
    file_id = request.match_info["file_id"]

    try:
        file = await bot.get_file(file_id)
        url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
        return web.HTTPFound(url)
    except Exception as e:
        return web.Response(text=str(e))


# =========================
# SIMPLE WEB SHOP
# =========================

@web_app.get("/")
async def shop_index(request):

    html = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>ZARY & CO</title>
<style>
body{font-family:Arial;background:#f7f7f7;margin:0}
header{background:#000;color:#fff;padding:20px;text-align:center}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;padding:10px}
.card{background:#fff;border-radius:8px;padding:10px}
.card img{width:100%;border-radius:6px}
.price{font-weight:bold;margin-top:5px}
button{background:black;color:white;border:none;padding:8px;margin-top:5px;width:100%}
.cart{position:fixed;bottom:10px;right:10px;background:black;color:white;padding:10px;border-radius:20px}
</style>
</head>
<body>

<header>ZARY & CO</header>

<div class="grid" id="grid"></div>

<div class="cart" onclick="checkout()">🛒 Cart</div>

<script>
let cart=[]

async function loadProducts(){
let r=await fetch('/api/shop/products')
let products=await r.json()

let grid=document.getElementById('grid')

products.forEach(p=>{
let d=document.createElement('div')
d.className='card'

d.innerHTML=`
<img src="${p.photo}">
<div>${p.title}</div>
<div class="price">${p.price_on_request ? 'Цена по запросу' : p.price+' сум'}</div>
<button onclick='add(${JSON.stringify(p)})'>В корзину</button>
`

grid.appendChild(d)
})
}

function add(p){
cart.push(p)
alert("Добавлено в корзину")
}

async function checkout(){

let name=prompt("Имя")
let phone=prompt("Телефон")
let city=prompt("Город")
let address=prompt("Адрес")

let r=await fetch('/api/shop/order',{
method:'POST',
headers:{'Content-Type':'application/json'},
body:JSON.stringify({
name:name,
phone:phone,
city:city,
address:address,
items:cart
})
})

let res=await r.json()

alert("Заказ №"+res.order_id+" создан")

cart=[]
}

loadProducts()
</script>

</body>
</html>
"""

    return web.Response(text=html, content_type="text/html")


# =========================
# START BOT
# =========================

async def main():

    print("Starting bot...")

    asyncio.create_task(reminders_loop())

    runner = web.AppRunner(web_app)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    print("Web server started")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
