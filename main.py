import os
import json
import time
import random
import logging
import threading
from datetime import datetime, timedelta
from functools import wraps
from typing import Dict, Any, List, Optional

from flask import Flask
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
import telebot
from telebot import types
from telebot.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
)

# =====================================
# CONFIG / FILES
# =====================================
TOKEN = os.getenv("BOT_TOKEN", "")
PORT = int(os.getenv("PORT", "8000"))

if not TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi. Environment variable ga qo'ying.")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

DATA_FILE = "users.json"
ORDERS_FILE = "orders.json"
CONFIG_FILE = "config.json"
PROMO_FILE = "promo.json"
ADMINS_FILE = "admins.json"
LOGS_FILE = "bot.log"
BACKUP_DIR = "backups"

DEFAULT_REQUIRED_CHANNELS = [
    {"username": "@ALFA_BONUS_NEWS", "title": "ALFA BONUS NEWS", "auto_remove_at": 0, "confirmed_count": 0},
    {"username": "@NWS_ALFA_07", "title": "NWS ALFA 07", "auto_remove_at": 0, "confirmed_count": 0},
    {"username": "@NWS_ALFA_UC", "title": "NWS ALFA UC", "auto_remove_at": 0, "confirmed_count": 0},
]

DEFAULT_ADMINS = {
    "5996676608": {
        "username": "@NWSxALFA",
        "role": "superadmin",
        "added_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
}

DEFAULT_MESSAGES = {
    "welcome": "👋 Xush kelibsiz!",
    "not_subscribed": "⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling.\n\n✅ Obuna bo'lgach «Tekshirish» ni bosing.",
    "subscribe_bonus_text": "🎉 Obuna uchun bonus berildi!",
}

DEFAULT_CONFIG = {
    "required_channels": DEFAULT_REQUIRED_CHANNELS,
    "earn_tasks": [],
    "referral_bonus": 1000,
    "welcome_bonus": 100,
    "subscribe_bonus": 200,
    "daily_bonus_range": [100, 500],
    "min_topup": 5000,
    "services": [],
    "payment_cards": [],
    "payment_channel_id": None,
    "broadcast_targets": [],
    "messages": DEFAULT_MESSAGES,
}

DEFAULT_PROMO_CODES = {
    "WELCOME100": 100,
    "BONUS500": 500,
}

logging.basicConfig(
    filename=LOGS_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    encoding="utf-8",
)
logger = logging.getLogger(__name__)
lock = threading.RLock()


# =====================================
# WEB / KEEP ALIVE
# =====================================
@app.route("/")
def home():
    return "Bot ishlamoqda! 🤖"


@app.route("/health")
def health():
    return {"status": "ok", "users": len(users), "time": datetime.now().isoformat()}


def run_web():
    app.run(host="0.0.0.0", port=PORT)


def keep_alive():
    t = threading.Thread(target=run_web, daemon=True)
    t.start()


# =====================================
# DATABASE
# =====================================
class Database:
    @staticmethod
    def _read_json(path: str, default):
        if not os.path.exists(path):
            return default
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"{path} o'qishda xato: {e}")
            return default

    @staticmethod
    def load_all():
        users_data = Database._read_json(DATA_FILE, {})
        orders_data = Database._read_json(ORDERS_FILE, [])
        config_data = Database._read_json(CONFIG_FILE, {})
        promo_data = Database._read_json(PROMO_FILE, DEFAULT_PROMO_CODES.copy())
        admins_data = Database._read_json(ADMINS_FILE, DEFAULT_ADMINS.copy())

        merged_config = json.loads(json.dumps(DEFAULT_CONFIG))
        merged_config.update(config_data or {})
        merged_config["daily_bonus_range"] = list(merged_config.get("daily_bonus_range", [100, 500]))
        merged_config["messages"] = {**DEFAULT_MESSAGES, **merged_config.get("messages", {})}

        # normalize admin keys to str
        admins_data = {str(k): v for k, v in admins_data.items()}

        return users_data, orders_data, merged_config, promo_data, admins_data

    @staticmethod
    def save_all(users_data, orders_data, config_data, promo_data, admins_data):
        with lock:
            for path, data in {
                DATA_FILE: users_data,
                ORDERS_FILE: orders_data,
                CONFIG_FILE: config_data,
                PROMO_FILE: promo_data,
                ADMINS_FILE: admins_data,
            }.items():
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=4)
                except Exception as e:
                    logger.error(f"Saqlashda xato {path}: {e}")

    @staticmethod
    def backup():
        os.makedirs(BACKUP_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        for path in [DATA_FILE, ORDERS_FILE, CONFIG_FILE, PROMO_FILE, ADMINS_FILE]:
            if os.path.exists(path):
                backup_path = os.path.join(BACKUP_DIR, f"{path.replace('.json', '')}_{stamp}.json")
                try:
                    with open(path, "r", encoding="utf-8") as src, open(backup_path, "w", encoding="utf-8") as dst:
                        dst.write(src.read())
                except Exception as e:
                    logger.error(f"Backup xato {path}: {e}")


users, orders, config, promo_codes, ADMINS = Database.load_all()


def save_db():
    Database.save_all(users, orders, config, promo_codes, ADMINS)


def auto_backup():
    while True:
        time.sleep(86400)
        Database.backup()
        logger.info("Avtomatik backup yaratildi")


threading.Thread(target=auto_backup, daemon=True).start()


# =====================================
# HELPERS
# =====================================
def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def is_admin(user_id: int) -> bool:
    return str(user_id) in ADMINS


def is_superadmin(user_id: int) -> bool:
    return str(user_id) in ADMINS and ADMINS[str(user_id)].get("role") == "superadmin"


def get_text(key: str) -> str:
    return config.get("messages", {}).get(key, DEFAULT_MESSAGES.get(key, ""))


def new_id(seq: List[Dict[str, Any]]) -> int:
    return (max([x.get("id", 0) for x in seq], default=0) + 1) if seq else 1


def ensure_user(message_or_user) -> str:
    if hasattr(message_or_user, "from_user"):
        user = message_or_user.from_user
    else:
        user = message_or_user

    user_id = str(user.id)
    if user_id not in users:
        users[user_id] = {
            "user_id": user_id,
            "username": f"@{user.username}" if user.username else "Noma'lum",
            "first_name": user.first_name or "",
            "last_name": user.last_name or "",
            "balance": 0,
            "referrals_count": 0,
            "referred_by": None,
            "completed_earn_tasks": [],
            "confirmed_required_channels": [],
            "bonus_date": "",
            "language": "uz",
            "join_date": now_str(),
            "last_active": now_str(),
            "used_promo": [],
            "blocked": False,
            "notifications": True,
            "orders_count": 0,
            "subscription_bonus": False,
            "welcome_given": None,
        }
        save_db()
    else:
        # sync username / name changes
        new_username = f"@{user.username}" if user.username else "Noma'lum"
        changed = False
        if users[user_id].get("username") != new_username:
            users[user_id]["username"] = new_username
            changed = True
        if users[user_id].get("first_name") != (user.first_name or ""):
            users[user_id]["first_name"] = user.first_name or ""
            changed = True
        if users[user_id].get("last_name") != (user.last_name or ""):
            users[user_id]["last_name"] = user.last_name or ""
            changed = True
        if changed:
            save_db()
    return user_id


def safe_username(user_or_id) -> str:
    if isinstance(user_or_id, (int, str)):
        uid = str(user_or_id)
        val = users.get(uid, {}).get("username", "Noma'lum")
        if val and val != "Noma'lum":
            return val if val.startswith("@") else f"@{val}"
        return "Noma'lum"

    if getattr(user_or_id, "username", None):
        return f"@{user_or_id.username}"
    if getattr(user_or_id, "first_name", None):
        return user_or_id.first_name
    return "Noma'lum"


def user_blocked(user_id: str) -> bool:
    return users.get(user_id, {}).get("blocked", False)


def is_channel_member(channel_username: str, user_id: int) -> bool:
    try:
        member = bot.get_chat_member(channel_username, user_id)
        return member.status not in ["left", "kicked"]
    except Exception as e:
        logger.error(f"Obuna tekshirish xato {channel_username}: {e}")
        return False


def check_subscription(user_id: int) -> bool:
    required_channels = config.get("required_channels", [])
    for channel in required_channels:
        if not is_channel_member(channel["username"], user_id):
            return False
    return True


def register_confirmed_channels(uid: str, telegram_user_id: int):
    """Track how many unique users confirmed each required channel & auto-remove if threshold reached."""
    confirmed = users[uid].setdefault("confirmed_required_channels", [])
    required_channels = config.get("required_channels", [])
    to_remove = []
    changed = False
    for ch in required_channels:
        uname = ch["username"]
        if uname in confirmed:
            continue
        if is_channel_member(uname, telegram_user_id):
            confirmed.append(uname)
            ch["confirmed_count"] = int(ch.get("confirmed_count", 0)) + 1
            changed = True
            threshold = int(ch.get("auto_remove_at", 0) or 0)
            if threshold > 0 and ch["confirmed_count"] >= threshold:
                to_remove.append(uname)
    if to_remove:
        config["required_channels"] = [c for c in required_channels if c["username"] not in to_remove]
        for uname in to_remove:
            notify_admins(f"ℹ️ Majburiy kanal avtomatik olib tashlandi (limitga yetdi): {uname}")
        changed = True
    if changed:
        save_db()


def notify_admins(text: str):
    for admin_id in list(ADMINS.keys()):
        try:
            bot.send_message(int(admin_id), text)
        except Exception:
            pass


def subscription_required(func):
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        uid = ensure_user(message)
        users[uid]["last_active"] = now_str()
        if user_blocked(uid):
            bot.send_message(message.chat.id, "❌ Siz bloklangansiz.")
            return
        if not check_subscription(message.from_user.id):
            show_required_channels(message.chat.id)
            return
        return func(message, *args, **kwargs)
    return wrapper


def admin_required(func):
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        if not is_admin(message.from_user.id):
            return
        return func(message, *args, **kwargs)
    return wrapper


def superadmin_required(func):
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        if not is_superadmin(message.from_user.id):
            bot.send_message(message.chat.id, "❌ Bu amal faqat super admin uchun.")
            return
        return func(message, *args, **kwargs)
    return wrapper


# =====================================
# MENUS
# =====================================
def build_main_menu(is_admin_flag: bool = False):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    rows = [
        ["💸 Pul ishlash", "🎁 Kunlik bonus"],
        ["📊 Hisobim", "👥 Referal"],
        ["➕ Hisobni to'ldirish", "🛍 Xizmatlar"],
        ["🏆 Reyting", "🎟 Promokod"],
        ["⚙️ Sozlamalar"],
    ]
    for row in rows:
        kb.add(*row)
    if is_admin_flag:
        kb.add("👨‍💻 Admin panel")
    return kb


def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📊 Statistika", "📦 Buyurtmalar")
    kb.add("👤 Foydalanuvchilar", "📢 Reklama")
    kb.add("💳 To'lov (kartalar)", "🛠 Xizmatlar")
    kb.add("📝 Majburiy kanallar", "💼 Pul ishlash vazifalari")
    kb.add("🎟 Promokodlar", "💰 Referal/Bonuslar")
    kb.add("✉️ Matnlar", "👨‍💻 Adminlar")
    kb.add("⬅️ Asosiy menyu")
    return kb


def back_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("⬅️ Ortga")
    return kb


def show_required_channels(chat_id: int):
    markup = InlineKeyboardMarkup(row_width=1)
    for channel in config.get("required_channels", []):
        markup.add(
            InlineKeyboardButton(
                f"📢 {channel.get('title', channel['username'])}",
                url=f"https://t.me/{channel['username'].replace('@', '')}",
            )
        )
    markup.add(InlineKeyboardButton("✅ Tekshirish", callback_data="check_subs"))
    bot.send_message(chat_id, get_text("not_subscribed"), reply_markup=markup)


def create_order(kind: str, user_id: str, extra: Dict[str, Any]) -> int:
    order_id = new_id(orders)
    order = {
        "id": order_id,
        "kind": kind,
        "user_id": user_id,
        "status": "pending",
        "date": datetime.now().isoformat(),
    }
    order.update(extra)
    orders.append(order)
    save_db()
    return order_id


def find_order(order_id: int) -> Optional[Dict[str, Any]]:
    for order in orders:
        if order.get("id") == order_id:
            return order
    return None


def complete_order_stats(uid: str):
    users[uid]["orders_count"] = users[uid].get("orders_count", 0) + 1


# =====================================
# REFERRAL (simple, single level)
# =====================================
def add_referral(referrer_id: str, new_user_id: str) -> bool:
    try:
        if referrer_id == new_user_id:
            return False
        if referrer_id not in users or new_user_id not in users:
            return False
        if users[new_user_id].get("referred_by"):
            return False

        users[new_user_id]["referred_by"] = referrer_id
        users[referrer_id]["referrals_count"] = users[referrer_id].get("referrals_count", 0) + 1
        bonus = int(config.get("referral_bonus", 1000))
        users[referrer_id]["balance"] += bonus
        save_db()

        try:
            bot.send_message(
                int(referrer_id),
                f"👥 Sizga yangi referal qo'shildi!\n💰 Bonus: +{bonus} so'm\n👤 {safe_username(new_user_id)}",
            )
        except Exception:
            pass
        return True
    except Exception as e:
        logger.error(f"Referral xato: {e}")
        return False


# =====================================
# START
# =====================================
@bot.message_handler(commands=["start"])
def start(message):
    user_id = ensure_user(message)
    users[user_id]["last_active"] = now_str()

    if user_blocked(user_id):
        bot.send_message(message.chat.id, "❌ Siz bloklangansiz.")
        return

    if not check_subscription(message.from_user.id):
        show_required_channels(message.chat.id)
        return

    register_confirmed_channels(user_id, message.from_user.id)

    args = message.text.split(maxsplit=1)
    referrer_id = args[1].strip() if len(args) > 1 else None

    if users[user_id].get("welcome_given") is None:
        welcome_bonus = int(config.get("welcome_bonus", 100))
        users[user_id]["balance"] += welcome_bonus
        users[user_id]["welcome_given"] = True
        if referrer_id and referrer_id.isdigit() and referrer_id in users and referrer_id != user_id:
            add_referral(referrer_id, user_id)
        save_db()
        bot.send_message(
            message.chat.id,
            f"{get_text('welcome')}\n\n💰 Ro'yxatdan o'tish bonusi: +{welcome_bonus} so'm\n⚖️ Balans: {users[user_id]['balance']} so'm",
            reply_markup=build_main_menu(is_admin(message.from_user.id)),
        )
        return

    save_db()
    bot.send_message(
        message.chat.id,
        f"{get_text('welcome')}\n\n💰 Balans: {users[user_id]['balance']} so'm\n👥 Referallar: {users[user_id].get('referrals_count', 0)} ta",
        reply_markup=build_main_menu(is_admin(message.from_user.id)),
    )


@bot.callback_query_handler(func=lambda call: call.data == "check_subs")
def check_subs_callback(call):
    uid = ensure_user(call.from_user)
    if check_subscription(call.from_user.id):
        register_confirmed_channels(uid, call.from_user.id)
        bonus_text = ""
        if not users[uid].get("subscription_bonus", False):
            bonus = int(config.get("subscribe_bonus", 200))
            users[uid]["balance"] += bonus
            users[uid]["subscription_bonus"] = True
            save_db()
            bonus_text = f"\n\n{get_text('subscribe_bonus_text')} (+{bonus} so'm)"
        bot.answer_callback_query(call.id, "✅ Obuna tasdiqlandi")
        try:
            bot.edit_message_text(
                f"✅ Barcha kanallarga obuna bo'lgansiz!{bonus_text}",
                call.message.chat.id,
                call.message.message_id,
            )
        except Exception:
            pass
        bot.send_message(call.message.chat.id, "🔽 Asosiy menyu:", reply_markup=build_main_menu(is_admin(call.from_user.id)))
    else:
        bot.answer_callback_query(call.id, "❌ Hali barcha kanallarga obuna bo'lmagansiz")
        show_required_channels(call.message.chat.id)


# =====================================
# PROFILE / BONUS / REF
# =====================================
@bot.message_handler(func=lambda m: m.text == "📊 Hisobim")
@subscription_required
def profile(message):
    user_id = str(message.from_user.id)
    user = users[user_id]
    text = (
        f"👤 <b>Shaxsiy kabinet</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"📛 Username: {safe_username(message.from_user)}\n"
        f"📅 Ro'yxat: {user.get('join_date', 'Noma\'lum')}\n\n"
        f"💰 Balans: {user.get('balance', 0):,} so'm\n"
        f"👥 Referallar: {user.get('referrals_count', 0)} ta\n"
        f"📦 Buyurtmalar: {user.get('orders_count', 0)} ta"
    )
    bot.send_message(message.chat.id, text)


@bot.message_handler(func=lambda m: m.text == "🎁 Kunlik bonus")
@subscription_required
def daily_bonus(message):
    user_id = str(message.from_user.id)
    today = datetime.now().strftime("%Y-%m-%d")
    if users[user_id].get("bonus_date") == today:
        next_dt = datetime.strptime(today, "%Y-%m-%d") + timedelta(days=1)
        delta = next_dt - datetime.now()
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60
        bot.send_message(message.chat.id, f"❌ Bugun bonus olgansiz.\n⏰ Keyingi bonus: {hours} soat {minutes} daqiqadan so'ng")
        return

    min_bonus, max_bonus = config.get("daily_bonus_range", [100, 500])
    bonus = random.randint(int(min_bonus), int(max_bonus))
    users[user_id]["balance"] += bonus
    users[user_id]["bonus_date"] = today
    save_db()
    bot.send_message(message.chat.id, f"🎉 Kunlik bonus!\n💰 +{bonus} so'm")


@bot.message_handler(func=lambda m: m.text == "👥 Referal")
@subscription_required
def referral_menu(message):
    user_id = str(message.from_user.id)
    me = bot.get_me().username
    ref_link = f"https://t.me/{me}?start={user_id}"
    text = (
        f"👥 <b>Referal dasturi</b>\n\n"
        f"👥 Referallaringiz: {users[user_id].get('referrals_count', 0)} ta\n"
        f"💰 Har bir referal uchun bonus: {int(config.get('referral_bonus', 1000)):,} so'm\n\n"
        f"🔗 Havolangiz:\n<code>{ref_link}</code>"
    )
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📢 Do'stlarga yuborish", switch_inline_query=f"Taklif havolam: {ref_link}"))
    bot.send_message(message.chat.id, text, reply_markup=markup)


# =====================================
# LEADERBOARD
# =====================================
@bot.message_handler(func=lambda m: m.text == "🏆 Reyting")
@subscription_required
def leaderboard_menu(message):
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("👥 Referallar bo'yicha", callback_data="top_ref"))
    markup.add(InlineKeyboardButton("📦 Buyurtmalar bo'yicha", callback_data="top_orders"))
    markup.add(InlineKeyboardButton("💰 Balans bo'yicha", callback_data="top_balance"))
    bot.send_message(message.chat.id, "🏆 Reyting turini tanlang:", reply_markup=markup)


def _render_top(field: str, label: str, suffix: str):
    ranking = [(uid, u.get(field, 0)) for uid, u in users.items() if u.get(field, 0) > 0]
    ranking.sort(key=lambda x: x[1], reverse=True)
    medals = ["🥇", "🥈", "🥉"]
    if not ranking:
        return f"🏆 <b>{label}</b>\n\nHozircha ma'lumot yo'q"
    lines = [f"🏆 <b>{label}</b>"]
    for i, (uid, val) in enumerate(ranking[:10], start=1):
        prefix = medals[i - 1] if i <= 3 else f"{i}."
        lines.append(f"\n{prefix} {safe_username(uid)} — {val:,} {suffix}")
    return "\n".join(lines)


@bot.callback_query_handler(func=lambda c: c.data in ["top_ref", "top_orders", "top_balance"])
def leaderboard_callback(c):
    if c.data == "top_ref":
        text = _render_top("referrals_count", "TOP referallar", "ta")
    elif c.data == "top_orders":
        text = _render_top("orders_count", "TOP buyurtmalar", "ta")
    else:
        text = _render_top("balance", "TOP balans", "so'm")
    try:
        bot.edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=c.message.reply_markup)
    except Exception:
        bot.send_message(c.message.chat.id, text)
    bot.answer_callback_query(c.id)


# =====================================
# EARN TASKS (admin-managed, unified)
# =====================================
def _incomplete_tasks(uid: str):
    done = users[uid].get("completed_earn_tasks", [])
    return [t for t in config.get("earn_tasks", []) if t["id"] not in done]


@bot.message_handler(func=lambda m: m.text == "💸 Pul ishlash")
@subscription_required
def earn_menu(message):
    user_id = str(message.from_user.id)
    tasks_left = _incomplete_tasks(user_id)
    if not tasks_left:
        bot.send_message(message.chat.id, "✅ Hozircha barcha topshiriqlar bajarilgan yoki mavjud emas.")
        return
    show_earn_task(message.chat.id, tasks_left[0])


def show_earn_task(chat_id: int, task: Dict[str, Any]):
    kind_label = "📢 Kanal" if task["type"] == "channel" else "👁 Post"
    action_label = "➕ Obuna bo'lish" if task["type"] == "channel" else "👁 Ko'rish"
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(action_label, url=task["link"]),
        InlineKeyboardButton("✅ Tekshirish", callback_data=f"check_earn_{task['id']}"),
        InlineKeyboardButton("⏭ Keyingi", callback_data=f"skip_earn_{task['id']}"),
    )
    bot.send_message(chat_id, f"{kind_label}: {task.get('title', '')}\n{task['link']}\n\n💰 Mukofot: {task.get('reward', 0):,} so'm", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("check_earn_"))
def check_earn(c):
    uid = str(c.from_user.id)
    task_id = int(c.data.split("_")[-1])
    task = next((t for t in config.get("earn_tasks", []) if t["id"] == task_id), None)
    if not task:
        bot.answer_callback_query(c.id, "❌ Topshiriq topilmadi")
        return
    done = users[uid].setdefault("completed_earn_tasks", [])
    if task_id in done:
        bot.answer_callback_query(c.id, "❌ Bu topshiriq oldin bajarilgan")
        return
    if task["type"] == "channel":
        uname = task["link"].split("/")[-1]
        if not is_channel_member(f"@{uname}", c.from_user.id):
            bot.answer_callback_query(c.id, "❌ Hali obuna bo'lmagansiz")
            return
    done.append(task_id)
    reward = int(task.get("reward", 0))
    users[uid]["balance"] += reward
    save_db()
    bot.answer_callback_query(c.id, f"+{reward} so'm")
    remaining = _incomplete_tasks(uid)
    if remaining:
        show_earn_task(c.message.chat.id, remaining[0])
    try:
        bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=None)
    except Exception:
        pass
    if not remaining:
        bot.send_message(c.message.chat.id, "✅ Barcha topshiriqlar bajarildi")


@bot.callback_query_handler(func=lambda c: c.data.startswith("skip_earn_"))
def skip_earn(c):
    uid = str(c.from_user.id)
    current = int(c.data.split("_")[-1])
    remaining = [t for t in _incomplete_tasks(uid) if t["id"] != current]
    try:
        bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=None)
    except Exception:
        pass
    if not remaining:
        bot.answer_callback_query(c.id, "❌ Boshqa topshiriq yo'q")
        return
    show_earn_task(c.message.chat.id, remaining[0])


def unsubscribe_recheck_loop():
    """Periodically re-check channel-type earn tasks; deduct penalty if user unsubscribed."""
    while True:
        time.sleep(6 * 3600)
        try:
            channel_tasks = {t["id"]: t for t in config.get("earn_tasks", []) if t["type"] == "channel"}
            if not channel_tasks:
                continue
            for uid, u in list(users.items()):
                done = u.get("completed_earn_tasks", [])
                if not done:
                    continue
                for tid in list(done):
                    task = channel_tasks.get(tid)
                    if not task:
                        continue
                    uname = task["link"].split("/")[-1]
                    if not is_channel_member(f"@{uname}", int(uid)):
                        penalty = int(task.get("penalty", 0))
                        u["balance"] = max(0, u.get("balance", 0) - penalty)
                        done.remove(tid)
            save_db()
        except Exception as e:
            logger.error(f"Unsubscribe recheck xato: {e}")


threading.Thread(target=unsubscribe_recheck_loop, daemon=True).start()


# =====================================
# TOP-UP (manual card -> amount -> receipt -> payment channel)
# =====================================
@bot.message_handler(func=lambda m: m.text == "➕ Hisobni to'ldirish")
@subscription_required
def topup_balance(message):
    cards = config.get("payment_cards", [])
    if not cards:
        bot.send_message(message.chat.id, "❌ Hozircha to'lov kartasi mavjud emas. Admin bilan bog'laning.")
        return
    markup = InlineKeyboardMarkup(row_width=1)
    for card in cards:
        markup.add(InlineKeyboardButton(f"💳 {card.get('bank', '')} — {card.get('holder', '')}", callback_data=f"topup_card_{card['id']}"))
    bot.send_message(message.chat.id, "💳 To'lov qilish uchun kartani tanlang:", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("topup_card_"))
def topup_card_selected(c):
    uid = ensure_user(c.from_user)
    card_id = int(c.data.split("_")[-1])
    card = next((x for x in config.get("payment_cards", []) if x["id"] == card_id), None)
    if not card:
        bot.answer_callback_query(c.id, "❌ Karta topilmadi")
        return
    min_topup = int(config.get("min_topup", 5000))
    bot.answer_callback_query(c.id)
    bot.send_message(
        c.message.chat.id,
        f"💳 Karta: <code>{card['number']}</code>\n🏦 Bank: {card.get('bank', '')}\n👤 Egasi: {card.get('holder', '')}\n\n"
        f"💰 Kartaga pul o'tkazing va o'tkazgan summangizni kiriting (min: {min_topup:,} so'm):",
    )
    msg = bot.send_message(c.message.chat.id, "Summani kiriting:", reply_markup=back_menu())
    bot.register_next_step_handler(msg, process_topup_amount, card_id)


def process_topup_amount(message, card_id: int):
    if message.text == "⬅️ Ortga":
        bot.send_message(message.chat.id, "🔙 Orqaga", reply_markup=build_main_menu(is_admin(message.from_user.id)))
        return
    uid = str(message.from_user.id)
    try:
        amount = int(message.text.strip().replace(" ", ""))
    except Exception:
        msg = bot.send_message(message.chat.id, "❌ Faqat son kiriting:")
        bot.register_next_step_handler(msg, process_topup_amount, card_id)
        return
    min_topup = int(config.get("min_topup", 5000))
    if amount < min_topup:
        msg = bot.send_message(message.chat.id, f"❌ Minimal summa: {min_topup:,} so'm. Qaytadan kiriting:")
        bot.register_next_step_handler(msg, process_topup_amount, card_id)
        return
    users[uid]["pending_topup"] = {"card_id": card_id, "amount": amount}
    save_db()
    msg = bot.send_message(message.chat.id, "🧾 Endi to'lov chekini (skrinshot) rasm ko'rinishida yuboring:", reply_markup=back_menu())
    bot.register_next_step_handler(msg, process_topup_receipt)


def process_topup_receipt(message):
    if getattr(message, "text", None) == "⬅️ Ortga":
        bot.send_message(message.chat.id, "🔙 Orqaga", reply_markup=build_main_menu(is_admin(message.from_user.id)))
        return
    uid = str(message.from_user.id)
    pending = users[uid].get("pending_topup")
    if not pending:
        bot.send_message(message.chat.id, "❌ Faol so'rov topilmadi. Qaytadan boshlang.", reply_markup=build_main_menu(is_admin(message.from_user.id)))
        return
    if message.content_type != "photo":
        msg = bot.send_message(message.chat.id, "❌ Iltimos, chekni rasm (screenshot) shaklida yuboring:")
        bot.register_next_step_handler(msg, process_topup_receipt)
        return

    receipt_file_id = message.photo[-1].file_id
    order_id = create_order("topup", uid, {
        "amount": pending["amount"],
        "card_id": pending["card_id"],
        "receipt_file_id": receipt_file_id,
    })
    users[uid].pop("pending_topup", None)
    save_db()
    bot.send_message(message.chat.id, f"✅ So'rovingiz qabul qilindi.\n🆔 Order: #{order_id}\n⏳ Admin tomonidan tekshirilmoqda.", reply_markup=build_main_menu(is_admin(message.from_user.id)))

    caption = (
        f"🆕 <b>Yangi to'lov so'rovi</b>\n\n"
        f"🆔 Order: #{order_id}\n"
        f"👤 {safe_username(message.from_user)} | <code>{uid}</code>\n"
        f"💰 Summa: {pending['amount']:,} so'm\n"
        f"📅 {now_str()}"
    )
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🔄 Ishlov berilmoqda", callback_data=f"payadm_process_{order_id}"))
    kb.add(
        InlineKeyboardButton("✅ Bajarildi", callback_data=f"payadm_approve_{order_id}"),
        InlineKeyboardButton("❌ Rad etish", callback_data=f"payadm_reject_{order_id}"),
    )

    channel_id = config.get("payment_channel_id")
    sent = False
    if channel_id:
        try:
            bot.send_photo(channel_id, receipt_file_id, caption=caption, reply_markup=kb)
            sent = True
        except Exception as e:
            logger.error(f"Payment kanaliga yuborishda xato: {e}")
    if not sent:
        for admin_id in list(ADMINS.keys()):
            try:
                bot.send_photo(int(admin_id), receipt_file_id, caption=caption, reply_markup=kb)
            except Exception:
                pass


@bot.callback_query_handler(func=lambda c: c.data.startswith("payadm_"))
def payadm_action(c):
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id, "❌ Ruxsat yo'q")
        return
    parts = c.data.split("_")
    action = parts[1]
    order_id = int(parts[2])
    order = find_order(order_id)
    if not order or order.get("kind") != "topup":
        bot.answer_callback_query(c.id, "❌ Buyurtma topilmadi")
        return

    if action == "process":
        if order.get("status") not in ("pending",):
            bot.answer_callback_query(c.id, "❌ Allaqachon ko'rilgan")
            return
        order["status"] = "processing"
        order["handled_by"] = safe_username(c.from_user)
        save_db()
        bot.answer_callback_query(c.id, "🔄 Siz ishlov berayotgan deb belgilandi")
        try:
            new_caption = (c.message.caption or "") + f"\n\n🔄 Ishlov berilmoqda: {order['handled_by']}"
            bot.edit_message_caption(new_caption, c.message.chat.id, c.message.message_id, reply_markup=c.message.reply_markup)
        except Exception:
            pass
        return

    if order.get("status") == "completed" or order.get("status") == "rejected":
        bot.answer_callback_query(c.id, "❌ Buyurtma allaqachon yakunlangan")
        return

    if action == "approve":
        order["status"] = "completed"
        order["approved_by"] = safe_username(c.from_user)
        order["completed_date"] = datetime.now().isoformat()
        uid = order["user_id"]
        users[uid]["balance"] += int(order.get("amount", 0))
        complete_order_stats(uid)
        save_db()
        try:
            bot.send_message(int(uid), f"✅ To'lovingiz tasdiqlandi.\n💰 +{order.get('amount', 0):,} so'm balansingizga qo'shildi.")
        except Exception:
            pass
        bot.answer_callback_query(c.id, "✅ Tasdiqlandi")
        try:
            new_caption = (c.message.caption or "") + f"\n\n✅ Bajarildi: {order['approved_by']}"
            bot.edit_message_caption(new_caption, c.message.chat.id, c.message.message_id, reply_markup=None)
        except Exception:
            pass
    elif action == "reject":
        order["status"] = "rejected"
        order["rejected_by"] = safe_username(c.from_user)
        save_db()
        try:
            bot.send_message(int(order["user_id"]), "❌ To'lovingiz rad etildi. Savol bo'lsa admin bilan bog'laning.")
        except Exception:
            pass
        bot.answer_callback_query(c.id, "❌ Rad etildi")
        try:
            new_caption = (c.message.caption or "") + f"\n\n❌ Rad etildi: {order['rejected_by']}"
            bot.edit_message_caption(new_caption, c.message.chat.id, c.message.message_id, reply_markup=None)
        except Exception:
            pass


# =====================================
# SERVICES / SHOP (admin managed)
# =====================================
def _service_categories() -> List[str]:
    cats = []
    for s in config.get("services", []):
        if s["category"] not in cats:
            cats.append(s["category"])
    return cats


@bot.message_handler(func=lambda m: m.text == "🛍 Xizmatlar")
@subscription_required
def shop(message):
    cats = _service_categories()
    if not cats:
        bot.send_message(message.chat.id, "❌ Hozircha xizmatlar mavjud emas.")
        return
    markup = InlineKeyboardMarkup(row_width=1)
    for cat in cats:
        markup.add(InlineKeyboardButton(f"📦 {cat}", callback_data=f"shopcat_{cat}"))
    bot.send_message(message.chat.id, "🛍 Do'kon bo'limi:", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("shopcat_"))
def shop_category(c):
    category = c.data.split("_", 1)[1]
    items = [s for s in config.get("services", []) if s["category"] == category]
    markup = InlineKeyboardMarkup(row_width=1)
    for s in items:
        markup.add(InlineKeyboardButton(f"{s['name']} — {s['price']:,} so'm", callback_data=f"buyserv_{s['id']}"))
    markup.add(InlineKeyboardButton("⬅️ Ortga", callback_data="shop_back"))
    try:
        bot.edit_message_text(f"🛍 {category}", c.message.chat.id, c.message.message_id, reply_markup=markup)
    except Exception:
        bot.send_message(c.message.chat.id, f"🛍 {category}", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data == "shop_back")
def shop_back(c):
    cats = _service_categories()
    markup = InlineKeyboardMarkup(row_width=1)
    for cat in cats:
        markup.add(InlineKeyboardButton(f"📦 {cat}", callback_data=f"shopcat_{cat}"))
    try:
        bot.edit_message_text("🛍 Do'kon bo'limi:", c.message.chat.id, c.message.message_id, reply_markup=markup)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data.startswith("buyserv_"))
def buy_service(c):
    service_id = int(c.data.split("_")[-1])
    service = next((s for s in config.get("services", []) if s["id"] == service_id), None)
    if not service:
        bot.answer_callback_query(c.id, "❌ Xizmat topilmadi")
        return
    uid = str(c.from_user.id)
    if users[uid]["balance"] < service["price"]:
        bot.answer_callback_query(c.id, "❌ Balans yetarli emas")
        return
    users[uid]["pending_purchase"] = {"service_id": service_id}
    save_db()
    bot.answer_callback_query(c.id)
    msg = bot.send_message(c.message.chat.id, f"📝 {service['name']} uchun ID yoki username kiriting:")
    bot.register_next_step_handler(msg, process_purchase_id)


def process_purchase_id(message):
    uid = str(message.from_user.id)
    pending = users[uid].get("pending_purchase")
    if not pending:
        bot.send_message(message.chat.id, "❌ Faol buyurtma topilmadi")
        return
    service = next((s for s in config.get("services", []) if s["id"] == pending["service_id"]), None)
    if not service:
        bot.send_message(message.chat.id, "❌ Xizmat topilmadi")
        users[uid].pop("pending_purchase", None)
        save_db()
        return
    if users[uid]["balance"] < service["price"]:
        bot.send_message(message.chat.id, "❌ Balans yetarli emas", reply_markup=build_main_menu(is_admin(message.from_user.id)))
        users[uid].pop("pending_purchase", None)
        save_db()
        return
    game_id = message.text.strip()
    users[uid]["balance"] -= service["price"]
    order_id = create_order("shop", uid, {
        "service_name": service["name"],
        "amount": service["price"],
        "game_id": game_id,
    })
    users[uid].pop("pending_purchase", None)
    save_db()
    bot.send_message(message.chat.id, f"✅ Buyurtma qabul qilindi.\n🆔 Order: #{order_id}\n📦 {service['name']}\n💰 {service['price']:,} so'm", reply_markup=build_main_menu(is_admin(message.from_user.id)))
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Bajarildi", callback_data=f"approve_order_{order_id}"),
        InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_order_{order_id}"),
    )
    for admin_id in list(ADMINS.keys()):
        try:
            bot.send_message(int(admin_id), f"🛒 Yangi buyurtma #{order_id}\n👤 {safe_username(message.from_user)}\n🆔 <code>{uid}</code>\n📦 {service['name']}\n💰 {service['price']:,} so'm\n🎮 ID: {game_id}", reply_markup=kb)
        except Exception as e:
            logger.error(f"Shop admin xabar xato: {e}")


# =====================================
# ORDERS (generic shop approve/reject) / ADMIN STATS
# =====================================
def get_admin_stats() -> Dict[str, Any]:
    today = datetime.now().strftime("%Y-%m-%d")
    return {
        "total_users": len(users),
        "new_today": sum(1 for u in users.values() if str(u.get("join_date", "")).startswith(today)),
        "active_today": sum(1 for u in users.values() if str(u.get("last_active", "")).startswith(today)),
        "total_balance": sum(int(u.get("balance", 0)) for u in users.values()),
        "pending_orders": sum(1 for o in orders if o.get("status") == "pending"),
    }


@bot.message_handler(func=lambda m: m.text == "👨‍💻 Admin panel" and is_admin(m.from_user.id))
def admin_panel(message):
    s = get_admin_stats()
    bot.send_message(
        message.chat.id,
        f"👨‍💻 <b>Admin panel</b>\n\n👥 Foydalanuvchilar: {s['total_users']}\n🆕 Bugun: {s['new_today']}\n⚡ Faol: {s['active_today']}\n💰 Jami balans: {s['total_balance']:,} so'm\n📦 Pending: {s['pending_orders']}",
        reply_markup=admin_menu(),
    )


@bot.message_handler(func=lambda m: m.text == "📊 Statistika" and is_admin(m.from_user.id))
@admin_required
def admin_stats(message):
    s = get_admin_stats()
    total_refs = sum(u.get("referrals_count", 0) for u in users.values())
    completed_orders = sum(1 for o in orders if o.get("status") == "completed")
    total_payments = sum(int(o.get("amount", 0)) for o in orders if o.get("kind") == "topup" and o.get("status") == "completed")
    bot.send_message(
        message.chat.id,
        f"📊 <b>Batafsil statistika</b>\n\n👥 Jami user: {s['total_users']}\n👥 Jami referal: {total_refs}\n💰 Jami balans: {s['total_balance']:,}\n📥 Jami to'lovlar: {total_payments:,}\n✅ Bajarilgan buyurtmalar: {completed_orders}\n⏳ Pending: {s['pending_orders']}",
    )


@bot.message_handler(func=lambda m: m.text == "📦 Buyurtmalar" and is_admin(m.from_user.id))
@admin_required
def admin_orders(message):
    pending = [o for o in orders if o.get("status") == "pending"]
    if not pending:
        bot.send_message(message.chat.id, "✅ Pending buyurtmalar yo'q", reply_markup=admin_menu())
        return
    text = [f"📦 <b>Pending buyurtmalar ({len(pending)})</b>"]
    markup = InlineKeyboardMarkup(row_width=1)
    for order in pending[:20]:
        text.append(f"\n#{order['id']} | {order.get('kind')} | {order.get('amount', 0)} so'm | user {order['user_id']}")
        markup.add(InlineKeyboardButton(f"Buyurtma #{order['id']}", callback_data=f"view_order_{order['id']}"))
    bot.send_message(message.chat.id, "\n".join(text), reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("view_order_"))
def view_order(c):
    if not is_admin(c.from_user.id):
        return
    order_id = int(c.data.split("_")[-1])
    order = find_order(order_id)
    if not order:
        bot.answer_callback_query(c.id, "❌ Buyurtma topilmadi")
        return
    text = (
        f"📦 <b>Buyurtma #{order['id']}</b>\n\n"
        f"Turi: {order.get('kind')}\n"
        f"User: {order.get('user_id')}\n"
        f"Miqdor: {order.get('amount', 0)} so'm\n"
        f"Holat: {order.get('status')}\n"
        f"Sana: {order.get('date')}"
    )
    if order.get("game_id"):
        text += f"\nGame ID: {order['game_id']}"
    markup = InlineKeyboardMarkup(row_width=2)
    if order.get("status") == "pending" and order.get("kind") == "shop":
        markup.add(
            InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_order_{order_id}"),
            InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_order_{order_id}"),
        )
    bot.edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("approve_order_"))
def approve_order(c):
    if not is_admin(c.from_user.id):
        return
    order_id = int(c.data.split("_")[-1])
    order = find_order(order_id)
    if not order:
        bot.answer_callback_query(c.id, "❌ Buyurtma topilmadi")
        return
    if order.get("status") != "pending":
        bot.answer_callback_query(c.id, "❌ Buyurtma allaqachon ko'rilgan")
        return
    order["status"] = "completed"
    order["approved_by"] = c.from_user.id
    order["approved_date"] = datetime.now().isoformat()
    complete_order_stats(order["user_id"])
    save_db()
    try:
        bot.send_message(int(order["user_id"]), f"✅ Buyurtmangiz bajarildi!\n🆔 Order: #{order_id}")
    except Exception:
        pass
    bot.answer_callback_query(c.id, "✅ Tasdiqlandi")
    try:
        bot.edit_message_text(f"✅ Buyurtma #{order_id} tasdiqlandi", c.message.chat.id, c.message.message_id)
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data.startswith("reject_order_"))
def reject_order(c):
    if not is_admin(c.from_user.id):
        return
    order_id = int(c.data.split("_")[-1])
    order = find_order(order_id)
    if not order:
        bot.answer_callback_query(c.id, "❌ Buyurtma topilmadi")
        return
    if order.get("status") != "pending":
        bot.answer_callback_query(c.id, "❌ Buyurtma allaqachon ko'rilgan")
        return
    order["status"] = "rejected"
    order["rejected_by"] = c.from_user.id
    order["rejected_date"] = datetime.now().isoformat()
    users[order["user_id"]]["balance"] += int(order.get("amount", 0))
    save_db()
    try:
        bot.send_message(int(order["user_id"]), f"❌ Buyurtma rad etildi.\n💰 {order.get('amount', 0):,} so'm balansga qaytarildi")
    except Exception:
        pass
    bot.answer_callback_query(c.id, "❌ Rad etildi")
    try:
        bot.edit_message_text(f"❌ Buyurtma #{order_id} rad etildi", c.message.chat.id, c.message.message_id)
    except Exception:
        pass


# =====================================
# ADMIN: USERS
# =====================================
@bot.message_handler(func=lambda m: m.text == "👤 Foydalanuvchilar" and is_admin(m.from_user.id))
@admin_required
def admin_users(message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("🔍 Foydalanuvchi qidirish", "⬅️ Ortga")
    bot.send_message(message.chat.id, "👤 Foydalanuvchilar bo'limi", reply_markup=kb)


@bot.message_handler(func=lambda m: m.text == "🔍 Foydalanuvchi qidirish" and is_admin(m.from_user.id))
@admin_required
def search_user(message):
    msg = bot.send_message(message.chat.id, "ID yoki username kiriting:", reply_markup=back_menu())
    bot.register_next_step_handler(msg, process_user_search)


def process_user_search(message):
    if message.text == "⬅️ Ortga":
        bot.send_message(message.chat.id, "🔙 Orqaga", reply_markup=admin_menu())
        return
    query = message.text.strip().lower().replace("@", "")
    found = []
    if query.isdigit() and query in users:
        found = [query]
    else:
        for uid, user in users.items():
            username = str(user.get("username", "")).lower().replace("@", "")
            if query in username:
                found.append(uid)
            if len(found) >= 10:
                break
    if not found:
        bot.send_message(message.chat.id, "❌ Topilmadi", reply_markup=admin_menu())
        return
    if len(found) == 1:
        return show_user_info(message.chat.id, found[0])
    markup = InlineKeyboardMarkup(row_width=1)
    for uid in found:
        markup.add(InlineKeyboardButton(f"{safe_username(uid)} | {users[uid].get('balance', 0):,} so'm", callback_data=f"admin_show_user_{uid}"))
    bot.send_message(message.chat.id, "Topilgan foydalanuvchilar:", reply_markup=markup)


def show_user_info(chat_id: int, user_id: str):
    user = users[user_id]
    text = (
        f"👤 <b>Foydalanuvchi</b>\n\n"
        f"ID: <code>{user_id}</code>\n"
        f"Username: {user.get('username', 'Noma\'lum')}\n"
        f"Ism: {user.get('first_name', '')}\n"
        f"Balans: {user.get('balance', 0):,} so'm\n"
        f"Referallar: {user.get('referrals_count', 0)}\n"
        f"Buyurtmalar: {user.get('orders_count', 0)}\n"
        f"Blocked: {'✅' if user.get('blocked') else '❌'}"
    )
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("💰 Balansni o'zgartirish", callback_data=f"admin_edit_balance_{user_id}"))
    markup.add(InlineKeyboardButton("🔒 Block/Unblock", callback_data=f"admin_toggle_block_{user_id}"))
    bot.send_message(chat_id, text, reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_show_user_"))
def admin_show_user(c):
    if not is_admin(c.from_user.id):
        return
    show_user_info(c.message.chat.id, c.data.split("_")[-1])


@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_edit_balance_"))
def admin_edit_balance(c):
    if not is_admin(c.from_user.id):
        return
    user_id = c.data.split("_")[-1]
    msg = bot.send_message(c.message.chat.id, f"Yangi balansni kiriting ({users[user_id].get('balance', 0):,}):")
    bot.register_next_step_handler(msg, lambda m: process_balance_edit(m, user_id))


def process_balance_edit(message, user_id: str):
    try:
        amount = int(message.text.strip())
    except Exception:
        bot.send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
        return
    old = users[user_id].get("balance", 0)
    users[user_id]["balance"] = amount
    save_db()
    bot.send_message(message.chat.id, f"✅ O'zgartirildi: {old:,} -> {amount:,}", reply_markup=admin_menu())
    try:
        bot.send_message(int(user_id), f"💰 Admin balansingizni o'zgartirdi.\nEski: {old:,}\nYangi: {amount:,}")
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_toggle_block_"))
def admin_toggle_block(c):
    if not is_admin(c.from_user.id):
        return
    user_id = c.data.split("_")[-1]
    users[user_id]["blocked"] = not users[user_id].get("blocked", False)
    save_db()
    state = "bloklandi" if users[user_id]["blocked"] else "blokdan chiqarildi"
    bot.answer_callback_query(c.id, f"✅ {state}")
    try:
        bot.send_message(int(user_id), f"ℹ️ Siz {state}")
    except Exception:
        pass
    show_user_info(c.message.chat.id, user_id)


# =====================================
# ADMIN: PAYMENT CARDS
# =====================================
@bot.message_handler(func=lambda m: m.text == "💳 To'lov (kartalar)" and is_admin(m.from_user.id))
@admin_required
def manage_cards(message):
    cards = config.get("payment_cards", [])
    text = ["💳 <b>To'lov kartalari</b>"]
    for c_ in cards:
        text.append(f"\n#{c_['id']} {c_['bank']} — <code>{c_['number']}</code> — {c_['holder']}")
    if not cards:
        text.append("\nHozircha karta yo'q")
    channel = config.get("payment_channel_id")
    text.append(f"\n\n📢 To'lov kanali: {channel if channel else 'sozlanmagan'}")
    text.append(f"💵 Minimal to'ldirish: {int(config.get('min_topup', 5000)):,} so'm")
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("➕ Karta qo'shish", callback_data="add_card"))
    if cards:
        markup.add(InlineKeyboardButton("❌ Kartani o'chirish", callback_data="remove_card"))
    markup.add(InlineKeyboardButton("📢 To'lov kanalini sozlash", callback_data="set_payment_channel"))
    markup.add(InlineKeyboardButton("💵 Minimal summani sozlash", callback_data="set_min_topup"))
    bot.send_message(message.chat.id, "\n".join(text), reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data == "add_card")
def add_card(c):
    if not is_admin(c.from_user.id):
        return
    msg = bot.send_message(c.message.chat.id, "💳 Karta raqamini kiriting:")
    bot.register_next_step_handler(msg, process_add_card_number)


def process_add_card_number(message):
    number = message.text.strip()
    msg = bot.send_message(message.chat.id, "🏦 Bank nomini kiriting:")
    bot.register_next_step_handler(msg, process_add_card_bank, number)


def process_add_card_bank(message, number: str):
    bank = message.text.strip()
    msg = bot.send_message(message.chat.id, "👤 Karta egasining ismini kiriting:")
    bot.register_next_step_handler(msg, process_add_card_holder, number, bank)


def process_add_card_holder(message, number: str, bank: str):
    holder = message.text.strip()
    cards = config.setdefault("payment_cards", [])
    cards.append({"id": new_id(cards), "number": number, "bank": bank, "holder": holder})
    save_db()
    bot.send_message(message.chat.id, "✅ Karta qo'shildi", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data == "remove_card")
def remove_card(c):
    if not is_admin(c.from_user.id):
        return
    cards = config.get("payment_cards", [])
    markup = InlineKeyboardMarkup(row_width=1)
    for card in cards:
        markup.add(InlineKeyboardButton(f"{card['bank']} — {card['number']}", callback_data=f"delete_card_{card['id']}"))
    bot.send_message(c.message.chat.id, "O'chirish uchun tanlang:", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("delete_card_"))
def delete_card(c):
    if not is_admin(c.from_user.id):
        return
    card_id = int(c.data.split("_")[-1])
    config["payment_cards"] = [x for x in config.get("payment_cards", []) if x["id"] != card_id]
    save_db()
    bot.answer_callback_query(c.id, "✅ O'chirildi")


@bot.callback_query_handler(func=lambda c: c.data == "set_payment_channel")
def set_payment_channel(c):
    if not is_admin(c.from_user.id):
        return
    msg = bot.send_message(c.message.chat.id, "📢 To'lov kanalidan istalgan xabarni forward qiling, yoki kanal ID sini yuboring (masalan -1001234567890). Bot shu kanalda admin bo'lishi shart.")
    bot.register_next_step_handler(msg, process_set_payment_channel)


def process_set_payment_channel(message):
    chat_id = None
    if getattr(message, "forward_from_chat", None):
        chat_id = message.forward_from_chat.id
    else:
        try:
            chat_id = int(message.text.strip())
        except Exception:
            pass
    if not chat_id:
        bot.send_message(message.chat.id, "❌ Kanal aniqlanmadi", reply_markup=admin_menu())
        return
    config["payment_channel_id"] = chat_id
    save_db()
    try:
        bot.send_message(chat_id, "✅ Bu kanal endi to'lov so'rovlari uchun sozlandi.")
    except Exception:
        pass
    bot.send_message(message.chat.id, "✅ To'lov kanali saqlandi", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data == "set_min_topup")
def set_min_topup(c):
    if not is_admin(c.from_user.id):
        return
    msg = bot.send_message(c.message.chat.id, "💵 Minimal to'ldirish summasini kiriting:")
    bot.register_next_step_handler(msg, process_set_min_topup)


def process_set_min_topup(message):
    try:
        amount = int(message.text.strip())
    except Exception:
        bot.send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
        return
    config["min_topup"] = amount
    save_db()
    bot.send_message(message.chat.id, "✅ Saqlandi", reply_markup=admin_menu())


# =====================================
# ADMIN: SERVICES (shop management)
# =====================================
@bot.message_handler(func=lambda m: m.text == "🛠 Xizmatlar" and is_admin(m.from_user.id))
@admin_required
def manage_services(message):
    services = config.get("services", [])
    text = ["🛠 <b>Xizmatlar</b>"]
    for s in services:
        text.append(f"\n#{s['id']} [{s['category']}] {s['name']} — {s['price']:,} so'm")
    if not services:
        text.append("\nHozircha xizmat yo'q")
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("➕ Xizmat qo'shish", callback_data="add_service"))
    if services:
        markup.add(InlineKeyboardButton("✏️ Narxni tahrirlash", callback_data="edit_service_price"))
        markup.add(InlineKeyboardButton("❌ Xizmatni o'chirish", callback_data="remove_service"))
    bot.send_message(message.chat.id, "\n".join(text), reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data == "add_service")
def add_service(c):
    if not is_admin(c.from_user.id):
        return
    msg = bot.send_message(c.message.chat.id, "📦 Kategoriya nomini kiriting (masalan: UC, Premium, Stars):")
    bot.register_next_step_handler(msg, process_add_service_category)


def process_add_service_category(message):
    category = message.text.strip()
    msg = bot.send_message(message.chat.id, "📝 Xizmat nomini kiriting:")
    bot.register_next_step_handler(msg, process_add_service_name, category)


def process_add_service_name(message, category: str):
    name = message.text.strip()
    msg = bot.send_message(message.chat.id, "💰 Narxini kiriting (so'm):")
    bot.register_next_step_handler(msg, process_add_service_price, category, name)


def process_add_service_price(message, category: str, name: str):
    try:
        price = int(message.text.strip())
    except Exception:
        bot.send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
        return
    services = config.setdefault("services", [])
    services.append({"id": new_id(services), "category": category, "name": name, "price": price})
    save_db()
    bot.send_message(message.chat.id, "✅ Xizmat qo'shildi", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data == "edit_service_price")
def edit_service_price(c):
    if not is_admin(c.from_user.id):
        return
    services = config.get("services", [])
    markup = InlineKeyboardMarkup(row_width=1)
    for s in services:
        markup.add(InlineKeyboardButton(f"{s['name']} ({s['price']:,})", callback_data=f"editprice_{s['id']}"))
    bot.send_message(c.message.chat.id, "Tahrirlash uchun tanlang:", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("editprice_"))
def editprice(c):
    if not is_admin(c.from_user.id):
        return
    service_id = int(c.data.split("_")[-1])
    msg = bot.send_message(c.message.chat.id, "💰 Yangi narxni kiriting:")
    bot.register_next_step_handler(msg, process_editprice, service_id)


def process_editprice(message, service_id: int):
    try:
        price = int(message.text.strip())
    except Exception:
        bot.send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
        return
    for s in config.get("services", []):
        if s["id"] == service_id:
            s["price"] = price
    save_db()
    bot.send_message(message.chat.id, "✅ Saqlandi", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data == "remove_service")
def remove_service(c):
    if not is_admin(c.from_user.id):
        return
    services = config.get("services", [])
    markup = InlineKeyboardMarkup(row_width=1)
    for s in services:
        markup.add(InlineKeyboardButton(f"{s['name']}", callback_data=f"delservice_{s['id']}"))
    bot.send_message(c.message.chat.id, "O'chirish uchun tanlang:", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("delservice_"))
def delservice(c):
    if not is_admin(c.from_user.id):
        return
    service_id = int(c.data.split("_")[-1])
    config["services"] = [s for s in config.get("services", []) if s["id"] != service_id]
    save_db()
    bot.answer_callback_query(c.id, "✅ O'chirildi")


# =====================================
# ADMIN: REQUIRED CHANNELS
# =====================================
@bot.message_handler(func=lambda m: m.text == "📝 Majburiy kanallar" and is_admin(m.from_user.id))
@admin_required
def manage_required_channels(message):
    required = config.get("required_channels", [])
    lines = ["🔐 Majburiy kanallar"]
    for i, ch in enumerate(required, start=1):
        thr = ch.get("auto_remove_at", 0) or 0
        thr_text = f"{ch.get('confirmed_count', 0)}/{thr}" if thr else "cheklanmagan"
        lines.append(f"{i}. {ch.get('title')} - {ch.get('username')} (avto-o'chirish: {thr_text})")
    if not required:
        lines.append("Hozircha kanal yo'q")
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("➕ Qo'shish", callback_data="add_required_channel"))
    if required:
        markup.add(InlineKeyboardButton("❌ O'chirish", callback_data="remove_required_channel"))
        markup.add(InlineKeyboardButton("🔢 Avto-o'chirish limitini sozlash", callback_data="set_autoremove"))
    bot.send_message(message.chat.id, "\n".join(lines), reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data == "add_required_channel")
def add_required_channel(c):
    if not is_admin(c.from_user.id):
        return
    msg = bot.send_message(c.message.chat.id, "Format: @username - Title")
    bot.register_next_step_handler(msg, process_add_required_channel)


def process_add_required_channel(message):
    raw = message.text.strip()
    parts = raw.split(" - ", 1)
    if len(parts) != 2:
        bot.send_message(message.chat.id, "❌ Format noto'g'ri", reply_markup=admin_menu())
        return
    username, title = parts[0].strip(), parts[1].strip()
    if not username.startswith("@"):
        username = "@" + username
    config.setdefault("required_channels", []).append({"username": username, "title": title, "auto_remove_at": 0, "confirmed_count": 0})
    save_db()
    bot.send_message(message.chat.id, "✅ Qo'shildi", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data == "remove_required_channel")
def remove_required_channel(c):
    if not is_admin(c.from_user.id):
        return
    required = config.get("required_channels", [])
    markup = InlineKeyboardMarkup(row_width=1)
    for i, ch in enumerate(required):
        markup.add(InlineKeyboardButton(f"{ch['title']}", callback_data=f"delreqch_{i}"))
    bot.send_message(c.message.chat.id, "O'chirish uchun tanlang:", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("delreqch_"))
def delreqch(c):
    if not is_admin(c.from_user.id):
        return
    idx = int(c.data.split("_")[-1])
    required = config.get("required_channels", [])
    if 0 <= idx < len(required):
        required.pop(idx)
        config["required_channels"] = required
        save_db()
    bot.answer_callback_query(c.id, "✅ O'chirildi")


@bot.callback_query_handler(func=lambda c: c.data == "set_autoremove")
def set_autoremove(c):
    if not is_admin(c.from_user.id):
        return
    required = config.get("required_channels", [])
    markup = InlineKeyboardMarkup(row_width=1)
    for i, ch in enumerate(required):
        markup.add(InlineKeyboardButton(f"{ch['title']}", callback_data=f"autoremove_{i}"))
    bot.send_message(c.message.chat.id, "Qaysi kanal uchun limit belgilaysiz?", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("autoremove_"))
def autoremove_pick(c):
    if not is_admin(c.from_user.id):
        return
    idx = int(c.data.split("_")[-1])
    msg = bot.send_message(c.message.chat.id, "Nechta tasdiqlangan obunachidan keyin kanal avtomatik o'chirilsin? (0 = cheksiz):")
    bot.register_next_step_handler(msg, process_autoremove, idx)


def process_autoremove(message, idx: int):
    try:
        threshold = int(message.text.strip())
    except Exception:
        bot.send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
        return
    required = config.get("required_channels", [])
    if 0 <= idx < len(required):
        required[idx]["auto_remove_at"] = threshold
        save_db()
    bot.send_message(message.chat.id, "✅ Saqlandi", reply_markup=admin_menu())


# =====================================
# ADMIN: EARN TASKS
# =====================================
@bot.message_handler(func=lambda m: m.text == "💼 Pul ishlash vazifalari" and is_admin(m.from_user.id))
@admin_required
def manage_earn_tasks(message):
    tasks = config.get("earn_tasks", [])
    lines = ["💼 <b>Pul ishlash vazifalari</b>"]
    for t in tasks:
        lines.append(f"\n#{t['id']} [{t['type']}] {t.get('title','')} — mukofot: {t.get('reward',0):,}, jarima: {t.get('penalty',0):,}")
    if not tasks:
        lines.append("\nHozircha vazifa yo'q")
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("➕ Vazifa qo'shish", callback_data="add_earn_task"))
    if tasks:
        markup.add(InlineKeyboardButton("❌ Vazifani o'chirish", callback_data="remove_earn_task"))
    bot.send_message(message.chat.id, "\n".join(lines), reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data == "add_earn_task")
def add_earn_task(c):
    if not is_admin(c.from_user.id):
        return
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📢 Kanal", callback_data="earntype_channel"),
        InlineKeyboardButton("👁 Post", callback_data="earntype_post"),
    )
    bot.send_message(c.message.chat.id, "Vazifa turini tanlang:", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("earntype_"))
def earntype_pick(c):
    if not is_admin(c.from_user.id):
        return
    task_type = c.data.split("_")[-1]
    msg = bot.send_message(c.message.chat.id, "Sarlavha (nom) kiriting:")
    bot.register_next_step_handler(msg, process_earn_title, task_type)


def process_earn_title(message, task_type: str):
    title = message.text.strip()
    msg = bot.send_message(message.chat.id, "Link kiriting (https://t.me/...):")
    bot.register_next_step_handler(msg, process_earn_link, task_type, title)


def process_earn_link(message, task_type: str, title: str):
    link = message.text.strip()
    msg = bot.send_message(message.chat.id, "💰 Mukofot summasini kiriting (bajarganda beriladi):")
    bot.register_next_step_handler(msg, process_earn_reward, task_type, title, link)


def process_earn_reward(message, task_type: str, title: str, link: str):
    try:
        reward = int(message.text.strip())
    except Exception:
        bot.send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
        return
    msg = bot.send_message(message.chat.id, "⚠️ Agar kanal bo'lsa: keyinchalik obunadan chiqib ketsa qancha balansdan ayiriladi? (0 = ayirilmasin):")
    bot.register_next_step_handler(msg, process_earn_penalty, task_type, title, link, reward)


def process_earn_penalty(message, task_type: str, title: str, link: str, reward: int):
    try:
        penalty = int(message.text.strip())
    except Exception:
        bot.send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
        return
    tasks = config.setdefault("earn_tasks", [])
    tasks.append({"id": new_id(tasks), "type": task_type, "title": title, "link": link, "reward": reward, "penalty": penalty})
    save_db()
    bot.send_message(message.chat.id, "✅ Vazifa qo'shildi", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data == "remove_earn_task")
def remove_earn_task(c):
    if not is_admin(c.from_user.id):
        return
    tasks = config.get("earn_tasks", [])
    markup = InlineKeyboardMarkup(row_width=1)
    for t in tasks:
        markup.add(InlineKeyboardButton(f"{t.get('title','')}", callback_data=f"delearntask_{t['id']}"))
    bot.send_message(c.message.chat.id, "O'chirish uchun tanlang:", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("delearntask_"))
def delearntask(c):
    if not is_admin(c.from_user.id):
        return
    task_id = int(c.data.split("_")[-1])
    config["earn_tasks"] = [t for t in config.get("earn_tasks", []) if t["id"] != task_id]
    save_db()
    bot.answer_callback_query(c.id, "✅ O'chirildi")


# =====================================
# ADMIN: PROMO CODES
# =====================================
@bot.message_handler(func=lambda m: m.text == "🎟 Promokodlar" and is_admin(m.from_user.id))
@admin_required
def manage_promo(message):
    lines = ["🎟 <b>Promokodlar</b>"]
    for code, amount in promo_codes.items():
        lines.append(f"\n{code} — {amount:,} so'm")
    if not promo_codes:
        lines.append("\nHozircha promokod yo'q")
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("➕ Qo'shish", callback_data="add_promo"))
    if promo_codes:
        markup.add(InlineKeyboardButton("❌ O'chirish", callback_data="remove_promo"))
    bot.send_message(message.chat.id, "\n".join(lines), reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data == "add_promo")
def add_promo(c):
    if not is_admin(c.from_user.id):
        return
    msg = bot.send_message(c.message.chat.id, "Format: KOD - summa (masalan: BONUS100 - 100)")
    bot.register_next_step_handler(msg, process_add_promo)


def process_add_promo(message):
    parts = message.text.strip().split(" - ")
    if len(parts) != 2:
        bot.send_message(message.chat.id, "❌ Format noto'g'ri", reply_markup=admin_menu())
        return
    code = parts[0].strip().upper()
    try:
        amount = int(parts[1].strip())
    except Exception:
        bot.send_message(message.chat.id, "❌ Summa noto'g'ri", reply_markup=admin_menu())
        return
    promo_codes[code] = amount
    save_db()
    bot.send_message(message.chat.id, "✅ Promokod qo'shildi", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data == "remove_promo")
def remove_promo(c):
    if not is_admin(c.from_user.id):
        return
    markup = InlineKeyboardMarkup(row_width=1)
    for code in promo_codes:
        markup.add(InlineKeyboardButton(code, callback_data=f"delpromo_{code}"))
    bot.send_message(c.message.chat.id, "O'chirish uchun tanlang:", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("delpromo_"))
def delpromo(c):
    if not is_admin(c.from_user.id):
        return
    code = c.data.split("_", 1)[1]
    promo_codes.pop(code, None)
    save_db()
    bot.answer_callback_query(c.id, "✅ O'chirildi")


@bot.message_handler(func=lambda m: m.text == "🎟 Promokod")
@subscription_required
def promo_menu(message):
    msg = bot.send_message(message.chat.id, "🎟 Promokodni kiriting:", reply_markup=back_menu())
    bot.register_next_step_handler(msg, process_promo)


def process_promo(message):
    if message.text == "⬅️ Ortga":
        bot.send_message(message.chat.id, "🔙 Orqaga", reply_markup=build_main_menu(is_admin(message.from_user.id)))
        return
    uid = str(message.from_user.id)
    code = message.text.strip().upper()
    if code not in promo_codes:
        bot.send_message(message.chat.id, "❌ Promokod noto'g'ri", reply_markup=build_main_menu(is_admin(message.from_user.id)))
        return
    if code in users[uid].get("used_promo", []):
        bot.send_message(message.chat.id, "❌ Bu promokod oldin ishlatilgan", reply_markup=build_main_menu(is_admin(message.from_user.id)))
        return
    amount = int(promo_codes[code])
    users[uid].setdefault("used_promo", []).append(code)
    users[uid]["balance"] += amount
    save_db()
    bot.send_message(message.chat.id, f"✅ Promokod ishladi: +{amount} so'm", reply_markup=build_main_menu(is_admin(message.from_user.id)))


# =====================================
# ADMIN: REFERRAL / BONUS SETTINGS
# =====================================
@bot.message_handler(func=lambda m: m.text == "💰 Referal/Bonuslar" and is_admin(m.from_user.id))
@admin_required
def referral_settings(message):
    text = (
        f"💰 <b>Referal va bonus sozlamalari</b>\n\n"
        f"👥 Referal bonusi: {int(config.get('referral_bonus', 1000)):,} so'm\n"
        f"🎁 Ro'yxatdan o'tish bonusi: {int(config.get('welcome_bonus', 100)):,} so'm\n"
        f"✅ Obuna bonusi: {int(config.get('subscribe_bonus', 200)):,} so'm\n"
        f"📅 Kunlik bonus: {config.get('daily_bonus_range', [100,500])[0]:,} - {config.get('daily_bonus_range', [100,500])[1]:,} so'm"
    )
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("👥 Referal bonusini o'zgartirish", callback_data="edit_ref_bonus"))
    markup.add(InlineKeyboardButton("🎁 Ro'yxat bonusini o'zgartirish", callback_data="edit_welcome_bonus"))
    markup.add(InlineKeyboardButton("✅ Obuna bonusini o'zgartirish", callback_data="edit_subscribe_bonus"))
    markup.add(InlineKeyboardButton("📅 Kunlik bonusni o'zgartirish", callback_data="edit_daily_bonus"))
    bot.send_message(message.chat.id, text, reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data == "edit_ref_bonus")
def edit_ref_bonus(c):
    if not is_admin(c.from_user.id):
        return
    msg = bot.send_message(c.message.chat.id, "Yangi referal bonusini kiriting:")
    bot.register_next_step_handler(msg, lambda m: process_simple_config_int(m, "referral_bonus"))


@bot.callback_query_handler(func=lambda c: c.data == "edit_welcome_bonus")
def edit_welcome_bonus(c):
    if not is_admin(c.from_user.id):
        return
    msg = bot.send_message(c.message.chat.id, "Yangi ro'yxatdan o'tish bonusini kiriting:")
    bot.register_next_step_handler(msg, lambda m: process_simple_config_int(m, "welcome_bonus"))


@bot.callback_query_handler(func=lambda c: c.data == "edit_subscribe_bonus")
def edit_subscribe_bonus(c):
    if not is_admin(c.from_user.id):
        return
    msg = bot.send_message(c.message.chat.id, "Yangi obuna bonusini kiriting:")
    bot.register_next_step_handler(msg, lambda m: process_simple_config_int(m, "subscribe_bonus"))


def process_simple_config_int(message, key: str):
    try:
        amount = int(message.text.strip())
    except Exception:
        bot.send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
        return
    config[key] = amount
    save_db()
    bot.send_message(message.chat.id, "✅ Saqlandi", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data == "edit_daily_bonus")
def edit_daily_bonus(c):
    if not is_admin(c.from_user.id):
        return
    msg = bot.send_message(c.message.chat.id, "Min va max qiymatlarni kiriting (masalan: 100 500):")
    bot.register_next_step_handler(msg, process_edit_daily_bonus)


def process_edit_daily_bonus(message):
    parts = message.text.strip().split()
    if len(parts) != 2:
        bot.send_message(message.chat.id, "❌ Format noto'g'ri", reply_markup=admin_menu())
        return
    try:
        min_v, max_v = int(parts[0]), int(parts[1])
    except Exception:
        bot.send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
        return
    config["daily_bonus_range"] = [min_v, max_v]
    save_db()
    bot.send_message(message.chat.id, "✅ Saqlandi", reply_markup=admin_menu())


# =====================================
# ADMIN: TEXTS (Matnlar)
# =====================================
EDITABLE_TEXT_KEYS = {
    "welcome": "Xush kelibsiz xabari",
    "not_subscribed": "Obuna talab xabari",
    "subscribe_bonus_text": "Obuna bonusi xabari",
}


@bot.message_handler(func=lambda m: m.text == "✉️ Matnlar" and is_admin(m.from_user.id))
@admin_required
def manage_texts(message):
    markup = InlineKeyboardMarkup(row_width=1)
    for key, label in EDITABLE_TEXT_KEYS.items():
        markup.add(InlineKeyboardButton(f"✏️ {label}", callback_data=f"edittext_{key}"))
    bot.send_message(message.chat.id, "✉️ Tahrirlash uchun matnni tanlang:", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("edittext_"))
def edittext(c):
    if not is_admin(c.from_user.id):
        return
    key = c.data.split("_", 1)[1]
    current = get_text(key)
    msg = bot.send_message(c.message.chat.id, f"Joriy matn:\n\n{current}\n\nYangi matnni yuboring:")
    bot.register_next_step_handler(msg, process_edittext, key)


def process_edittext(message, key: str):
    config.setdefault("messages", {})[key] = message.text
    save_db()
    bot.send_message(message.chat.id, "✅ Saqlandi", reply_markup=admin_menu())


# =====================================
# ADMIN: MANAGE ADMINS (superadmin only)
# =====================================
@bot.message_handler(func=lambda m: m.text == "👨‍💻 Adminlar" and is_admin(m.from_user.id))
@admin_required
def manage_admins(message):
    lines = ["👨‍💻 <b>Adminlar</b>"]
    for uid, info in ADMINS.items():
        lines.append(f"\n{info.get('username','')} | <code>{uid}</code> | {info.get('role')}")
    markup = InlineKeyboardMarkup(row_width=1)
    if is_superadmin(message.from_user.id):
        markup.add(InlineKeyboardButton("➕ Admin qo'shish", callback_data="add_admin"))
        markup.add(InlineKeyboardButton("❌ Adminni o'chirish", callback_data="remove_admin"))
    bot.send_message(message.chat.id, "\n".join(lines), reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data == "add_admin")
def add_admin(c):
    if not is_superadmin(c.from_user.id):
        bot.answer_callback_query(c.id, "❌ Faqat super admin")
        return
    msg = bot.send_message(c.message.chat.id, "Yangi admin ID sini kiriting:")
    bot.register_next_step_handler(msg, process_add_admin)


def process_add_admin(message):
    if not message.text.strip().isdigit():
        bot.send_message(message.chat.id, "❌ Faqat ID (raqam) kiriting", reply_markup=admin_menu())
        return
    new_admin_id = message.text.strip()
    username = "Noma'lum"
    try:
        chat = bot.get_chat(int(new_admin_id))
        username = f"@{chat.username}" if chat.username else (chat.first_name or "Noma'lum")
    except Exception:
        pass
    ADMINS[new_admin_id] = {"username": username, "role": "admin", "added_date": now_str()}
    save_db()
    bot.send_message(message.chat.id, f"✅ {username} admin qilib qo'shildi", reply_markup=admin_menu())
    try:
        bot.send_message(int(new_admin_id), "🎉 Siz botga admin etib tayinlandingiz!")
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data == "remove_admin")
def remove_admin(c):
    if not is_superadmin(c.from_user.id):
        bot.answer_callback_query(c.id, "❌ Faqat super admin")
        return
    markup = InlineKeyboardMarkup(row_width=1)
    for uid, info in ADMINS.items():
        if info.get("role") == "superadmin":
            continue
        markup.add(InlineKeyboardButton(f"{info.get('username','')} ({uid})", callback_data=f"deladmin_{uid}"))
    bot.send_message(c.message.chat.id, "O'chirish uchun tanlang:", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("deladmin_"))
def deladmin(c):
    if not is_superadmin(c.from_user.id):
        return
    uid = c.data.split("_", 1)[1]
    if uid in ADMINS and ADMINS[uid].get("role") != "superadmin":
        ADMINS.pop(uid, None)
        save_db()
        bot.answer_callback_query(c.id, "✅ O'chirildi")
    else:
        bot.answer_callback_query(c.id, "❌ Bo'lmaydi")


# =====================================
# ADMIN: BROADCAST (users / channels-groups)
# =====================================
@bot.message_handler(func=lambda m: m.text == "📢 Reklama" and is_admin(m.from_user.id))
@admin_required
def send_ad(message):
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("👥 Barcha foydalanuvchilarga", callback_data="ad_target_users"))
    markup.add(InlineKeyboardButton("📢 Kanal/guruhga (saqlangan)", callback_data="ad_target_saved"))
    markup.add(InlineKeyboardButton("➕ Yangi kanal/guruh qo'shish", callback_data="ad_add_target"))
    bot.send_message(message.chat.id, "📢 Reklamani qayerga yubormoqchisiz?", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data == "ad_target_users")
def ad_target_users(c):
    if not is_admin(c.from_user.id):
        return
    msg = bot.send_message(c.message.chat.id, "📢 Reklama matni yoki media yuboring:", reply_markup=back_menu())
    bot.register_next_step_handler(msg, process_ad_users)


def process_ad_users(message):
    if getattr(message, "text", None) == "⬅️ Ortga":
        bot.send_message(message.chat.id, "🔙 Orqaga", reply_markup=admin_menu())
        return
    sent, failed = 0, 0
    for uid in list(users.keys()):
        try:
            _forward_ad_content(message, int(uid))
            sent += 1
        except Exception:
            failed += 1
    bot.send_message(message.chat.id, f"✅ Tugadi\nYuborildi: {sent}\nXato: {failed}", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data == "ad_target_saved")
def ad_target_saved(c):
    if not is_admin(c.from_user.id):
        return
    targets = config.get("broadcast_targets", [])
    if not targets:
        bot.send_message(c.message.chat.id, "❌ Saqlangan kanal/guruh yo'q. Avval qo'shing.", reply_markup=admin_menu())
        return
    markup = InlineKeyboardMarkup(row_width=1)
    for t in targets:
        markup.add(InlineKeyboardButton(t.get("title", str(t["id"])), callback_data=f"adtarget_{t['id']}"))
    markup.add(InlineKeyboardButton("📢 Barchasiga", callback_data="adtarget_all"))
    bot.send_message(c.message.chat.id, "Qaysi manzilga yuboraylik?", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("adtarget_"))
def adtarget_pick(c):
    if not is_admin(c.from_user.id):
        return
    target = c.data.split("_", 1)[1]
    msg = bot.send_message(c.message.chat.id, "📢 Reklama matni yoki media yuboring:", reply_markup=back_menu())
    bot.register_next_step_handler(msg, process_ad_targets, target)


def process_ad_targets(message, target: str):
    if getattr(message, "text", None) == "⬅️ Ortga":
        bot.send_message(message.chat.id, "🔙 Orqaga", reply_markup=admin_menu())
        return
    targets = config.get("broadcast_targets", [])
    chat_ids = [t["id"] for t in targets] if target == "all" else [int(target)]
    sent, failed = 0, 0
    for cid in chat_ids:
        try:
            _forward_ad_content(message, cid)
            sent += 1
        except Exception:
            failed += 1
    bot.send_message(message.chat.id, f"✅ Tugadi\nYuborildi: {sent}\nXato: {failed}", reply_markup=admin_menu())


def _forward_ad_content(message, chat_id: int):
    if message.content_type == "text":
        bot.send_message(chat_id, message.text)
    elif message.content_type == "photo":
        bot.send_photo(chat_id, message.photo[-1].file_id, caption=message.caption)
    elif message.content_type == "video":
        bot.send_video(chat_id, message.video.file_id, caption=message.caption)
    elif message.content_type == "document":
        bot.send_document(chat_id, message.document.file_id, caption=message.caption)
    else:
        bot.send_message(chat_id, "📢 Yangi e'lon")


@bot.callback_query_handler(func=lambda c: c.data == "ad_add_target")
def ad_add_target(c):
    if not is_admin(c.from_user.id):
        return
    msg = bot.send_message(c.message.chat.id, "📢 Kanal/guruhdan istalgan xabarni forward qiling (bot u yerda admin bo'lishi kerak):")
    bot.register_next_step_handler(msg, process_ad_add_target)


def process_ad_add_target(message):
    if not getattr(message, "forward_from_chat", None):
        bot.send_message(message.chat.id, "❌ Forward qilingan xabar topilmadi", reply_markup=admin_menu())
        return
    chat = message.forward_from_chat
    targets = config.setdefault("broadcast_targets", [])
    if not any(t["id"] == chat.id for t in targets):
        targets.append({"id": chat.id, "title": chat.title or str(chat.id)})
        save_db()
    bot.send_message(message.chat.id, f"✅ Qo'shildi: {chat.title or chat.id}", reply_markup=admin_menu())


# =====================================
# SETTINGS / HISTORY / CONTACT
# =====================================
@bot.message_handler(func=lambda m: m.text == "⚙️ Sozlamalar")
@subscription_required
def settings(message):
    uid = str(message.from_user.id)
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("🔔 Bildirishnomalar", "📜 Buyurtmalar tarixi")
    kb.add("📩 Adminga yozish", "⬅️ Ortga")
    status = "✅ Yoqilgan" if users[uid].get("notifications", True) else "❌ O'chirilgan"
    bot.send_message(message.chat.id, f"⚙️ Sozlamalar\n\n🔔 Bildirishnomalar: {status}", reply_markup=kb)


@bot.message_handler(func=lambda m: m.text == "🔔 Bildirishnomalar")
@subscription_required
def toggle_notifications(message):
    uid = str(message.from_user.id)
    users[uid]["notifications"] = not users[uid].get("notifications", True)
    save_db()
    bot.send_message(message.chat.id, f"✅ Holat: {'yoqildi' if users[uid]['notifications'] else 'o\'chirildi'}", reply_markup=build_main_menu(is_admin(message.from_user.id)))


@bot.message_handler(func=lambda m: m.text == "📜 Buyurtmalar tarixi")
@subscription_required
def order_history(message):
    uid = str(message.from_user.id)
    my_orders = [o for o in orders if o.get("user_id") == uid]
    my_orders.sort(key=lambda x: x.get("date", ""), reverse=True)
    if not my_orders:
        bot.send_message(message.chat.id, "📜 Buyurtmalar mavjud emas")
        return
    text = ["📜 <b>Oxirgi buyurtmalar</b>"]
    for order in my_orders[:10]:
        text.append(f"\n#{order.get('id')} | {order.get('kind')} | {order.get('amount', 0)} so'm | {order.get('status')}")
    bot.send_message(message.chat.id, "\n".join(text))


@bot.message_handler(func=lambda m: m.text == "📩 Adminga yozish")
@subscription_required
def contact_admin(message):
    msg = bot.send_message(message.chat.id, "📩 Xabaringizni yozing:", reply_markup=back_menu())
    bot.register_next_step_handler(msg, send_to_admin)


def send_to_admin(message):
    if message.text == "⬅️ Ortga":
        bot.send_message(message.chat.id, "🔙 Orqaga", reply_markup=build_main_menu(is_admin(message.from_user.id)))
        return
    uid = str(message.from_user.id)
    for admin_id in list(ADMINS.keys()):
        try:
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("✏️ Javob yozish", callback_data=f"reply_user_{uid}"))
            if message.content_type == "text":
                bot.send_message(int(admin_id), f"📩 Userdan xabar\n👤 {safe_username(message.from_user)}\n🆔 <code>{uid}</code>\n\n{message.text}", reply_markup=kb)
            elif message.content_type == "photo":
                bot.send_photo(int(admin_id), message.photo[-1].file_id, caption=f"📩 Userdan rasm\n👤 {safe_username(message.from_user)}\n🆔 <code>{uid}</code>\n\n{message.caption or ''}", reply_markup=kb)
        except Exception as e:
            logger.error(f"Admin msg xato: {e}")
    bot.send_message(message.chat.id, "✅ Xabar yuborildi", reply_markup=build_main_menu(is_admin(message.from_user.id)))


@bot.callback_query_handler(func=lambda c: c.data.startswith("reply_user_"))
def reply_user(c):
    if not is_admin(c.from_user.id):
        return
    uid = c.data.split("_")[-1]
    msg = bot.send_message(c.message.chat.id, f"User {uid} uchun javob yozing:")
    bot.register_next_step_handler(msg, lambda m: send_admin_reply(m, uid))


def send_admin_reply(message, user_id: str):
    try:
        if message.content_type == "text":
            bot.send_message(int(user_id), f"📩 <b>Admin javobi:</b>\n\n{message.text}")
        elif message.content_type == "photo":
            bot.send_photo(int(user_id), message.photo[-1].file_id, caption=f"📩 <b>Admin javobi:</b>\n\n{message.caption or ''}")
        bot.send_message(message.chat.id, "✅ Javob yuborildi", reply_markup=admin_menu())
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Xato: {e}", reply_markup=admin_menu())


# =====================================
# NAVIGATION / FALLBACK
# =====================================
@bot.message_handler(func=lambda m: m.text == "⬅️ Asosiy menyu")
def to_main_menu(message):
    bot.send_message(message.chat.id, "🔙 Asosiy menyu", reply_markup=build_main_menu(is_admin(message.from_user.id)))


@bot.message_handler(func=lambda m: m.text == "⬅️ Ortga")
def back(message):
    bot.send_message(message.chat.id, "🔙 Asosiy menyu", reply_markup=build_main_menu(is_admin(message.from_user.id)))


@bot.message_handler(func=lambda m: True, content_types=["text"])
def unknown(message):
    ensure_user(message)
    if user_blocked(str(message.from_user.id)):
        bot.send_message(message.chat.id, "❌ Siz bloklangansiz.")
        return
    bot.send_message(message.chat.id, "❌ Noto'g'ri buyruq. Menyudan tanlang.", reply_markup=build_main_menu(is_admin(message.from_user.id)))


# =====================================
# RUN
# =====================================
if __name__ == "__main__":
    print("=" * 50)
    print("🤖 BOT ISHGA TUSHMOQDA...")
    print("=" * 50)
    keep_alive()
    try:
        me = bot.get_me()
        print(f"✅ Bot: @{me.username}")
    except Exception as e:
        print(f"❌ Bot ma'lumotini olishda xato: {e}")
    print(f"👥 Foydalanuvchilar: {len(users)}")
    print(f"📦 Buyurtmalar: {len(orders)}")
    print(f"👨‍💻 Adminlar: {len(ADMINS)}")
    print("=" * 50)
    logger.info("Bot ishga tushdi")
    try:
        bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)
    except Exception as e:
        logger.error(f"Kritik xato: {e}", exc_info=True)
        print(f"❌ Xato: {e}")
    finally:
        save_db()
        Database.backup()
        logger.info("Bot to'xtatildi")
        print("✅ Ma'lumotlar saqlandi")