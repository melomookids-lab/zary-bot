"""
ZARY & CO — РОЗНИЧНЫЙ БОТ (Retail Bot)
Версия: 2.0 Production Ready
- Исправлены баги с напоминаниями
- Множественные админы (до 3)
- Автоотчеты Excel в конце месяца
- Улучшенная корзина и избранное
- Доставка: Б2Б/Яндекс/ПВЗ
"""

import os
import re
import html
import asyncio
import threading
import sqlite3
import aiosqlite
from datetime import datetime, timedelta, time as dtime
from calendar import monthrange
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional, Dict, Any, List, Set
from pathlib import Path

from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from aiogram.types.input_file import FSInputFile
from aiogram.exceptions import TelegramAPIError

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

# =========================
# CONFIGURATION
# =========================
class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN env is empty!")
    
    # Множественные админы (до 3)
    ADMIN_IDS = []
    for i in range(1, 4):
        admin_id = os.getenv(f"ADMIN_ID_{i}", "").strip()
        if admin_id and admin_id.isdigit():
            ADMIN_IDS.append(int(admin_id))
    
    # Если старый формат (один админ)
    if not ADMIN_IDS:
        old_admin = os.getenv("MANAGER_CHAT_ID", "").strip()
        if old_admin and old_admin.isdigit():
            ADMIN_IDS.append(int(old_admin))
    
    if not ADMIN_IDS:
        raise RuntimeError("At least one ADMIN_ID required!")
    
    PRIMARY_ADMIN = ADMIN_IDS[0]  # Главный админ для отчетов
    
    CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0").strip()) or 0
    CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "zaryco_official").strip().lstrip("@")
    
    PHONE = os.getenv("MANAGER_PHONE", "+998771202255").strip()
    MANAGER_USERNAME = os.getenv("MANAGER_USERNAME", "").strip().lstrip("@")
    
    PORT = int(os.getenv("PORT", "10000"))
    DB_PATH = os.getenv("DB_PATH", "bot.db")
    
    # Директории
    REPORTS_DIR = Path("reports")
    EXPORTS_DIR = Path("exports")
    
    # Время
    TZ = ZoneInfo("Asia/Tashkent")
    WORK_START = dtime(9, 0)
    WORK_END = dtime(21, 0)
    
    # Автопостинг
    AUTOPOST_HOUR = int(os.getenv("AUTOPOST_HOUR", "18"))
    AUTOPOST_MINUTE = int(os.getenv("AUTOPOST_MINUTE", "0"))
    
    # Напоминания
    REMINDER_FIRST = 30 * 60  # 30 минут
    REMINDER_REPEAT = 60 * 60  # каждый час
    
    # Ссылки
    INSTAGRAM_URL = "https://www.instagram.com/zary.co/"
    YOUTUBE_URL = "https://www.youtube.com/@ZARYCOOFFICIAL"
    TELEGRAM_CHANNEL_URL = f"https://t.me/{CHANNEL_USERNAME}"

# =========================
# DATABASE (Async)
# =========================
class Database:
    def __init__(self):
        self.db_path = Config.DB_PATH
        self._pool = None
    
    async def connect(self):
        self._pool = await aiosqlite.connect(self.db_path)
        self._pool.row_factory = aiosqlite.Row
        await self._pool.execute("PRAGMA foreign_keys = ON")
        await self._pool.execute("PRAGMA journal_mode = WAL")
        await self.init_tables()
    
    async def close(self):
        if self._pool:
            await self._pool.close()
    
    async def init_tables(self):
        await self._pool.executescript(f"""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                lang TEXT NOT NULL DEFAULT 'ru',
                created_at TEXT NOT NULL,
                phone TEXT,
                city TEXT,
                is_blocked INTEGER DEFAULT 0
            );
            
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name_ru TEXT NOT NULL,
                name_uz TEXT NOT NULL,
                category TEXT,
                price INTEGER,
                sizes TEXT,
                photo_id TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS carts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_id INTEGER,
                product_name TEXT,
                qty INTEGER DEFAULT 1,
                size TEXT,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_id INTEGER,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, product_id)
            );
            
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                name TEXT,
                phone TEXT,
                city TEXT,
                items TEXT,  -- JSON: [{"name": "...", "qty": 1, "size": "..."}]
                total_amount INTEGER DEFAULT 0,
                delivery_type TEXT,  -- b2b, yandex_courier, yandex_pvz
                delivery_address TEXT,
                comment TEXT,
                promo_code TEXT,
                discount_percent INTEGER DEFAULT 0,
                status TEXT DEFAULT 'new',  -- new, processing, shipped, delivered, cancelled
                manager_seen INTEGER DEFAULT 0,  -- 0 = не просмотрено
                manager_id INTEGER,
                created_at TEXT NOT NULL,
                reminded_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            
            CREATE TABLE IF NOT EXISTS monthly_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                sent_at TEXT,
                filename TEXT,
                total_orders INTEGER,
                total_amount INTEGER,
                status TEXT DEFAULT 'pending'
            );
            
            CREATE TABLE IF NOT EXISTS posts_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                media_type TEXT,
                file_id TEXT,
                text TEXT,
                status TEXT DEFAULT 'queued',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                posted_at TEXT
            );
            
            CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
            CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
            CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);
            CREATE INDEX IF NOT EXISTS idx_carts_user ON carts(user_id);
        """)
        await self._pool.commit()
    
    # Users
    async def user_get(self, user_id: int) -> Optional[Dict]:
        async with self._pool.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def user_upsert(self, user_id: int, username: str, lang: str, phone: str = None):
        now = datetime.now(Config.TZ).strftime("%Y-%m-%d %H:%M:%S")
        existing = await self.user_get(user_id)
        if existing:
            await self._pool.execute(
                "UPDATE users SET username = ?, lang = ?, phone = COALESCE(?, phone) WHERE user_id = ?",
                (username, lang, phone, user_id)
            )
        else:
            await self._pool.execute(
                "INSERT INTO users (user_id, username, lang, created_at, phone) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, lang, now, phone)
            )
        await self._pool.commit()
    
    # Carts
    async def cart_add(self, user_id: int, product_name: str, qty: int = 1, size: str = ""):
        await self._pool.execute(
            "INSERT INTO carts (user_id, product_name, qty, size) VALUES (?, ?, ?, ?)",
            (user_id, product_name, qty, size)
        )
        await self._pool.commit()
    
    async def cart_get(self, user_id: int) -> List[Dict]:
        async with self._pool.execute(
            "SELECT * FROM carts WHERE user_id = ? ORDER BY id DESC", (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
    
    async def cart_clear(self, user_id: int):
        await self._pool.execute("DELETE FROM carts WHERE user_id = ?", (user_id,))
        await self._pool.commit()
    
    async def cart_remove_item(self, cart_id: int):
        await self._pool.execute("DELETE FROM carts WHERE id = ?", (cart_id,))
        await self._pool.commit()
    
    # Favorites
    async def favorite_toggle(self, user_id: int, product_id: int) -> bool:
        # True = added, False = removed
        async with self._pool.execute(
            "SELECT 1 FROM favorites WHERE user_id = ? AND product_id = ?",
            (user_id, product_id)
        ) as cursor:
            exists = await cursor.fetchone()
        
        if exists:
            await self._pool.execute(
                "DELETE FROM favorites WHERE user_id = ? AND product_id = ?",
                (user_id, product_id)
            )
            await self._pool.commit()
            return False
        else:
            await self._pool.execute(
                "INSERT INTO favorites (user_id, product_id) VALUES (?, ?)",
                (user_id, product_id)
            )
            await self._pool.commit()
            return True
    
    async def favorites_get(self, user_id: int) -> List[Dict]:
        async with self._pool.execute(
            "SELECT f.*, p.name_ru, p.name_uz, p.price, p.photo_id "
            "FROM favorites f JOIN products p ON f.product_id = p.id "
            "WHERE f.user_id = ?", (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
    
    # Orders
    async def order_create(self, data: Dict) -> int:
        now = datetime.now(Config.TZ).strftime("%Y-%m-%d %H:%M:%S")
        cursor = await self._pool.execute(
            """INSERT INTO orders (
                user_id, username, name, phone, city, items, total_amount,
                delivery_type, delivery_address, comment, promo_code, discount_percent,
                status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data['user_id'], data.get('username', ''), data['name'], data['phone'],
                data['city'], data['items'], data.get('total_amount', 0),
                data.get('delivery_type', ''), data.get('delivery_address', ''),
                data.get('comment', ''), data.get('promo_code', ''),
                data.get('discount_percent', 0), 'new', now
            )
        )
        await self._pool.commit()
        return cursor.lastrowid
    
    async def order_get(self, order_id: int) -> Optional[Dict]:
        async with self._pool.execute(
            "SELECT * FROM orders WHERE id = ?", (order_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def order_update_status(self, order_id: int, status: str, manager_id: int = None):
        params = [status]
        query = "UPDATE orders SET status = ?"
        if manager_id:
            query += ", manager_id = ?, manager_seen = 1"
            params.append(manager_id)
        query += " WHERE id = ?"
        params.append(order_id)
        
        await self._pool.execute(query, params)
        await self._pool.commit()
    
    async def order_mark_seen(self, order_id: int, manager_id: int):
        await self._pool.execute(
            "UPDATE orders SET manager_seen = 1, manager_id = ? WHERE id = ?",
            (manager_id, order_id)
        )
        await self._pool.commit()
    
    async def orders_get_by_status(self, status: str, limit: int = 50) -> List[Dict]:
        async with self._pool.execute(
            "SELECT * FROM orders WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            (status, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
    
    async def orders_get_for_reminder(self) -> List[Dict]:
        """Только new + не просмотренные менеджером + старше 30 мин"""
        cutoff = (datetime.now(Config.TZ) - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
        async with self._pool.execute(
            "SELECT * FROM orders WHERE status = 'new' AND manager_seen = 0 "
            "AND created_at < ? AND (reminded_at IS NULL OR reminded_at < ?)",
            (cutoff, cutoff)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
    
    async def order_update_reminded(self, order_id: int):
        now = datetime.now(Config.TZ).strftime("%Y-%m-%d %H:%M:%S")
        await self._pool.execute(
            "UPDATE orders SET reminded_at = ? WHERE id = ?",
            (now, order_id)
        )
        await self._pool.commit()
    
    async def orders_get_monthly(self, year: int, month: int) -> List[Dict]:
        start = f"{year}-{month:02d}-01"
        last_day = monthrange(year, month)[1]
        end = f"{year}-{month:02d}-{last_day} 23:59:59"
        
        async with self._pool.execute(
            "SELECT * FROM orders WHERE created_at BETWEEN ? AND ? ORDER BY id",
            (start, end)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
    
    async def report_mark_sent(self, year: int, month: int, filename: str, total_orders: int, total_amount: int):
        now = datetime.now(Config.TZ).strftime("%Y-%m-%d %H:%M:%S")
        await self._pool.execute(
            "INSERT INTO monthly_reports (year, month, sent_at, filename, total_orders, total_amount, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'sent')",
            (year, month, now, filename, total_orders, total_amount)
        )
        await self._pool.commit()
    
    async def report_is_sent(self, year: int, month: int) -> bool:
        async with self._pool.execute(
            "SELECT 1 FROM monthly_reports WHERE year = ? AND month = ? AND status = 'sent'",
            (year, month)
        ) as cursor:
            return await cursor.fetchone() is not None
    
    # Stats
    async def get_stats(self) -> Dict:
        async with self._pool.execute(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN status = 'new' THEN 1 ELSE 0 END) as new, "
            "SUM(CASE WHEN status = 'processing' THEN 1 ELSE 0 END) as processing, "
            "SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) as delivered, "
            "COUNT(DISTINCT user_id) as unique_users "
            "FROM orders"
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else {}

db = Database()

# =========================
# TEXTS
# =========================
TEXT = {
    "ru": {
        "welcome": "👋 Добро пожаловать в <b>ZARY & CO</b>!\n\n"
                  "🧸 Детская одежда премиум качества\n"
                  "📦 Доставка по всему Узбекистану 1-5 дней\n\n"
                  "Выберите действие 👇",
        
        "menu": "📍 Главное меню",
        
        "catalog": "📸 <b>Каталог</b>\n\nВыберите категорию:",
        "price": "🧾 <b>Прайс-лист</b>\n\nВыберите категорию:",
        
        "size": "📏 <b>Подбор размера</b>\n\nВыберите способ:",
        "size_age": "Введите возраст ребенка (1-15 лет):\nПример: <code>7</code>",
        "size_height": "Введите рост в см:\nПример: <code>125</code>",
        "size_result": "📏 Рекомендуемый размер: <b>{size}</b>",
        
        "cart": "🛒 <b>Корзина</b>\n\n{items}\n\n💰 Итого: <b>{total} сум</b>",
        "cart_empty": "🛒 Корзина пуста\n\nДобавьте товары из каталога",
        "cart_added": "✅ Товар добавлен в корзину",
        "cart_removed": "❌ Товар удален",
        
        "favorites": "❤️ <b>Избранное</b>\n\n{items}",
        "fav_empty": "❤️ Избранное пусто",
        "fav_added": "❤️ Добавлено в избранное",
        "fav_removed": "💔 Удалено из избранного",
        
        "delivery": "🚚 <b>Доставка</b>\n\n"
                   "1. <b>B2B Почта</b> — 2-5 дней, по всему Узбекистану\n"
                   "2. <b>Яндекс Курьер</b> — 1-3 дня, крупные города\n"
                   "3. <b>Яндекс ПВЗ</b> — 1-3 дня, пункты выдачи\n\n"
                   "Стоимость зависит от города и веса",
        
        "order_start": "📝 <b>Оформление заказа</b>\n\nВведите ваше имя:",
        "order_phone": "📱 Отправьте номер телефона:",
        "order_city": "🏙 Введите город:",
        "order_delivery": "🚚 Выберите способ доставки:",
        "order_address": "📍 Введите адрес доставки:",
        "order_comment": "💬 Комментарий (необязательно):",
        "order_confirm": "📝 <b>Проверьте заказ:</b>\n\n"
                        "👤 {name}\n📱 {phone}\n🏙 {city}\n"
                        "🚚 {delivery}\n📍 {address}\n"
                        "💬 {comment}\n\n"
                        "Товары:\n{items}\n\n"
                        "💰 Итого: {total} сум",
        "order_success": "✅ Заказ #{order_id} принят!\n\n"
                        "Менеджер свяжется с вами в течение 15 минут\n"
                        "Рабочее время: 09:00-21:00",
        
        "history": "📜 <b>История заказов</b>\n\n{orders}",
        "history_empty": "📜 У вас пока нет заказов",
        
        "contact": "📞 <b>Контакты</b>\n\n"
                  "☎️ {phone}\n"
                  "⏰ Пн-Пт: 09:00-21:00\n"
                  "📱 @{username}\n\n"
                  "Или оставьте номер — мы перезвоним",
        
        "faq": "❓ <b>Частые вопросы</b>\n\nВыберите тему:",
        "faq_delivery": "🚚 <b>Доставка</b>\nДоставляем по всему Узбекистану 1-5 дней",
        "faq_payment": "💳 <b>Оплата</b>\nНаличными курьеру или переводом",
        "faq_return": "🔄 <b>Возврат</b>\n14 дней при сохранении товарного вида",
        "faq_size": "📏 <b>Размеры</b>\nИспользуйте подбор размера в боте",
        
        "admin_menu": "🛠 <b>Панель администратора</b>\n\nВыберите действие:",
        "admin_orders": "📋 <b>Заказы</b>\n\n{orders}",
        "admin_stats": "📊 <b>Статистика</b>\n\n"
                      "📦 Всего заказов: {total}\n"
                      "🆕 Новых: {new}\n"
                      "⚙️ В обработке: {processing}\n"
                      "✅ Доставлено: {delivered}\n"
                      "👥 Уникальных клиентов: {unique_users}",
        
        "status_new": "🆕 Новый",
        "status_processing": "⚙️ В обработке",
        "status_shipped": "🚚 Отправлен",
        "status_delivered": "✅ Доставлен",
        "status_cancelled": "❌ Отменен",
        
        "error": "⚠️ Произошла ошибка. Попробуйте позже.",
        "cancelled": "❌ Отменено",
        "unknown": "🤔 Я не понял. Используйте меню 👇",
    },
    
    "uz": {
        "welcome": "👋 <b>ZARY & CO</b> ga xush kelibsiz!\n\n"
                  "🧸 Bolalar kiyimi premium sifat\n"
                  "📦 O'zbekiston bo'ylab yetkazib berish 1-5 kun\n\n"
                  "Amalni tanlang 👇",
        
        "menu": "📍 Asosiy menyu",
        
        "catalog": "📸 <b>Katalog</b>\n\nKategoriyani tanlang:",
        "price": "🧾 <b>Narxlar</b>\n\nKategoriyani tanlang:",
        
        "size": "📏 <b>O'lcham tanlash</b>\n\nUsulni tanlang:",
        "size_age": "Yoshini kiriting (1-15 yosh):\nMisol: <code>7</code>",
        "size_height": "Bo'yni sm da kiriting:\nMisol: <code>125</code>",
        "size_result": "📏 Tavsiya etilgan o'lcham: <b>{size}</b>",
        
        "cart": "🛒 <b>Savat</b>\n\n{items}\n\n💰 Jami: <b>{total} so'm</b>",
        "cart_empty": "🛒 Savat bo'sh\n\nKatalogdan mahsulot qo'shing",
        "cart_added": "✅ Savatga qo'shildi",
        "cart_removed": "❌ O'chirildi",
        
        "favorites": "❤️ <b>Sevimlilar</b>\n\n{items}",
        "fav_empty": "❤️ Sevimlilar bo'sh",
        "fav_added": "❤️ Sevimlilarga qo'shildi",
        "fav_removed": "💔 Sevimlilardan o'chirildi",
        
        "delivery": "🚚 <b>Yetkazib berish</b>\n\n"
                   "1. <b>B2B Pochta</b> — 2-5 kun, O'zbekiston bo'ylab\n"
                   "2. <b>Yandex Kuryer</b> — 1-3 kun, yirik shaharlarga\n"
                   "3. <b>Yandex PVZ</b> — 1-3 kun, topshirish punktlari\n\n"
                   "Narxi shahar va vaznga qarab",
        
        "order_start": "📝 <b>Buyurtma berish</b>\n\nIsmingizni kiriting:",
        "order_phone": "📱 Telefon raqamingizni yuboring:",
        "order_city": "🏙 Shaharni kiriting:",
        "order_delivery": "🚚 Yetkazib berish usulini tanlang:",
        "order_address": "📍 Yetkazib berish manzilini kiriting:",
        "order_comment": "💬 Izoh (ixtiyoriy):",
        "order_confirm": "📝 <b>Buyurtmani tekshiring:</b>\n\n"
                        "👤 {name}\n📱 {phone}\n🏙 {city}\n"
                        "🚚 {delivery}\n📍 {address}\n"
                        "💬 {comment}\n\n"
                        "Tovarlar:\n{items}\n\n"
                        "💰 Jami: {total} so'm",
        "order_success": "✅ Buyurtma #{order_id} qabul qilindi!\n\n"
                        "Menejer 15 daqiqa ichida bog'lanadi\n"
                        "Ish vaqti: 09:00-21:00",
        
        "history": "📜 <b>Buyurtmalar tarixi</b>\n\n{orders}",
        "history_empty": "📜 Hozircha buyurtmalar yo'q",
        
        "contact": "📞 <b>Aloqa</b>\n\n"
                  "☎️ {phone}\n"
                  "⏰ Du-Sha: 09:00-21:00\n"
                  "📱 @{username}\n\n"
                  "Yoki raqam qoldiring — qo'ng'iroq qilamiz",
        
        "faq": "❓ <b>Ko'p so'raladigan savollar</b>\n\nMavzuni tanlang:",
        "faq_delivery": "🚚 <b>Yetkazib berish</b>\nO'zbekiston bo'ylab 1-5 kun",
        "faq_payment": "💳 <b>To'lov</b>\nNaqd yoki o'tkazma orqali",
        "faq_return": "🔄 <b>Qaytarish</b>\n14 kun ichida tovar ko'rinishi saqlangan bo'lsa",
        "faq_size": "📏 <b>O'lchamlar</b>\nBotdagi o'lcham tanlashdan foydalaning",
        
        "admin_menu": "🛠 <b>Admin paneli</b>\n\nAmalni tanlang:",
        "admin_orders": "📋 <b>Buyurtmalar</b>\n\n{orders}",
        "admin_stats": "📊 <b>Statistika</b>\n\n"
                      "📦 Jami buyurtmalar: {total}\n"
                      "🆕 Yangi: {new}\n"
                      "⚙️ Ishlanmoqda: {processing}\n"
                      "✅ Yetkazildi: {delivered}\n"
                      "👥 Unikal mijozlar: {unique_users}",
        
        "status_new": "🆕 Yangi",
        "status_processing": "⚙️ Ishlanmoqda",
        "status_shipped": "🚚 Yuborildi",
        "status_delivered": "✅ Yetkazildi",
        "status_cancelled": "❌ Bekor qilindi",
        
        "error": "⚠️ Xatolik yuz berdi. Keyinroq urinib ko'ring.",
        "cancelled": "❌ Bekor qilindi",
        "unknown": "🤔 Tushunmadim. Menyudan foydalaning 👇",
    }
}

# =========================
# KEYBOARDS
# =========================
def kb_main(lang: str, is_admin: bool = False) -> ReplyKeyboardMarkup:
    if lang == "uz":
        rows = [
            [KeyboardButton(text="📸 Katalog"), KeyboardButton(text="🧾 Narxlar")],
            [KeyboardButton(text="📏 O'lcham"), KeyboardButton(text="🛒 Savat")],
            [KeyboardButton(text="❤️ Sevimlilar"), KeyboardButton(text="📜 Buyurtmalar")],
            [KeyboardButton(text="🚚 Yetkazib berish"), KeyboardButton(text="❓ FAQ")],
            [KeyboardButton(text="📞 Aloqa"), KeyboardButton(text="✅ Buyurtma")],
        ]
        if is_admin:
            rows.append([KeyboardButton(text="🛠 Admin")])
    else:
        rows = [
            [KeyboardButton(text="📸 Каталог"), KeyboardButton(text="🧾 Прайс")],
            [KeyboardButton(text="📏 Размер"), KeyboardButton(text="🛒 Корзина")],
            [KeyboardButton(text="❤️ Избранное"), KeyboardButton(text="📜 История")],
            [KeyboardButton(text="🚚 Доставка"), KeyboardButton(text="❓ FAQ")],
            [KeyboardButton(text="📞 Связаться"), KeyboardButton(text="✅ Заказ")],
        ]
        if is_admin:
            rows.append([KeyboardButton(text="🛠 Админ")])
    
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def kb_catalog(lang: str) -> InlineKeyboardMarkup:
    cats = [
        [("👶 Мальчики / O'g'il bolalar", "cat:boys"), ("👧 Девочки / Qiz bolalar", "cat:girls")],
        [("🧒 Унисекс", "cat:unisex"), ("🎒 Школа / Maktab", "cat:school")],
        [("🔥 Новинки / Yangi", "cat:new"), ("💰 Акции / Aksiya", "cat:sale")],
    ]
    buttons = []
    for row in cats:
        buttons.append([
            InlineKeyboardButton(text=row[0][0], callback_data=row[0][1]),
            InlineKeyboardButton(text=row[1][0], callback_data=row[1][1])
        ])
    buttons.append([InlineKeyboardButton(
        text="⬅️ Назад / Orqaga", callback_data="back:menu"
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_size(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="👶 По возрасту / Yosh bo'yicha", callback_data="size:age"
        )],
        [InlineKeyboardButton(
            text="📏 По росту / Bo'y bo'yicha", callback_data="size:height"
        )],
        [InlineKeyboardButton(
            text="⬅️ Назад / Orqaga", callback_data="back:menu"
        )],
    ])

def kb_delivery(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📦 B2B Почта", callback_data="delivery:b2b"
        )],
        [InlineKeyboardButton(
            text="🚚 Яндекс Курьер", callback_data="delivery:yandex_courier"
        )],
        [InlineKeyboardButton(
            text="🏪 Яндекс ПВЗ", callback_data="delivery:yandex_pvz"
        )],
        [InlineKeyboardButton(
            text="⬅️ Назад / Orqaga", callback_data="back:menu"
        )],
    ])

def kb_cart_items(items: List[Dict], lang: str) -> InlineKeyboardMarkup:
    buttons = []
    for item in items:
        name = item['product_name'][:20]
        btn_text = f"❌ {name} ({item['qty']}x)" if lang == "ru" else f"❌ {name} ({item['qty']}x)"
        buttons.append([InlineKeyboardButton(
            text=btn_text, callback_data=f"cart_remove:{item['id']}"
        )])
    
    buttons.append([InlineKeyboardButton(
        text="✅ Оформить / Rasmiylashtirish", callback_data="cart:checkout"
    )])
    buttons.append([InlineKeyboardButton(
        text="🧹 Очистить / Tozalash", callback_data="cart:clear"
    )])
    buttons.append([InlineKeyboardButton(
        text="⬅️ Назад / Orqaga", callback_data="back:menu"
    )])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_order_confirm(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Подтвердить / Tasdiqlash", callback_data="order:confirm"
        )],
        [InlineKeyboardButton(
            text="✏️ Изменить / O'zgartirish", callback_data="order:edit"
        )],
        [InlineKeyboardButton(
            text="❌ Отмена / Bekor", callback_data="order:cancel"
        )],
    ])

def kb_admin(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📋 Новые заказы / Yangi buyurtmalar", callback_data="admin:new_orders"
        )],
        [InlineKeyboardButton(
            text="⚙️ В обработке / Ishlanmoqda", callback_data="admin:processing"
        )],
        [InlineKeyboardButton(
            text="📊 Статистика / Statistika", callback_data="admin:stats"
        )],
        [InlineKeyboardButton(
            text="📤 Excel отчет / Hisobot", callback_data="admin:export"
        )],
        [InlineKeyboardButton(
            text="⬅️ Назад / Orqaga", callback_data="back:menu"
        )],
    ])

def kb_admin_order(order_id: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👁 К просмотру", callback_data=f"order_seen:{order_id}"),
            InlineKeyboardButton(text="⚙️ В работу", callback_data=f"order_process:{order_id}")
        ],
        [
            InlineKeyboardButton(text="🚚 Отправлен", callback_data=f"order_ship:{order_id}"),
            InlineKeyboardButton(text="✅ Доставлен", callback_data=f"order_deliver:{order_id}")
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"order_cancel:{order_id}")
        ],
    ])

def kb_faq(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🚚 Доставка / Yetkazib berish", callback_data="faq:delivery"
        )],
        [InlineKeyboardButton(
            text="💳 Оплата / To'lov", callback_data="faq:payment"
        )],
        [InlineKeyboardButton(
            text="🔄 Возврат / Qaytarish", callback_data="faq:return"
        )],
        [InlineKeyboardButton(
            text="📏 Размеры / O'lchamlar", callback_data="faq:size"
        )],
        [InlineKeyboardButton(
            text="⬅️ Назад / Orqaga", callback_data="back:menu"
        )],
    ])

def kb_contact(lang: str) -> ReplyKeyboardMarkup:
    if lang == "uz":
        btn = KeyboardButton(text="📱 Raqamni yuborish", request_contact=True)
        cancel = KeyboardButton(text="❌ Bekor qilish")
    else:
        btn = KeyboardButton(text="📱 Отправить номер", request_contact=True)
        cancel = KeyboardButton(text="❌ Отмена")
    return ReplyKeyboardMarkup(keyboard=[[btn], [cancel]], resize_keyboard=True, one_time_keyboard=True)

def kb_channel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📣 Канал / Kanal", url=Config.TELEGRAM_CHANNEL_URL)],
        [InlineKeyboardButton(text="⬅️ Меню / Menyu", callback_data="back:menu")],
    ])

# =========================
# HELPERS
# =========================
def esc(s: str) -> str:
    return html.escape(str(s) if s else "")

def is_admin(user_id: int) -> bool:
    return user_id in Config.ADMIN_IDS

def format_price(price: int) -> str:
    return f"{price:,}".replace(",", " ")

def size_by_age(age: int) -> str:
    mapping = {
        1: "86", 2: "92", 3: "98", 4: "104", 5: "110",
        6: "116", 7: "122", 8: "128", 9: "134", 10: "140",
        11: "146", 12: "152", 13: "158", 14: "164", 15: "164"
    }
    return mapping.get(age, "122-128")

def size_by_height(height: int) -> str:
    sizes = [86, 92, 98, 104, 110, 116, 122, 128, 134, 140, 146, 152, 158, 164]
    closest = min(sizes, key=lambda x: abs(x - height))
    return str(closest)

def now_str() -> str:
    return datetime.now(Config.TZ).strftime("%Y-%m-%d %H:%M:%S")

# =========================
# FSM STATES
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
    order_confirm = State()

# =========================
# BOT INIT
# =========================
bot = Bot(token=Config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# =========================
# HANDLERS
# =========================

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    
    user_id = message.from_user.id
    username = message.from_user.username or ""
    lang = "uz" if message.from_user.language_code == "uz" else "ru"
    
    await db.user_upsert(user_id, username, lang)
    
    await message.answer(TEXT[lang]["welcome"], reply_markup=kb_main(lang, is_admin(user_id)))
    await message.answer(TEXT[lang]["menu"], reply_markup=kb_main(lang, is_admin(user_id)))

@dp.message(F.text.in_(["🌐 Til", "🌐 Язык"]))
async def cmd_lang(message: Message, state: FSMContext):
    user = await db.user_get(message.from_user.id)
    lang = "uz" if user and user['lang'] == "ru" else "ru"
    await db.user_upsert(message.from_user.id, message.from_user.username or "", lang)
    await message.answer(TEXT[lang]["welcome"], reply_markup=kb_main(lang, is_admin(message.from_user.id)))

@dp.callback_query(F.data == "back:menu")
async def back_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await db.user_get(call.from_user.id)
    lang = user['lang'] if user else "ru"
    await call.message.answer(TEXT[lang]["menu"], reply_markup=kb_main(lang, is_admin(call.from_user.id)))
    await call.answer()

# Catalog
@dp.message(F.text.in_(["📸 Каталог", "📸 Katalog"]))
async def cmd_catalog(message: Message, state: FSMContext):
    user = await db.user_get(message.from_user.id)
    lang = user['lang'] if user else "ru"
    await message.answer(TEXT[lang]["catalog"], reply_markup=kb_catalog(lang))

@dp.callback_query(F.data.startswith("cat:"))
async def cat_select(call: CallbackQuery, state: FSMContext):
    user = await db.user_get(call.from_user.id)
    lang = user['lang'] if user else "ru"
    cat = call.data.split(":")[1]
    # Здесь должна быть логика показа товаров
    await call.answer(f"Категория: {cat}")

# Price
@dp.message(F.text.in_(["🧾 Прайс", "🧾 Narxlar"]))
async def cmd_price(message: Message, state: FSMContext):
    user = await db.user_get(message.from_user.id)
    lang = user['lang'] if user else "ru"
    await message.answer(TEXT[lang]["price"], reply_markup=kb_catalog(lang))

# Size
@dp.message(F.text.in_(["📏 Размер", "📏 O'lcham"]))
async def cmd_size(message: Message, state: FSMContext):
    user = await db.user_get(message.from_user.id)
    lang = user['lang'] if user else "ru"
    await message.answer(TEXT[lang]["size"], reply_markup=kb_size(lang))

@dp.callback_query(F.data.startswith("size:"))
async def size_select(call: CallbackQuery, state: FSMContext):
    user = await db.user_get(call.from_user.id)
    lang = user['lang'] if user else "ru"
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
    user = await db.user_get(message.from_user.id)
    lang = user['lang'] if user else "ru"
    
    if not message.text or not message.text.isdigit():
        await message.answer(TEXT[lang]["size_age"])
        return
    
    age = int(message.text)
    if not 1 <= age <= 15:
        await message.answer(TEXT[lang]["size_age"])
        return
    
    size = size_by_age(age)
    await message.answer(TEXT[lang]["size_result"].format(size=size), reply_markup=kb_main(lang))
    await state.clear()

@dp.message(States.size_height)
async def size_height_input(message: Message, state: FSMContext):
    user = await db.user_get(message.from_user.id)
    lang = user['lang'] if user else "ru"
    
    if not message.text or not message.text.isdigit():
        await message.answer(TEXT[lang]["size_height"])
        return
    
    height = int(message.text)
    if not 50 <= height <= 180:
        await message.answer(TEXT[lang]["size_height"])
        return
    
    size = size_by_height(height)
    await message.answer(TEXT[lang]["size_result"].format(size=size), reply_markup=kb_main(lang))
    await state.clear()

# Cart
@dp.message(F.text.in_(["🛒 Корзина", "🛒 Savat"]))
async def cmd_cart(message: Message, state: FSMContext):
    user = await db.user_get(message.from_user.id)
    lang = user['lang'] if user else "ru"
    
    items = await db.cart_get(message.from_user.id)
    
    if not items:
        await message.answer(TEXT[lang]["cart_empty"], reply_markup=kb_main(lang))
        return
    
    items_text = "\n".join([f"• {esc(it['product_name'])} x{it['qty']}" for it in items])
    total = sum(it['qty'] * 100000 for it in items)  # Заглушка для цены
    
    text = TEXT[lang]["cart"].format(items=items_text, total=format_price(total))
    await message.answer(text, reply_markup=kb_cart_items(items, lang))

@dp.callback_query(F.data.startswith("cart_remove:"))
async def cart_remove(call: CallbackQuery, state: FSMContext):
    cart_id = int(call.data.split(":")[1])
    await db.cart_remove_item(cart_id)
    
    user = await db.user_get(call.from_user.id)
    lang = user['lang'] if user else "ru"
    
    items = await db.cart_get(call.from_user.id)
    if not items:
        await call.message.edit_text(TEXT[lang]["cart_empty"])
    else:
        items_text = "\n".join([f"• {esc(it['product_name'])} x{it['qty']}" for it in items])
        total = sum(it['qty'] * 100000 for it in items)
        text = TEXT[lang]["cart"].format(items=items_text, total=format_price(total))
        await call.message.edit_text(text, reply_markup=kb_cart_items(items, lang))
    
    await call.answer(TEXT[lang]["cart_removed"])

@dp.callback_query(F.data == "cart:clear")
async def cart_clear(call: CallbackQuery, state: FSMContext):
    await db.cart_clear(call.from_user.id)
    user = await db.user_get(call.from_user.id)
    lang = user['lang'] if user else "ru"
    await call.message.edit_text(TEXT[lang]["cart_empty"])
    await call.answer()

# Favorites
@dp.message(F.text.in_(["❤️ Избранное", "❤️ Sevimlilar"]))
async def cmd_favorites(message: Message, state: FSMContext):
    user = await db.user_get(message.from_user.id)
    lang = user['lang'] if user else "ru"
    
    favs = await db.favorites_get(message.from_user.id)
    if not favs:
        await message.answer(TEXT[lang]["fav_empty"], reply_markup=kb_main(lang))
        return
    
    # Показать избранное
    await message.answer(TEXT[lang]["favorites"].format(items="..."))

# Delivery
@dp.message(F.text.in_(["🚚 Доставка", "🚚 Yetkazib berish"]))
async def cmd_delivery(message: Message, state: FSMContext):
    user = await db.user_get(message.from_user.id)
    lang = user['lang'] if user else "ru"
    await message.answer(TEXT[lang]["delivery"], reply_markup=kb_delivery(lang))

# FAQ
@dp.message(F.text.in_(["❓ FAQ"]))
async def cmd_faq(message: Message, state: FSMContext):
    user = await db.user_get(message.from_user.id)
    lang = user['lang'] if user else "ru"
    await message.answer(TEXT[lang]["faq"], reply_markup=kb_faq(lang))

@dp.callback_query(F.data.startswith("faq:"))
async def faq_answer(call: CallbackQuery, state: FSMContext):
    user = await db.user_get(call.from_user.id)
    lang = user['lang'] if user else "ru"
    topic = call.data.split(":")[1]
    
    answers = {
        "delivery": TEXT[lang]["faq_delivery"],
        "payment": TEXT[lang]["faq_payment"],
        "return": TEXT[lang]["faq_return"],
        "size": TEXT[lang]["faq_size"],
    }
    
    await call.message.answer(answers.get(topic, TEXT[lang]["unknown"]), reply_markup=kb_faq(lang))
    await call.answer()

# Contact
@dp.message(F.text.in_(["📞 Связаться", "📞 Aloqa"]))
async def cmd_contact(message: Message, state: FSMContext):
    user = await db.user_get(message.from_user.id)
    lang = user['lang'] if user else "ru"
    
    text = TEXT[lang]["contact"].format(
        phone=Config.PHONE,
        username=Config.MANAGER_USERNAME or "zaryco_official"
    )
    await message.answer(text, reply_markup=kb_contact(lang))

# Order flow
@dp.message(F.text.in_(["✅ Заказ", "✅ Buyurtma"]))
async def cmd_order(message: Message, state: FSMContext):
    user = await db.user_get(message.from_user.id)
    lang = user['lang'] if user else "ru"
    
    # Проверить корзину
    cart = await db.cart_get(message.from_user.id)
    if not cart:
        await message.answer("Сначала добавьте товары в корзину!" if lang == "ru" else "Avval savatga qo'shing!")
        return
    
    await state.set_state(States.order_name)
    await message.answer(TEXT[lang]["order_start"])

@dp.message(States.order_name)
async def order_name(message: Message, state: FSMContext):
    user = await db.user_get(message.from_user.id)
    lang = user['lang'] if user else "ru"
    
    if not message.text:
        await message.answer(TEXT[lang]["order_start"])
        return
    
    await state.update_data(name=message.text)
    await state.set_state(States.order_phone)
    await message.answer(TEXT[lang]["order_phone"], reply_markup=kb_contact(lang))

@dp.message(States.order_phone)
async def order_phone(message: Message, state: FSMContext):
    user = await db.user_get(message.from_user.id)
    lang = user['lang'] if user else "ru"
    
    phone = message.contact.phone_number if message.contact else message.text
    if not phone:
        await message.answer(TEXT[lang]["order_phone"], reply_markup=kb_contact(lang))
        return
    
    await state.update_data(phone=phone)
    await state.set_state(States.order_city)
    await message.answer(TEXT[lang]["order_city"], reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена" if lang == "ru" else "❌ Bekor qilish")]],
        resize_keyboard=True
    ))

@dp.message(States.order_city)
async def order_city(message: Message, state: FSMContext):
    user = await db.user_get(message.from_user.id)
    lang = user['lang'] if user else "ru"
    
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
    
    user = await db.user_get(call.from_user.id)
    lang = user['lang'] if user else "ru"
    
    await state.set_state(States.order_address)
    await call.message.answer(TEXT[lang]["order_address"])
    await call.answer()

@dp.message(States.order_address)
async def order_address(message: Message, state: FSMContext):
    user = await db.user_get(message.from_user.id)
    lang = user['lang'] if user else "ru"
    
    if not message.text:
        await message.answer(TEXT[lang]["order_address"])
        return
    
    await state.update_data(address=message.text)
    await state.set_state(States.order_comment)
    await message.answer(TEXT[lang]["order_comment"], reply_markup=ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Пропустить" if lang == "ru" else "O'tkazib yuborish")],
            [KeyboardButton(text="❌ Отмена" if lang == "ru" else "❌ Bekor qilish")]
        ],
        resize_keyboard=True
    ))

@dp.message(States.order_comment)
async def order_comment(message: Message, state: FSMContext):
    user = await db.user_get(message.from_user.id)
    lang = user['lang'] if user else "ru"
    
    comment = message.text if message.text not in ["Пропустить", "O'tkazib yuborish"] else ""
    await state.update_data(comment=comment)
    
    data = await state.get_data()
    cart = await db.cart_get(message.from_user.id)
    
    items_text = "\n".join([f"• {esc(it['product_name'])} x{it['qty']}" for it in cart])
    total = sum(it['qty'] * 100000 for it in cart)  # Заглушка
    
    delivery_names = {
        "b2b": "B2B Почта",
        "yandex_courier": "Яндекс Курьер",
        "yandex_pvz": "Яндекс ПВЗ"
    }
    
    text = TEXT[lang]["order_confirm"].format(
        name=esc(data['name']),
        phone=esc(data['phone']),
        city=esc(data['city']),
        delivery=delivery_names.get(data['delivery'], data['delivery']),
        address=esc(data['address']),
        comment=esc(data.get('comment', '—')),
        items=items_text,
        total=format_price(total)
    )
    
    await state.set_state(States.order_confirm)
    await message.answer(text, reply_markup=kb_order_confirm(lang))

@dp.callback_query(F.data == "order:confirm", States.order_confirm)
async def order_confirm(call: CallbackQuery, state: FSMContext):
    user = await db.user_get(call.from_user.id)
    lang = user['lang'] if user else "ru"
    data = await state.get_data()
    
    cart = await db.cart_get(call.from_user.id)
    items_json = str([{"name": it['product_name'], "qty": it['qty']} for it in cart])
    total = sum(it['qty'] * 100000 for it in cart)
    
    order_data = {
        'user_id': call.from_user.id,
        'username': call.from_user.username or "",
        'name': data['name'],
        'phone': data['phone'],
        'city': data['city'],
        'items': items_json,
        'total_amount': total,
        'delivery_type': data['delivery'],
        'delivery_address': data['address'],
        'comment': data.get('comment', ''),
        'promo_code': '',
        'discount_percent': 0
    }
    
    order_id = await db.order_create(order_data)
    
    # Уведомить админов
    for admin_id in Config.ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🆕 Новый заказ #{order_id}\n\n"
                f"👤 {esc(data['name'])}\n"
                f"📱 {esc(data['phone'])}\n"
                f"🏙 {esc(data['city'])}\n"
                f"💰 {format_price(total)} сум",
                reply_markup=kb_admin_order(order_id, "ru")
            )
        except Exception as e:
            print(f"Failed to notify admin {admin_id}: {e}")
    
    await db.cart_clear(call.from_user.id)
    await state.clear()
    
    await call.message.answer(TEXT[lang]["order_success"].format(order_id=order_id), reply_markup=kb_main(lang))
    await call.answer()

# History
@dp.message(F.text.in_(["📜 История", "📜 Buyurtmalar"]))
async def cmd_history(message: Message, state: FSMContext):
    user = await db.user_get(message.from_user.id)
    lang = user['lang'] if user else "ru"
    
    # Получить заказы пользователя
    orders = []  # Заглушка - нужно добавить метод в БД
    
    if not orders:
        await message.answer(TEXT[lang]["history_empty"], reply_markup=kb_main(lang))
        return

# Admin panel
@dp.message(F.text.in_(["🛠 Админ", "🛠 Admin"]))
async def cmd_admin(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    user = await db.user_get(message.from_user.id)
    lang = user['lang'] if user else "ru"
    
    await message.answer(TEXT[lang]["admin_menu"], reply_markup=kb_admin(lang))

@dp.callback_query(F.data.startswith("admin:"))
async def admin_action(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Access denied")
        return
    
    action = call.data.split(":")[1]
    user = await db.user_get(call.from_user.id)
    lang = user['lang'] if user else "ru"
    
    if action == "stats":
        stats = await db.get_stats()
        text = TEXT[lang]["admin_stats"].format(**stats)
        await call.message.answer(text, reply_markup=kb_admin(lang))
    
    elif action == "new_orders":
        orders = await db.orders_get_by_status("new")
        if not orders:
            await call.message.answer("Нет новых заказов")
        else:
            for order in orders[:5]:
                text = f"🆕 Заказ #{order['id']}\n👤 {esc(order['name'])}\n📱 {esc(order['phone'])}"
                await call.message.answer(text, reply_markup=kb_admin_order(order['id'], lang))
    
    await call.answer()

# Order status management
@dp.callback_query(F.data.startswith("order_seen:"))
async def order_seen(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    
    order_id = int(call.data.split(":")[1])
    await db.order_mark_seen(order_id, call.from_user.id)
    await call.answer("Отмечено как просмотренное")

@dp.callback_query(F.data.startswith("order_process:"))
async def order_process(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    
    order_id = int(call.data.split(":")[1])
    await db.order_update_status(order_id, "processing", call.from_user.id)
    
    # Уведомить клиента
    order = await db.order_get(order_id)
    if order:
        user = await db.user_get(order['user_id'])
        lang = user['lang'] if user else "ru"
        try:
            await bot.send_message(
                order['user_id'],
                f"⚙️ Заказ #{order_id} в обработке!\n\n"
                f"Менеджер скоро свяжется с вами.",
                reply_markup=kb_main(lang)
            )
        except Exception as e:
            print(f"Failed to notify user: {e}")
    
    await call.answer("Статус обновлен")

@dp.callback_query(F.data.startswith("order_ship:"))
async def order_ship(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    
    order_id = int(call.data.split(":")[1])
    await db.order_update_status(order_id, "shipped", call.from_user.id)
    await call.answer("Отмечено как отправлено")

@dp.callback_query(F.data.startswith("order_deliver:"))
async def order_deliver(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    
    order_id = int(call.data.split(":")[1])
    await db.order_update_status(order_id, "delivered", call.from_user.id)
    await call.answer("Отмечено как доставлено")

@dp.callback_query(F.data.startswith("order_cancel:"))
async def order_cancel(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    
    order_id = int(call.data.split(":")[1])
    await db.order_update_status(order_id, "cancelled", call.from_user.id)
    await call.answer("Заказ отменен")

# =========================
# MONTHLY REPORT
# =========================
async def send_monthly_report():
    """Отправить отчет за прошедший месяц"""
    now = datetime.now(Config.TZ)
    year, month = now.year, now.month
    
    # Проверить не отправляли ли уже
    if await db.report_is_sent(year, month):
        return
    
    # Получить заказы за месяц
    orders = await db.orders_get_monthly(year, month)
    if not orders:
        return
    
    # Создать Excel
    Config.REPORTS_DIR.mkdir(exist_ok=True)
    filename = Config.REPORTS_DIR / f"report_{year}_{month:02d}.xlsx"
    
    wb = Workbook()
    ws = wb.active
    ws.title = f"Report {month}.{year}"
    
    # Заголовки
    headers = ["ID", "Дата", "Клиент", "Телефон", "Город", "Товары", "Сумма", "Статус"]
    ws.append(headers)
    
    # Стили заголовка
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    
    # Данные
    total_amount = 0
    for order in orders:
        ws.append([
            order['id'],
            order['created_at'],
            order['name'],
            order['phone'],
            order['city'],
            order['items'][:50] + "..." if len(order['items']) > 50 else order['items'],
            order['total_amount'],
            order['status']
        ])
        total_amount += order['total_amount'] or 0
    
    # Автоширина
    for col in ws.columns:
        max_len = 0
        col_letter = col[0].column_letter
        for cell in col:
            try:
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)))
            except:
                pass
        ws.column_dimensions[col_letter].width = min(max_len + 2, 50)
    
    wb.save(filename)
    
    # Отправить админам
    stats = {
        "period": f"{month:02d}.{year}",
        "total_orders": len(orders),
        "total_amount": total_amount
    }
    
    text = (
        f"📊 <b>Месячный отчет — {stats['period']}</b>\n\n"
        f"📦 Всего заказов: {stats['total_orders']}\n"
        f"💰 Общая сумма: {format_price(stats['total_amount'])} сум\n\n"
        f"Файл во вложении."
    )
    
    for admin_id in Config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
            await bot.send_document(admin_id, FSInputFile(str(filename)))
        except Exception as e:
            print(f"Failed to send report to {admin_id}: {e}")
    
    # Сохранить в БД
    await db.report_mark_sent(year, month, str(filename), stats['total_orders'], stats['total_amount'])

# =========================
# REMINDERS (исправлено!)
# =========================
async def check_reminders():
    """Проверить напоминания - только непросмотренные заказы"""
    orders = await db.orders_get_for_reminder()
    
    if not orders:
        return
    
    # Группировать по админам для рассылки
    for admin_id in Config.ADMIN_IDS:
        try:
            lines = []
            for order in orders[:10]:  # Максимум 10
                lines.append(
                    f"🆕 #{order['id']} | {esc(order['name'])} | "
                    f"{esc(order['phone'])} | {esc(order['city'])}"
                )
            
            text = "🔔 <b>Напоминание: новые заказы требуют внимания!</b>\n\n" + "\n".join(lines)
            await bot.send_message(admin_id, text)
        except Exception as e:
            print(f"Reminder failed for {admin_id}: {e}")
    
    # Обновить reminded_at
    for order in orders:
        await db.order_update_reminded(order['id'])

# =========================
# SCHEDULER
# =========================
async def start_scheduler():
    scheduler = AsyncIOScheduler()
    
    # Напоминания каждые 30 минут
    scheduler.add_job(check_reminders, "interval", minutes=30)
    
    # Отчет в последний день месяца в 23:00
    scheduler.add_job(send_monthly_report, "cron", day="last", hour=23, minute=0)
    
    # Также проверить при старте (если пропустили)
    scheduler.add_job(send_monthly_report, "date", run_date=datetime.now() + timedelta(seconds=60))
    
    scheduler.start()

# =========================
# WEB SERVER (Render)
# =========================
async def health_server():
    app = web.Application()
    
    async def health(request):
        return web.Response(text="OK", status=200)
    
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", Config.PORT)
    await site.start()
    print(f"Health server on port {Config.PORT}")

# =========================
# MAIN
# =========================
async def main():
    await db.connect()
    await start_scheduler()
    await health_server()
    
    print(f"✅ Bot started with {len(Config.ADMIN_IDS)} admins")
    print(f"Admins: {Config.ADMIN_IDS}")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
