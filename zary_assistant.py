# ZARY ASSISTANT v2
# Full production bot

import os
import re
import sqlite3
import logging
import threading
from datetime import datetime

from flask import Flask

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ================= CONFIG =================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "").strip()

CHANNEL_URL = "https://t.me/zaryco_official"
INSTAGRAM_URL = "https://www.instagram.com/zary.co/"
YOUTUBE_URL = "https://www.youtube.com/@ZARYCOOFFICIAL"

PORT = int(os.getenv("PORT", "10000"))
DB_PATH = "zary.db"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN empty!")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("zary")

# ================= HEALTH =================

app = Flask(__name__)

@app.route("/", methods=["GET", "HEAD"])
def health():
    return ("ok", 200)

def run_health():
    app.run(host="0.0.0.0", port=PORT)

# ================= DATABASE =================

def db_init():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created TEXT,
        user_id INTEGER,
        name TEXT,
        phone TEXT,
        city TEXT,
        category TEXT,
        size TEXT,
        comment TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS cart(
        user_id INTEGER,
        item TEXT
    )
    """)

    con.commit()
    con.close()

def db_add_user(uid):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO users(id) VALUES(?)", (uid,))
    con.commit()
    con.close()

# ================= UI =================

def menu():
    kb = [
        ["Xudi", "Kurtka/Ustki"],
        ["Kostyumlar", "Maktab formasi"],
        ["Yozgi", "Yangi"],
        ["🧺 Корзина", "📜 История"],
        ["📞 Связаться", "✅ Оформить заказ"],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def channel_btn():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📣 Telegram kanal", url=CHANNEL_URL)]
    ])

def socials():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📣 Telegram", url=CHANNEL_URL)],
        [InlineKeyboardButton("📸 Instagram", url=INSTAGRAM_URL)],
        [InlineKeyboardButton("▶️ YouTube", url=YOUTUBE_URL)],
    ])

# ================= STATES =================

CATEGORY, SIZE, NAME, PHONE, CITY, COMMENT = range(6)

# ================= COMMANDS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_add_user(update.effective_user.id)

    text = (
        "👋 ZARY & CO ga xush kelibsiz!\n\n"
        "✨ Milliy premium bolalar brendi\n"
        "✨ Yuqori sifat\n"
        "✨ Zamonaviy dizayn\n\n"
        "👇 Bo‘limni tanlang:"
    )
    await update.message.reply_text(text, reply_markup=menu())

async def chatid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"chat_id: {update.effective_chat.id}")

# ================= CATALOG =================

async def catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📸 Barcha kolleksiya kanalimizda 👇",
        reply_markup=menu(),
    )
    await update.message.reply_text("➡️ Kanal:", reply_markup=channel_btn())

# ================= CART =================

async def add_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    item = update.message.text
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("INSERT INTO cart VALUES(?,?)",
                (update.effective_user.id, item))
    con.commit()
    con.close()
    await update.message.reply_text("🧺 Добавлено в корзину")

async def show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT item FROM cart WHERE user_id=?",
                (update.effective_user.id,))
    rows = cur.fetchall()
    con.close()

    if not rows:
        await update.message.reply_text("🧺 Корзина пустая")
        return

    text = "🧺 Корзина:\n\n"
    for r in rows:
        text += f"• {r[0]}\n"

    await update.message.reply_text(text)

# ================= HISTORY =================

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT category,created FROM orders WHERE user_id=?",
                (update.effective_user.id,))
    rows = cur.fetchall()
    con.close()

    if not rows:
        await update.message.reply_text("История пустая")
        return

    text = "📜 История заказов:\n\n"
    for r in rows:
        text += f"{r[0]} — {r[1]}\n"

    await update.message.reply_text(text)

# ================= ORDER =================

async def order_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Что хотите заказать?", reply_markup=menu())
    return CATEGORY

async def order_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["category"] = update.message.text
    await update.message.reply_text("Размер?")
    return SIZE

async def order_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["size"] = update.message.text
    await update.message.reply_text("Имя?")
    return NAME

async def order_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text
    kb = ReplyKeyboardMarkup(
        [[KeyboardButton("📲 Отправить контакт", request_contact=True)]],
        resize_keyboard=True,
    )
    await update.message.reply_text("Телефон:", reply_markup=kb)
    return PHONE

async def order_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.contact:
        context.user_data["phone"] = update.message.contact.phone_number
    else:
        context.user_data["phone"] = update.message.text

    await update.message.reply_text("Город?")
    return CITY

async def order_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["city"] = update.message.text
    await update.message.reply_text("Комментарий?")
    return COMMENT

async def order_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["comment"] = update.message.text

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
    INSERT INTO orders(created,user_id,name,phone,city,category,size,comment)
    VALUES(?,?,?,?,?,?,?,?)
    """, (
        now,
        update.effective_user.id,
        context.user_data["name"],
        context.user_data["phone"],
        context.user_data["city"],
        context.user_data["category"],
        context.user_data["size"],
        context.user_data["comment"],
    ))
    con.commit()
    con.close()

    if ADMIN_CHAT_ID:
        await context.bot.send_message(
            int(ADMIN_CHAT_ID),
            f"🆕 Заказ\n{context.user_data}"
        )

    await update.message.reply_text(
        "✅ Rahmat! Menejer bog‘lanadi 💚",
        reply_markup=menu(),
    )
    await update.message.reply_text("🔗 Sahifalar:", reply_markup=socials())

    return ConversationHandler.END

# ================= REPORT =================

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM orders")
    total = cur.fetchone()[0]
    con.close()

    await update.message.reply_text(f"📊 Всего заказов: {total}")

# ================= BUILD =================

def build():
    bot = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^✅ Оформить заказ$"), order_start)],
        states={
            CATEGORY: [MessageHandler(filters.TEXT, order_category)],
            SIZE: [MessageHandler(filters.TEXT, order_size)],
            NAME: [MessageHandler(filters.TEXT, order_name)],
            PHONE: [
                MessageHandler(filters.CONTACT, order_phone),
                MessageHandler(filters.TEXT, order_phone),
            ],
            CITY: [MessageHandler(filters.TEXT, order_city)],
            COMMENT: [MessageHandler(filters.TEXT, order_comment)],
        },
        fallbacks=[],
    )

    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(CommandHandler("chatid", chatid))
    bot.add_handler(CommandHandler("report", report))

    bot.add_handler(MessageHandler(filters.Regex("^🧺 Корзина$"), show_cart))
    bot.add_handler(MessageHandler(filters.Regex("^📜 История$"), history))

    bot.add_handler(MessageHandler(
        filters.Regex("^(Xudi|Kurtka/Ustki|Kostyumlar|Maktab formasi|Yozgi|Yangi)$"),
        catalog,
    ))

    bot.add_handler(conv)

    return bot

# ================= MAIN =================

def main():
    db_init()
    threading.Thread(target=run_health, daemon=True).start()
    bot = build()
    bot.run_polling()

if __name__ == "__main__":
    main()
