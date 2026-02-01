import os
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, time
from zoneinfo import ZoneInfo

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
    ReplyKeyboardRemove,
)

# =========================
# CONFIG
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env is empty. Set it in Render Environment Variables: BOT_TOKEN=...")

MANAGER_CHAT_ID = 7195737024  # твой Telegram ID

# Рабочее время менеджера (Ташкент)
TZ = ZoneInfo("Asia/Tashkent")
WORK_START = time(9, 0)
WORK_END = time(21, 0)

# Соцсети
INSTAGRAM_URL = "https://www.instagram.com/zary.co/"
YOUTUBE_URL = "https://www.youtube.com/@ZARYCOOFFICIAL"

# Если есть username менеджера (опционально), напиши без @, например "zaryco_manager"
MANAGER_USERNAME = ""  # можно оставить пустым

# =========================
# PHOTO CATALOG (file_id)
# =========================
PHOTO_CATALOG = {
    "hoodie": {"ru": "Худи", "uz": "Xudi", "items": []},
    "outerwear": {"ru": "Куртки/Верх", "uz": "Kurtka/Ustki", "items": []},
    "sets": {"ru": "Костюмы", "uz": "Kostyumlar", "items": []},
    "school": {"ru": "Школьная форма", "uz": "Maktab formasi", "items": []},
    "summer": {"ru": "Лето", "uz": "Yozgi", "items": []},
    "new": {"ru": "Новинки", "uz": "Yangi", "items": []},
}

# =========================
# TEXTS
# =========================
TEXT = {
    "ru": {
        "hello": (
            "👋 Добро пожаловать в ZARY & CO 🇺🇿\n"
            "Стильная, удобная и качественная детская одежда — для школы, прогулок и праздников.\n\n"
            "Выберите действие 👇"
        ),
        "hello_ask_lang": "Выберите язык 👇",
        "brand": (
            "✨ **ZARY & CO — национальный бренд детской одежды 🇺🇿**\n"
            "Мы создаём одежду с заботой о детях: удобно, красиво и качественно.\n"
            "Одежда сохраняет вид даже после многих стирок.\n\n"
            "ZARY & CO — когда комфорт и стиль вместе."
        ),
        "worktime_in": "✅ Заявка принята. Менеджер свяжется с вами в ближайшее время (в рабочие часы).",
        "worktime_out": "✅ Заявка принята. Сейчас вне рабочего времени — менеджер свяжется с вами завтра в рабочие часы.",
        "subscribe": (
            "📲 Подпишитесь, чтобы быть в курсе новых коллекций:\n"
            f"Instagram: {INSTAGRAM_URL}\n"
            f"YouTube: {YOUTUBE_URL}"
        ),
        "menu_title": "Выберите действие 👇",
        "price_title": "🧾 **Прайс (укороченный)**\nВыберите раздел:",
        "price_boys": (
            "👶 **МАЛЬЧИКИ**\n"
            "• Верх: куртка/ветровка/бомбер/парка/анорак/жилетка\n"
            "• Толстовки: худи/свитшот/лонгслив/кардиган/флис\n"
            "• Низ: брюки/джинсы/шорты/комбинезон\n"
            "• Комплекты: спорткостюм/домашний/пижама/летний комплект"
        ),
        "price_girls": (
            "👧 **ДЕВОЧКИ**\n"
            "• Верх: куртка/ветровка/пальто/парка/анорак/жилетка\n"
            "• Платья/юбки: повседневное/нарядное/сарафан/юбка/юбка-шорты\n"
            "• Толстовки: худи/свитшот/лонгслив/кардиган/флис/жакет\n"
            "• Низ: брюки/джинсы/леггинсы/шорты/комбинезон\n"
            "• Комплекты: костюм/домашний/пижама/летний комплект"
        ),
        "price_unisex": (
            "🧒 **УНИСЕКС / БАЗА**\n"
            "• Футболка/лонгслив/водолазка/рубашка\n"
            "• Свитер/жилет/пижама/домашний комплект\n"
            "• Спорткостюм базовый/комбинезоны\n"
            "• Школьный костюм\n"
            "• Индивидуальная модель под ТЗ"
        ),
        "photos_title": "📸 **Каталог (фото)**\nВыберите раздел:",
        "photos_empty": "В этом разделе пока нет фото. Напишите менеджеру — отправим варианты и цены.",
        "size_title": "📏 **Подбор размера (1–15 лет)**\nВыберите способ:",
        "size_age_ask": "Напишите возраст ребёнка (1–15). Пример: `7`",
        "size_height_ask": "Теперь напишите рост в см. Пример: `125`",
        "size_bad_age": "Введите возраст цифрой от 1 до 15. Пример: `7`",
        "size_bad_height": "Введите рост цифрой (например: 125).",
        "size_result": (
            "📏 **Размерная сетка (по росту):**\n"
            "86 | 92 | 98 | 104 | 110\n"
            "116 | 122 | 128 | 134 | 140\n"
            "146 | 152 | 158 | 164\n\n"
            "👶 По возрасту: {age} → примерно **{age_rec}**\n"
            "📏 По росту: {height} см → рекомендуем **{height_rec}**\n\n"
            "ℹ️ Точный размер подтверждает менеджер (по модели и посадке)."
        ),
        "order_start": "🧾 Оформляем заказ.\nКак вас зовут?",
        "order_phone": "📲 Отправьте номер телефона (или нажмите кнопку «📲 Отправить контакт»).",
        "order_city": "🏙 Ваш город/район?",
        "order_addr": "📍 Адрес доставки (улица/дом/квартира или ориентир):",
        "order_item": "👕 Что хотите заказать? (например: куртка / худи / костюм / школьная форма)",
        "order_size": "👶 Возраст и рост ребёнка одним сообщением.\nПример: `7 лет, 125 см`",
        "order_comment": "✍️ Комментарий (цвет/размер/кол-во) или напишите «нет»",
        "order_review": (
            "🧾 **Проверьте заказ:**\n"
            "• Имя: {name}\n"
            "• Телефон: {phone}\n"
            "• Город/район: {city}\n"
            "• Адрес: {addr}\n"
            "• Товар: {item}\n"
            "• Возраст/рост: {size}\n"
            "• Комментарий: {comment}\n\n"
            "Подтвердить?"
        ),
        "order_sent": "✅ Спасибо за заказ! Заявка принята.\nМенеджер свяжется с вами для уточнения деталей ✅",
        "edit_choose": "✏️ Что хотите исправить?",
        "flow_locked": "Сейчас идёт оформление заказа. Хотите продолжить или выйти в меню?",
        "contact_title": (
            "📞 **Связаться**\n"
            "Мы принимаем заявки 24/7.\n"
            "Менеджер отвечает с 09:00 до 21:00.\n"
        ),
        "unknown": "Пожалуйста, выберите действие кнопками 👇",
        "cancelled": "❌ Готово. Возвращаю в меню 👇",
    },
    "uz": {
        "hello": (
            "👋 Assalomu alaykum! ZARY & CO 🇺🇿 ga xush kelibsiz!\n"
            "Zamonaviy, qulay va sifatli bolalar kiyimlari — maktab, sayr va bayram uchun.\n\n"
            "Bo‘limni tanlang 👇"
        ),
        "hello_ask_lang": "Tilni tanlang 👇",
        "brand": (
            "✨ **ZARY & CO — milliy bolalar kiyim brendi 🇺🇿**\n"
            "Qulay, chiroyli va sifatli.\n"
            "Ko‘p yuvilganda ham sifatini saqlaydi.\n\n"
            "ZARY & CO — qulaylik va uslub birga."
        ),
        "worktime_in": "✅ Buyurtma qabul qilindi. Menejer ish vaqtida tez orada bog‘lanadi.",
        "worktime_out": "✅ Buyurtma qabul qilindi. Hozir ish vaqti emas — menejer ertaga ish vaqtida bog‘lanadi.",
        "subscribe": (
            "📲 Yangi kolleksiyalar uchun obuna bo‘ling:\n"
            f"Instagram: {INSTAGRAM_URL}\n"
            f"YouTube: {YOUTUBE_URL}"
        ),
        "menu_title": "Bo‘limni tanlang 👇",
        "price_title": "🧾 **Narxlar (qisqa)**\nBo‘limni tanlang:",
        "price_boys": (
            "👶 **O‘G‘IL BOLALAR**\n"
            "• Ustki: kurtka/vetrovka/bomber/parka/anorak/jilet\n"
            "• Ustki kiyim: xudi/svitshot/longsliv/kardigan/flis\n"
            "• Past: shim/jins/shorti/kombinezon\n"
            "• To‘plam: sport/uy/pijama/yozgi"
        ),
        "price_girls": (
            "👧 **QIZ BOLALAR**\n"
            "• Ustki: kurtka/vetrovka/palto/parka/anorak/jilet\n"
            "• Ko‘ylak/yubka: oddiy/bayram/sarafan/yubka/yubka-shorti\n"
            "• Ustki: xudi/svitshot/longsliv/kardigan/flis/jaket\n"
            "• Past: shim/jins/leggins/shorti/kombinezon\n"
            "• To‘plam: kostyum/uy/pijama/yozgi"
        ),
        "price_unisex": (
            "🧒 **UNISEKS / BAZA**\n"
            "• Futbolka/longsliv/vodolazka/ko‘ylak\n"
            "• Sviter/jilet/pijama/uy to‘plami\n"
            "• Sport kostyum/kombinezon\n"
            "• Maktab kostyumi\n"
            "• Individual model (TZ)"
        ),
        "photos_title": "📸 **Katalog (rasm)**\nBo‘limni tanlang:",
        "photos_empty": "Bu bo‘limda hozircha rasm yo‘q. Menejerga yozing — variant va narxlarni yuboramiz.",
        "size_title": "📏 **O‘lcham tanlash (1–15 yosh)**\nUsulni tanlang:",
        "size_age_ask": "Bolaning yoshini yozing (1–15). Masalan: `7`",
        "size_height_ask": "Endi bo‘yini sm da yozing. Masalan: `125`",
        "size_bad_age": "Yoshni 1 dan 15 gacha raqam bilan yozing. Masalan: `7`",
        "size_bad_height": "Bo‘yini raqam bilan yozing (masalan: 125).",
        "size_result": (
            "📏 **O‘lcham setkasi (bo‘y bo‘yicha):**\n"
            "86 | 92 | 98 | 104 | 110\n"
            "116 | 122 | 128 | 134 | 140\n"
            "146 | 152 | 158 | 164\n\n"
            "👶 Yosh bo‘yicha: {age} → taxminan **{age_rec}**\n"
            "📏 Bo‘y bo‘yicha: {height} sm → tavsiya **{height_rec}**\n\n"
            "ℹ️ Aniq o‘lcham menejer tomonidan tasdiqlanadi (modelga bog‘liq)."
        ),
        "order_start": "🧾 Buyurtma.\nIsmingiz?",
        "order_phone": "📲 Telefon raqam yuboring (yoki «📲 Kontakt yuborish» tugmasi).",
        "order_city": "🏙 Shahar/tuman?",
        "order_addr": "📍 Yetkazib berish manzili:",
        "order_item": "👕 Nima buyurtma qilasiz? (masalan: kurtka / xudi / kostyum / maktab formasi)",
        "order_size": "👶 Yosh va bo‘yni bitta xabarda.\nMasalan: `7 yosh, 125 sm`",
        "order_comment": "✍️ Izoh (rang/o‘lcham/soni) yoki «yo‘q» deb yozing",
        "order_review": (
            "🧾 **Buyurtmani tekshiring:**\n"
            "• Ism: {name}\n"
            "• Telefon: {phone}\n"
            "• Shahar/tuman: {city}\n"
            "• Manzil: {addr}\n"
            "• Mahsulot: {item}\n"
            "• Yosh/bo‘y: {size}\n"
            "• Izoh: {comment}\n\n"
            "Tasdiqlaysizmi?"
        ),
        "order_sent": "✅ Buyurtma uchun rahmat! Qabul qilindi.\nMenejer tafsilotlar uchun bog‘lanadi ✅",
        "edit_choose": "✏️ Nimani tuzatamiz?",
        "flow_locked": "Hozir buyurtma rasmiylashtirilmoqda. Davom etamizmi yoki menyuga chiqamizmi?",
        "contact_title": (
            "📞 **Aloqa**\n"
            "Buyurtmalar 24/7 qabul qilinadi.\n"
            "Menejer 09:00–21:00 da javob beradi.\n"
        ),
        "unknown": "Iltimos, tugmalar orqali tanlang 👇",
        "cancelled": "❌ Tayyor. Menyuga qaytdik 👇",
    },
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
    order_addr = State()
    order_item = State()
    order_size = State()
    order_comment = State()
    order_confirm = State()

    edit_field = State()  # which field editing


# =========================
# HELPERS
# =========================
def now_local() -> datetime:
    return datetime.now(TZ)


def in_work_time(dt: datetime) -> bool:
    t = dt.time()
    return WORK_START <= t <= WORK_END


def clean_phone(raw: str) -> str:
    return (raw or "").strip().replace(" ", "").replace("-", "")


def looks_like_phone(s: str) -> bool:
    s = clean_phone(s)
    digits = re.sub(r"\D", "", s)
    return 9 <= len(digits) <= 15


async def get_lang(state: FSMContext) -> str:
    data = await state.get_data()
    return data.get("lang", "ru")


async def set_lang_keep(state: FSMContext, lang: str):
    await state.clear()
    await state.update_data(lang=lang)


def kb_lang() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Русский 🇷🇺", callback_data="lang:ru"),
                InlineKeyboardButton(text="O‘zbek 🇺🇿", callback_data="lang:uz"),
            ]
        ]
    )


def kb_menu(lang: str) -> ReplyKeyboardMarkup:
    if lang == "uz":
        rows = [
            [KeyboardButton(text="🧾 Narxlar"), KeyboardButton(text="📸 Katalog")],
            [KeyboardButton(text="📏 O‘lcham"), KeyboardButton(text="✅ Buyurtma")],
            [KeyboardButton(text="📞 Aloqa"), KeyboardButton(text="✨ Brend")],
            [KeyboardButton(text="🌐 Til"), KeyboardButton(text="❌ Bekor qilish")],
        ]
    else:
        rows = [
            [KeyboardButton(text="🧾 Прайс"), KeyboardButton(text="📸 Каталог")],
            [KeyboardButton(text="📏 Размер"), KeyboardButton(text="✅ Заказ")],
            [KeyboardButton(text="📞 Связаться"), KeyboardButton(text="✨ О бренде")],
            [KeyboardButton(text="🌐 Язык"), KeyboardButton(text="❌ Отмена")],
        ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def kb_price(lang: str) -> InlineKeyboardMarkup:
    if lang == "uz":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="👶 O‘g‘il bolalar", callback_data="price:boys")],
                [InlineKeyboardButton(text="👧 Qiz bolalar", callback_data="price:girls")],
                [InlineKeyboardButton(text="🧒 Uniseks/Baza", callback_data="price:unisex")],
                [InlineKeyboardButton(text="✅ Buyurtma", callback_data="go:order")],
                [InlineKeyboardButton(text="⬅️ Menyu", callback_data="back:menu")],
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👶 Мальчики", callback_data="price:boys")],
            [InlineKeyboardButton(text="👧 Девочки", callback_data="price:girls")],
            [InlineKeyboardButton(text="🧒 Унисекс/База", callback_data="price:unisex")],
            [InlineKeyboardButton(text="✅ Оформить заказ", callback_data="go:order")],
            [InlineKeyboardButton(text="⬅️ Меню", callback_data="back:menu")],
        ]
    )


def kb_photos(lang: str) -> InlineKeyboardMarkup:
    rows = []
    for key, v in PHOTO_CATALOG.items():
        title = v["uz"] if lang == "uz" else v["ru"]
        rows.append([InlineKeyboardButton(text=title, callback_data=f"photo:{key}")])
    rows.append(
        [InlineKeyboardButton(text="⬅️ Menyu" if lang == "uz" else "⬅️ Меню", callback_data="back:menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_size_mode(lang: str) -> InlineKeyboardMarkup:
    if lang == "uz":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="👶 Yosh bo‘yicha", callback_data="size:age")],
                [InlineKeyboardButton(text="📏 Bo‘y bo‘yicha", callback_data="size:height")],
                [InlineKeyboardButton(text="⬅️ Menyu", callback_data="back:menu")],
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👶 По возрасту", callback_data="size:age")],
            [InlineKeyboardButton(text="📏 По росту", callback_data="size:height")],
            [InlineKeyboardButton(text="⬅️ Меню", callback_data="back:menu")],
        ]
    )


def kb_order_confirm(lang: str) -> InlineKeyboardMarkup:
    if lang == "uz":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="order:confirm")],
                [InlineKeyboardButton(text="✏️ Tuzatish", callback_data="order:edit")],
                [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="order:cancel")],
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data="order:confirm")],
            [InlineKeyboardButton(text="✏️ Исправить", callback_data="order:edit")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="order:cancel")],
        ]
    )


def kb_edit_fields(lang: str) -> InlineKeyboardMarkup:
    if lang == "uz":
        rows = [
            [InlineKeyboardButton(text="Ism", callback_data="edit:name")],
            [InlineKeyboardButton(text="Telefon", callback_data="edit:phone")],
            [InlineKeyboardButton(text="Shahar/tuman", callback_data="edit:city")],
            [InlineKeyboardButton(text="Manzil", callback_data="edit:addr")],
            [InlineKeyboardButton(text="Mahsulot", callback_data="edit:item")],
            [InlineKeyboardButton(text="Yosh/bo‘y", callback_data="edit:size")],
            [InlineKeyboardButton(text="Izoh", callback_data="edit:comment")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="order:back_confirm")],
        ]
    else:
        rows = [
            [InlineKeyboardButton(text="Имя", callback_data="edit:name")],
            [InlineKeyboardButton(text="Телефон", callback_data="edit:phone")],
            [InlineKeyboardButton(text="Город/район", callback_data="edit:city")],
            [InlineKeyboardButton(text="Адрес", callback_data="edit:addr")],
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


def age_to_size_range(age: int) -> str:
    mapping = {
        1: "86–92",
        2: "92–98",
        3: "98–104",
        4: "104–110",
        5: "110–116",
        6: "116–122",
        7: "122–128",
        8: "128–134",
        9: "134–140",
        10: "140–146",
        11: "146–152",
        12: "152–158",
        13: "158–164",
        14: "164",
        15: "164",
    }
    return mapping.get(age, "—")


def height_to_size(height: int) -> int:
    sizes = [86, 92, 98, 104, 110, 116, 122, 128, 134, 140, 146, 152, 158, 164]
    return min(sizes, key=lambda x: abs(x - height))


async def flow_guard(message: Message, state: FSMContext, lang: str) -> bool:
    st = await state.get_state()
    if st and st.startswith("Flow:order_"):
        if (lang == "ru" and message.text == "❌ Отмена") or (lang == "uz" and message.text == "❌ Bekor qilish"):
            return False
        await message.answer(
            TEXT[lang]["flow_locked"],
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="➡️ Продолжить заказ" if lang == "ru" else "➡️ Buyurtmani davom ettirish",
                            callback_data="order:back_confirm",
                        )
                    ],
                    [InlineKeyboardButton(text="⬅️ Меню" if lang == "ru" else "⬅️ Menyu", callback_data="back:menu")],
                    [InlineKeyboardButton(text="❌ Отмена" if lang == "ru" else "❌ Bekor qilish", callback_data="order:cancel")],
                ]
            ),
        )
        return True
    return False


async def send_order_review(message: Message, state: FSMContext, lang: str):
    data = await state.get_data()
    review = TEXT[lang]["order_review"].format(
        name=data.get("order_name", "-"),
        phone=data.get("order_phone", "-"),
        city=data.get("order_city", "-"),
        addr=data.get("order_addr", "-"),
        item=data.get("order_item", "-"),
        size=data.get("order_size", "-"),
        comment=data.get("order_comment", "-"),
    )
    await state.set_state(Flow.order_confirm)
    await message.answer(review, reply_markup=kb_order_confirm(lang))


# =========================
# HANDLERS
# =========================
async def cmd_start(message: Message, state: FSMContext):
    lang = await get_lang(state)
    data = await state.get_data()
    if "lang" not in data:
        await message.answer(TEXT["ru"]["hello_ask_lang"], reply_markup=kb_lang())
        return
    await set_lang_keep(state, lang)
    await message.answer(TEXT[lang]["hello"], reply_markup=kb_menu(lang))


async def pick_lang(call: CallbackQuery, state: FSMContext):
    lang = call.data.split(":")[1]
    await state.update_data(lang=lang)
    await call.message.answer(TEXT[lang]["hello"], reply_markup=kb_menu(lang))
    await call.answer()


async def back_menu(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    await set_lang_keep(state, lang)
    await call.message.answer(TEXT[lang]["menu_title"], reply_markup=kb_menu(lang))
    await call.answer()


async def menu_by_text(message: Message, state: FSMContext):
    lang = await get_lang(state)

    if await flow_guard(message, state, lang):
        return

    txt = (message.text or "").strip()

    if (lang == "ru" and txt == "🌐 Язык") or (lang == "uz" and txt == "🌐 Til"):
        await message.answer(TEXT[lang]["hello_ask_lang"], reply_markup=kb_lang())
        return

    if (lang == "ru" and txt == "✨ О бренде") or (lang == "uz" and txt == "✨ Brend"):
        await message.answer(TEXT[lang]["brand"], reply_markup=kb_menu(lang))
        await message.answer(TEXT[lang]["subscribe"], reply_markup=kb_menu(lang))
        return

    if (lang == "ru" and txt == "🧾 Прайс") or (lang == "uz" and txt == "🧾 Narxlar"):
        await message.answer(TEXT[lang]["price_title"], reply_markup=kb_price(lang))
        return

    if (lang == "ru" and txt == "📸 Каталог") or (lang == "uz" and txt == "📸 Katalog"):
        await message.answer(TEXT[lang]["photos_title"], reply_markup=kb_photos(lang))
        return

    if (lang == "ru" and txt == "📏 Размер") or (lang == "uz" and txt == "📏 O‘lcham"):
        await message.answer(TEXT[lang]["size_title"], reply_markup=kb_size_mode(lang))
        return

    if (lang == "ru" and txt == "✅ Заказ") or (lang == "uz" and txt == "✅ Buyurtma"):
        await start_order(message, state)
        return

    if (lang == "ru" and txt == "📞 Связаться") or (lang == "uz" and txt == "📞 Aloqa"):
        msg = TEXT[lang]["contact_title"]
        if MANAGER_USERNAME:
            msg += f"\n👩‍💼 Menejer: @{MANAGER_USERNAME}" if lang == "uz" else f"\n👩‍💼 Менеджер: @{MANAGER_USERNAME}"
        await message.answer(msg, reply_markup=kb_menu(lang))
        await message.answer(TEXT[lang]["subscribe"], reply_markup=kb_menu(lang))
        return

    if (lang == "ru" and txt == "❌ Отмена") or (lang == "uz" and txt == "❌ Bekor qilish"):
        await set_lang_keep(state, lang)
        await message.answer(TEXT[lang]["cancelled"], reply_markup=kb_menu(lang))
        return

    await message.answer(TEXT[lang]["unknown"], reply_markup=kb_menu(lang))


# ---------- PRICE ----------
async def price_section(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    sec = call.data.split(":")[1]
    if sec == "boys":
        await call.message.answer(TEXT[lang]["price_boys"], reply_markup=kb_price(lang))
    elif sec == "girls":
        await call.message.answer(TEXT[lang]["price_girls"], reply_markup=kb_price(lang))
    else:
        await call.message.answer(TEXT[lang]["price_unisex"], reply_markup=kb_price(lang))
    await call.answer()


# ---------- PHOTOS ----------
async def photo_section(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    key = call.data.split(":")[1]
    block = PHOTO_CATALOG.get(key)
    if not block:
        await call.message.answer(TEXT[lang]["photos_empty"], reply_markup=kb_photos(lang))
        await call.answer()
        return

    items = block.get("items", [])
    if not items:
        await call.message.answer(TEXT[lang]["photos_empty"], reply_markup=kb_photos(lang))
        await call.answer()
        return

    for it in items[:10]:
        cap = it.get("caption_uz") if lang == "uz" else it.get("caption_ru")
        cap = cap or ""
        order_btn_text = "✅ Заказать это" if lang == "ru" else "✅ Shu mahsulot"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=order_btn_text, callback_data=f"order:prefill:{cap[:30] or block.get('ru','')}")],
                [InlineKeyboardButton(text="⬅️ Меню" if lang == "ru" else "⬅️ Menyu", callback_data="back:menu")],
            ]
        )
        await call.message.answer_photo(photo=it["file_id"], caption=cap, reply_markup=kb)

    await call.answer()


# ---------- SIZE ----------
async def size_mode(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    mode = call.data.split(":")[1]
    if mode == "age":
        await state.set_state(Flow.size_age)
        await call.message.answer(TEXT[lang]["size_age_ask"], reply_markup=ReplyKeyboardRemove())
    else:
        await state.set_state(Flow.size_height)
        await call.message.answer(TEXT[lang]["size_height_ask"], reply_markup=ReplyKeyboardRemove())
    await call.answer()


async def size_age(message: Message, state: FSMContext):
    lang = await get_lang(state)
    txt = (message.text or "").strip()
    if not txt.isdigit():
        await message.answer(TEXT[lang]["size_bad_age"])
        return
    age = int(txt)
    if not (1 <= age <= 15):
        await message.answer(TEXT[lang]["size_bad_age"])
        return
    await state.update_data(_size_age=age)
    await state.set_state(Flow.size_height)
    await message.answer(TEXT[lang]["size_height_ask"])


async def size_height(message: Message, state: FSMContext):
    lang = await get_lang(state)
    txt = (message.text or "").strip()
    if not txt.isdigit():
        await message.answer(TEXT[lang]["size_bad_height"])
        return
    height = int(txt)
    if height < 70 or height > 190:
        await message.answer(TEXT[lang]["size_bad_height"])
        return

    data = await state.get_data()
    age = int(data.get("_size_age", 7))
    age_rec = age_to_size_range(age)
    height_rec = height_to_size(height)

    await set_lang_keep(state, lang)
    await message.answer(
        TEXT[lang]["size_result"].format(age=age, height=height, age_rec=age_rec, height_rec=height_rec),
        reply_markup=kb_menu(lang),
    )
    await message.answer(TEXT[lang]["subscribe"], reply_markup=kb_menu(lang))


# ---------- ORDER ----------
async def start_order(message: Message, state: FSMContext):
    lang = await get_lang(state)
    await state.set_state(Flow.order_name)
    await message.answer(TEXT[lang]["order_start"], reply_markup=ReplyKeyboardRemove())


async def go_order(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    await state.set_state(Flow.order_name)
    await call.message.answer(TEXT[lang]["order_start"], reply_markup=ReplyKeyboardRemove())
    await call.answer()


async def order_prefill(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    payload = call.data.split("order:prefill:", 1)[1]
    await state.update_data(order_item=payload)
    await state.set_state(Flow.order_name)
    await call.message.answer(TEXT[lang]["order_start"], reply_markup=ReplyKeyboardRemove())
    await call.answer()


async def order_name(message: Message, state: FSMContext):
    lang = await get_lang(state)
    name = (message.text or "").strip()
    if not name:
        await message.answer(TEXT[lang]["order_start"])
        return
    await state.update_data(order_name=name)
    await state.set_state(Flow.order_phone)
    await message.answer(TEXT[lang]["order_phone"], reply_markup=kb_contact_request(lang))


async def order_phone(message: Message, state: FSMContext):
    lang = await get_lang(state)

    if message.contact and message.contact.phone_number:
        phone = message.contact.phone_number
    else:
        phone = (message.text or "").strip()

    phone = clean_phone(phone)
    if not looks_like_phone(phone):
        await message.answer(TEXT[lang]["order_phone"], reply_markup=kb_contact_request(lang))
        return

    await state.update_data(order_phone=phone)
    await state.set_state(Flow.order_city)
    await message.answer(TEXT[lang]["order_city"], reply_markup=ReplyKeyboardRemove())


async def order_city(message: Message, state: FSMContext):
    lang = await get_lang(state)
    city = (message.text or "").strip()
    if not city:
        await message.answer(TEXT[lang]["order_city"])
        return
    await state.update_data(order_city=city)
    await state.set_state(Flow.order_addr)
    await message.answer(TEXT[lang]["order_addr"])


async def order_addr(message: Message, state: FSMContext):
    lang = await get_lang(state)
    addr = (message.text or "").strip()
    if not addr:
        await message.answer(TEXT[lang]["order_addr"])
        return
    await state.update_data(order_addr=addr)

    data = await state.get_data()
    if data.get("order_item"):
        await state.set_state(Flow.order_size)
        await message.answer(TEXT[lang]["order_size"])
        return

    await state.set_state(Flow.order_item)
    await message.answer(TEXT[lang]["order_item"])


async def order_item(message: Message, state: FSMContext):
    lang = await get_lang(state)
    item = (message.text or "").strip()
    if not item:
        await message.answer(TEXT[lang]["order_item"])
        return
    await state.update_data(order_item=item)
    await state.set_state(Flow.order_size)
    await message.answer(TEXT[lang]["order_size"])


async def order_size(message: Message, state: FSMContext):
    lang = await get_lang(state)
    size = (message.text or "").strip()
    if not size:
        await message.answer(TEXT[lang]["order_size"])
        return
    await state.update_data(order_size=size)
    await state.set_state(Flow.order_comment)
    await message.answer(TEXT[lang]["order_comment"])


async def order_comment(message: Message, state: FSMContext):
    lang = await get_lang(state)
    comment = (message.text or "").strip()
    if not comment:
        comment = "нет" if lang == "ru" else "yo‘q"

    await state.update_data(order_comment=comment)
    await send_order_review(message, state, lang)


async def order_cancel(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    await set_lang_keep(state, lang)
    await call.message.answer(TEXT[lang]["cancelled"], reply_markup=kb_menu(lang))
    await call.answer()


async def order_back_confirm(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    await send_order_review(call.message, state, lang)
    await call.answer()


async def order_edit(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    await call.message.answer(TEXT[lang]["edit_choose"], reply_markup=kb_edit_fields(lang))
    await call.answer()


async def edit_pick(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    field = call.data.split(":")[1]
    await state.update_data(_edit_field=field)

    prompts = {
        "name": TEXT[lang]["order_start"],
        "phone": TEXT[lang]["order_phone"],
        "city": TEXT[lang]["order_city"],
        "addr": TEXT[lang]["order_addr"],
        "item": TEXT[lang]["order_item"],
        "size": TEXT[lang]["order_size"],
        "comment": TEXT[lang]["order_comment"],
    }
    await call.message.answer(prompts.get(field, TEXT[lang]["unknown"]), reply_markup=ReplyKeyboardRemove())
    await state.set_state(Flow.edit_field)
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
        value = clean_phone(value)
        if not looks_like_phone(value):
            await message.answer(TEXT[lang]["order_phone"], reply_markup=kb_contact_request(lang))
            return
    else:
        value = (message.text or "").strip()
        if not value:
            await message.answer(TEXT[lang]["unknown"])
            return

    key_map = {
        "name": "order_name",
        "phone": "order_phone",
        "city": "order_city",
        "addr": "order_addr",
        "item": "order_item",
        "size": "order_size",
        "comment": "order_comment",
    }
    if field in key_map:
        await state.update_data(**{key_map[field]: value})

    # нормально возвращаем подтверждение (без фейкового CallbackQuery)
    await send_order_review(message, state, lang)


async def order_confirm(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    data = await state.get_data()

    summary = (
        "🧾 Данные заказа:\n"
        f"• Имя: {data.get('order_name','-')}\n"
        f"• Телефон: {data.get('order_phone','-')}\n"
        f"• Город/район: {data.get('order_city','-')}\n"
        f"• Адрес: {data.get('order_addr','-')}\n"
        f"• Товар: {data.get('order_item','-')}\n"
        f"• Возраст/рост: {data.get('order_size','-')}\n"
        f"• Комментарий: {data.get('order_comment','-')}\n"
    )

    ts = now_local().strftime("%Y-%m-%d %H:%M")
    username = f"@{call.from_user.username}" if call.from_user.username else "-"
    manager_text = (
        f"🛎 Новый заказ ({ts}, lang={lang})\n\n{summary}\n"
        f"👤 user_id: {call.from_user.id}\n"
        f"👤 username: {username}"
    )

    try:
        await call.message.bot.send_message(chat_id=MANAGER_CHAT_ID, text=manager_text)
    except Exception as e:
        print(f"Ошибка отправки менеджеру: {e}")

    msg = TEXT[lang]["worktime_in"] if in_work_time(now_local()) else TEXT[lang]["worktime_out"]
    await call.message.answer(TEXT[lang]["order_sent"])
    await call.message.answer(msg)
    await call.message.answer(TEXT[lang]["subscribe"], reply_markup=kb_menu(lang))
    await call.message.answer("😊✨")

    await set_lang_keep(state, lang)
    await call.message.answer(TEXT[lang]["menu_title"], reply_markup=kb_menu(lang))
    await call.answer()


# =========================
# DISPATCHER BUILD
# =========================
def build_dp() -> Dispatcher:
    dp = Dispatcher()

    dp.message.register(cmd_start, CommandStart())
    dp.callback_query.register(pick_lang, F.data.startswith("lang:"))
    dp.callback_query.register(back_menu, F.data == "back:menu")

    dp.callback_query.register(price_section, F.data.startswith("price:"))
    dp.callback_query.register(go_order, F.data == "go:order")

    dp.callback_query.register(photo_section, F.data.startswith("photo:"))
    dp.callback_query.register(order_prefill, F.data.startswith("order:prefill:"))

    dp.callback_query.register(size_mode, F.data.startswith("size:"))
    dp.message.register(size_age, Flow.size_age)
    dp.message.register(size_height, Flow.size_height)

    dp.message.register(order_name, Flow.order_name)
    dp.message.register(order_phone, Flow.order_phone)
    dp.message.register(order_city, Flow.order_city)
    dp.message.register(order_addr, Flow.order_addr)
    dp.message.register(order_item, Flow.order_item)
    dp.message.register(order_size, Flow.order_size)
    dp.message.register(order_comment, Flow.order_comment)
    dp.message.register(edit_field_value, Flow.edit_field)

    dp.callback_query.register(order_cancel, F.data == "order:cancel")
    dp.callback_query.register(order_confirm, F.data == "order:confirm")
    dp.callback_query.register(order_edit, F.data == "order:edit")
    dp.callback_query.register(order_back_confirm, F.data == "order:back_confirm")
    dp.callback_query.register(edit_pick, F.data.startswith("edit:"))

    dp.message.register(menu_by_text, F.text)

    return dp


# =========================
# RENDER PORT BINDING (fix "No open ports detected")
# =========================
class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        return  # mute logs


def start_health_server():
    port = int(os.getenv("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print(f"✅ Health server listening on порт {port} (Render port binding).")


async def main():
    # IMPORTANT for Render Web Service
    start_health_server()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
    dp = build_dp()
    print("✅ ZARY & CO assistant started (polling).")
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
