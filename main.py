import os
import json
import time
import random
import logging
import threading
from datetime import datetime, timedelta
from functools import wraps
from typing import Dict, Any, List, Optional

import requests
from flask import Flask
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
import telebot
from telebot import types
from telebot.apihelper import ApiTelegramException
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

bot = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True, num_threads=8)
app = Flask(__name__)

DATA_FILE = "users.json"
ORDERS_FILE = "orders.json"
CONFIG_FILE = "config.json"
PROMO_FILE = "promo.json"
ADMINS_FILE = "admins.json"
LOGS_FILE = "bot.log"
BACKUP_DIR = "backups"

# =====================================
# STICKERS / ANIMATIONS (public sticker file_ids from Telegram's own sticker sets;
# if any of these ever become invalid, sending is wrapped in try/except so nothing breaks)
# =====================================
STICKERS = {
    "welcome": "CAACAgIAAxkBAAEBTQFmS3example_welcome",  # falls back silently if invalid
    "success": "CAACAgIAAxkBAAEBTQJmS3example_success",
    "fail": "CAACAgIAAxkBAAEBTQNmS3example_fail",
    "money": "CAACAgIAAxkBAAEBTQRmS3example_money",
    "game_win": "CAACAgIAAxkBAAEBTQVmS3example_gamewin",
    "game_lose": "CAACAgIAAxkBAAEBTQZmS3example_gamelose",
}

GIF_LOADING = "https://media.giphy.com/media/3oEjI6SIIHBdRxXI40/giphy.gif"


def safe_send_sticker(chat_id, key: str):
    """Best-effort sticker sender — never breaks the flow if the sticker id is bad/unavailable."""
    file_id = STICKERS.get(key)
    if not file_id:
        return
    try:
        bot.send_sticker(chat_id, file_id)
    except Exception as e:
        logger.debug(f"Stiker yuborilmadi ({key}): {e}")


def safe_send_animation(chat_id, url_or_id: str, caption: str = None):
    try:
        bot.send_animation(chat_id, url_or_id, caption=caption)
    except Exception as e:
        logger.debug(f"Animatsiya yuborilmadi: {e}")


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
    "join_chat_prompt": "💬 Rasmiy chatimizga qo'shiling — u yerda yangiliklar, aksiyalar va yordam bor!",
}

# Default mini-games configuration (admin can edit odds/multipliers per game)
DEFAULT_GAMES = {
    "coin": {
        "name": "🪙 Tanga",
        "enabled": True,
        "win_chance": 45,       # percent chance to win
        "multiplier": 1.8,      # payout multiplier on win
        "min_bet": 500,
        "max_bet": 50000,
    },
    "dice": {
        "name": "🎲 Zar",
        "enabled": True,
        "win_chance": 30,
        "multiplier": 2.5,
        "min_bet": 500,
        "max_bet": 50000,
    },
    "slot": {
        "name": "🎰 Slot",
        "enabled": True,
        "win_chance": 20,
        "multiplier": 4.0,
        "min_bet": 1000,
        "max_bet": 30000,
    },
}

DEFAULT_CONFIG = {
    "required_channels": DEFAULT_REQUIRED_CHANNELS,
    "earn_tasks": [],
    "referral_bonus": 1000,
    "welcome_bonus": 100,
    "subscribe_bonus": 200,
    "daily_bonus_range": [100, 500],
    "min_topup": 5000,
    "services": [],            # each: {id, category, name, price, description}
    "service_categories": [],  # each: {id, name}
    "payment_cards": [],
    "payment_channel_id": None,
    "orders_channel_id": None,   # separate channel for shop/order requests
    "broadcast_targets": [],     # each: {id, title, type: group/channel}
    "messages": DEFAULT_MESSAGES,
    "games": DEFAULT_GAMES,
    "promo_limits": {},           # code -> {"max_uses": int, "used_count": int}
    "chat_link": None,            # NEW: official chat link (e.g. https://t.me/joinchat/xxx or @username)
    "chat_title": "💬 Chatga qo'shilish",  # NEW: button label
    "chat_enabled": True,          # NEW: admin on/off switch for the join-chat button
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
    try:
        return {"status": "ok", "users": len(users), "time": datetime.now().isoformat()}
    except Exception as e:
        return {"status": "error", "error": str(e)}, 500


def run_web():
    try:
        app.run(host="0.0.0.0", port=PORT)
    except Exception as e:
        logger.error(f"Web server xato: {e}")


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
                content = f.read().strip()
                if not content:
                    return default
                return json.loads(content)
        except Exception as e:
            logger.error(f"{path} o'qishda xato: {e}")
            # try to recover from the most recent backup instead of losing all data
            recovered = Database._recover_from_backup(path)
            if recovered is not None:
                logger.info(f"{path} backupdan tiklandi")
                return recovered
            return default

    @staticmethod
    def _recover_from_backup(path: str):
        if not os.path.isdir(BACKUP_DIR):
            return None
        base = path.replace(".json", "")
        candidates = sorted(
            [f for f in os.listdir(BACKUP_DIR) if f.startswith(base + "_")],
            reverse=True,
        )
        for c in candidates:
            try:
                with open(os.path.join(BACKUP_DIR, c), "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                continue
        return None

    @staticmethod
    def load_all():
        users_data = Database._read_json(DATA_FILE, {})
        orders_data = Database._read_json(ORDERS_FILE, [])
        config_data = Database._read_json(CONFIG_FILE, {})
        promo_data = Database._read_json(PROMO_FILE, DEFAULT_PROMO_CODES.copy())
        admins_data = Database._read_json(ADMINS_FILE, DEFAULT_ADMINS.copy())

        if not isinstance(users_data, dict):
            users_data = {}
        if not isinstance(orders_data, list):
            orders_data = []
        if not isinstance(config_data, dict):
            config_data = {}
        if not isinstance(promo_data, dict):
            promo_data = DEFAULT_PROMO_CODES.copy()
        if not isinstance(admins_data, dict):
            admins_data = DEFAULT_ADMINS.copy()

        merged_config = json.loads(json.dumps(DEFAULT_CONFIG))
        merged_config.update(config_data or {})
        merged_config["daily_bonus_range"] = list(merged_config.get("daily_bonus_range", [100, 500]))
        merged_config["messages"] = {**DEFAULT_MESSAGES, **merged_config.get("messages", {})}
        merged_games = json.loads(json.dumps(DEFAULT_GAMES))
        for k, v in (merged_config.get("games", {}) or {}).items():
            if k in merged_games:
                merged_games[k].update(v)
            else:
                merged_games[k] = v
        merged_config["games"] = merged_games
        merged_config.setdefault("promo_limits", {})
        merged_config.setdefault("service_categories", [])
        merged_config.setdefault("orders_channel_id", None)
        merged_config.setdefault("chat_link", None)
        merged_config.setdefault("chat_title", "💬 Chatga qo'shilish")
        merged_config.setdefault("chat_enabled", True)

        # normalize admin keys to str
        admins_data = {str(k): v for k, v in admins_data.items()}
        if not admins_data:
            admins_data = DEFAULT_ADMINS.copy()

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
                Database._atomic_write(path, data)

    @staticmethod
    def _atomic_write(path: str, data):
        """Write to a temp file first, then rename — avoids corrupting the json file
        if the process is killed mid-write."""
        tmp_path = f"{path}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
        except Exception as e:
            logger.error(f"Saqlashda xato {path}: {e}")
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    @staticmethod
    def backup():
        try:
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
            Database._cleanup_old_backups()
        except Exception as e:
            logger.error(f"Backup umumiy xato: {e}")

    @staticmethod
    def _cleanup_old_backups(keep: int = 30):
        """Keep only the most recent N backups per file to avoid unbounded disk growth."""
        try:
            if not os.path.isdir(BACKUP_DIR):
                return
            groups: Dict[str, List[str]] = {}
            for f in os.listdir(BACKUP_DIR):
                base = f.rsplit("_", 2)[0]
                groups.setdefault(base, []).append(f)
            for base, files in groups.items():
                files.sort(reverse=True)
                for old in files[keep:]:
                    try:
                        os.remove(os.path.join(BACKUP_DIR, old))
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Backup tozalashda xato: {e}")


users, orders, config, promo_codes, ADMINS = Database.load_all()

# In-memory write buffering — batches rapid successive save_db() calls so we don't
# do a blocking disk write on every single button press (this is the main source
# of perceived bot "lag" under load).
_save_pending = False
_save_lock = threading.Lock()


def save_db(force: bool = False):
    """Marks data as dirty and lets a background thread flush it, so handlers
    return to the user immediately instead of blocking on disk I/O."""
    global _save_pending
    if force:
        try:
            Database.save_all(users, orders, config, promo_codes, ADMINS)
        except Exception as e:
            logger.error(f"save_db(force) xato: {e}")
        return
    with _save_lock:
        _save_pending = True


def _flush_loop():
    global _save_pending
    while True:
        time.sleep(1.5)
        try:
            with _save_lock:
                pending = _save_pending
                _save_pending = False
            if pending:
                Database.save_all(users, orders, config, promo_codes, ADMINS)
        except Exception as e:
            logger.error(f"Flush loop xato: {e}")


threading.Thread(target=_flush_loop, daemon=True).start()


def auto_backup():
    while True:
        time.sleep(86400)
        try:
            Database.backup()
            logger.info("Avtomatik backup yaratildi")
        except Exception as e:
            logger.error(f"Auto backup xato: {e}")


threading.Thread(target=auto_backup, daemon=True).start()


# =====================================
# SAFE TELEGRAM API WRAPPERS
# (every outward call to Telegram is wrapped so one failed send/edit never
# crashes a handler or takes down the whole bot)
# =====================================
def safe_call(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except ApiTelegramException as e:
        logger.warning(f"Telegram API xato ({func.__name__ if hasattr(func,'__name__') else func}): {e}")
        return None
    except Exception as e:
        logger.error(f"Kutilmagan xato ({func.__name__ if hasattr(func,'__name__') else func}): {e}")
        return None


def safe_send_message(chat_id, text, **kwargs):
    return safe_call(bot.send_message, chat_id, text, **kwargs)


def safe_edit_message_text(text, chat_id, message_id, **kwargs):
    return safe_call(bot.edit_message_text, text, chat_id, message_id, **kwargs)


def safe_edit_message_caption(caption, chat_id, message_id, **kwargs):
    return safe_call(bot.edit_message_caption, caption, chat_id, message_id, **kwargs)


def safe_send_photo(chat_id, photo, **kwargs):
    return safe_call(bot.send_photo, chat_id, photo, **kwargs)


def safe_answer_callback_query(call_id, text=None, **kwargs):
    return safe_call(bot.answer_callback_query, call_id, text, **kwargs)


# =====================================
# HELPERS
# =====================================
def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def is_admin(user_id: int) -> bool:
    try:
        return str(user_id) in ADMINS
    except Exception:
        return False


def is_superadmin(user_id: int) -> bool:
    try:
        return str(user_id) in ADMINS and ADMINS[str(user_id)].get("role") == "superadmin"
    except Exception:
        return False


def get_text(key: str) -> str:
    try:
        return config.get("messages", {}).get(key, DEFAULT_MESSAGES.get(key, ""))
    except Exception:
        return DEFAULT_MESSAGES.get(key, "")


def new_id(seq: List[Dict[str, Any]]) -> int:
    try:
        return (max([x.get("id", 0) for x in seq], default=0) + 1) if seq else 1
    except Exception:
        return int(time.time())


def safe_int(value, default=0) -> int:
    try:
        return int(str(value).strip().replace(" ", ""))
    except Exception:
        return default


def safe_float(value, default=0.0) -> float:
    try:
        return float(str(value).strip().replace(" ", ""))
    except Exception:
        return default


def ensure_user(message_or_user) -> str:
    try:
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
                "games_played": 0,
                "games_won": 0,
                "total_wagered": 0,
                "total_won": 0,
                "admin_topups_total": 0,
                "joined_chat": False,
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
            for k, default_v in {
                "games_played": 0, "games_won": 0, "total_wagered": 0,
                "total_won": 0, "admin_topups_total": 0, "joined_chat": False,
            }.items():
                if k not in users[user_id]:
                    users[user_id][k] = default_v
                    changed = True
            if changed:
                save_db()
        return user_id
    except Exception as e:
        logger.error(f"ensure_user xato: {e}")
        # Still try to return something usable
        try:
            uid = str(message_or_user.from_user.id if hasattr(message_or_user, "from_user") else message_or_user.id)
        except Exception:
            uid = "0"
        users.setdefault(uid, {"user_id": uid, "balance": 0})
        return uid


def safe_username(user_or_id) -> str:
    try:
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
    except Exception:
        return "Noma'lum"


def user_blocked(user_id: str) -> bool:
    try:
        return users.get(user_id, {}).get("blocked", False)
    except Exception:
        return False


def is_channel_member(channel_username: str, user_id: int) -> bool:
    try:
        member = bot.get_chat_member(channel_username, user_id)
        return member.status not in ["left", "kicked"]
    except Exception as e:
        logger.error(f"Obuna tekshirish xato {channel_username}: {e}")
        # Fail-open would let unsubscribed users in; fail-closed is safer for the
        # business logic here — but we don't want a Telegram hiccup to permanently
        # lock a legit user out either, so we only fail-closed (return False),
        # matching prior behavior, while the error is fully contained.
        return False


def check_subscription(user_id: int) -> bool:
    try:
        required_channels = config.get("required_channels", [])
        for channel in required_channels:
            if not is_channel_member(channel["username"], user_id):
                return False
        return True
    except Exception as e:
        logger.error(f"check_subscription xato: {e}")
        return False


def register_confirmed_channels(uid: str, telegram_user_id: int):
    """Track how many unique users confirmed each required channel & auto-remove if threshold reached."""
    try:
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
    except Exception as e:
        logger.error(f"register_confirmed_channels xato: {e}")


def notify_admins(text: str):
    for admin_id in list(ADMINS.keys()):
        try:
            bot.send_message(int(admin_id), text)
        except Exception as e:
            logger.debug(f"Adminga xabar yuborilmadi ({admin_id}): {e}")


def send_order_to_channel(caption: str, markup=None, photo_file_id: Optional[str] = None):
    """Send shop/order requests to the dedicated orders channel, falling back to admins."""
    channel_id = config.get("orders_channel_id")
    sent = False
    if channel_id:
        try:
            if photo_file_id:
                bot.send_photo(channel_id, photo_file_id, caption=caption, reply_markup=markup)
            else:
                bot.send_message(channel_id, caption, reply_markup=markup)
            sent = True
        except Exception as e:
            logger.error(f"Orders kanaliga yuborishda xato: {e}")
    if not sent:
        for admin_id in list(ADMINS.keys()):
            try:
                if photo_file_id:
                    bot.send_photo(int(admin_id), photo_file_id, caption=caption, reply_markup=markup)
                else:
                    bot.send_message(int(admin_id), caption, reply_markup=markup)
            except Exception as e:
                logger.debug(f"Admin fallback xato ({admin_id}): {e}")


def subscription_required(func):
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        try:
            uid = ensure_user(message)
            users[uid]["last_active"] = now_str()
            if user_blocked(uid):
                safe_send_message(message.chat.id, "❌ Siz bloklangansiz.")
                return
            if not check_subscription(message.from_user.id):
                show_required_channels(message.chat.id)
                return
            return func(message, *args, **kwargs)
        except Exception as e:
            logger.error(f"Handler xato ({func.__name__}): {e}", exc_info=True)
            safe_send_message(message.chat.id, "⚠️ Kutilmagan xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.")
    return wrapper


def admin_required(func):
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        try:
            if not is_admin(message.from_user.id):
                return
            return func(message, *args, **kwargs)
        except Exception as e:
            logger.error(f"Admin handler xato ({func.__name__}): {e}", exc_info=True)
            safe_send_message(message.chat.id, "⚠️ Xatolik yuz berdi.")
    return wrapper


def superadmin_required(func):
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        try:
            if not is_superadmin(message.from_user.id):
                safe_send_message(message.chat.id, "❌ Bu amal faqat super admin uchun.")
                return
            return func(message, *args, **kwargs)
        except Exception as e:
            logger.error(f"Superadmin handler xato ({func.__name__}): {e}", exc_info=True)
            safe_send_message(message.chat.id, "⚠️ Xatolik yuz berdi.")
    return wrapper


def safe_callback_handler(func):
    """Wraps every callback_query handler so a single bad callback (stale message,
    deleted message, network hiccup) can't silently freeze that button forever or
    crash the polling thread."""
    @wraps(func)
    def wrapper(call, *args, **kwargs):
        try:
            return func(call, *args, **kwargs)
        except Exception as e:
            logger.error(f"Callback xato ({func.__name__}): {e}", exc_info=True)
            safe_answer_callback_query(call.id, "⚠️ Xatolik yuz berdi, qaytadan urinib ko'ring")
    return wrapper


def safe_next_step(func):
    """Wraps register_next_step_handler callbacks so users can't get stuck in a
    broken conversation state after an exception."""
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        try:
            return func(message, *args, **kwargs)
        except Exception as e:
            logger.error(f"Next-step xato ({func.__name__}): {e}", exc_info=True)
            try:
                safe_send_message(message.chat.id, "⚠️ Xatolik yuz berdi. Qaytadan boshlang.", reply_markup=_menu_for(message.from_user.id))
            except Exception:
                pass
    return wrapper


# =====================================
# MENUS (restructured per new requirements)
# "💬 Chatga qo'shilish" is now the FIRST button on every user-facing menu.
# =====================================
def build_main_menu(is_admin_flag: bool = False):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if is_admin_flag:
        # Admin sees the chat button + admin panel entry point on main menu
        if config.get("chat_enabled", True) and config.get("chat_link"):
            kb.add(config.get("chat_title", "💬 Chatga qo'shilish"))
        kb.add("👨‍💻 Admin panel")
        return kb
    if config.get("chat_enabled", True) and config.get("chat_link"):
        kb.add(config.get("chat_title", "💬 Chatga qo'shilish"))
    rows = [
        ["💸 Pul ishlash", "📊 Hisobim"],
        ["🛍 Xizmatlar", "🏆 Reyting"],
    ]
    for row in rows:
        kb.add(*row)
    return kb


def earn_submenu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("🎁 Kunlik bonus", "👥 Referal")
    kb.add("🎟 Promokod", "🎮 Mini-o'yinlar")
    kb.add("📋 Vazifalar", "⬅️ Asosiy menyu")
    return kb


def profile_submenu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("➕ Hisobni to'ldirish", "⚙️ Sozlamalar")
    kb.add("📜 Buyurtmalar tarixi", "📩 Adminga yozish")
    kb.add("⬅️ Asosiy menyu")
    return kb


def games_submenu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    active_games = [g for g in config.get("games", {}).values() if g.get("enabled", True)]
    names = [g["name"] for g in active_games]
    for i in range(0, len(names), 2):
        kb.add(*names[i:i + 2])
    kb.add("⬅️ Ortga")
    return kb


def settings_submenu(uid: str):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    notif = "🔔 Bildirishnoma: ON" if users.get(uid, {}).get("notifications", True) else "🔕 Bildirishnoma: OFF"
    kb.add(notif)
    kb.add("🌐 Til sozlamalari", "📄 Mening ma'lumotlarim")
    kb.add("⬅️ Ortga")
    return kb


def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📊 Statistika", "📦 Buyurtmalar")
    kb.add("👤 Foydalanuvchilar", "📢 Reklama")
    kb.add("💳 To'lov (kartalar)", "🛠 Xizmatlar")
    kb.add("📝 Majburiy kanallar", "💼 Pul ishlash vazifalari")
    kb.add("🎟 Promokodlar", "💰 Referal/Bonuslar")
    kb.add("🎮 Mini-o'yinlar sozlamalari", "💵 Hisob to'ldirish (admin)")
    kb.add("💬 Chat sozlamalari", "✉️ Matnlar")
    kb.add("👨‍💻 Adminlar")
    kb.add("⬅️ Foydalanuvchi rejimi")
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
    safe_send_message(chat_id, get_text("not_subscribed"), reply_markup=markup)


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
# CHAT JOIN FEATURE (new — button always first in menus)
# =====================================
@bot.message_handler(func=lambda m: m.text and config.get("chat_link") and m.text == config.get("chat_title", "💬 Chatga qo'shilish"))
def join_chat_handler(message):
    try:
        uid = ensure_user(message)
        link = config.get("chat_link")
        if not link:
            return
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("💬 Chatga o'tish", url=link))
        safe_send_message(
            message.chat.id,
            get_text("join_chat_prompt"),
            reply_markup=markup,
        )
        if not users[uid].get("joined_chat"):
            users[uid]["joined_chat"] = True
            save_db()
    except Exception as e:
        logger.error(f"join_chat_handler xato: {e}")
        safe_send_message(message.chat.id, "⚠️ Xatolik yuz berdi.")


@bot.message_handler(func=lambda m: m.text == "💬 Chat sozlamalari" and is_admin(m.from_user.id))
@admin_required
def admin_chat_settings(message):
    link = config.get("chat_link") or "sozlanmagan"
    enabled = "✅ Yoqilgan" if config.get("chat_enabled", True) else "❌ O'chirilgan"
    title = config.get("chat_title", "💬 Chatga qo'shilish")
    text = (
        f"💬 <b>Chatga qo'shilish tugmasi sozlamalari</b>\n\n"
        f"🔗 Havola: {link}\n"
        f"📝 Tugma nomi: {title}\n"
        f"⚙️ Holat: {enabled}"
    )
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("🔗 Havolani o'zgartirish", callback_data="chat_set_link"))
    markup.add(InlineKeyboardButton("📝 Tugma nomini o'zgartirish", callback_data="chat_set_title"))
    markup.add(InlineKeyboardButton(f"🔄 Holatni almashtirish", callback_data="chat_toggle"))
    safe_send_message(message.chat.id, text, reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data == "chat_set_link")
@safe_callback_handler
def chat_set_link(c):
    if not is_admin(c.from_user.id):
        return
    msg = safe_send_message(c.message.chat.id, "🔗 Chat havolasini kiriting (masalan https://t.me/+AbCdEf yoki @username):")
    if msg:
        bot.register_next_step_handler(msg, process_chat_set_link)


@safe_next_step
def process_chat_set_link(message):
    link = message.text.strip()
    if link.startswith("@"):
        link = f"https://t.me/{link[1:]}"
    config["chat_link"] = link
    save_db()
    safe_send_message(message.chat.id, "✅ Chat havolasi saqlandi", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data == "chat_set_title")
@safe_callback_handler
def chat_set_title(c):
    if not is_admin(c.from_user.id):
        return
    msg = safe_send_message(c.message.chat.id, "📝 Yangi tugma nomini kiriting (masalan: 💬 Chatga qo'shilish):")
    if msg:
        bot.register_next_step_handler(msg, process_chat_set_title)


@safe_next_step
def process_chat_set_title(message):
    config["chat_title"] = message.text.strip()
    save_db()
    safe_send_message(message.chat.id, "✅ Tugma nomi saqlandi", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data == "chat_toggle")
@safe_callback_handler
def chat_toggle(c):
    if not is_admin(c.from_user.id):
        return
    config["chat_enabled"] = not config.get("chat_enabled", True)
    save_db()
    safe_answer_callback_query(c.id, "✅ Holat o'zgartirildi")


# =====================================
# START
# =====================================
@bot.message_handler(commands=["start"])
def start(message):
    try:
        user_id = ensure_user(message)
        users[user_id]["last_active"] = now_str()

        if user_blocked(user_id):
            safe_send_message(message.chat.id, "❌ Siz bloklangansiz.")
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
            safe_send_sticker(message.chat.id, "welcome")
            safe_send_message(
                message.chat.id,
                f"{get_text('welcome')}\n\n💰 Ro'yxatdan o'tish bonusi: +{welcome_bonus} so'm\n⚖️ Balans: {users[user_id]['balance']} so'm",
                reply_markup=build_main_menu(is_admin(message.from_user.id)),
            )
            return

        save_db()
        safe_send_message(
            message.chat.id,
            f"{get_text('welcome')}\n\n💰 Balans: {users[user_id]['balance']} so'm\n👥 Referallar: {users[user_id].get('referrals_count', 0)} ta",
            reply_markup=build_main_menu(is_admin(message.from_user.id)),
        )
    except Exception as e:
        logger.error(f"/start xato: {e}", exc_info=True)
        safe_send_message(message.chat.id, "⚠️ Botni ishga tushirishda xatolik. Qaytadan /start bosing.")


@bot.callback_query_handler(func=lambda call: call.data == "check_subs")
@safe_callback_handler
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
        safe_answer_callback_query(call.id, "✅ Obuna tasdiqlandi")
        safe_edit_message_text(
            f"✅ Barcha kanallarga obuna bo'lgansiz!{bonus_text}",
            call.message.chat.id,
            call.message.message_id,
        )
        safe_send_sticker(call.message.chat.id, "success")
        safe_send_message(call.message.chat.id, "🔽 Asosiy menyu:", reply_markup=build_main_menu(is_admin(call.from_user.id)))
    else:
        safe_answer_callback_query(call.id, "❌ Hali barcha kanallarga obuna bo'lmagansiz")
        show_required_channels(call.message.chat.id)


# =====================================
# NAVIGATION HUBS: Pul ishlash / Hisobim
# =====================================
@bot.message_handler(func=lambda m: m.text == "💸 Pul ishlash")
@subscription_required
def earn_hub(message):
    safe_send_message(message.chat.id, "💸 Pul ishlash bo'limi. Kerakli bo'limni tanlang:", reply_markup=earn_submenu())


@bot.message_handler(func=lambda m: m.text == "📊 Hisobim")
@subscription_required
def profile_hub(message):
    user_id = str(message.from_user.id)
    user = users[user_id]
    text = (
        f"👤 <b>Shaxsiy kabinet</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"📛 Username: {safe_username(message.from_user)}\n"
        f"📅 Ro'yxat: {user.get('join_date', 'Noma\'lum')}\n\n"
        f"💰 Balans: {user.get('balance', 0):,} so'm\n"
        f"👥 Referallar: {user.get('referrals_count', 0)} ta\n"
        f"📦 Buyurtmalar: {user.get('orders_count', 0)} ta\n"
        f"🎮 O'yinlar: {user.get('games_played', 0)} ta (yutgan: {user.get('games_won', 0)})"
    )
    safe_send_message(message.chat.id, text, reply_markup=profile_submenu())


# =====================================
# BONUS / REFERRAL / PROMO (now under "Pul ishlash")
# =====================================
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
        safe_send_message(message.chat.id, f"❌ Bugun bonus olgansiz.\n⏰ Keyingi bonus: {hours} soat {minutes} daqiqadan so'ng")
        return

    min_bonus, max_bonus = config.get("daily_bonus_range", [100, 500])
    bonus = random.randint(int(min_bonus), int(max_bonus))
    users[user_id]["balance"] += bonus
    users[user_id]["bonus_date"] = today
    save_db()
    safe_send_sticker(message.chat.id, "money")
    safe_send_message(message.chat.id, f"🎉 Kunlik bonus!\n💰 +{bonus} so'm")


@bot.message_handler(func=lambda m: m.text == "👥 Referal")
@subscription_required
def referral_menu(message):
    user_id = str(message.from_user.id)
    me = safe_call(bot.get_me)
    me_username = me.username if me else "bot"
    ref_link = f"https://t.me/{me_username}?start={user_id}"
    text = (
        f"👥 <b>Referal dasturi</b>\n\n"
        f"👥 Referallaringiz: {users[user_id].get('referrals_count', 0)} ta\n"
        f"💰 Har bir referal uchun bonus: {int(config.get('referral_bonus', 1000)):,} so'm\n\n"
        f"🔗 Havolangiz:\n<code>{ref_link}</code>"
    )
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📢 Do'stlarga yuborish", switch_inline_query=f"Taklif havolam: {ref_link}"))
    safe_send_message(message.chat.id, text, reply_markup=markup)


@bot.message_handler(func=lambda m: m.text == "🎟 Promokod")
@subscription_required
def promo_menu(message):
    msg = safe_send_message(message.chat.id, "🎟 Promokodni kiriting:", reply_markup=back_menu())
    if msg:
        bot.register_next_step_handler(msg, process_promo)


@safe_next_step
def process_promo(message):
    if message.text == "⬅️ Ortga":
        safe_send_message(message.chat.id, "🔙 Orqaga", reply_markup=earn_submenu())
        return
    uid = str(message.from_user.id)
    code = message.text.strip().upper()
    if code not in promo_codes:
        safe_send_message(message.chat.id, "❌ Promokod noto'g'ri", reply_markup=earn_submenu())
        return
    if code in users[uid].get("used_promo", []):
        safe_send_message(message.chat.id, "❌ Bu promokod oldin ishlatilgan", reply_markup=earn_submenu())
        return
    limits = config.get("promo_limits", {}).get(code)
    if limits:
        max_uses = int(limits.get("max_uses", 0) or 0)
        used_count = int(limits.get("used_count", 0) or 0)
        if max_uses > 0 and used_count >= max_uses:
            safe_send_message(message.chat.id, "❌ Bu promokodning limiti tugagan", reply_markup=earn_submenu())
            return
        limits["used_count"] = used_count + 1
    amount = int(promo_codes[code])
    users[uid].setdefault("used_promo", []).append(code)
    users[uid]["balance"] += amount
    save_db()
    safe_send_sticker(message.chat.id, "success")
    safe_send_message(message.chat.id, f"✅ Promokod ishladi: +{amount} so'm", reply_markup=earn_submenu())


# =====================================
# MINI-GAMES (coin / dice / slot) — admin-tunable odds & multiplier
# =====================================
def _game_key_from_text(text: str) -> Optional[str]:
    try:
        for key, g in config.get("games", {}).items():
            if g.get("name") == text:
                return key
    except Exception:
        pass
    return None


@bot.message_handler(func=lambda m: m.text == "🎮 Mini-o'yinlar")
@subscription_required
def games_menu(message):
    active = [g for g in config.get("games", {}).values() if g.get("enabled", True)]
    if not active:
        safe_send_message(message.chat.id, "❌ Hozircha o'yinlar mavjud emas.", reply_markup=earn_submenu())
        return
    safe_send_message(message.chat.id, "🎮 O'yinni tanlang:", reply_markup=games_submenu())


@bot.message_handler(func=lambda m: _game_key_from_text(m.text) is not None)
@subscription_required
def game_selected(message):
    key = _game_key_from_text(message.text)
    game = config["games"][key]
    if not game.get("enabled", True):
        safe_send_message(message.chat.id, "❌ Bu o'yin hozircha o'chirilgan.", reply_markup=games_submenu())
        return
    uid = str(message.from_user.id)
    users[uid]["pending_game"] = key
    save_db()
    msg = safe_send_message(
        message.chat.id,
        f"{game['name']}\n\n💰 Balans: {users[uid]['balance']:,} so'm\n"
        f"🎯 Yutish ehtimoli: {game.get('win_chance', 0)}%\n"
        f"✖️ Koeffitsiyent: x{game.get('multiplier', 1)}\n"
        f"📉 Min stavka: {game.get('min_bet', 0):,} so'm\n"
        f"📈 Max stavka: {game.get('max_bet', 0):,} so'm\n\n"
        f"Stavka summasini kiriting:",
        reply_markup=back_menu(),
    )
    if msg:
        bot.register_next_step_handler(msg, process_game_bet, key)


@safe_next_step
def process_game_bet(message, key: str):
    if message.text == "⬅️ Ortga":
        safe_send_message(message.chat.id, "🔙 Orqaga", reply_markup=games_submenu())
        return
    uid = str(message.from_user.id)
    game = config.get("games", {}).get(key)
    if not game or not game.get("enabled", True):
        safe_send_message(message.chat.id, "❌ O'yin mavjud emas", reply_markup=games_submenu())
        return

    bet = safe_int(message.text, default=None)
    if bet is None:
        msg = safe_send_message(message.chat.id, "❌ Faqat son kiriting:")
        if msg:
            bot.register_next_step_handler(msg, process_game_bet, key)
        return

    min_bet = int(game.get("min_bet", 0))
    max_bet = int(game.get("max_bet", 0))
    if bet < min_bet or (max_bet > 0 and bet > max_bet):
        msg = safe_send_message(message.chat.id, f"❌ Stavka {min_bet:,} - {max_bet:,} so'm oralig'ida bo'lishi kerak. Qaytadan kiriting:")
        if msg:
            bot.register_next_step_handler(msg, process_game_bet, key)
        return
    if users[uid]["balance"] < bet:
        safe_send_message(message.chat.id, "❌ Balansingiz yetarli emas", reply_markup=games_submenu())
        return

    win_chance = float(game.get("win_chance", 50))
    multiplier = float(game.get("multiplier", 2))
    won = random.uniform(0, 100) < win_chance

    users[uid]["balance"] -= bet
    users[uid]["games_played"] = users[uid].get("games_played", 0) + 1
    users[uid]["total_wagered"] = users[uid].get("total_wagered", 0) + bet

    if won:
        payout = int(bet * multiplier)
        users[uid]["balance"] += payout
        users[uid]["games_won"] = users[uid].get("games_won", 0) + 1
        users[uid]["total_won"] = users[uid].get("total_won", 0) + payout
        save_db()
        safe_send_sticker(message.chat.id, "game_win")
        safe_send_message(
            message.chat.id,
            f"🎉 Siz yutdingiz!\n{game['name']}\n💰 Stavka: {bet:,} so'm\n✅ Yutuq: +{payout:,} so'm\n⚖️ Balans: {users[uid]['balance']:,} so'm",
            reply_markup=games_submenu(),
        )
    else:
        save_db()
        safe_send_sticker(message.chat.id, "game_lose")
        safe_send_message(
            message.chat.id,
            f"😔 Siz yutqazdingiz.\n{game['name']}\n💸 Stavka: -{bet:,} so'm\n⚖️ Balans: {users[uid]['balance']:,} so'm",
            reply_markup=games_submenu(),
        )


# =====================================
# LEADERBOARD (enhanced)
# =====================================
@bot.message_handler(func=lambda m: m.text == "🏆 Reyting")
@subscription_required
def leaderboard_menu(message):
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("👥 Referallar bo'yicha", callback_data="top_ref"))
    markup.add(InlineKeyboardButton("📦 Buyurtmalar bo'yicha", callback_data="top_orders"))
    markup.add(InlineKeyboardButton("💰 Balans bo'yicha", callback_data="top_balance"))
    markup.add(InlineKeyboardButton("🎮 O'yinlarda yutuq bo'yicha", callback_data="top_gamewin"))
    markup.add(InlineKeyboardButton("🎯 Mening o'rnim", callback_data="my_rank"))
    safe_send_message(message.chat.id, "🏆 Reyting turini tanlang:", reply_markup=markup)


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


def _user_rank(uid: str, field: str):
    ranking = [(u, d.get(field, 0)) for u, d in users.items()]
    ranking.sort(key=lambda x: x[1], reverse=True)
    for i, (u, val) in enumerate(ranking, start=1):
        if u == uid:
            return i, val
    return None, 0


@bot.callback_query_handler(func=lambda c: c.data in ["top_ref", "top_orders", "top_balance", "top_gamewin"])
@safe_callback_handler
def leaderboard_callback(c):
    if c.data == "top_ref":
        text = _render_top("referrals_count", "TOP referallar", "ta")
    elif c.data == "top_orders":
        text = _render_top("orders_count", "TOP buyurtmalar", "ta")
    elif c.data == "top_gamewin":
        text = _render_top("total_won", "TOP o'yin yutuqlari", "so'm")
    else:
        text = _render_top("balance", "TOP balans", "so'm")
    result = safe_edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=c.message.reply_markup)
    if result is None:
        safe_send_message(c.message.chat.id, text)
    safe_answer_callback_query(c.id)


@bot.callback_query_handler(func=lambda c: c.data == "my_rank")
@safe_callback_handler
def my_rank_callback(c):
    uid = str(c.from_user.id)
    rank_bal, bal = _user_rank(uid, "balance")
    rank_ref, ref = _user_rank(uid, "referrals_count")
    rank_ord, ordc = _user_rank(uid, "orders_count")
    text = (
        f"🎯 <b>Sizning o'rningiz</b>\n\n"
        f"💰 Balans: #{rank_bal} ({bal:,} so'm)\n"
        f"👥 Referallar: #{rank_ref} ({ref} ta)\n"
        f"📦 Buyurtmalar: #{rank_ord} ({ordc} ta)"
    )
    safe_answer_callback_query(c.id)
    safe_send_message(c.message.chat.id, text)


# =====================================
# EARN TASKS (admin-managed, unified) — accessed via Pul ishlash flow
# =====================================
def _incomplete_tasks(uid: str):
    done = users[uid].get("completed_earn_tasks", [])
    return [t for t in config.get("earn_tasks", []) if t["id"] not in done]


@bot.message_handler(func=lambda m: m.text == "📋 Vazifalar")
@subscription_required
def earn_tasks_entry(message):
    user_id = str(message.from_user.id)
    tasks_left = _incomplete_tasks(user_id)
    if not tasks_left:
        safe_send_message(message.chat.id, "✅ Hozircha barcha topshiriqlar bajarilgan yoki mavjud emas.")
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
    safe_send_message(chat_id, f"{kind_label}: {task.get('title', '')}\n{task['link']}\n\n💰 Mukofot: {task.get('reward', 0):,} so'm", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("check_earn_"))
@safe_callback_handler
def check_earn(c):
    uid = str(c.from_user.id)
    task_id = int(c.data.split("_")[-1])
    task = next((t for t in config.get("earn_tasks", []) if t["id"] == task_id), None)
    if not task:
        safe_answer_callback_query(c.id, "❌ Topshiriq topilmadi")
        return
    done = users[uid].setdefault("completed_earn_tasks", [])
    if task_id in done:
        safe_answer_callback_query(c.id, "❌ Bu topshiriq oldin bajarilgan")
        return
    if task["type"] == "channel":
        uname = task["link"].split("/")[-1]
        if not is_channel_member(f"@{uname}", c.from_user.id):
            safe_answer_callback_query(c.id, "❌ Hali obuna bo'lmagansiz")
            return
    done.append(task_id)
    reward = int(task.get("reward", 0))
    users[uid]["balance"] += reward
    save_db()
    safe_answer_callback_query(c.id, f"+{reward} so'm")
    remaining = _incomplete_tasks(uid)
    safe_call(bot.edit_message_reply_markup, c.message.chat.id, c.message.message_id, reply_markup=None)
    if remaining:
        show_earn_task(c.message.chat.id, remaining[0])
    else:
        safe_send_message(c.message.chat.id, "✅ Barcha topshiriqlar bajarildi")


@bot.callback_query_handler(func=lambda c: c.data.startswith("skip_earn_"))
@safe_callback_handler
def skip_earn(c):
    uid = str(c.from_user.id)
    current = int(c.data.split("_")[-1])
    remaining = [t for t in _incomplete_tasks(uid) if t["id"] != current]
    safe_call(bot.edit_message_reply_markup, c.message.chat.id, c.message.message_id, reply_markup=None)
    if not remaining:
        safe_answer_callback_query(c.id, "❌ Boshqa topshiriq yo'q")
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
                    try:
                        uname = task["link"].split("/")[-1]
                        if not is_channel_member(f"@{uname}", int(uid)):
                            penalty = int(task.get("penalty", 0))
                            u["balance"] = max(0, u.get("balance", 0) - penalty)
                            done.remove(tid)
                    except Exception as e:
                        logger.error(f"Recheck ichki xato (uid={uid}): {e}")
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
        safe_send_message(message.chat.id, "❌ Hozircha to'lov kartasi mavjud emas. Admin bilan bog'laning.")
        return
    markup = InlineKeyboardMarkup(row_width=1)
    for card in cards:
        markup.add(InlineKeyboardButton(f"💳 {card.get('bank', '')} — {card.get('holder', '')}", callback_data=f"topup_card_{card['id']}"))
    safe_send_message(message.chat.id, "💳 To'lov qilish uchun kartani tanlang:", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("topup_card_"))
@safe_callback_handler
def topup_card_selected(c):
    uid = ensure_user(c.from_user)
    card_id = int(c.data.split("_")[-1])
    card = next((x for x in config.get("payment_cards", []) if x["id"] == card_id), None)
    if not card:
        safe_answer_callback_query(c.id, "❌ Karta topilmadi")
        return
    min_topup = int(config.get("min_topup", 5000))
    safe_answer_callback_query(c.id)
    safe_send_message(
        c.message.chat.id,
        f"💳 Karta: <code>{card['number']}</code>\n🏦 Bank: {card.get('bank', '')}\n👤 Egasi: {card.get('holder', '')}\n\n"
        f"💰 Kartaga pul o'tkazing va o'tkazgan summangizni kiriting (min: {min_topup:,} so'm):",
    )
    msg = safe_send_message(c.message.chat.id, "Summani kiriting:", reply_markup=back_menu())
    if msg:
        bot.register_next_step_handler(msg, process_topup_amount, card_id)


@safe_next_step
def process_topup_amount(message, card_id: int):
    if message.text == "⬅️ Ortga":
        safe_send_message(message.chat.id, "🔙 Orqaga", reply_markup=profile_submenu())
        return
    uid = str(message.from_user.id)
    amount = safe_int(message.text, default=None)
    if amount is None:
        msg = safe_send_message(message.chat.id, "❌ Faqat son kiriting:")
        if msg:
            bot.register_next_step_handler(msg, process_topup_amount, card_id)
        return
    min_topup = int(config.get("min_topup", 5000))
    if amount < min_topup:
        msg = safe_send_message(message.chat.id, f"❌ Minimal summa: {min_topup:,} so'm. Qaytadan kiriting:")
        if msg:
            bot.register_next_step_handler(msg, process_topup_amount, card_id)
        return
    users[uid]["pending_topup"] = {"card_id": card_id, "amount": amount}
    save_db()
    msg = safe_send_message(message.chat.id, "🧾 Endi to'lov chekini (skrinshot) rasm ko'rinishida yuboring:", reply_markup=back_menu())
    if msg:
        bot.register_next_step_handler(msg, process_topup_receipt)


@safe_next_step
def process_topup_receipt(message):
    if getattr(message, "text", None) == "⬅️ Ortga":
        safe_send_message(message.chat.id, "🔙 Orqaga", reply_markup=profile_submenu())
        return
    uid = str(message.from_user.id)
    pending = users[uid].get("pending_topup")
    if not pending:
        safe_send_message(message.chat.id, "❌ Faol so'rov topilmadi. Qaytadan boshlang.", reply_markup=profile_submenu())
        return
    if message.content_type != "photo":
        msg = safe_send_message(message.chat.id, "❌ Iltimos, chekni rasm (screenshot) shaklida yuboring:")
        if msg:
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
    safe_send_message(message.chat.id, f"✅ So'rovingiz qabul qilindi.\n🆔 Order: #{order_id}\n⏳ Admin tomonidan tekshirilmoqda.", reply_markup=profile_submenu())

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
            except Exception as e:
                logger.debug(f"Admin fallback xato ({admin_id}): {e}")


@bot.callback_query_handler(func=lambda c: c.data.startswith("payadm_"))
@safe_callback_handler
def payadm_action(c):
    if not is_admin(c.from_user.id):
        safe_answer_callback_query(c.id, "❌ Ruxsat yo'q")
        return
    parts = c.data.split("_")
    action = parts[1]
    order_id = int(parts[2])
    order = find_order(order_id)
    if not order or order.get("kind") != "topup":
        safe_answer_callback_query(c.id, "❌ Buyurtma topilmadi")
        return

    if action == "process":
        if order.get("status") not in ("pending",):
            safe_answer_callback_query(c.id, "❌ Allaqachon ko'rilgan")
            return
        order["status"] = "processing"
        order["handled_by"] = safe_username(c.from_user)
        save_db()
        safe_answer_callback_query(c.id, "🔄 Siz ishlov berayotgan deb belgilandi")
        new_caption = (c.message.caption or "") + f"\n\n🔄 Ishlov berilmoqda: {order['handled_by']}"
        safe_edit_message_caption(new_caption, c.message.chat.id, c.message.message_id, reply_markup=c.message.reply_markup)
        return

    if order.get("status") == "completed" or order.get("status") == "rejected":
        safe_answer_callback_query(c.id, "❌ Buyurtma allaqachon yakunlangan")
        return

    if action == "approve":
        order["status"] = "completed"
        order["approved_by"] = safe_username(c.from_user)
        order["completed_date"] = datetime.now().isoformat()
        uid = order["user_id"]
        users[uid]["balance"] += int(order.get("amount", 0))
        complete_order_stats(uid)
        save_db()
        safe_send_message(int(uid), f"✅ To'lovingiz tasdiqlandi.\n💰 +{order.get('amount', 0):,} so'm balansingizga qo'shildi.")
        safe_send_sticker(int(uid), "success")
        safe_answer_callback_query(c.id, "✅ Tasdiqlandi")
        new_caption = (c.message.caption or "") + f"\n\n✅ Bajarildi: {order['approved_by']}"
        safe_edit_message_caption(new_caption, c.message.chat.id, c.message.message_id, reply_markup=None)
    elif action == "reject":
        order["status"] = "rejected"
        order["rejected_by"] = safe_username(c.from_user)
        save_db()
        safe_send_message(int(order["user_id"]), "❌ To'lovingiz rad etildi. Savol bo'lsa admin bilan bog'laning.")
        safe_answer_callback_query(c.id, "❌ Rad etildi")
        new_caption = (c.message.caption or "") + f"\n\n❌ Rad etildi: {order['rejected_by']}"
        safe_edit_message_caption(new_caption, c.message.chat.id, c.message.message_id, reply_markup=None)


# =====================================
# ADMIN: DIRECT TOP-UP (admin adds/removes balance instantly + logs to history)
# =====================================
@bot.message_handler(func=lambda m: m.text == "💵 Hisob to'ldirish (admin)" and is_admin(m.from_user.id))
@admin_required
def admin_direct_topup_entry(message):
    msg = safe_send_message(message.chat.id, "👤 Foydalanuvchi ID sini kiriting:", reply_markup=back_menu())
    if msg:
        bot.register_next_step_handler(msg, admin_direct_topup_userid)


@safe_next_step
def admin_direct_topup_userid(message):
    if message.text == "⬅️ Ortga":
        safe_send_message(message.chat.id, "🔙 Orqaga", reply_markup=admin_menu())
        return
    target_id = message.text.strip()
    if target_id not in users:
        safe_send_message(message.chat.id, "❌ Bunday foydalanuvchi topilmadi", reply_markup=admin_menu())
        return
    msg = safe_send_message(
        message.chat.id,
        f"👤 {safe_username(target_id)} | Joriy balans: {users[target_id].get('balance', 0):,} so'm\n\n"
        f"💰 Qo'shmoqchi bo'lgan summani kiriting (ayirish uchun minus bilan, masalan -1000):",
        reply_markup=back_menu(),
    )
    if msg:
        bot.register_next_step_handler(msg, admin_direct_topup_amount, target_id)


@safe_next_step
def admin_direct_topup_amount(message, target_id: str):
    if message.text == "⬅️ Ortga":
        safe_send_message(message.chat.id, "🔙 Orqaga", reply_markup=admin_menu())
        return
    if target_id not in users:
        safe_send_message(message.chat.id, "❌ Foydalanuvchi topilmadi", reply_markup=admin_menu())
        return
    amount = safe_int(message.text, default=None)
    if amount is None:
        msg = safe_send_message(message.chat.id, "❌ Faqat son kiriting:")
        if msg:
            bot.register_next_step_handler(msg, admin_direct_topup_amount, target_id)
        return
    old_balance = users[target_id].get("balance", 0)
    users[target_id]["balance"] = max(0, old_balance + amount)
    users[target_id]["admin_topups_total"] = users[target_id].get("admin_topups_total", 0) + amount
    order_id = create_order("admin_topup", target_id, {
        "amount": amount,
        "admin_id": str(message.from_user.id),
        "admin_username": safe_username(message.from_user),
        "status": "completed",
        "old_balance": old_balance,
        "new_balance": users[target_id]["balance"],
    })
    save_db()
    sign = "+" if amount >= 0 else ""
    safe_send_message(
        message.chat.id,
        f"✅ Bajarildi. Order #{order_id}\n👤 {safe_username(target_id)}\n💰 {sign}{amount:,} so'm\n"
        f"⚖️ Eski balans: {old_balance:,} → Yangi: {users[target_id]['balance']:,}",
        reply_markup=admin_menu(),
    )
    safe_send_message(
        int(target_id),
        f"💰 Administrator balansingizni o'zgartirdi.\n{sign}{amount:,} so'm\n⚖️ Yangi balans: {users[target_id]['balance']:,} so'm",
    )


# =====================================
# SERVICES / SHOP (admin managed, with category CRUD)
# =====================================
def _service_categories() -> List[str]:
    """Returns category names — prefers explicit service_categories list, falls back to derived from services."""
    explicit = [c["name"] for c in config.get("service_categories", [])]
    if explicit:
        return explicit
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
        safe_send_message(message.chat.id, "❌ Hozircha xizmatlar mavjud emas.")
        return
    markup = InlineKeyboardMarkup(row_width=1)
    for cat in cats:
        markup.add(InlineKeyboardButton(f"📦 {cat}", callback_data=f"shopcat_{cat}"))
    safe_send_message(message.chat.id, "🛍 Do'kon bo'limi:", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("shopcat_"))
@safe_callback_handler
def shop_category(c):
    category = c.data.split("_", 1)[1]
    items = [s for s in config.get("services", []) if s["category"] == category]
    markup = InlineKeyboardMarkup(row_width=1)
    for s in items:
        markup.add(InlineKeyboardButton(f"{s['name']} — {s['price']:,} so'm", callback_data=f"buyserv_{s['id']}"))
    markup.add(InlineKeyboardButton("⬅️ Ortga", callback_data="shop_back"))
    text = f"🛍 {category}"
    if not items:
        text += "\n\nHozircha bu kategoriyada mahsulot yo'q"
    result = safe_edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=markup)
    if result is None:
        safe_send_message(c.message.chat.id, text, reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data == "shop_back")
@safe_callback_handler
def shop_back(c):
    cats = _service_categories()
    markup = InlineKeyboardMarkup(row_width=1)
    for cat in cats:
        markup.add(InlineKeyboardButton(f"📦 {cat}", callback_data=f"shopcat_{cat}"))
    safe_edit_message_text("🛍 Do'kon bo'limi:", c.message.chat.id, c.message.message_id, reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("buyserv_"))
@safe_callback_handler
def buy_service(c):
    service_id = int(c.data.split("_")[-1])
    service = next((s for s in config.get("services", []) if s["id"] == service_id), None)
    if not service:
        safe_answer_callback_query(c.id, "❌ Xizmat topilmadi")
        return
    uid = str(c.from_user.id)
    if users[uid]["balance"] < service["price"]:
        safe_answer_callback_query(c.id, "❌ Balans yetarli emas")
        return
    users[uid]["pending_purchase"] = {"service_id": service_id}
    save_db()
    safe_answer_callback_query(c.id)
    desc = f"\n\nℹ️ {service.get('description')}" if service.get("description") else ""
    msg = safe_send_message(c.message.chat.id, f"📝 {service['name']} uchun ID yoki username kiriting:{desc}")
    if msg:
        bot.register_next_step_handler(msg, process_purchase_id)


@safe_next_step
def process_purchase_id(message):
    uid = str(message.from_user.id)
    pending = users[uid].get("pending_purchase")
    if not pending:
        safe_send_message(message.chat.id, "❌ Faol buyurtma topilmadi")
        return
    service = next((s for s in config.get("services", []) if s["id"] == pending["service_id"]), None)
    if not service:
        safe_send_message(message.chat.id, "❌ Xizmat topilmadi")
        users[uid].pop("pending_purchase", None)
        save_db()
        return
    if users[uid]["balance"] < service["price"]:
        safe_send_message(message.chat.id, "❌ Balans yetarli emas", reply_markup=build_main_menu(is_admin(message.from_user.id)))
        users[uid].pop("pending_purchase", None)
        save_db()
        return
    game_id = message.text.strip()
    users[uid]["balance"] -= service["price"]
    order_id = create_order("shop", uid, {
        "service_name": service["name"],
        "category": service.get("category", ""),
        "amount": service["price"],
        "game_id": game_id,
    })
    users[uid].pop("pending_purchase", None)
    save_db()
    safe_send_message(message.chat.id, f"✅ Buyurtma qabul qilindi.\n🆔 Order: #{order_id}\n📦 {service['name']}\n💰 {service['price']:,} so'm", reply_markup=build_main_menu(is_admin(message.from_user.id)))
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Bajarildi", callback_data=f"approve_order_{order_id}"),
        InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_order_{order_id}"),
    )
    caption = (
        f"🛒 <b>Yangi buyurtma so'rovi</b>\n\n"
        f"🆔 Order: #{order_id}\n"
        f"👤 {safe_username(message.from_user)}\n"
        f"🆔 <code>{uid}</code>\n"
        f"📦 Kategoriya: {service.get('category', '')}\n"
        f"📦 Xizmat: {service['name']}\n"
        f"💰 Narx: {service['price']:,} so'm\n"
        f"🎮 ID/username: {game_id}\n"
        f"📅 {now_str()}"
    )
    send_order_to_channel(caption, markup=kb)


# =====================================
# ORDERS (generic shop approve/reject) / ADMIN STATS
# =====================================
def get_admin_stats() -> Dict[str, Any]:
    today = datetime.now().strftime("%Y-%m-%d")
    total_wagered = sum(int(u.get("total_wagered", 0)) for u in users.values())
    total_game_payout = sum(int(u.get("total_won", 0)) for u in users.values())
    return {
        "total_users": len(users),
        "new_today": sum(1 for u in users.values() if str(u.get("join_date", "")).startswith(today)),
        "active_today": sum(1 for u in users.values() if str(u.get("last_active", "")).startswith(today)),
        "blocked_users": sum(1 for u in users.values() if u.get("blocked")),
        "total_balance": sum(int(u.get("balance", 0)) for u in users.values()),
        "pending_orders": sum(1 for o in orders if o.get("status") == "pending"),
        "processing_orders": sum(1 for o in orders if o.get("status") == "processing"),
        "completed_orders": sum(1 for o in orders if o.get("status") == "completed"),
        "rejected_orders": sum(1 for o in orders if o.get("status") == "rejected"),
        "total_wagered": total_wagered,
        "total_game_payout": total_game_payout,
        "house_edge_result": total_wagered - total_game_payout,
    }


@bot.message_handler(func=lambda m: m.text == "👨‍💻 Admin panel" and is_admin(m.from_user.id))
def admin_panel(message):
    try:
        s = get_admin_stats()
        safe_send_message(
            message.chat.id,
            f"👨‍💻 <b>Admin panel</b>\n\n👥 Foydalanuvchilar: {s['total_users']}\n🆕 Bugun: {s['new_today']}\n⚡ Faol: {s['active_today']}\n💰 Jami balans: {s['total_balance']:,} so'm\n📦 Pending: {s['pending_orders']}",
            reply_markup=admin_menu(),
        )
    except Exception as e:
        logger.error(f"admin_panel xato: {e}", exc_info=True)
        safe_send_message(message.chat.id, "⚠️ Xatolik yuz berdi.")


def admin_as_user_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if config.get("chat_enabled", True) and config.get("chat_link"):
        kb.add(config.get("chat_title", "💬 Chatga qo'shilish"))
    kb.add("💸 Pul ishlash", "📊 Hisobim")
    kb.add("🛍 Xizmatlar", "🏆 Reyting")
    kb.add("👨‍💻 Admin panel")
    return kb


@bot.message_handler(func=lambda m: m.text == "⬅️ Foydalanuvchi rejimi" and is_admin(m.from_user.id))
@admin_required
def switch_to_user_mode(message):
    safe_send_message(message.chat.id, "🔙 Foydalanuvchi rejimiga o'tdingiz", reply_markup=admin_as_user_menu())


@bot.message_handler(func=lambda m: m.text == "📊 Statistika" and is_admin(m.from_user.id))
@admin_required
def admin_stats(message):
    s = get_admin_stats()
    total_refs = sum(u.get("referrals_count", 0) for u in users.values())
    total_payments = sum(int(o.get("amount", 0)) for o in orders if o.get("kind") == "topup" and o.get("status") == "completed")
    total_admin_topups = sum(int(o.get("amount", 0)) for o in orders if o.get("kind") == "admin_topup")
    total_games_played = sum(u.get("games_played", 0) for u in users.values())
    total_games_won = sum(u.get("games_won", 0) for u in users.values())
    safe_send_message(
        message.chat.id,
        f"📊 <b>Batafsil statistika</b>\n\n"
        f"👥 Jami user: {s['total_users']}\n"
        f"🆕 Bugun qo'shilgan: {s['new_today']}\n"
        f"⚡ Bugun faol: {s['active_today']}\n"
        f"🚫 Bloklangan: {s['blocked_users']}\n"
        f"👥 Jami referal: {total_refs}\n\n"
        f"💰 Jami balans (barcha userlar): {s['total_balance']:,} so'm\n"
        f"📥 Kartadan to'lovlar (tasdiqlangan): {total_payments:,} so'm\n"
        f"💵 Admin orqali kiritilgan: {total_admin_topups:,} so'm\n\n"
        f"📦 Buyurtmalar — pending: {s['pending_orders']}, ishlov: {s['processing_orders']}, bajarilgan: {s['completed_orders']}, rad etilgan: {s['rejected_orders']}\n\n"
        f"🎮 O'yinlar: {total_games_played} ta o'ynalgan, {total_games_won} ta yutilgan\n"
        f"🎯 Stavkalar jami: {s['total_wagered']:,} so'm\n"
        f"🎁 Yutuqlar jami: {s['total_game_payout']:,} so'm\n"
        f"🏦 Bot foydasi (o'yinlardan): {s['house_edge_result']:,} so'm",
    )


# =====================================
# ADMIN: ORDERS (enhanced — filter by status/kind)
# =====================================
@bot.message_handler(func=lambda m: m.text == "📦 Buyurtmalar" and is_admin(m.from_user.id))
@admin_required
def admin_orders(message):
    s = get_admin_stats()
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(f"⏳ Pending ({s['pending_orders']})", callback_data="ordf_pending"),
        InlineKeyboardButton(f"🔄 Ishlov ({s['processing_orders']})", callback_data="ordf_processing"),
    )
    markup.add(
        InlineKeyboardButton(f"✅ Bajarilgan ({s['completed_orders']})", callback_data="ordf_completed"),
        InlineKeyboardButton(f"❌ Rad etilgan ({s['rejected_orders']})", callback_data="ordf_rejected"),
    )
    markup.add(InlineKeyboardButton("🛒 Shop", callback_data="ordf_kind_shop"), InlineKeyboardButton("💳 To'lov", callback_data="ordf_kind_topup"))
    markup.add(InlineKeyboardButton("💵 Admin to'ldirish", callback_data="ordf_kind_admin_topup"))
    markup.add(InlineKeyboardButton("📋 Barchasi (oxirgi 20)", callback_data="ordf_all"))
    safe_send_message(message.chat.id, f"📦 <b>Buyurtmalar boshqaruvi</b>\n\nJami buyurtmalar: {len(orders)}\nFiltrni tanlang:", reply_markup=markup)


def _render_orders_list(filtered: List[Dict[str, Any]], title: str):
    filtered = sorted(filtered, key=lambda x: x.get("date", ""), reverse=True)[:20]
    if not filtered:
        return f"📦 <b>{title}</b>\n\nBuyurtmalar topilmadi", None
    lines = [f"📦 <b>{title}</b> ({len(filtered)})"]
    markup = InlineKeyboardMarkup(row_width=1)
    for order in filtered:
        lines.append(f"\n#{order['id']} | {order.get('kind')} | {order.get('amount', 0):,} so'm | {order.get('status')} | user {order['user_id']}")
        markup.add(InlineKeyboardButton(f"Buyurtma #{order['id']}", callback_data=f"view_order_{order['id']}"))
    return "\n".join(lines), markup


@bot.callback_query_handler(func=lambda c: c.data.startswith("ordf_"))
@safe_callback_handler
def order_filter(c):
    if not is_admin(c.from_user.id):
        return
    key = c.data.split("_", 1)[1]
    if key == "all":
        text, markup = _render_orders_list(orders, "Barcha buyurtmalar")
    elif key.startswith("kind_"):
        kind = key.split("_", 1)[1]
        text, markup = _render_orders_list([o for o in orders if o.get("kind") == kind], f"Buyurtmalar: {kind}")
    else:
        text, markup = _render_orders_list([o for o in orders if o.get("status") == key], f"Buyurtmalar: {key}")
    safe_answer_callback_query(c.id)
    safe_send_message(c.message.chat.id, text, reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("view_order_"))
@safe_callback_handler
def view_order(c):
    if not is_admin(c.from_user.id):
        return
    order_id = int(c.data.split("_")[-1])
    order = find_order(order_id)
    if not order:
        safe_answer_callback_query(c.id, "❌ Buyurtma topilmadi")
        return
    text = (
        f"📦 <b>Buyurtma #{order['id']}</b>\n\n"
        f"Turi: {order.get('kind')}\n"
        f"User: {order.get('user_id')} ({safe_username(order.get('user_id'))})\n"
        f"Miqdor: {order.get('amount', 0):,} so'm\n"
        f"Holat: {order.get('status')}\n"
        f"Sana: {order.get('date')}"
    )
    if order.get("game_id"):
        text += f"\nGame ID: {order['game_id']}"
    if order.get("category"):
        text += f"\nKategoriya: {order['category']}"
    if order.get("service_name"):
        text += f"\nXizmat: {order['service_name']}"
    markup = InlineKeyboardMarkup(row_width=2)
    if order.get("status") == "pending" and order.get("kind") == "shop":
        markup.add(
            InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_order_{order_id}"),
            InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_order_{order_id}"),
        )
    safe_answer_callback_query(c.id)
    safe_send_message(c.message.chat.id, text, reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("approve_order_"))
@safe_callback_handler
def approve_order(c):
    if not is_admin(c.from_user.id):
        return
    order_id = int(c.data.split("_")[-1])
    order = find_order(order_id)
    if not order:
        safe_answer_callback_query(c.id, "❌ Buyurtma topilmadi")
        return
    if order.get("status") != "pending":
        safe_answer_callback_query(c.id, "❌ Buyurtma allaqachon ko'rilgan")
        return
    order["status"] = "completed"
    order["approved_by"] = c.from_user.id
    order["approved_date"] = datetime.now().isoformat()
    complete_order_stats(order["user_id"])
    save_db()
    safe_send_message(int(order["user_id"]), f"✅ Buyurtmangiz bajarildi!\n🆔 Order: #{order_id}")
    safe_send_sticker(int(order["user_id"]), "success")
    safe_answer_callback_query(c.id, "✅ Tasdiqlandi")
    result = safe_edit_message_text(f"✅ Buyurtma #{order_id} tasdiqlandi", c.message.chat.id, c.message.message_id)
    if result is None:
        safe_edit_message_caption(f"✅ Buyurtma #{order_id} tasdiqlandi", c.message.chat.id, c.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("reject_order_"))
@safe_callback_handler
def reject_order(c):
    if not is_admin(c.from_user.id):
        return
    order_id = int(c.data.split("_")[-1])
    order = find_order(order_id)
    if not order:
        safe_answer_callback_query(c.id, "❌ Buyurtma topilmadi")
        return
    if order.get("status") != "pending":
        safe_answer_callback_query(c.id, "❌ Buyurtma allaqachon ko'rilgan")
        return
    order["status"] = "rejected"
    order["rejected_by"] = c.from_user.id
    order["rejected_date"] = datetime.now().isoformat()
    users[order["user_id"]]["balance"] += int(order.get("amount", 0))
    save_db()
    safe_send_message(int(order["user_id"]), f"❌ Buyurtma rad etildi.\n💰 {order.get('amount', 0):,} so'm balansga qaytarildi")
    safe_answer_callback_query(c.id, "❌ Rad etildi")
    result = safe_edit_message_text(f"❌ Buyurtma #{order_id} rad etildi", c.message.chat.id, c.message.message_id)
    if result is None:
        safe_edit_message_caption(f"❌ Buyurtma #{order_id} rad etildi", c.message.chat.id, c.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data == "set_orders_channel")
@safe_callback_handler
def set_orders_channel(c):
    if not is_admin(c.from_user.id):
        return
    msg = safe_send_message(c.message.chat.id, "📢 Buyurtmalar (shop) kanalidan istalgan xabarni forward qiling, yoki kanal ID sini yuboring. Bot shu kanalda admin bo'lishi shart.")
    if msg:
        bot.register_next_step_handler(msg, process_set_orders_channel)


@safe_next_step
def process_set_orders_channel(message):
    chat_id = None
    if getattr(message, "forward_from_chat", None):
        chat_id = message.forward_from_chat.id
    else:
        chat_id = safe_int(message.text, default=None)
    if not chat_id:
        safe_send_message(message.chat.id, "❌ Kanal aniqlanmadi", reply_markup=admin_menu())
        return
    config["orders_channel_id"] = chat_id
    save_db()
    safe_send_message(chat_id, "✅ Bu kanal endi buyurtma so'rovlari uchun sozlandi.")
    safe_send_message(message.chat.id, "✅ Buyurtmalar kanali saqlandi", reply_markup=admin_menu())


# =====================================
# ADMIN: USERS (enhanced — full info + all actions)
# =====================================
@bot.message_handler(func=lambda m: m.text == "👤 Foydalanuvchilar" and is_admin(m.from_user.id))
@admin_required
def admin_users(message):
    s = get_admin_stats()
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("🔍 Foydalanuvchi qidirish", "📋 So'nggi qo'shilganlar")
    kb.add("🚫 Bloklanganlar ro'yxati", "🏆 Eng faol userlar")
    kb.add("⬅️ Ortga")
    safe_send_message(message.chat.id, f"👤 Foydalanuvchilar bo'limi\n\n👥 Jami: {s['total_users']} | 🆕 Bugun: {s['new_today']} | 🚫 Bloklangan: {s['blocked_users']}", reply_markup=kb)


@bot.message_handler(func=lambda m: m.text == "🔍 Foydalanuvchi qidirish" and is_admin(m.from_user.id))
@admin_required
def search_user(message):
    msg = safe_send_message(message.chat.id, "ID yoki username kiriting:", reply_markup=back_menu())
    if msg:
        bot.register_next_step_handler(msg, process_user_search)


@safe_next_step
def process_user_search(message):
    if message.text == "⬅️ Ortga":
        safe_send_message(message.chat.id, "🔙 Orqaga", reply_markup=admin_menu())
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
        safe_send_message(message.chat.id, "❌ Topilmadi", reply_markup=admin_menu())
        return
    if len(found) == 1:
        return show_user_info(message.chat.id, found[0])
    markup = InlineKeyboardMarkup(row_width=1)
    for uid in found:
        markup.add(InlineKeyboardButton(f"{safe_username(uid)} | {users[uid].get('balance', 0):,} so'm", callback_data=f"admin_show_user_{uid}"))
    safe_send_message(message.chat.id, "Topilgan foydalanuvchilar:", reply_markup=markup)


@bot.message_handler(func=lambda m: m.text == "📋 So'nggi qo'shilganlar" and is_admin(m.from_user.id))
@admin_required
def recent_users(message):
    ranked = sorted(users.items(), key=lambda x: x[1].get("join_date", ""), reverse=True)[:10]
    if not ranked:
        safe_send_message(message.chat.id, "❌ Foydalanuvchilar yo'q", reply_markup=admin_menu())
        return
    markup = InlineKeyboardMarkup(row_width=1)
    lines = ["📋 <b>So'nggi qo'shilgan foydalanuvchilar</b>"]
    for uid, u in ranked:
        lines.append(f"\n{safe_username(uid)} | {u.get('join_date')}")
        markup.add(InlineKeyboardButton(f"{safe_username(uid)}", callback_data=f"admin_show_user_{uid}"))
    safe_send_message(message.chat.id, "\n".join(lines), reply_markup=markup)


@bot.message_handler(func=lambda m: m.text == "🚫 Bloklanganlar ro'yxati" and is_admin(m.from_user.id))
@admin_required
def blocked_users_list(message):
    blocked = [uid for uid, u in users.items() if u.get("blocked")]
    if not blocked:
        safe_send_message(message.chat.id, "✅ Bloklangan foydalanuvchilar yo'q", reply_markup=admin_menu())
        return
    markup = InlineKeyboardMarkup(row_width=1)
    for uid in blocked[:20]:
        markup.add(InlineKeyboardButton(f"{safe_username(uid)}", callback_data=f"admin_show_user_{uid}"))
    safe_send_message(message.chat.id, f"🚫 Bloklangan foydalanuvchilar ({len(blocked)}):", reply_markup=markup)


@bot.message_handler(func=lambda m: m.text == "🏆 Eng faol userlar" and is_admin(m.from_user.id))
@admin_required
def most_active_users(message):
    ranked = sorted(users.items(), key=lambda x: x[1].get("orders_count", 0) + x[1].get("games_played", 0), reverse=True)[:10]
    markup = InlineKeyboardMarkup(row_width=1)
    lines = ["🏆 <b>Eng faol foydalanuvchilar</b>"]
    for uid, u in ranked:
        lines.append(f"\n{safe_username(uid)} | buyurtma: {u.get('orders_count', 0)} | o'yin: {u.get('games_played', 0)}")
        markup.add(InlineKeyboardButton(f"{safe_username(uid)}", callback_data=f"admin_show_user_{uid}"))
    safe_send_message(message.chat.id, "\n".join(lines), reply_markup=markup)


def show_user_info(chat_id: int, user_id: str):
    if user_id not in users:
        safe_send_message(chat_id, "❌ Foydalanuvchi topilmadi")
        return
    user = users[user_id]
    text = (
        f"👤 <b>Foydalanuvchi</b>\n\n"
        f"ID: <code>{user_id}</code>\n"
        f"Username: {user.get('username', 'Noma\'lum')}\n"
        f"Ism: {user.get('first_name', '')} {user.get('last_name', '')}\n"
        f"📅 Ro'yxat: {user.get('join_date', 'Noma\'lum')}\n"
        f"⏱ Oxirgi faollik: {user.get('last_active', 'Noma\'lum')}\n\n"
        f"💰 Balans: {user.get('balance', 0):,} so'm\n"
        f"👥 Referallar: {user.get('referrals_count', 0)}\n"
        f"🔗 Kim taklif qilgan: {safe_username(user.get('referred_by')) if user.get('referred_by') else '—'}\n"
        f"📦 Buyurtmalar: {user.get('orders_count', 0)}\n"
        f"🎮 O'yinlar: {user.get('games_played', 0)} (yutgan: {user.get('games_won', 0)})\n"
        f"🎯 Stavka jami: {user.get('total_wagered', 0):,} so'm\n"
        f"🎁 Yutuq jami: {user.get('total_won', 0):,} so'm\n"
        f"💵 Admin to'ldirishlar jami: {user.get('admin_topups_total', 0):,} so'm\n"
        f"🎟 Ishlatilgan promokodlar: {', '.join(user.get('used_promo', [])) or '—'}\n"
        f"🔔 Bildirishnoma: {'✅' if user.get('notifications', True) else '❌'}\n"
        f"🚫 Blocked: {'✅' if user.get('blocked') else '❌'}\n"
        f"👑 Admin: {'✅' if is_admin(int(user_id)) else '❌'}"
    )
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("💰 Balansni o'zgartirish", callback_data=f"admin_edit_balance_{user_id}"))
    markup.add(InlineKeyboardButton("🔒 Block/Unblock", callback_data=f"admin_toggle_block_{user_id}"))
    markup.add(InlineKeyboardButton("📦 Buyurtmalar tarixi", callback_data=f"admin_user_orders_{user_id}"))
    markup.add(InlineKeyboardButton("✉️ Xabar yuborish", callback_data=f"admin_msg_user_{user_id}"))
    markup.add(InlineKeyboardButton("🔄 Referalni tozalash", callback_data=f"admin_clear_ref_{user_id}"))
    markup.add(InlineKeyboardButton("🗑 Foydalanuvchini o'chirish", callback_data=f"admin_delete_user_{user_id}"))
    safe_send_message(chat_id, text, reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_show_user_"))
@safe_callback_handler
def admin_show_user(c):
    if not is_admin(c.from_user.id):
        return
    show_user_info(c.message.chat.id, c.data.split("_")[-1])


@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_edit_balance_"))
@safe_callback_handler
def admin_edit_balance(c):
    if not is_admin(c.from_user.id):
        return
    user_id = c.data.split("_")[-1]
    if user_id not in users:
        safe_answer_callback_query(c.id, "❌ Foydalanuvchi topilmadi")
        return
    msg = safe_send_message(c.message.chat.id, f"Yangi balansni kiriting ({users[user_id].get('balance', 0):,}):")
    if msg:
        bot.register_next_step_handler(msg, lambda m: process_balance_edit(m, user_id))


@safe_next_step
def process_balance_edit(message, user_id: str):
    amount = safe_int(message.text, default=None)
    if amount is None:
        safe_send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
        return
    if user_id not in users:
        safe_send_message(message.chat.id, "❌ Foydalanuvchi topilmadi", reply_markup=admin_menu())
        return
    old = users[user_id].get("balance", 0)
    users[user_id]["balance"] = amount
    save_db()
    safe_send_message(message.chat.id, f"✅ O'zgartirildi: {old:,} -> {amount:,}", reply_markup=admin_menu())
    safe_send_message(int(user_id), f"💰 Admin balansingizni o'zgartirdi.\nEski: {old:,}\nYangi: {amount:,}")


@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_toggle_block_"))
@safe_callback_handler
def admin_toggle_block(c):
    if not is_admin(c.from_user.id):
        return
    user_id = c.data.split("_")[-1]
    if user_id not in users:
        safe_answer_callback_query(c.id, "❌ Foydalanuvchi topilmadi")
        return
    users[user_id]["blocked"] = not users[user_id].get("blocked", False)
    save_db()
    state = "bloklandi" if users[user_id]["blocked"] else "blokdan chiqarildi"
    safe_answer_callback_query(c.id, f"✅ {state}")
    safe_send_message(int(user_id), f"ℹ️ Siz {state}")
    show_user_info(c.message.chat.id, user_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_user_orders_"))
@safe_callback_handler
def admin_user_orders(c):
    if not is_admin(c.from_user.id):
        return
    user_id = c.data.split("_")[-1]
    my_orders = sorted([o for o in orders if o.get("user_id") == user_id], key=lambda x: x.get("date", ""), reverse=True)[:15]
    if not my_orders:
        safe_answer_callback_query(c.id, "❌ Buyurtmalar yo'q")
        return
    lines = [f"📦 <b>{safe_username(user_id)} buyurtmalari</b>"]
    for o in my_orders:
        lines.append(f"\n#{o['id']} | {o.get('kind')} | {o.get('amount', 0):,} so'm | {o.get('status')}")
    safe_answer_callback_query(c.id)
    safe_send_message(c.message.chat.id, "\n".join(lines))


@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_msg_user_"))
@safe_callback_handler
def admin_msg_user(c):
    if not is_admin(c.from_user.id):
        return
    user_id = c.data.split("_")[-1]
    msg = safe_send_message(c.message.chat.id, f"✉️ {safe_username(user_id)} ga yubormoqchi bo'lgan xabarni yozing:")
    if msg:
        bot.register_next_step_handler(msg, lambda m: send_admin_reply(m, user_id))


@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_clear_ref_"))
@safe_callback_handler
def admin_clear_ref(c):
    if not is_admin(c.from_user.id):
        return
    user_id = c.data.split("_")[-1]
    if user_id not in users:
        safe_answer_callback_query(c.id, "❌ Foydalanuvchi topilmadi")
        return
    users[user_id]["referred_by"] = None
    save_db()
    safe_answer_callback_query(c.id, "✅ Referal tozalandi")
    show_user_info(c.message.chat.id, user_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_delete_user_"))
@safe_callback_handler
def admin_delete_user_confirm(c):
    if not is_admin(c.from_user.id):
        return
    user_id = c.data.split("_")[-1]
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("✅ Ha, o'chirish", callback_data=f"admin_delete_confirm_{user_id}"),
        InlineKeyboardButton("❌ Bekor qilish", callback_data=f"admin_show_user_{user_id}"),
    )
    safe_call(bot.edit_message_reply_markup, c.message.chat.id, c.message.message_id, reply_markup=markup)
    safe_answer_callback_query(c.id, "⚠️ Tasdiqlang")


@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_delete_confirm_"))
@safe_callback_handler
def admin_delete_user(c):
    if not is_superadmin(c.from_user.id):
        safe_answer_callback_query(c.id, "❌ Faqat super admin o'chira oladi")
        return
    user_id = c.data.split("_", 1)[1]
    users.pop(user_id, None)
    save_db()
    safe_answer_callback_query(c.id, "✅ Foydalanuvchi o'chirildi")
    safe_edit_message_text(f"🗑 Foydalanuvchi <code>{user_id}</code> o'chirildi", c.message.chat.id, c.message.message_id)


# =====================================
# ADMIN: PAYMENT CARDS (enhanced)
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
    orders_channel = config.get("orders_channel_id")
    text.append(f"\n\n📢 To'lov (chek) kanali: {channel if channel else 'sozlanmagan'}")
    text.append(f"📢 Buyurtma (shop) kanali: {orders_channel if orders_channel else 'sozlanmagan'}")
    text.append(f"💵 Minimal to'ldirish: {int(config.get('min_topup', 5000)):,} so'm")
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("➕ Karta qo'shish", callback_data="add_card"))
    if cards:
        markup.add(InlineKeyboardButton("✏️ Kartani tahrirlash", callback_data="edit_card"))
        markup.add(InlineKeyboardButton("❌ Kartani o'chirish", callback_data="remove_card"))
    markup.add(InlineKeyboardButton("📢 To'lov (chek) kanalini sozlash", callback_data="set_payment_channel"))
    markup.add(InlineKeyboardButton("📢 Buyurtma (shop) kanalini sozlash", callback_data="set_orders_channel"))
    markup.add(InlineKeyboardButton("💵 Minimal summani sozlash", callback_data="set_min_topup"))
    safe_send_message(message.chat.id, "\n".join(text), reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data == "add_card")
@safe_callback_handler
def add_card(c):
    if not is_admin(c.from_user.id):
        return
    msg = safe_send_message(c.message.chat.id, "💳 Karta raqamini kiriting:")
    if msg:
        bot.register_next_step_handler(msg, process_add_card_number)


@safe_next_step
def process_add_card_number(message):
    number = message.text.strip()
    msg = safe_send_message(message.chat.id, "🏦 Bank nomini kiriting:")
    if msg:
        bot.register_next_step_handler(msg, process_add_card_bank, number)


@safe_next_step
def process_add_card_bank(message, number: str):
    bank = message.text.strip()
    msg = safe_send_message(message.chat.id, "👤 Karta egasining ismini kiriting:")
    if msg:
        bot.register_next_step_handler(msg, process_add_card_holder, number, bank)


@safe_next_step
def process_add_card_holder(message, number: str, bank: str):
    holder = message.text.strip()
    cards = config.setdefault("payment_cards", [])
    cards.append({"id": new_id(cards), "number": number, "bank": bank, "holder": holder})
    save_db()
    safe_send_message(message.chat.id, "✅ Karta qo'shildi", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data == "edit_card")
@safe_callback_handler
def edit_card(c):
    if not is_admin(c.from_user.id):
        return
    cards = config.get("payment_cards", [])
    markup = InlineKeyboardMarkup(row_width=1)
    for card in cards:
        markup.add(InlineKeyboardButton(f"{card['bank']} — {card['number']}", callback_data=f"editcard_{card['id']}"))
    safe_send_message(c.message.chat.id, "Tahrirlash uchun tanlang:", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("editcard_"))
@safe_callback_handler
def editcard_pick(c):
    if not is_admin(c.from_user.id):
        return
    card_id = int(c.data.split("_")[-1])
    msg = safe_send_message(c.message.chat.id, "Yangi karta raqamini kiriting:")
    if msg:
        bot.register_next_step_handler(msg, process_editcard_number, card_id)


@safe_next_step
def process_editcard_number(message, card_id: int):
    number = message.text.strip()
    msg = safe_send_message(message.chat.id, "Yangi bank nomini kiriting:")
    if msg:
        bot.register_next_step_handler(msg, process_editcard_bank, card_id, number)


@safe_next_step
def process_editcard_bank(message, card_id: int, number: str):
    bank = message.text.strip()
    msg = safe_send_message(message.chat.id, "Yangi karta egasi ismini kiriting:")
    if msg:
        bot.register_next_step_handler(msg, process_editcard_holder, card_id, number, bank)


@safe_next_step
def process_editcard_holder(message, card_id: int, number: str, bank: str):
    holder = message.text.strip()
    for c_ in config.get("payment_cards", []):
        if c_["id"] == card_id:
            c_.update({"number": number, "bank": bank, "holder": holder})
    save_db()
    safe_send_message(message.chat.id, "✅ Karta yangilandi", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data == "remove_card")
@safe_callback_handler
def remove_card(c):
    if not is_admin(c.from_user.id):
        return
    cards = config.get("payment_cards", [])
    markup = InlineKeyboardMarkup(row_width=1)
    for card in cards:
        markup.add(InlineKeyboardButton(f"{card['bank']} — {card['number']}", callback_data=f"delete_card_{card['id']}"))
    safe_send_message(c.message.chat.id, "O'chirish uchun tanlang:", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("delete_card_"))
@safe_callback_handler
def delete_card(c):
    if not is_admin(c.from_user.id):
        return
    card_id = int(c.data.split("_")[-1])
    config["payment_cards"] = [x for x in config.get("payment_cards", []) if x["id"] != card_id]
    save_db()
    safe_answer_callback_query(c.id, "✅ O'chirildi")


@bot.callback_query_handler(func=lambda c: c.data == "set_payment_channel")
@safe_callback_handler
def set_payment_channel(c):
    if not is_admin(c.from_user.id):
        return
    msg = safe_send_message(c.message.chat.id, "📢 To'lov kanalidan istalgan xabarni forward qiling, yoki kanal ID sini yuboring (masalan -1001234567890). Bot shu kanalda admin bo'lishi shart.")
    if msg:
        bot.register_next_step_handler(msg, process_set_payment_channel)


@safe_next_step
def process_set_payment_channel(message):
    chat_id = None
    if getattr(message, "forward_from_chat", None):
        chat_id = message.forward_from_chat.id
    else:
        chat_id = safe_int(message.text, default=None)
    if not chat_id:
        safe_send_message(message.chat.id, "❌ Kanal aniqlanmadi", reply_markup=admin_menu())
        return
    config["payment_channel_id"] = chat_id
    save_db()
    safe_send_message(chat_id, "✅ Bu kanal endi to'lov so'rovlari uchun sozlandi.")
    safe_send_message(message.chat.id, "✅ To'lov kanali saqlandi", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data == "set_min_topup")
@safe_callback_handler
def set_min_topup(c):
    if not is_admin(c.from_user.id):
        return
    msg = safe_send_message(c.message.chat.id, "💵 Minimal to'ldirish summasini kiriting:")
    if msg:
        bot.register_next_step_handler(msg, process_set_min_topup)


@safe_next_step
def process_set_min_topup(message):
    amount = safe_int(message.text, default=None)
    if amount is None:
        safe_send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
        return
    config["min_topup"] = amount
    save_db()
    safe_send_message(message.chat.id, "✅ Saqlandi", reply_markup=admin_menu())


# =====================================
# ADMIN: SERVICES (categories CRUD + products CRUD)
# =====================================
@bot.message_handler(func=lambda m: m.text == "🛠 Xizmatlar" and is_admin(m.from_user.id))
@admin_required
def manage_services(message):
    categories = config.get("service_categories", [])
    services = config.get("services", [])
    text = ["🛠 <b>Xizmatlar boshqaruvi</b>\n"]
    if categories:
        text.append("📦 <b>Kategoriyalar:</b>")
        for cat in categories:
            count = sum(1 for s in services if s["category"] == cat["name"])
            text.append(f"• {cat['name']} ({count} mahsulot)")
    else:
        text.append("Hozircha kategoriya yo'q")
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("➕ Kategoriya qo'shish", callback_data="add_category"))
    if categories:
        markup.add(InlineKeyboardButton("✏️ Kategoriyani tahrirlash", callback_data="edit_category"))
        markup.add(InlineKeyboardButton("❌ Kategoriyani o'chirish", callback_data="remove_category"))
        markup.add(InlineKeyboardButton("📦 Mahsulotlarni boshqarish", callback_data="manage_products"))
    safe_send_message(message.chat.id, "\n".join(text), reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data == "add_category")
@safe_callback_handler
def add_category(c):
    if not is_admin(c.from_user.id):
        return
    msg = safe_send_message(c.message.chat.id, "📦 Yangi kategoriya nomini kiriting:")
    if msg:
        bot.register_next_step_handler(msg, process_add_category)


@safe_next_step
def process_add_category(message):
    name = message.text.strip()
    cats = config.setdefault("service_categories", [])
    if any(c["name"] == name for c in cats):
        safe_send_message(message.chat.id, "❌ Bu kategoriya allaqachon mavjud", reply_markup=admin_menu())
        return
    cats.append({"id": new_id(cats), "name": name})
    save_db()
    safe_send_message(message.chat.id, "✅ Kategoriya qo'shildi", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data == "edit_category")
@safe_callback_handler
def edit_category(c):
    if not is_admin(c.from_user.id):
        return
    cats = config.get("service_categories", [])
    markup = InlineKeyboardMarkup(row_width=1)
    for cat in cats:
        markup.add(InlineKeyboardButton(cat["name"], callback_data=f"editcat_{cat['id']}"))
    safe_send_message(c.message.chat.id, "Tahrirlash uchun tanlang:", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("editcat_"))
@safe_callback_handler
def editcat_pick(c):
    if not is_admin(c.from_user.id):
        return
    cat_id = int(c.data.split("_")[-1])
    msg = safe_send_message(c.message.chat.id, "Yangi kategoriya nomini kiriting:")
    if msg:
        bot.register_next_step_handler(msg, process_editcat, cat_id)


@safe_next_step
def process_editcat(message, cat_id: int):
    new_name = message.text.strip()
    cats = config.get("service_categories", [])
    old_name = None
    for cat in cats:
        if cat["id"] == cat_id:
            old_name = cat["name"]
            cat["name"] = new_name
    if old_name:
        for s in config.get("services", []):
            if s["category"] == old_name:
                s["category"] = new_name
    save_db()
    safe_send_message(message.chat.id, "✅ Kategoriya yangilandi", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data == "remove_category")
@safe_callback_handler
def remove_category(c):
    if not is_admin(c.from_user.id):
        return
    cats = config.get("service_categories", [])
    markup = InlineKeyboardMarkup(row_width=1)
    for cat in cats:
        markup.add(InlineKeyboardButton(cat["name"], callback_data=f"delcat_{cat['id']}"))
    safe_send_message(c.message.chat.id, "O'chirish uchun tanlang (mahsulotlar ham o'chadi):", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("delcat_"))
@safe_callback_handler
def delcat(c):
    if not is_admin(c.from_user.id):
        return
    cat_id = int(c.data.split("_")[-1])
    cats = config.get("service_categories", [])
    cat = next((x for x in cats if x["id"] == cat_id), None)
    if cat:
        config["services"] = [s for s in config.get("services", []) if s["category"] != cat["name"]]
        config["service_categories"] = [x for x in cats if x["id"] != cat_id]
        save_db()
    safe_answer_callback_query(c.id, "✅ O'chirildi")


@bot.callback_query_handler(func=lambda c: c.data == "manage_products")
@safe_callback_handler
def manage_products(c):
    if not is_admin(c.from_user.id):
        return
    cats = config.get("service_categories", [])
    markup = InlineKeyboardMarkup(row_width=1)
    for cat in cats:
        markup.add(InlineKeyboardButton(f"📦 {cat['name']}", callback_data=f"prodcat_{cat['name']}"))
    safe_send_message(c.message.chat.id, "Qaysi kategoriya mahsulotlarini boshqarasiz?", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("prodcat_"))
@safe_callback_handler
def prodcat_view(c):
    if not is_admin(c.from_user.id):
        return
    category = c.data.split("_", 1)[1]
    items = [s for s in config.get("services", []) if s["category"] == category]
    text = [f"📦 <b>{category}</b>"]
    for s in items:
        desc = f" — {s.get('description')}" if s.get("description") else ""
        text.append(f"\n#{s['id']} {s['name']} — {s['price']:,} so'm{desc}")
    if not items:
        text.append("\nMahsulot yo'q")
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("➕ Mahsulot qo'shish", callback_data=f"addprod_{category}"))
    if items:
        markup.add(InlineKeyboardButton("✏️ Narxni/nomni tahrirlash", callback_data=f"editprodmenu_{category}"))
        markup.add(InlineKeyboardButton("❌ Mahsulotni o'chirish", callback_data=f"delprodmenu_{category}"))
    safe_send_message(c.message.chat.id, "\n".join(text), reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("addprod_"))
@safe_callback_handler
def add_service(c):
    if not is_admin(c.from_user.id):
        return
    category = c.data.split("_", 1)[1]
    msg = safe_send_message(c.message.chat.id, "📝 Mahsulot nomini kiriting:")
    if msg:
        bot.register_next_step_handler(msg, process_add_service_name, category)


@safe_next_step
def process_add_service_name(message, category: str):
    name = message.text.strip()
    msg = safe_send_message(message.chat.id, "💰 Narxini kiriting (so'm):")
    if msg:
        bot.register_next_step_handler(msg, process_add_service_price, category, name)


@safe_next_step
def process_add_service_price(message, category: str, name: str):
    price = safe_int(message.text, default=None)
    if price is None:
        safe_send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
        return
    msg = safe_send_message(message.chat.id, "📝 Qo'shimcha izoh kiriting (ixtiyoriy, o'tkazib yuborish uchun '-' yozing):")
    if msg:
        bot.register_next_step_handler(msg, process_add_service_desc, category, name, price)


@safe_next_step
def process_add_service_desc(message, category: str, name: str, price: int):
    desc = message.text.strip()
    if desc == "-":
        desc = ""
    services = config.setdefault("services", [])
    services.append({"id": new_id(services), "category": category, "name": name, "price": price, "description": desc})
    if not any(cc["name"] == category for cc in config.get("service_categories", [])):
        config.setdefault("service_categories", []).append({"id": new_id(config["service_categories"]), "name": category})
    save_db()
    safe_send_message(message.chat.id, "✅ Mahsulot qo'shildi", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data.startswith("editprodmenu_"))
@safe_callback_handler
def editprodmenu(c):
    if not is_admin(c.from_user.id):
        return
    category = c.data.split("_", 1)[1]
    items = [s for s in config.get("services", []) if s["category"] == category]
    markup = InlineKeyboardMarkup(row_width=1)
    for s in items:
        markup.add(InlineKeyboardButton(f"{s['name']} ({s['price']:,})", callback_data=f"editprice_{s['id']}"))
    safe_send_message(c.message.chat.id, "Tahrirlash uchun tanlang:", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("editprice_"))
@safe_callback_handler
def editprice(c):
    if not is_admin(c.from_user.id):
        return
    service_id = int(c.data.split("_")[-1])
    msg = safe_send_message(c.message.chat.id, "📝 Yangi nomni kiriting (o'zgartirmaslik uchun '-'):")
    if msg:
        bot.register_next_step_handler(msg, process_editname, service_id)


@safe_next_step
def process_editname(message, service_id: int):
    name = message.text.strip()
    msg = safe_send_message(message.chat.id, "💰 Yangi narxni kiriting:")
    if msg:
        bot.register_next_step_handler(msg, process_editprice, service_id, name)


@safe_next_step
def process_editprice(message, service_id: int, name: str):
    price = safe_int(message.text, default=None)
    if price is None:
        safe_send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
        return
    for s in config.get("services", []):
        if s["id"] == service_id:
            if name != "-":
                s["name"] = name
            s["price"] = price
    save_db()
    safe_send_message(message.chat.id, "✅ Saqlandi", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data.startswith("delprodmenu_"))
@safe_callback_handler
def delprodmenu(c):
    if not is_admin(c.from_user.id):
        return
    category = c.data.split("_", 1)[1]
    items = [s for s in config.get("services", []) if s["category"] == category]
    markup = InlineKeyboardMarkup(row_width=1)
    for s in items:
        markup.add(InlineKeyboardButton(f"{s['name']}", callback_data=f"delservice_{s['id']}"))
    safe_send_message(c.message.chat.id, "O'chirish uchun tanlang:", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("delservice_"))
@safe_callback_handler
def delservice(c):
    if not is_admin(c.from_user.id):
        return
    service_id = int(c.data.split("_")[-1])
    config["services"] = [s for s in config.get("services", []) if s["id"] != service_id]
    save_db()
    safe_answer_callback_query(c.id, "✅ O'chirildi")


# =====================================
# ADMIN: REQUIRED CHANNELS (enhanced — shows progress toward auto-remove)
# =====================================
@bot.message_handler(func=lambda m: m.text == "📝 Majburiy kanallar" and is_admin(m.from_user.id))
@admin_required
def manage_required_channels(message):
    required = config.get("required_channels", [])
    lines = ["🔐 <b>Majburiy kanallar</b>"]
    for i, ch in enumerate(required, start=1):
        thr = int(ch.get("auto_remove_at", 0) or 0)
        confirmed = int(ch.get("confirmed_count", 0))
        if thr:
            remaining = max(0, thr - confirmed)
            progress = f"{confirmed}/{thr} tasdiqlangan (yana {remaining} tadan keyin o'chadi)"
        else:
            progress = f"{confirmed} ta tasdiqlangan (cheklanmagan)"
        lines.append(f"\n{i}. {ch.get('title')} - {ch.get('username')}\n   📊 {progress}")
    if not required:
        lines.append("\nHozircha kanal yo'q")
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("➕ Qo'shish", callback_data="add_required_channel"))
    if required:
        markup.add(InlineKeyboardButton("✏️ Tahrirlash", callback_data="edit_required_channel"))
        markup.add(InlineKeyboardButton("❌ O'chirish", callback_data="remove_required_channel"))
        markup.add(InlineKeyboardButton("🔢 Avto-o'chirish limitini sozlash", callback_data="set_autoremove"))
        markup.add(InlineKeyboardButton("🔄 Hisoblagichni nolga tushirish", callback_data="reset_channel_count"))
    safe_send_message(message.chat.id, "\n".join(lines), reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data == "add_required_channel")
@safe_callback_handler
def add_required_channel(c):
    if not is_admin(c.from_user.id):
        return
    msg = safe_send_message(c.message.chat.id, "Format: @username - Title")
    if msg:
        bot.register_next_step_handler(msg, process_add_required_channel)


@safe_next_step
def process_add_required_channel(message):
    raw = message.text.strip()
    parts = raw.split(" - ", 1)
    if len(parts) != 2:
        safe_send_message(message.chat.id, "❌ Format noto'g'ri", reply_markup=admin_menu())
        return
    username, title = parts[0].strip(), parts[1].strip()
    if not username.startswith("@"):
        username = "@" + username
    config.setdefault("required_channels", []).append({"username": username, "title": title, "auto_remove_at": 0, "confirmed_count": 0})
    save_db()
    safe_send_message(message.chat.id, "✅ Qo'shildi", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data == "edit_required_channel")
@safe_callback_handler
def edit_required_channel(c):
    if not is_admin(c.from_user.id):
        return
    required = config.get("required_channels", [])
    markup = InlineKeyboardMarkup(row_width=1)
    for i, ch in enumerate(required):
        markup.add(InlineKeyboardButton(f"{ch['title']}", callback_data=f"editreqch_{i}"))
    safe_send_message(c.message.chat.id, "Tahrirlash uchun tanlang:", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("editreqch_"))
@safe_callback_handler
def editreqch_pick(c):
    if not is_admin(c.from_user.id):
        return
    idx = int(c.data.split("_")[-1])
    msg = safe_send_message(c.message.chat.id, "Yangi format: @username - Title")
    if msg:
        bot.register_next_step_handler(msg, process_editreqch, idx)


@safe_next_step
def process_editreqch(message, idx: int):
    raw = message.text.strip()
    parts = raw.split(" - ", 1)
    if len(parts) != 2:
        safe_send_message(message.chat.id, "❌ Format noto'g'ri", reply_markup=admin_menu())
        return
    username, title = parts[0].strip(), parts[1].strip()
    if not username.startswith("@"):
        username = "@" + username
    required = config.get("required_channels", [])
    if 0 <= idx < len(required):
        required[idx]["username"] = username
        required[idx]["title"] = title
        save_db()
    safe_send_message(message.chat.id, "✅ Yangilandi", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data == "remove_required_channel")
@safe_callback_handler
def remove_required_channel(c):
    if not is_admin(c.from_user.id):
        return
    required = config.get("required_channels", [])
    markup = InlineKeyboardMarkup(row_width=1)
    for i, ch in enumerate(required):
        markup.add(InlineKeyboardButton(f"{ch['title']}", callback_data=f"delreqch_{i}"))
    safe_send_message(c.message.chat.id, "O'chirish uchun tanlang:", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("delreqch_"))
@safe_callback_handler
def delreqch(c):
    if not is_admin(c.from_user.id):
        return
    idx = int(c.data.split("_")[-1])
    required = config.get("required_channels", [])
    if 0 <= idx < len(required):
        required.pop(idx)
        config["required_channels"] = required
        save_db()
    safe_answer_callback_query(c.id, "✅ O'chirildi")


@bot.callback_query_handler(func=lambda c: c.data == "set_autoremove")
@safe_callback_handler
def set_autoremove(c):
    if not is_admin(c.from_user.id):
        return
    required = config.get("required_channels", [])
    markup = InlineKeyboardMarkup(row_width=1)
    for i, ch in enumerate(required):
        markup.add(InlineKeyboardButton(f"{ch['title']}", callback_data=f"autoremove_{i}"))
    safe_send_message(c.message.chat.id, "Qaysi kanal uchun limit belgilaysiz?", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("autoremove_"))
@safe_callback_handler
def autoremove_pick(c):
    if not is_admin(c.from_user.id):
        return
    idx = int(c.data.split("_")[-1])
    msg = safe_send_message(c.message.chat.id, "Nechta tasdiqlangan obunachidan keyin kanal avtomatik o'chirilsin? (0 = cheksiz):")
    if msg:
        bot.register_next_step_handler(msg, process_autoremove, idx)


@safe_next_step
def process_autoremove(message, idx: int):
    threshold = safe_int(message.text, default=None)
    if threshold is None:
        safe_send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
        return
    required = config.get("required_channels", [])
    if 0 <= idx < len(required):
        required[idx]["auto_remove_at"] = threshold
        save_db()
    safe_send_message(message.chat.id, "✅ Saqlandi", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data == "reset_channel_count")
@safe_callback_handler
def reset_channel_count(c):
    if not is_admin(c.from_user.id):
        return
    required = config.get("required_channels", [])
    markup = InlineKeyboardMarkup(row_width=1)
    for i, ch in enumerate(required):
        markup.add(InlineKeyboardButton(f"{ch['title']}", callback_data=f"resetcount_{i}"))
    safe_send_message(c.message.chat.id, "Qaysi kanal hisoblagichini nollaymiz?", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("resetcount_"))
@safe_callback_handler
def resetcount(c):
    if not is_admin(c.from_user.id):
        return
    idx = int(c.data.split("_")[-1])
    required = config.get("required_channels", [])
    if 0 <= idx < len(required):
        required[idx]["confirmed_count"] = 0
        save_db()
    safe_answer_callback_query(c.id, "✅ Nollandi")


# =====================================
# ADMIN: EARN TASKS (enhanced)
# =====================================
@bot.message_handler(func=lambda m: m.text == "💼 Pul ishlash vazifalari" and is_admin(m.from_user.id))
@admin_required
def manage_earn_tasks(message):
    tasks = config.get("earn_tasks", [])
    lines = ["💼 <b>Pul ishlash vazifalari</b>"]
    for t in tasks:
        completed_by = sum(1 for u in users.values() if t["id"] in u.get("completed_earn_tasks", []))
        lines.append(f"\n#{t['id']} [{t['type']}] {t.get('title','')} — mukofot: {t.get('reward',0):,}, jarima: {t.get('penalty',0):,}\n   ✅ Bajarganlar: {completed_by} ta")
    if not tasks:
        lines.append("\nHozircha vazifa yo'q")
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("➕ Vazifa qo'shish", callback_data="add_earn_task"))
    if tasks:
        markup.add(InlineKeyboardButton("✏️ Vazifani tahrirlash", callback_data="edit_earn_task"))
        markup.add(InlineKeyboardButton("❌ Vazifani o'chirish", callback_data="remove_earn_task"))
    safe_send_message(message.chat.id, "\n".join(lines), reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data == "add_earn_task")
@safe_callback_handler
def add_earn_task(c):
    if not is_admin(c.from_user.id):
        return
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📢 Kanal", callback_data="earntype_channel"),
        InlineKeyboardButton("👁 Post", callback_data="earntype_post"),
    )
    safe_send_message(c.message.chat.id, "Vazifa turini tanlang:", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("earntype_"))
@safe_callback_handler
def earntype_pick(c):
    if not is_admin(c.from_user.id):
        return
    task_type = c.data.split("_")[-1]
    msg = safe_send_message(c.message.chat.id, "Sarlavha (nom) kiriting:")
    if msg:
        bot.register_next_step_handler(msg, process_earn_title, task_type)


@safe_next_step
def process_earn_title(message, task_type: str):
    title = message.text.strip()
    msg = safe_send_message(message.chat.id, "Link kiriting (https://t.me/...):")
    if msg:
        bot.register_next_step_handler(msg, process_earn_link, task_type, title)


@safe_next_step
def process_earn_link(message, task_type: str, title: str):
    link = message.text.strip()
    msg = safe_send_message(message.chat.id, "💰 Mukofot summasini kiriting (bajarganda beriladi):")
    if msg:
        bot.register_next_step_handler(msg, process_earn_reward, task_type, title, link)


@safe_next_step
def process_earn_reward(message, task_type: str, title: str, link: str):
    reward = safe_int(message.text, default=None)
    if reward is None:
        safe_send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
        return
    msg = safe_send_message(message.chat.id, "⚠️ Agar kanal bo'lsa: keyinchalik obunadan chiqib ketsa qancha balansdan ayiriladi? (0 = ayirilmasin):")
    if msg:
        bot.register_next_step_handler(msg, process_earn_penalty, task_type, title, link, reward)


@safe_next_step
def process_earn_penalty(message, task_type: str, title: str, link: str, reward: int):
    penalty = safe_int(message.text, default=None)
    if penalty is None:
        safe_send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
        return
    tasks = config.setdefault("earn_tasks", [])
    tasks.append({"id": new_id(tasks), "type": task_type, "title": title, "link": link, "reward": reward, "penalty": penalty})
    save_db()
    safe_send_message(message.chat.id, "✅ Vazifa qo'shildi", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data == "edit_earn_task")
@safe_callback_handler
def edit_earn_task(c):
    if not is_admin(c.from_user.id):
        return
    tasks = config.get("earn_tasks", [])
    markup = InlineKeyboardMarkup(row_width=1)
    for t in tasks:
        markup.add(InlineKeyboardButton(f"{t.get('title','')}", callback_data=f"editearn_{t['id']}"))
    safe_send_message(c.message.chat.id, "Tahrirlash uchun tanlang:", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("editearn_"))
@safe_callback_handler
def editearn_pick(c):
    if not is_admin(c.from_user.id):
        return
    task_id = int(c.data.split("_")[-1])
    msg = safe_send_message(c.message.chat.id, "Yangi mukofot summasini kiriting:")
    if msg:
        bot.register_next_step_handler(msg, process_edit_earn_reward, task_id)


@safe_next_step
def process_edit_earn_reward(message, task_id: int):
    reward = safe_int(message.text, default=None)
    if reward is None:
        safe_send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
        return
    for t in config.get("earn_tasks", []):
        if t["id"] == task_id:
            t["reward"] = reward
    save_db()
    safe_send_message(message.chat.id, "✅ Yangilandi", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data == "remove_earn_task")
@safe_callback_handler
def remove_earn_task(c):
    if not is_admin(c.from_user.id):
        return
    tasks = config.get("earn_tasks", [])
    markup = InlineKeyboardMarkup(row_width=1)
    for t in tasks:
        markup.add(InlineKeyboardButton(f"{t.get('title','')}", callback_data=f"delearntask_{t['id']}"))
    safe_send_message(c.message.chat.id, "O'chirish uchun tanlang:", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("delearntask_"))
@safe_callback_handler
def delearntask(c):
    if not is_admin(c.from_user.id):
        return
    task_id = int(c.data.split("_")[-1])
    config["earn_tasks"] = [t for t in config.get("earn_tasks", []) if t["id"] != task_id]
    save_db()
    safe_answer_callback_query(c.id, "✅ O'chirildi")


# =====================================
# ADMIN: PROMO CODES (enhanced — with usage limits)
# =====================================
@bot.message_handler(func=lambda m: m.text == "🎟 Promokodlar" and is_admin(m.from_user.id))
@admin_required
def manage_promo(message):
    lines = ["🎟 <b>Promokodlar</b>"]
    limits = config.get("promo_limits", {})
    for code, amount in promo_codes.items():
        lim = limits.get(code)
        if lim:
            max_uses = int(lim.get("max_uses", 0) or 0)
            used = int(lim.get("used_count", 0) or 0)
            lim_text = f" | limit: {used}/{max_uses}" if max_uses > 0 else " | limit: cheksiz"
        else:
            lim_text = " | limit: cheksiz"
        lines.append(f"\n{code} — {amount:,} so'm{lim_text}")
    if not promo_codes:
        lines.append("\nHozircha promokod yo'q")
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("➕ Qo'shish", callback_data="add_promo"))
    if promo_codes:
        markup.add(InlineKeyboardButton("🔢 Limit belgilash", callback_data="set_promo_limit"))
        markup.add(InlineKeyboardButton("❌ O'chirish", callback_data="remove_promo"))
    safe_send_message(message.chat.id, "\n".join(lines), reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data == "add_promo")
@safe_callback_handler
def add_promo(c):
    if not is_admin(c.from_user.id):
        return
    msg = safe_send_message(c.message.chat.id, "Format: KOD - summa (masalan: BONUS100 - 100)")
    if msg:
        bot.register_next_step_handler(msg, process_add_promo)


@safe_next_step
def process_add_promo(message):
    parts = message.text.strip().split(" - ")
    if len(parts) != 2:
        safe_send_message(message.chat.id, "❌ Format noto'g'ri", reply_markup=admin_menu())
        return
    code = parts[0].strip().upper()
    amount = safe_int(parts[1], default=None)
    if amount is None:
        safe_send_message(message.chat.id, "❌ Summa noto'g'ri", reply_markup=admin_menu())
        return
    promo_codes[code] = amount
    save_db()
    safe_send_message(message.chat.id, "✅ Promokod qo'shildi", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data == "set_promo_limit")
@safe_callback_handler
def set_promo_limit(c):
    if not is_admin(c.from_user.id):
        return
    markup = InlineKeyboardMarkup(row_width=1)
    for code in promo_codes:
        markup.add(InlineKeyboardButton(code, callback_data=f"promolimit_{code}"))
    safe_send_message(c.message.chat.id, "Qaysi promokod uchun limit belgilaysiz?", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("promolimit_"))
@safe_callback_handler
def promolimit_pick(c):
    if not is_admin(c.from_user.id):
        return
    code = c.data.split("_", 1)[1]
    msg = safe_send_message(c.message.chat.id, "Nechta marta ishlatilishi mumkinligini kiriting (0 = cheksiz):")
    if msg:
        bot.register_next_step_handler(msg, process_promolimit, code)


@safe_next_step
def process_promolimit(message, code: str):
    max_uses = safe_int(message.text, default=None)
    if max_uses is None:
        safe_send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
        return
    limits = config.setdefault("promo_limits", {})
    existing = limits.get(code, {"used_count": 0})
    existing["max_uses"] = max_uses
    limits[code] = existing
    save_db()
    safe_send_message(message.chat.id, "✅ Limit saqlandi", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data == "remove_promo")
@safe_callback_handler
def remove_promo(c):
    if not is_admin(c.from_user.id):
        return
    markup = InlineKeyboardMarkup(row_width=1)
    for code in promo_codes:
        markup.add(InlineKeyboardButton(code, callback_data=f"delpromo_{code}"))
    safe_send_message(c.message.chat.id, "O'chirish uchun tanlang:", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("delpromo_"))
@safe_callback_handler
def delpromo(c):
    if not is_admin(c.from_user.id):
        return
    code = c.data.split("_", 1)[1]
    promo_codes.pop(code, None)
    config.get("promo_limits", {}).pop(code, None)
    save_db()
    safe_answer_callback_query(c.id, "✅ O'chirildi")


# =====================================
# ADMIN: MINI-GAMES SETTINGS (win-chance / multiplier / bet limits / on-off)
# =====================================
@bot.message_handler(func=lambda m: m.text == "🎮 Mini-o'yinlar sozlamalari" and is_admin(m.from_user.id))
@admin_required
def manage_games(message):
    games = config.get("games", {})
    lines = ["🎮 <b>Mini-o'yinlar sozlamalari</b>"]
    markup = InlineKeyboardMarkup(row_width=1)
    for key, g in games.items():
        status = "✅ Yoqilgan" if g.get("enabled", True) else "❌ O'chirilgan"
        lines.append(
            f"\n{g['name']} — {status}\n"
            f"   🎯 Yutish ehtimoli: {g.get('win_chance', 0)}%\n"
            f"   ✖️ Koeffitsiyent: x{g.get('multiplier', 1)}\n"
            f"   📉 Min: {g.get('min_bet', 0):,} | 📈 Max: {g.get('max_bet', 0):,}"
        )
        markup.add(InlineKeyboardButton(f"⚙️ {g['name']} sozlash", callback_data=f"gamecfg_{key}"))
    safe_send_message(message.chat.id, "\n".join(lines), reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("gamecfg_"))
@safe_callback_handler
def gamecfg(c):
    if not is_admin(c.from_user.id):
        return
    key = c.data.split("_", 1)[1]
    g = config["games"].get(key)
    if not g:
        safe_answer_callback_query(c.id, "❌ Topilmadi")
        return
    status = "✅ Yoqilgan" if g.get("enabled", True) else "❌ O'chirilgan"
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("🎯 Yutish %ni o'zgartirish", callback_data=f"gset_chance_{key}"))
    markup.add(InlineKeyboardButton("✖️ Koeffitsiyentni o'zgartirish", callback_data=f"gset_mult_{key}"))
    markup.add(InlineKeyboardButton("📉 Min stavka", callback_data=f"gset_min_{key}"), InlineKeyboardButton("📈 Max stavka", callback_data=f"gset_max_{key}"))
    markup.add(InlineKeyboardButton(f"🔄 {status} (bosing o'zgartirish uchun)", callback_data=f"gset_toggle_{key}"))
    safe_answer_callback_query(c.id)
    safe_send_message(
        c.message.chat.id,
        f"{g['name']}\n\n🎯 Yutish ehtimoli: {g.get('win_chance')}%\n✖️ Koeffitsiyent: x{g.get('multiplier')}\n"
        f"📉 Min: {g.get('min_bet'):,}\n📈 Max: {g.get('max_bet'):,}\nHolat: {status}",
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("gset_toggle_"))
@safe_callback_handler
def gset_toggle(c):
    if not is_admin(c.from_user.id):
        return
    key = c.data.split("_", 2)[2]
    config["games"][key]["enabled"] = not config["games"][key].get("enabled", True)
    save_db()
    safe_answer_callback_query(c.id, "✅ Holat o'zgartirildi")


@bot.callback_query_handler(func=lambda c: c.data.startswith("gset_chance_"))
@safe_callback_handler
def gset_chance(c):
    if not is_admin(c.from_user.id):
        return
    key = c.data.split("_", 2)[2]
    msg = safe_send_message(c.message.chat.id, "Yutish ehtimolini foizda kiriting (0-100):")
    if msg:
        bot.register_next_step_handler(msg, process_gset_chance, key)


@safe_next_step
def process_gset_chance(message, key: str):
    val = safe_float(message.text, default=None)
    if val is None:
        safe_send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
        return
    val = max(0, min(100, val))
    config["games"][key]["win_chance"] = val
    save_db()
    safe_send_message(message.chat.id, "✅ Saqlandi", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data.startswith("gset_mult_"))
@safe_callback_handler
def gset_mult(c):
    if not is_admin(c.from_user.id):
        return
    key = c.data.split("_", 2)[2]
    msg = safe_send_message(c.message.chat.id, "Yangi koeffitsiyentni kiriting (masalan 2.5):")
    if msg:
        bot.register_next_step_handler(msg, process_gset_mult, key)


@safe_next_step
def process_gset_mult(message, key: str):
    val = safe_float(message.text, default=None)
    if val is None:
        safe_send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
        return
    config["games"][key]["multiplier"] = val
    save_db()
    safe_send_message(message.chat.id, "✅ Saqlandi", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data.startswith("gset_min_"))
@safe_callback_handler
def gset_min(c):
    if not is_admin(c.from_user.id):
        return
    key = c.data.split("_", 2)[2]
    msg = safe_send_message(c.message.chat.id, "Yangi minimal stavkani kiriting:")
    if msg:
        bot.register_next_step_handler(msg, process_gset_min, key)


@safe_next_step
def process_gset_min(message, key: str):
    val = safe_int(message.text, default=None)
    if val is None:
        safe_send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
        return
    config["games"][key]["min_bet"] = val
    save_db()
    safe_send_message(message.chat.id, "✅ Saqlandi", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data.startswith("gset_max_"))
@safe_callback_handler
def gset_max(c):
    if not is_admin(c.from_user.id):
        return
    key = c.data.split("_", 2)[2]
    msg = safe_send_message(c.message.chat.id, "Yangi maksimal stavkani kiriting:")
    if msg:
        bot.register_next_step_handler(msg, process_gset_max, key)


@safe_next_step
def process_gset_max(message, key: str):
    val = safe_int(message.text, default=None)
    if val is None:
        safe_send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
        return
    config["games"][key]["max_bet"] = val
    save_db()
    safe_send_message(message.chat.id, "✅ Saqlandi", reply_markup=admin_menu())


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
    safe_send_message(message.chat.id, text, reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data == "edit_ref_bonus")
@safe_callback_handler
def edit_ref_bonus(c):
    if not is_admin(c.from_user.id):
        return
    msg = safe_send_message(c.message.chat.id, "Yangi referal bonusini kiriting:")
    if msg:
        bot.register_next_step_handler(msg, lambda m: process_simple_config_int(m, "referral_bonus"))


@bot.callback_query_handler(func=lambda c: c.data == "edit_welcome_bonus")
@safe_callback_handler
def edit_welcome_bonus(c):
    if not is_admin(c.from_user.id):
        return
    msg = safe_send_message(c.message.chat.id, "Yangi ro'yxatdan o'tish bonusini kiriting:")
    if msg:
        bot.register_next_step_handler(msg, lambda m: process_simple_config_int(m, "welcome_bonus"))


@bot.callback_query_handler(func=lambda c: c.data == "edit_subscribe_bonus")
@safe_callback_handler
def edit_subscribe_bonus(c):
    if not is_admin(c.from_user.id):
        return
    msg = safe_send_message(c.message.chat.id, "Yangi obuna bonusini kiriting:")
    if msg:
        bot.register_next_step_handler(msg, lambda m: process_simple_config_int(m, "subscribe_bonus"))


@safe_next_step
def process_simple_config_int(message, key: str):
    amount = safe_int(message.text, default=None)
    if amount is None:
        safe_send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
        return
    config[key] = amount
    save_db()
    safe_send_message(message.chat.id, "✅ Saqlandi", reply_markup=admin_menu())


@bot.callback_query_handler(func=lambda c: c.data == "edit_daily_bonus")
@safe_callback_handler
def edit_daily_bonus(c):
    if not is_admin(c.from_user.id):
        return
    msg = safe_send_message(c.message.chat.id, "Min va max qiymatlarni kiriting (masalan: 100 500):")
    if msg:
        bot.register_next_step_handler(msg, process_edit_daily_bonus)


@safe_next_step
def process_edit_daily_bonus(message):
    parts = message.text.strip().split()
    if len(parts) != 2:
        safe_send_message(message.chat.id, "❌ Format noto'g'ri", reply_markup=admin_menu())
        return
    min_v = safe_int(parts[0], default=None)
    max_v = safe_int(parts[1], default=None)
    if min_v is None or max_v is None:
        safe_send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
        return
    config["daily_bonus_range"] = [min_v, max_v]
    save_db()
    safe_send_message(message.chat.id, "✅ Saqlandi", reply_markup=admin_menu())


# =====================================
# ADMIN: TEXTS (Matnlar)
# =====================================
EDITABLE_TEXT_KEYS = {
    "welcome": "Xush kelibsiz xabari",
    "not_subscribed": "Obuna talab xabari",
    "subscribe_bonus_text": "Obuna bonusi xabari",
    "join_chat_prompt": "Chatga qo'shilish taklif xabari",
}


@bot.message_handler(func=lambda m: m.text == "✉️ Matnlar" and is_admin(m.from_user.id))
@admin_required
def manage_texts(message):
    markup = InlineKeyboardMarkup(row_width=1)
    for key, label in EDITABLE_TEXT_KEYS.items():
        markup.add(InlineKeyboardButton(f"✏️ {label}", callback_data=f"edittext_{key}"))
    safe_send_message(message.chat.id, "✉️ Tahrirlash uchun matnni tanlang:", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("edittext_"))
@safe_callback_handler
def edittext(c):
    if not is_admin(c.from_user.id):
        return
    key = c.data.split("_", 1)[1]
    current = get_text(key)
    msg = safe_send_message(c.message.chat.id, f"Joriy matn:\n\n{current}\n\nYangi matnni yuboring:")
    if msg:
        bot.register_next_step_handler(msg, process_edittext, key)


@safe_next_step
def process_edittext(message, key: str):
    config.setdefault("messages", {})[key] = message.text
    save_db()
    safe_send_message(message.chat.id, "✅ Saqlandi", reply_markup=admin_menu())


# =====================================
# ADMIN: MANAGE ADMINS (superadmin only)
# =====================================
@bot.message_handler(func=lambda m: m.text == "👨‍💻 Adminlar" and is_admin(m.from_user.id))
@admin_required
def manage_admins(message):
    lines = ["👨‍💻 <b>Adminlar</b>"]
    for uid, info in ADMINS.items():
        lines.append(f"\n{info.get('username','')} | <code>{uid}</code> | {info.get('role')} | qo'shilgan: {info.get('added_date', '')}")
    markup = InlineKeyboardMarkup(row_width=1)
    if is_superadmin(message.from_user.id):
        markup.add(InlineKeyboardButton("➕ Admin qo'shish", callback_data="add_admin"))
        markup.add(InlineKeyboardButton("❌ Adminni o'chirish", callback_data="remove_admin"))
    safe_send_message(message.chat.id, "\n".join(lines), reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data == "add_admin")
@safe_callback_handler
def add_admin(c):
    if not is_superadmin(c.from_user.id):
        safe_answer_callback_query(c.id, "❌ Faqat super admin")
        return
    msg = safe_send_message(c.message.chat.id, "Yangi admin ID sini kiriting:")
    if msg:
        bot.register_next_step_handler(msg, process_add_admin)


@safe_next_step
def process_add_admin(message):
    if not message.text.strip().isdigit():
        safe_send_message(message.chat.id, "❌ Faqat ID (raqam) kiriting", reply_markup=admin_menu())
        return
    new_admin_id = message.text.strip()
    username = "Noma'lum"
    chat = safe_call(bot.get_chat, int(new_admin_id))
    if chat:
        username = f"@{chat.username}" if chat.username else (chat.first_name or "Noma'lum")
    ADMINS[new_admin_id] = {"username": username, "role": "admin", "added_date": now_str()}
    save_db()
    safe_send_message(message.chat.id, f"✅ {username} admin qilib qo'shildi", reply_markup=admin_menu())
    safe_send_message(int(new_admin_id), "🎉 Siz botga admin etib tayinlandingiz!")


@bot.callback_query_handler(func=lambda c: c.data == "remove_admin")
@safe_callback_handler
def remove_admin(c):
    if not is_superadmin(c.from_user.id):
        safe_answer_callback_query(c.id, "❌ Faqat super admin")
        return
    markup = InlineKeyboardMarkup(row_width=1)
    for uid, info in ADMINS.items():
        if info.get("role") == "superadmin":
            continue
        markup.add(InlineKeyboardButton(f"{info.get('username','')} ({uid})", callback_data=f"deladmin_{uid}"))
    safe_send_message(c.message.chat.id, "O'chirish uchun tanlang:", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("deladmin_"))
@safe_callback_handler
def deladmin(c):
    if not is_superadmin(c.from_user.id):
        return
    uid = c.data.split("_", 1)[1]
    if uid in ADMINS and ADMINS[uid].get("role") != "superadmin":
        ADMINS.pop(uid, None)
        save_db()
        safe_answer_callback_query(c.id, "✅ O'chirildi")
    else:
        safe_answer_callback_query(c.id, "❌ Bo'lmaydi")


# =====================================
# ADMIN: BROADCAST (fully enhanced)
# Supports: forward message, plain text, photo, video, audio/voice, document
# Targets: all users, saved groups, saved channels, specific saved target, everything
# =====================================
@bot.message_handler(func=lambda m: m.text == "📢 Reklama" and is_admin(m.from_user.id))
@admin_required
def send_ad(message):
    targets = config.get("broadcast_targets", [])
    n_groups = sum(1 for t in targets if t.get("type") == "group")
    n_channels = sum(1 for t in targets if t.get("type") == "channel")
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton(f"👥 Barcha foydalanuvchilarga ({len(users)})", callback_data="ad_target_users"))
    markup.add(InlineKeyboardButton(f"📢 Saqlangan kanallarga ({n_channels})", callback_data="ad_target_channels"))
    markup.add(InlineKeyboardButton(f"👨‍👩‍👧 Saqlangan guruhlarga ({n_groups})", callback_data="ad_target_groups"))
    markup.add(InlineKeyboardButton(f"🌐 Hammasiga (users + guruh + kanal)", callback_data="ad_target_everything"))
    markup.add(InlineKeyboardButton("➕ Yangi kanal/guruh qo'shish", callback_data="ad_add_target"))
    markup.add(InlineKeyboardButton("📋 Saqlangan manzillar ro'yxati", callback_data="ad_list_targets"))
    safe_send_message(message.chat.id, "📢 <b>Reklama bo'limi</b>\n\nReklamani qayerga yubormoqchisiz?", reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data == "ad_list_targets")
@safe_callback_handler
def ad_list_targets(c):
    if not is_admin(c.from_user.id):
        return
    targets = config.get("broadcast_targets", [])
    if not targets:
        safe_answer_callback_query(c.id, "❌ Saqlangan manzil yo'q")
        return
    lines = ["📋 <b>Saqlangan manzillar</b>"]
    markup = InlineKeyboardMarkup(row_width=1)
    for t in targets:
        icon = "📢" if t.get("type") == "channel" else "👨‍👩‍👧"
        lines.append(f"\n{icon} {t.get('title', str(t['id']))} | <code>{t['id']}</code>")
        markup.add(InlineKeyboardButton(f"❌ O'chirish: {t.get('title', str(t['id']))}", callback_data=f"deltarget_{t['id']}"))
    safe_answer_callback_query(c.id)
    safe_send_message(c.message.chat.id, "\n".join(lines), reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data.startswith("deltarget_"))
@safe_callback_handler
def deltarget(c):
    if not is_admin(c.from_user.id):
        return
    target_id = int(c.data.split("_", 1)[1])
    config["broadcast_targets"] = [t for t in config.get("broadcast_targets", []) if t["id"] != target_id]
    save_db()
    safe_answer_callback_query(c.id, "✅ O'chirildi")


def _prompt_ad_content(chat_id: int, target_mode: str):
    msg = safe_send_message(
        chat_id,
        "📢 Reklama kontentini yuboring.\n\nQabul qilinadi: ✉️ oddiy matn, 🔁 forward xabar, 🖼 rasm, 🎥 video, 🎵 audio, 🎙 ovozli xabar, 📄 fayl (hujjat).",
        reply_markup=back_menu(),
    )
    if msg:
        bot.register_next_step_handler(msg, process_ad_broadcast, target_mode)


@bot.callback_query_handler(func=lambda c: c.data == "ad_target_users")
@safe_callback_handler
def ad_target_users(c):
    if not is_admin(c.from_user.id):
        return
    safe_answer_callback_query(c.id)
    _prompt_ad_content(c.message.chat.id, "users")


@bot.callback_query_handler(func=lambda c: c.data == "ad_target_channels")
@safe_callback_handler
def ad_target_channels(c):
    if not is_admin(c.from_user.id):
        return
    if not any(t.get("type") == "channel" for t in config.get("broadcast_targets", [])):
        safe_answer_callback_query(c.id, "❌ Saqlangan kanal yo'q")
        return
    safe_answer_callback_query(c.id)
    _prompt_ad_content(c.message.chat.id, "channels")


@bot.callback_query_handler(func=lambda c: c.data == "ad_target_groups")
@safe_callback_handler
def ad_target_groups(c):
    if not is_admin(c.from_user.id):
        return
    if not any(t.get("type") == "group" for t in config.get("broadcast_targets", [])):
        safe_answer_callback_query(c.id, "❌ Saqlangan guruh yo'q")
        return
    safe_answer_callback_query(c.id)
    _prompt_ad_content(c.message.chat.id, "groups")


@bot.callback_query_handler(func=lambda c: c.data == "ad_target_everything")
@safe_callback_handler
def ad_target_everything(c):
    if not is_admin(c.from_user.id):
        return
    safe_answer_callback_query(c.id)
    _prompt_ad_content(c.message.chat.id, "everything")


def _resolve_ad_chat_ids(target_mode: str) -> List[int]:
    targets = config.get("broadcast_targets", [])
    if target_mode == "users":
        return [int(uid) for uid in users.keys()]
    if target_mode == "channels":
        return [t["id"] for t in targets if t.get("type") == "channel"]
    if target_mode == "groups":
        return [t["id"] for t in targets if t.get("type") == "group"]
    if target_mode == "everything":
        return [int(uid) for uid in users.keys()] + [t["id"] for t in targets]
    return []


@safe_next_step
def process_ad_broadcast(message, target_mode: str):
    if getattr(message, "text", None) == "⬅️ Ortga":
        safe_send_message(message.chat.id, "🔙 Orqaga", reply_markup=admin_menu())
        return
    chat_ids = _resolve_ad_chat_ids(target_mode)
    if not chat_ids:
        safe_send_message(message.chat.id, "❌ Yuborish uchun manzil topilmadi", reply_markup=admin_menu())
        return
    safe_send_message(message.chat.id, f"⏳ Yuborilmoqda ({len(chat_ids)} ta manzilga)...")

    def _do_broadcast():
        sent, failed = 0, 0
        is_forward = message.forward_from is not None or message.forward_from_chat is not None
        for cid in chat_ids:
            try:
                if is_forward:
                    bot.forward_message(cid, message.chat.id, message.message_id)
                else:
                    _forward_ad_content(message, cid)
                sent += 1
            except Exception as e:
                failed += 1
                logger.error(f"Broadcast xato ({cid}): {e}")
            time.sleep(0.05)  # gentle pacing to avoid Telegram flood limits
        safe_send_message(
            message.chat.id,
            f"✅ Reklama yuborish tugadi\n📤 Yuborildi: {sent}\n❌ Xato: {failed}\n🎯 Manzil turi: {target_mode}",
            reply_markup=admin_menu(),
        )

    # Run the (potentially slow, many-recipient) broadcast in the background so
    # the admin's UI and all other users' requests are never blocked by it.
    threading.Thread(target=_do_broadcast, daemon=True).start()


def _forward_ad_content(message, chat_id: int):
    if message.content_type == "text":
        bot.send_message(chat_id, message.text)
    elif message.content_type == "photo":
        bot.send_photo(chat_id, message.photo[-1].file_id, caption=message.caption)
    elif message.content_type == "video":
        bot.send_video(chat_id, message.video.file_id, caption=message.caption)
    elif message.content_type == "audio":
        bot.send_audio(chat_id, message.audio.file_id, caption=message.caption)
    elif message.content_type == "voice":
        bot.send_voice(chat_id, message.voice.file_id, caption=message.caption)
    elif message.content_type == "document":
        bot.send_document(chat_id, message.document.file_id, caption=message.caption)
    elif message.content_type == "animation":
        bot.send_animation(chat_id, message.animation.file_id, caption=message.caption)
    elif message.content_type == "video_note":
        bot.send_video_note(chat_id, message.video_note.file_id)
    else:
        bot.send_message(chat_id, "📢 Yangi e'lon")


@bot.callback_query_handler(func=lambda c: c.data == "ad_add_target")
@safe_callback_handler
def ad_add_target(c):
    if not is_admin(c.from_user.id):
        return
    msg = safe_send_message(c.message.chat.id, "📢 Kanal/guruhdan istalgan xabarni forward qiling (bot u yerda admin bo'lishi kerak):")
    if msg:
        bot.register_next_step_handler(msg, process_ad_add_target)


@safe_next_step
def process_ad_add_target(message):
    if not getattr(message, "forward_from_chat", None):
        safe_send_message(message.chat.id, "❌ Forward qilingan xabar topilmadi", reply_markup=admin_menu())
        return
    chat = message.forward_from_chat
    chat_type = "channel" if chat.type == "channel" else "group"
    targets = config.setdefault("broadcast_targets", [])
    if not any(t["id"] == chat.id for t in targets):
        targets.append({"id": chat.id, "title": chat.title or str(chat.id), "type": chat_type})
        save_db()
    safe_send_message(message.chat.id, f"✅ Qo'shildi: {chat.title or chat.id} ({chat_type})", reply_markup=admin_menu())


# =====================================
# SETTINGS (enhanced, under Hisobim) / HISTORY / CONTACT
# =====================================
@bot.message_handler(func=lambda m: m.text == "⚙️ Sozlamalar")
@subscription_required
def settings(message):
    uid = str(message.from_user.id)
    status = "✅ Yoqilgan" if users[uid].get("notifications", True) else "❌ O'chirilgan"
    safe_send_message(message.chat.id, f"⚙️ <b>Sozlamalar</b>\n\n🔔 Bildirishnomalar: {status}", reply_markup=settings_submenu(uid))


@bot.message_handler(func=lambda m: m.text and m.text.startswith(("🔔 Bildirishnoma", "🔕 Bildirishnoma")))
@subscription_required
def toggle_notifications(message):
    uid = str(message.from_user.id)
    users[uid]["notifications"] = not users[uid].get("notifications", True)
    save_db()
    safe_send_message(
        message.chat.id,
        f"✅ Holat: {'yoqildi' if users[uid]['notifications'] else 'o\'chirildi'}",
        reply_markup=settings_submenu(uid),
    )


@bot.message_handler(func=lambda m: m.text == "🌐 Til sozlamalari")
@subscription_required
def language_settings(message):
    safe_send_message(message.chat.id, "🌐 Hozircha faqat o'zbek tili qo'llab-quvvatlanadi. Tez orada boshqa tillar qo'shiladi.", reply_markup=settings_submenu(str(message.from_user.id)))


@bot.message_handler(func=lambda m: m.text == "📄 Mening ma'lumotlarim")
@subscription_required
def my_data(message):
    uid = str(message.from_user.id)
    user = users[uid]
    text = (
        f"📄 <b>Mening ma'lumotlarim</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"📛 Username: {safe_username(message.from_user)}\n"
        f"📅 Ro'yxatdan o'tgan sana: {user.get('join_date')}\n"
        f"⏱ Oxirgi faollik: {user.get('last_active')}\n"
        f"💰 Balans: {user.get('balance', 0):,} so'm\n"
        f"👥 Referallar: {user.get('referrals_count', 0)}\n"
        f"📦 Buyurtmalar: {user.get('orders_count', 0)}\n"
        f"🎮 O'ynagan o'yinlar: {user.get('games_played', 0)}"
    )
    safe_send_message(message.chat.id, text, reply_markup=settings_submenu(uid))


@bot.message_handler(func=lambda m: m.text == "📜 Buyurtmalar tarixi")
@subscription_required
def order_history(message):
    uid = str(message.from_user.id)
    my_orders = [o for o in orders if o.get("user_id") == uid]
    my_orders.sort(key=lambda x: x.get("date", ""), reverse=True)
    if not my_orders:
        safe_send_message(message.chat.id, "📜 Buyurtmalar mavjud emas", reply_markup=profile_submenu())
        return
    text = ["📜 <b>Oxirgi buyurtmalar</b>"]
    for order in my_orders[:10]:
        text.append(f"\n#{order.get('id')} | {order.get('kind')} | {order.get('amount', 0):,} so'm | {order.get('status')}")
    safe_send_message(message.chat.id, "\n".join(text), reply_markup=profile_submenu())


@bot.message_handler(func=lambda m: m.text == "📩 Adminga yozish")
@subscription_required
def contact_admin(message):
    msg = safe_send_message(message.chat.id, "📩 Xabaringizni yozing:", reply_markup=back_menu())
    if msg:
        bot.register_next_step_handler(msg, send_to_admin)


@safe_next_step
def send_to_admin(message):
    if message.text == "⬅️ Ortga":
        safe_send_message(message.chat.id, "🔙 Orqaga", reply_markup=profile_submenu())
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
    safe_send_message(message.chat.id, "✅ Xabar yuborildi", reply_markup=profile_submenu())


@bot.callback_query_handler(func=lambda c: c.data.startswith("reply_user_"))
@safe_callback_handler
def reply_user(c):
    if not is_admin(c.from_user.id):
        return
    uid = c.data.split("_")[-1]
    msg = safe_send_message(c.message.chat.id, f"User {uid} uchun javob yozing:")
    if msg:
        bot.register_next_step_handler(msg, lambda m: send_admin_reply(m, uid))


@safe_next_step
def send_admin_reply(message, user_id: str):
    try:
        if message.content_type == "text":
            bot.send_message(int(user_id), f"📩 <b>Admin javobi:</b>\n\n{message.text}")
        elif message.content_type == "photo":
            bot.send_photo(int(user_id), message.photo[-1].file_id, caption=f"📩 <b>Admin javobi:</b>\n\n{message.caption or ''}")
        safe_send_message(message.chat.id, "✅ Javob yuborildi", reply_markup=admin_menu())
    except Exception as e:
        safe_send_message(message.chat.id, f"❌ Xato: {e}", reply_markup=admin_menu())


# =====================================
# NAVIGATION / FALLBACK
# =====================================
def _menu_for(user_id: int):
    """Admins navigating user-facing flows (Pul ishlash, Hisobim, etc.) should land back
    on the admin-as-user menu (which still has an Admin panel button), not the admin-only
    main menu — otherwise they'd get stuck unable to reach user features again."""
    if is_admin(user_id):
        return admin_as_user_menu()
    return build_main_menu(False)


@bot.message_handler(func=lambda m: m.text == "⬅️ Asosiy menyu")
def to_main_menu(message):
    safe_send_message(message.chat.id, "🔙 Asosiy menyu", reply_markup=_menu_for(message.from_user.id))


@bot.message_handler(func=lambda m: m.text == "⬅️ Ortga")
def back(message):
    safe_send_message(message.chat.id, "🔙 Asosiy menyu", reply_markup=_menu_for(message.from_user.id))


@bot.message_handler(func=lambda m: True, content_types=["text"])
def unknown(message):
    try:
        ensure_user(message)
        if user_blocked(str(message.from_user.id)):
            safe_send_message(message.chat.id, "❌ Siz bloklangansiz.")
            return
        safe_send_message(message.chat.id, "❌ Noto'g'ri buyruq. Menyudan tanlang.", reply_markup=_menu_for(message.from_user.id))
    except Exception as e:
        logger.error(f"unknown handler xato: {e}", exc_info=True)


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

    # Outer retry loop: if infinity_polling ever crashes (network drop, Telegram
    # server hiccup, etc.) the bot restarts polling instead of dying entirely.
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)
            break  # infinity_polling only returns on a clean stop
        except Exception as e:
            logger.error(f"Kritik xato, polling qayta ishga tushirilmoqda: {e}", exc_info=True)
            print(f"❌ Xato: {e}. 5 soniyadan keyin qayta urinish...")
            try:
                save_db(force=True)
            except Exception:
                pass
            time.sleep(5)
            continue

    save_db(force=True)
    Database.backup()
    logger.info("Bot to'xtatildi")
    print("✅ Ma'lumotlar saqlandi")
