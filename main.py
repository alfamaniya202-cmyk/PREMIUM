import os
import json
import time
import random
import logging
import threading
from datetime import datetime, timedelta
from functools import wraps
from typing import Dict, Any, List, Optional, Tuple, Union
from collections import defaultdict

import requests
from flask import Flask, request, jsonify
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
    KeyboardButton,
    ReplyKeyboardRemove,
)

# =====================================
# CONFIG / FILES
# =====================================
TOKEN = os.getenv("BOT_TOKEN", "")
PORT = int(os.getenv("PORT", "8000"))

if not TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi. Environment variable ga qo'ying.")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)
app = Flask(__name__)

DATA_FILE = "users.json"
ORDERS_FILE = "orders.json"
CONFIG_FILE = "config.json"
PROMO_FILE = "promo.json"
ADMINS_FILE = "admins.json"
LOTTERY_FILE = "lottery.json"
LOGS_FILE = "bot.log"
BACKUP_DIR = "backups"

# =====================================
# STICKERS (real stickerlarni o'zgartiring)
# =====================================
STICKERS = {
    "welcome": "CAACAgIAAxkBAAEBTQFmS3example_welcome",
    "success": "CAACAgIAAxkBAAEBTQJmS3example_success",
    "fail": "CAACAgIAAxkBAAEBTQNmS3example_fail",
    "money": "CAACAgIAAxkBAAEBTQRmS3example_money",
    "game_win": "CAACAgIAAxkBAAEBTQVmS3example_gamewin",
    "game_lose": "CAACAgIAAxkBAAEBTQZmS3example_gamelose",
    "dice_roll": "CAACAgIAAxkBAAEBTQdmS3example_dice",
    "wheel": "CAACAgIAAxkBAAEBTQhmS3example_wheel",
    "mines": "CAACAgIAAxkBAAEBTQhmS3example_mines",
}

# =====================================
# LOGGING
# =====================================
logging.basicConfig(
    filename=LOGS_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    encoding="utf-8",
)
logger = logging.getLogger(__name__)
lock = threading.RLock()

# =====================================
# DEFAULTS (kengaytirilgan)
# =====================================
DEFAULT_REQUIRED_CHANNELS = [
    {"username": "@ALFA_BONUS_NEWS", "title": "ALFA BONUS NEWS", "auto_remove_at": 0, "confirmed_count": 0, "check_enabled": True},
    {"username": "@NWS_ALFA_07", "title": "NWS ALFA 07", "auto_remove_at": 0, "confirmed_count": 0, "check_enabled": True},
    {"username": "@NWS_ALFA_UC", "title": "NWS ALFA UC", "auto_remove_at": 0, "confirmed_count": 0, "check_enabled": True},
]

DEFAULT_ADMINS = {
    "5996676608": {
        "username": "@NWSxALFA",
        "role": "superadmin",
        "added_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
}

DEFAULT_MESSAGES = {
    "welcome": "👋 Xush kelibsiz! Botimizga qo'shilganingizdan mamnunmiz! 🎉",
    "not_subscribed": "⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling.\n\n✅ Obuna bo'lgach «Tekshirish» ni bosing.",
    "subscribe_bonus_text": "🎉 Obuna uchun bonus berildi!",
    "join_chat_prompt": "💬 Rasmiy chatimizga qo'shiling — u yerda yangiliklar, aksiyalar va yordam bor!",
    "game_menu": "🎮 O'yinlardan birini tanlang va omadingizni sinab ko'ring!",
    "no_games": "❌ Hozircha o'yinlar mavjud emas.",
    "insufficient_balance": "❌ Balansingiz yetarli emas!",
    "invalid_bet": "❌ Noto'g'ri stavka!",
    "daily_bonus_taken": "❌ Bugun bonus olgansiz. Keyingi bonus {hours} soat {minutes} daqiqadan so'ng.",
    "daily_bonus_given": "🎉 Kunlik bonus!\n💰 +{bonus:,} so'm\n🔥 Ketma-ket kun: {streak} (x{multiplier:.1f})",
    "profile_text": "👤 <b>Shaxsiy kabinet</b>\n\n🆔 ID: <code>{user_id}</code>\n📛 Username: {username}\n📅 Ro'yxat: {join_date}\n\n💰 Balans: {balance:,} so'm\n👥 Referallar: {referrals} ta\n🔰 Daraja: {level}\n📦 Buyurtmalar: {orders} ta\n🎮 O'yinlar: {games_played} ta (yutgan: {games_won})\n🎰 Lotareya: {lottery_tickets} ta chipta, {lottery_wins} ta yutuq",
    "referral_text": "👥 <b>Referal dasturi</b>\n\n👥 Referallaringiz: {referrals} ta\n🔰 Sizning darajangiz: {level}\n💰 Hozirgi darajadagi bonus: {bonus:,} so'm\n📈 Keyingi daraja uchun: {next_required} ta referal\n\n🔗 Havolangiz:\n<code>{ref_link}</code>",
    "lottery_no_active": "🎰 Hozircha faol lotareyalar mavjud emas.\nKeyinroq qaytadan urinib ko'ring!",
    "lottery_bought": "✅ Chipta sotib olindi! Ticket #{ticket_number}",
    "lottery_not_enough_balance": "❌ Balans yetarli emas. Lotareya narxi: {price:,} so'm",
    "lottery_already_bought": "❌ Siz allaqachon chipta sotib olgansiz",
    "lottery_sold_out": "❌ Lotareya to'lgan",
    "game_result_win": "🎉 Siz yutdingiz!\n{game_name}\n💰 Stavka: {bet:,} so'm\n✅ Yutuq: +{payout:,} so'm\n⚖️ Balans: {balance:,} so'm",
    "game_result_lose": "😔 Siz yutqazdingiz.\n{game_name}\n💸 Stavka: -{bet:,} so'm\n⚖️ Balans: {balance:,} so'm",
    "order_created": "✅ Buyurtma qabul qilindi.\n🆔 Order: #{order_id}\n📦 {service_name}\n💰 {price:,} so'm",
    "order_completed": "✅ Buyurtmangiz bajarildi!\n🆔 Order: #{order_id}",
    "order_rejected": "❌ Buyurtma rad etildi.\n💰 {amount:,} so'm balansga qaytarildi",
    "admin_topup_notification": "💰 Administrator balansingizni o'zgartirdi.\n{sign}{amount:,} so'm\n⚖️ Yangi balans: {new_balance:,} so'm",
    "promo_success": "✅ Promokod ishladi: +{amount:,} so'm",
    "promo_already_used": "❌ Bu promokod oldin ishlatilgan",
    "promo_invalid": "❌ Promokod noto'g'ri",
    "promo_limit_exceeded": "❌ Bu promokodning limiti tugagan",
    "admin_panel_text": "👨‍💻 <b>Admin panel</b>\n\n👥 Foydalanuvchilar: {total_users}\n🆕 Bugun: {new_today}\n⚡ Faol: {active_today}\n💰 Jami balans: {total_balance:,} so'm\n📦 Pending: {pending_orders}\n🎰 Faol lotareyalar: {active_lotteries}",
    "order_admin_approved": "✅ Admin buyurtmani tasdiqladi",
    "order_admin_rejected": "❌ Admin buyurtmani rad etdi",
    "group_welcome": "👋 Assalomu alaykum! Bot bilan bog'lanish uchun @{bot_username} ga yozing yoki tugmani bosing.",
    "group_button_text": "🤖 Botga kirish",
}

DEFAULT_GAMES = {
    "coin": {
        "name": "🪙 Tanga",
        "enabled": True,
        "win_chance": 45,
        "multiplier": 1.8,
        "min_bet": 500,
        "max_bet": 50000,
        "description": "Tanga tashlash - 50% yaqin yutish ehtimoli"
    },
    "dice": {
        "name": "🎲 Zar",
        "enabled": True,
        "win_chance": 30,
        "multiplier": 2.5,
        "min_bet": 500,
        "max_bet": 50000,
        "description": "Zar tashlash - 5 yoki 6 kelsa yutasiz"
    },
    "slot": {
        "name": "🎰 Slot",
        "enabled": True,
        "win_chance": 20,
        "multiplier": 4.0,
        "min_bet": 1000,
        "max_bet": 30000,
        "description": "Slot mashinasi - katta yutuq imkoniyati"
    },
    "wheel": {
        "name": "🎡 Omad barabani",
        "enabled": True,
        "win_chance": 25,
        "multiplier": 3.0,
        "min_bet": 1000,
        "max_bet": 50000,
        "description": "Omad barabani - aylantiring va yuting!"
    },
    "mines": {
        "name": "💣 Mines",
        "enabled": True,
        "win_chance": 35,
        "multiplier": 2.2,
        "min_bet": 500,
        "max_bet": 30000,
        "description": "3 ta mina - ehtiyot bo'ling!"
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
    "services": [],
    "service_categories": [],
    "payment_cards": [],
    "payment_channel_id": None,
    "orders_channel_id": None,
    "broadcast_targets": [],
    "messages": DEFAULT_MESSAGES,
    "games": DEFAULT_GAMES,
    "promo_limits": {},
    "chat_link": None,
    "chat_title": "💬 Chatga qo'shilish",
    "chat_enabled": True,
    "maintenance_mode": False,
    "referral_levels": [
        {"level": 1, "bonus": 1000, "required": 0},
        {"level": 2, "bonus": 2000, "required": 5},
        {"level": 3, "bonus": 5000, "required": 20},
        {"level": 4, "bonus": 10000, "required": 50},
        {"level": 5, "bonus": 25000, "required": 100},
    ],
    "owner_id": None,
    "transfer_enabled": False,
    "transfer_request": None,
    "transfer_request_data": None,
    "bot_username": None,
    "admin_panel_text": DEFAULT_MESSAGES["admin_panel_text"],
    "group_welcome": DEFAULT_MESSAGES["group_welcome"],
    "group_button_text": DEFAULT_MESSAGES["group_button_text"],
}

DEFAULT_PROMO_CODES = {
    "WELCOME100": 100,
    "BONUS500": 500,
}

DEFAULT_LOTTERY = {
    "active": [],
    "history": [],
}

# =====================================
# DATABASE (yaxshilangan)
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
        lottery_data = Database._read_json(LOTTERY_FILE, DEFAULT_LOTTERY.copy())

        # To'liq merge qilish
        merged_config = json.loads(json.dumps(DEFAULT_CONFIG))
        merged_config.update(config_data or {})
        
        # Messages merge
        if "messages" in config_data:
            merged_config["messages"] = {**DEFAULT_MESSAGES, **config_data.get("messages", {})}
        
        # Games merge
        merged_games = json.loads(json.dumps(DEFAULT_GAMES))
        for k, v in (config_data.get("games", {}) or {}).items():
            if k in merged_games:
                merged_games[k].update(v)
            else:
                merged_games[k] = v
        merged_config["games"] = merged_games
        
        # Boshqa maydonlarni to'ldirish
        for key in ["daily_bonus_range", "promo_limits", "service_categories", 
                    "orders_channel_id", "chat_link", "chat_title", "chat_enabled",
                    "maintenance_mode", "referral_levels", "owner_id", 
                    "transfer_enabled", "transfer_request", "transfer_request_data",
                    "bot_username", "admin_panel_text", "group_welcome", "group_button_text"]:
            if key not in merged_config:
                merged_config[key] = DEFAULT_CONFIG.get(key)

        admins_data = {str(k): v for k, v in admins_data.items()}
        if not admins_data:
            admins_data = DEFAULT_ADMINS.copy()
            
        lottery_data.setdefault("active", [])
        lottery_data.setdefault("history", [])

        return users_data, orders_data, merged_config, promo_data, admins_data, lottery_data

    @staticmethod
    def save_all(users_data, orders_data, config_data, promo_data, admins_data, lottery_data):
        with lock:
            for path, data in {
                DATA_FILE: users_data,
                ORDERS_FILE: orders_data,
                CONFIG_FILE: config_data,
                PROMO_FILE: promo_data,
                ADMINS_FILE: admins_data,
                LOTTERY_FILE: lottery_data,
            }.items():
                Database._atomic_write(path, data)

    @staticmethod
    def _atomic_write(path: str, data):
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
            for path in [DATA_FILE, ORDERS_FILE, CONFIG_FILE, PROMO_FILE, ADMINS_FILE, LOTTERY_FILE]:
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

users, orders, config, promo_codes, ADMINS, lottery_data = Database.load_all()

# =====================================
# SAVE MECHANISM (xatoliklarga chidamli)
# =====================================
_save_pending = False
_save_lock = threading.Lock()
_retry_count = 0
_MAX_RETRIES = 3

def save_db(force: bool = False):
    global _save_pending, _retry_count
    if force:
        for attempt in range(_MAX_RETRIES):
            try:
                Database.save_all(users, orders, config, promo_codes, ADMINS, lottery_data)
                _retry_count = 0
                return
            except Exception as e:
                logger.error(f"save_db(force) attempt {attempt+1} xato: {e}")
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(1)
        return
    with _save_lock:
        _save_pending = True

def _flush_loop():
    global _save_pending, _retry_count
    while True:
        time.sleep(0.5)
        try:
            with _save_lock:
                pending = _save_pending
                _save_pending = False
            if pending:
                for attempt in range(_MAX_RETRIES):
                    try:
                        Database.save_all(users, orders, config, promo_codes, ADMINS, lottery_data)
                        _retry_count = 0
                        break
                    except Exception as e:
                        logger.error(f"Flush loop attempt {attempt+1} xato: {e}")
                        if attempt < _MAX_RETRIES - 1:
                            time.sleep(1)
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
# SAFE TELEGRAM API WRAPPERS (kengaytirilgan)
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
    if not chat_id:
        return None
    try:
        return safe_call(bot.send_message, chat_id, text, **kwargs)
    except Exception as e:
        logger.error(f"send_message xato ({chat_id}): {e}")
        return None

def safe_edit_message_text(text, chat_id, message_id, **kwargs):
    try:
        return safe_call(bot.edit_message_text, text, chat_id, message_id, **kwargs)
    except Exception as e:
        logger.error(f"edit_message_text xato: {e}")
        return None

def safe_edit_message_caption(caption, chat_id, message_id, **kwargs):
    try:
        return safe_call(bot.edit_message_caption, caption, chat_id, message_id, **kwargs)
    except Exception as e:
        logger.error(f"edit_message_caption xato: {e}")
        return None

def safe_send_photo(chat_id, photo, **kwargs):
    try:
        return safe_call(bot.send_photo, chat_id, photo, **kwargs)
    except Exception as e:
        logger.error(f"send_photo xato: {e}")
        return None

def safe_answer_callback_query(call_id, text=None, **kwargs):
    try:
        return safe_call(bot.answer_callback_query, call_id, text, **kwargs)
    except Exception as e:
        logger.error(f"answer_callback_query xato: {e}")
        return None

def safe_send_dice(chat_id, emoji: str = "🎲"):
    try:
        return safe_call(bot.send_dice, chat_id, emoji=emoji)
    except Exception as e:
        logger.error(f"send_dice xato: {e}")
        return None

def safe_send_sticker(chat_id: int, sticker_key: str):
    try:
        sticker_id = STICKERS.get(sticker_key)
        if sticker_id:
            return safe_call(bot.send_sticker, chat_id, sticker_id)
    except Exception as e:
        logger.error(f"send_sticker xato: {e}")
    return None

def safe_delete_message(chat_id: int, message_id: int):
    try:
        return safe_call(bot.delete_message, chat_id, message_id)
    except Exception as e:
        logger.error(f"delete_message xato: {e}")
        return None

def safe_pin_message(chat_id: int, message_id: int, disable_notification: bool = True):
    try:
        return safe_call(bot.pin_chat_message, chat_id, message_id, disable_notification=disable_notification)
    except Exception as e:
        logger.debug(f"Pin qilish xato ({chat_id}): {e}")
        return None

def safe_get_chat(chat_id):
    try:
        return safe_call(bot.get_chat, chat_id)
    except Exception as e:
        logger.error(f"get_chat xato: {e}")
        return None

def safe_get_chat_member(chat_id, user_id):
    try:
        return safe_call(bot.get_chat_member, chat_id, user_id)
    except Exception as e:
        logger.error(f"get_chat_member xato: {e}")
        return None

# =====================================
# ANIMATIONS
# =====================================
def send_loading_animation(chat_id: int, text: str = "⏳ Iltimos kuting..."):
    try:
        frames = ["🔄", "◐", "◑", "◒", "◓"]
        message = safe_send_message(chat_id, f"{frames[0]} {text}")
        if not message:
            return None
        
        for i in range(1, len(frames)):
            time.sleep(0.2)
            safe_edit_message_text(f"{frames[i]} {text}", chat_id, message.message_id)
        time.sleep(0.2)
        safe_edit_message_text(f"✅ {text}", chat_id, message.message_id)
        return message
    except Exception as e:
        logger.error(f"loading_animation xato: {e}")
        return None

def send_progress_animation(chat_id: int, step: int, total: int, text: str = "Ishlanmoqda"):
    try:
        progress = "█" * step + "░" * (total - step)
        percentage = int(step / total * 100)
        return safe_send_message(chat_id, f"📊 {text}\n{progress} {percentage}%")
    except Exception as e:
        logger.error(f"progress_animation xato: {e}")
        return None

def send_countdown(chat_id: int, seconds: int = 3, text: str = "Boshlanishiga"):
    try:
        for i in range(seconds, 0, -1):
            msg = safe_send_message(chat_id, f"⏳ {text} {i}...")
            time.sleep(1)
            if msg:
                safe_delete_message(chat_id, msg.message_id)
        safe_send_message(chat_id, f"🚀 {text} tugadi!")
    except Exception as e:
        logger.error(f"countdown xato: {e}")

# =====================================
# HELPERS (kengaytirilgan)
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

def is_owner(user_id: int) -> bool:
    owner_id = config.get("owner_id")
    if not owner_id:
        return False
    return str(user_id) == str(owner_id)

def get_text(key: str, **kwargs) -> str:
    try:
        template = config.get("messages", {}).get(key, DEFAULT_MESSAGES.get(key, ""))
        return template.format(**kwargs) if kwargs else template
    except Exception:
        return DEFAULT_MESSAGES.get(key, "")

def new_id(seq: List[Dict[str, Any]]) -> int:
    try:
        return (max([x.get("id", 0) for x in seq], default=0) + 1) if seq else 1
    except Exception:
        return int(time.time())

def safe_int(value, default=0) -> int:
    try:
        if value is None:
            return default
        return int(str(value).strip().replace(" ", "").replace(",", ""))
    except Exception:
        return default

def safe_float(value, default=0.0) -> float:
    try:
        if value is None:
            return default
        return float(str(value).strip().replace(" ", "").replace(",", ""))
    except Exception:
        return default

def ensure_user(message_or_user) -> str:
    try:
        if hasattr(message_or_user, "from_user"):
            user = message_or_user.from_user
        else:
            user = message_or_user

        if not user:
            return "0"

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
                "referrals_list": [],
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
                "mines_field": None,
                "mines_bet": 0,
                "mines_revealed": [],
                "mines_count": 3,
                "pending_game": None,
                "daily_streak": 0,
                "last_daily_bonus": None,
                "lottery_tickets": [],
                "lottery_wins": 0,
                "pending_topup": None,
                "pending_purchase": None,
            }
            save_db()
        else:
            # Foydalanuvchi ma'lumotlarini yangilash
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
            
            # Yangi maydonlarni qo'shish
            for k, default_v in {
                "games_played": 0, "games_won": 0, "total_wagered": 0,
                "total_won": 0, "admin_topups_total": 0, "joined_chat": False,
                "referrals_list": [], "mines_field": None, "mines_bet": 0,
                "mines_revealed": [], "mines_count": 3, "pending_game": None,
                "daily_streak": 0, "last_daily_bonus": None,
                "lottery_tickets": [], "lottery_wins": 0,
                "pending_topup": None, "pending_purchase": None,
            }.items():
                if k not in users[user_id]:
                    users[user_id][k] = default_v
                    changed = True
            
            if changed:
                save_db()
        return user_id
    except Exception as e:
        logger.error(f"ensure_user xato: {e}")
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
        if not channel_username:
            return False
        member = safe_get_chat_member(channel_username, user_id)
        if not member:
            return False
        return member.status not in ["left", "kicked"]
    except Exception as e:
        logger.debug(f"Obuna tekshirish xato {channel_username}: {e}")
        return False

def check_subscription(user_id: int) -> bool:
    try:
        required_channels = config.get("required_channels", [])
        for channel in required_channels:
            if channel.get("check_enabled", True):
                if not is_channel_member(channel["username"], user_id):
                    return False
        return True
    except Exception as e:
        logger.error(f"check_subscription xato: {e}")
        return False

def register_confirmed_channels(uid: str, telegram_user_id: int):
    try:
        confirmed = users[uid].setdefault("confirmed_required_channels", [])
        required_channels = config.get("required_channels", [])
        to_remove = []
        changed = False
        for ch in required_channels:
            if not ch.get("check_enabled", True):
                continue
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

def notify_admins(text: str, parse_mode: str = "HTML"):
    for admin_id in list(ADMINS.keys()):
        try:
            safe_send_message(int(admin_id), text, parse_mode=parse_mode)
        except Exception as e:
            logger.debug(f"Adminga xabar yuborilmadi ({admin_id}): {e}")

def send_order_to_channel(caption: str, markup=None, photo_file_id: Optional[str] = None):
    channel_id = config.get("orders_channel_id")
    sent = False
    if channel_id:
        try:
            if photo_file_id:
                safe_send_photo(channel_id, photo_file_id, caption=caption, reply_markup=markup)
            else:
                safe_send_message(channel_id, caption, reply_markup=markup)
            sent = True
        except Exception as e:
            logger.error(f"Orders kanaliga yuborishda xato: {e}")
    if not sent:
        for admin_id in list(ADMINS.keys()):
            try:
                if photo_file_id:
                    safe_send_photo(int(admin_id), photo_file_id, caption=caption, reply_markup=markup)
                else:
                    safe_send_message(int(admin_id), caption, reply_markup=markup)
            except Exception as e:
                logger.debug(f"Admin fallback xato ({admin_id}): {e}")

def is_group_chat(chat_type: str) -> bool:
    return chat_type in ["group", "supergroup"]

def is_private_chat(chat_type: str) -> bool:
    return chat_type == "private"

def get_bot_username() -> str:
    try:
        if config.get("bot_username"):
            return config["bot_username"]
        me = safe_call(bot.get_me)
        if me:
            config["bot_username"] = me.username
            save_db()
            return me.username
    except Exception:
        pass
    return "bot"

# =====================================
# DECORATORS (kengaytirilgan)
# =====================================
def subscription_required(func):
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        try:
            # Guruh xabarlarini o'tkazib yuborish
            if is_group_chat(message.chat.type):
                return
            
            if config.get("maintenance_mode", False) and not is_admin(message.from_user.id):
                safe_send_message(message.chat.id, "🔧 Bot texnik ishlar olib borilmoqda. Iltimos, keyinroq urinib ko'ring.")
                return
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
            if is_group_chat(message.chat.type):
                return
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
            if is_group_chat(message.chat.type):
                return
            if not is_superadmin(message.from_user.id):
                safe_send_message(message.chat.id, "❌ Bu amal faqat super admin uchun.")
                return
            return func(message, *args, **kwargs)
        except Exception as e:
            logger.error(f"Superadmin handler xato ({func.__name__}): {e}", exc_info=True)
            safe_send_message(message.chat.id, "⚠️ Xatolik yuz berdi.")
    return wrapper

def owner_required(func):
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        try:
            if is_group_chat(message.chat.type):
                return
            if not is_owner(message.from_user.id):
                safe_send_message(message.chat.id, "❌ Bu amal faqat bot egasi uchun.")
                return
            return func(message, *args, **kwargs)
        except Exception as e:
            logger.error(f"Owner handler xato ({func.__name__}): {e}", exc_info=True)
            safe_send_message(message.chat.id, "⚠️ Xatolik yuz berdi.")
    return wrapper

def safe_callback_handler(func):
    @wraps(func)
    def wrapper(call, *args, **kwargs):
        try:
            return func(call, *args, **kwargs)
        except Exception as e:
            logger.error(f"Callback xato ({func.__name__}): {e}", exc_info=True)
            safe_answer_callback_query(call.id, "⚠️ Xatolik yuz berdi, qaytadan urinib ko'ring")
    return wrapper

def safe_next_step(func):
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        try:
            if is_group_chat(message.chat.type):
                return
            return func(message, *args, **kwargs)
        except Exception as e:
            logger.error(f"Next-step xato ({func.__name__}): {e}", exc_info=True)
            try:
                safe_send_message(message.chat.id, "⚠️ Xatolik yuz berdi. Qaytadan boshlang.", reply_markup=_menu_for(message.from_user.id))
            except Exception:
                pass
    return wrapper

def group_handler(func):
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        try:
            if not is_group_chat(message.chat.type):
                return
            return func(message, *args, **kwargs)
        except Exception as e:
            logger.error(f"Group handler xato ({func.__name__}): {e}", exc_info=True)
    return wrapper

# =====================================
# MENUS (kengaytirilgan)
# =====================================
def _get_main_menu(user_id: int):
    try:
        is_admin_flag = is_admin(user_id)
        is_owner_flag = is_owner(user_id)
        
        kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        
        if config.get("chat_enabled", True) and config.get("chat_link"):
            kb.add(config.get("chat_title", "💬 Chatga qo'shilish"))
        
        if is_admin_flag:
            kb.add("👨‍💻 Admin panel")
            if is_owner_flag:
                kb.add("👑 Owner panel")
            return kb
        
        rows = [
            ["💸 Pul ishlash", "📊 Hisobim"],
            ["🛍 Xizmatlar", "🏆 Reyting"],
            ["🎮 O'yinlar", "🎰 Lotareya"],
        ]
        for row in rows:
            kb.add(*row)
        return kb
    except Exception as e:
        logger.error(f"_get_main_menu xato: {e}")
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("📊 Hisobim")
        return kb

def earn_submenu():
    try:
        kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        kb.add("🎁 Kunlik bonus", "👥 Referal")
        kb.add("🎟 Promokod", "🎮 O'yinlar")
        kb.add("📋 Vazifalar", "🎰 Lotareya")
        kb.add("⬅️ Asosiy menyu")
        return kb
    except Exception:
        return ReplyKeyboardMarkup(resize_keyboard=True).add("⬅️ Asosiy menyu")

def profile_submenu():
    try:
        kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        kb.add("➕ Hisobni to'ldirish", "⚙️ Sozlamalar")
        kb.add("📜 Buyurtmalar tarixi", "📩 Adminga yozish")
        kb.add("⬅️ Asosiy menyu")
        return kb
    except Exception:
        return ReplyKeyboardMarkup(resize_keyboard=True).add("⬅️ Asosiy menyu")

def games_submenu():
    try:
        kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        active_games = [g for g in config.get("games", {}).values() if g.get("enabled", True)]
        names = [g["name"] for g in active_games]
        for i in range(0, len(names), 2):
            row = names[i:i+2]
            kb.add(*row)
        kb.add("⬅️ Ortga")
        return kb
    except Exception:
        return ReplyKeyboardMarkup(resize_keyboard=True).add("⬅️ Ortga")

def settings_submenu(uid: str):
    try:
        kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        notif = "🔔 Bildirishnoma: ON" if users.get(uid, {}).get("notifications", True) else "🔕 Bildirishnoma: OFF"
        kb.add(notif)
        kb.add("🌐 Til sozlamalari", "📄 Mening ma'lumotlarim")
        kb.add("⬅️ Ortga")
        return kb
    except Exception:
        return ReplyKeyboardMarkup(resize_keyboard=True).add("⬅️ Ortga")

def admin_menu():
    try:
        kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        kb.add("📊 Statistika", "📦 Buyurtmalar")
        kb.add("👤 Foydalanuvchilar", "📢 Reklama")
        kb.add("💳 To'lov (kartalar)", "🛠 Xizmatlar")
        kb.add("📝 Majburiy kanallar", "💼 Pul ishlash vazifalari")
        kb.add("🎟 Promokodlar", "💰 Referal/Bonuslar")
        kb.add("🎮 Mini-o'yinlar sozlamalari", "💵 Hisob to'ldirish (admin)")
        kb.add("💬 Chat sozlamalari", "✉️ Matnlar")
        kb.add("👨‍💻 Adminlar", "🔧 Tizim sozlamalari")
        kb.add("🎰 Lotareya boshqaruvi", "⬅️ Foydalanuvchi rejimi")
        return kb
    except Exception:
        return ReplyKeyboardMarkup(resize_keyboard=True).add("⬅️ Foydalanuvchi rejimi")

def owner_menu():
    try:
        kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        kb.add("👑 Bot egasi sozlamalari")
        kb.add("🔄 Botni o'tkazish")
        kb.add("⬅️ Asosiy menyu")
        return kb
    except Exception:
        return ReplyKeyboardMarkup(resize_keyboard=True).add("⬅️ Asosiy menyu")

def admin_as_user_menu():
    try:
        kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        if config.get("chat_enabled", True) and config.get("chat_link"):
            kb.add(config.get("chat_title", "💬 Chatga qo'shilish"))
        kb.add("💸 Pul ishlash", "📊 Hisobim")
        kb.add("🛍 Xizmatlar", "🏆 Reyting")
        kb.add("🎮 O'yinlar", "🎰 Lotareya")
        kb.add("👨‍💻 Admin panel")
        return kb
    except Exception:
        return ReplyKeyboardMarkup(resize_keyboard=True).add("👨‍💻 Admin panel")

def _menu_for(user_id: int):
    try:
        if is_admin(user_id):
            return admin_as_user_menu()
        return _get_main_menu(user_id)
    except Exception:
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("📊 Hisobim")
        return kb

def back_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("⬅️ Ortga")
    return kb

def show_required_channels(chat_id: int):
    try:
        markup = InlineKeyboardMarkup(row_width=1)
        for channel in config.get("required_channels", []):
            if channel.get("check_enabled", True):
                markup.add(
                    InlineKeyboardButton(
                        f"📢 {channel.get('title', channel['username'])}",
                        url=f"https://t.me/{channel['username'].replace('@', '')}",
                    )
                )
        markup.add(InlineKeyboardButton("✅ Tekshirish", callback_data="check_subs"))
        safe_send_message(chat_id, get_text("not_subscribed"), reply_markup=markup)
    except Exception as e:
        logger.error(f"show_required_channels xato: {e}")
        safe_send_message(chat_id, "⚠️ Kanallarni tekshirishda xatolik.")

# =====================================
# DATABASE HELPERS
# =====================================
def create_order(kind: str, user_id: str, extra: Dict[str, Any]) -> int:
    try:
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
    except Exception as e:
        logger.error(f"create_order xato: {e}")
        return -1

def find_order(order_id: int) -> Optional[Dict[str, Any]]:
    try:
        for order in orders:
            if order.get("id") == order_id:
                return order
    except Exception as e:
        logger.error(f"find_order xato: {e}")
    return None

def complete_order_stats(uid: str):
    try:
        users[uid]["orders_count"] = users[uid].get("orders_count", 0) + 1
        save_db()
    except Exception as e:
        logger.error(f"complete_order_stats xato: {e}")

def get_referral_level(ref_count: int) -> Dict[str, Any]:
    try:
        levels = config.get("referral_levels", DEFAULT_CONFIG["referral_levels"])
        best = levels[0]
        for level in levels:
            if ref_count >= level.get("required", 0):
                best = level
        return best
    except Exception:
        return {"level": 1, "bonus": 1000, "required": 0}

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
        users[referrer_id].setdefault("referrals_list", []).append({
            "user_id": new_user_id,
            "username": users[new_user_id].get("username", "Noma'lum"),
            "date": now_str()
        })
        
        level = get_referral_level(users[referrer_id]["referrals_count"])
        bonus = int(level.get("bonus", 1000))
        users[referrer_id]["balance"] += bonus
        save_db()

        try:
            safe_send_message(
                int(referrer_id),
                get_text("referral_new", 
                    username=safe_username(new_user_id),
                    count=users[referrer_id]['referrals_count'],
                    bonus=bonus,
                    level=level.get('level')
                )
            )
        except Exception:
            pass
        return True
    except Exception as e:
        logger.error(f"Referral xato: {e}")
        return False

# =====================================
# LOTTERY SYSTEM (kengaytirilgan)
# =====================================
def create_lottery(admin_id: str, name: str, price: int, quantity: int, limit: int, prize: int) -> Dict[str, Any]:
    try:
        lottery = {
            "id": new_id(lottery_data.get("active", []) + lottery_data.get("history", [])),
            "name": name,
            "price": price,
            "quantity": quantity,
            "limit": limit,
            "prize": prize,
            "status": "active",
            "created_by": admin_id,
            "created_at": now_str(),
            "tickets": [],
            "winners": [],
            "prize_distribution": {},
            "draw_date": None,
            "total_sold": 0,
        }
        lottery_data.setdefault("active", []).append(lottery)
        save_db()
        return lottery
    except Exception as e:
        logger.error(f"create_lottery xato: {e}")
        return None

def buy_lottery_ticket(user_id: str, lottery_id: int) -> Optional[Dict[str, Any]]:
    try:
        lottery = find_active_lottery(lottery_id)
        if not lottery:
            return None
        
        if lottery["status"] != "active":
            return None
        
        if lottery["total_sold"] >= lottery["quantity"]:
            return None
        
        # Limit tekshirish
        limit = lottery.get("limit", 0)
        if limit > 0:
            user_tickets = [t for t in lottery["tickets"] if t["user_id"] == user_id]
            if len(user_tickets) >= limit:
                return None
        
        if users[user_id]["balance"] < lottery["price"]:
            return None
        
        users[user_id]["balance"] -= lottery["price"]
        ticket = {
            "user_id": user_id,
            "username": safe_username(user_id),
            "ticket_number": lottery["total_sold"] + 1,
            "purchase_date": now_str(),
        }
        lottery["tickets"].append(ticket)
        lottery["total_sold"] += 1
        users[user_id].setdefault("lottery_tickets", []).append(lottery["id"])
        save_db()
        return ticket
    except Exception as e:
        logger.error(f"buy_lottery_ticket xato: {e}")
        return None

def find_active_lottery(lottery_id: int) -> Optional[Dict[str, Any]]:
    try:
        for lottery in lottery_data.get("active", []):
            if lottery["id"] == lottery_id:
                return lottery
    except Exception as e:
        logger.error(f"find_active_lottery xato: {e}")
    return None

def find_lottery(lottery_id: int) -> Optional[Dict[str, Any]]:
    try:
        for lottery in lottery_data.get("active", []):
            if lottery["id"] == lottery_id:
                return lottery
        for lottery in lottery_data.get("history", []):
            if lottery["id"] == lottery_id:
                return lottery
    except Exception as e:
        logger.error(f"find_lottery xato: {e}")
    return None

def draw_lottery(lottery_id: int, prize_distribution: Dict[int, int]) -> Optional[List[Dict[str, Any]]]:
    try:
        lottery = find_active_lottery(lottery_id)
        if not lottery:
            return None
        
        if lottery["status"] != "active":
            return None
        
        if lottery["total_sold"] < 1:
            return None
        
        lottery["status"] = "pending_draw"
        lottery["prize_distribution"] = prize_distribution
        lottery["draw_date"] = now_str()
        
        tickets = lottery["tickets"].copy()
        random.shuffle(tickets)
        
        winners = []
        for place in sorted(prize_distribution.keys()):
            if place <= len(tickets):
                winner = tickets[place - 1]
                prize_amount = int(lottery["prize"] * (prize_distribution[place] / 100))
                winner_data = {
                    "user_id": winner["user_id"],
                    "username": winner["username"],
                    "ticket_number": winner["ticket_number"],
                    "place": place,
                    "prize": prize_amount,
                }
                winners.append(winner_data)
                
                users[winner["user_id"]]["balance"] += prize_amount
                users[winner["user_id"]]["lottery_wins"] = users[winner["user_id"]].get("lottery_wins", 0) + 1
        
        lottery["winners"] = winners
        lottery["status"] = "completed"
        
        lottery_data["active"] = [l for l in lottery_data.get("active", []) if l["id"] != lottery_id]
        lottery_data.setdefault("history", []).append(lottery)
        save_db()
        
        for winner in winners:
            try:
                safe_send_message(
                    int(winner["user_id"]),
                    f"🎉 <b>Tabriklaymiz!</b>\n\n"
                    f"Siz lotareyada {winner['place']}-o'rinni egalladingiz!\n"
                    f"🎰 Lotareya: {lottery['name']}\n"
                    f"💰 Yutuq: {winner['prize']:,} so'm\n"
                    f"🎟 Ticket: #{winner['ticket_number']}\n"
                    f"📅 Sana: {now_str()}"
                )
                safe_send_sticker(int(winner["user_id"]), "game_win")
            except Exception as e:
                logger.error(f"Winner notification xato: {e}")
        
        notify_admins(
            f"🎰 <b>Lotareya yakunlandi!</b>\n"
            f"📌 Nomi: {lottery['name']}\n"
            f"🎟 Sotilgan: {lottery['total_sold']} ta\n"
            f"🏆 G'oliblar: {len(winners)} ta\n"
            f"💰 Jami yutuq: {sum(w['prize'] for w in winners):,} so'm"
        )
        
        return winners
    except Exception as e:
        logger.error(f"draw_lottery xato: {e}")
        return None

def cancel_lottery(lottery_id: int) -> bool:
    try:
        lottery = find_active_lottery(lottery_id)
        if not lottery:
            return False
        
        if lottery["status"] != "active":
            return False
        
        for ticket in lottery["tickets"]:
            user_id = ticket["user_id"]
            users[user_id]["balance"] += lottery["price"]
            if lottery["id"] in users[user_id].get("lottery_tickets", []):
                users[user_id]["lottery_tickets"].remove(lottery["id"])
        
        lottery["status"] = "cancelled"
        lottery_data["active"] = [l for l in lottery_data.get("active", []) if l["id"] != lottery_id]
        lottery_data.setdefault("history", []).append(lottery)
        save_db()
        
        for ticket in lottery["tickets"]:
            try:
                safe_send_message(
                    int(ticket["user_id"]),
                    f"❌ Lotareya bekor qilindi\n"
                    f"🎰 {lottery['name']}\n"
                    f"💰 {lottery['price']:,} so'm balansingizga qaytarildi"
                )
            except Exception as e:
                logger.error(f"Cancellation notification xato: {e}")
        
        return True
    except Exception as e:
        logger.error(f"cancel_lottery xato: {e}")
        return False

# =====================================
# GAME HELPERS
# =====================================
def _game_key_from_text(text: str) -> Optional[str]:
    try:
        for key, g in config.get("games", {}).items():
            if g.get("name") == text:
                return key
    except Exception:
        pass
    return None

def _get_game_by_key(key: str) -> Optional[Dict[str, Any]]:
    try:
        return config.get("games", {}).get(key)
    except Exception:
        return None

def show_mines_field(chat_id: int, uid: str):
    try:
        field = users[uid].get("mines_field")
        if not field:
            return
        revealed = users[uid].get("mines_revealed", [])
        markup = InlineKeyboardMarkup(row_width=5)
        for r in range(5):
            row = []
            for c in range(5):
                if (r, c) in revealed:
                    if field[r][c] == -1:
                        row.append(InlineKeyboardButton("💣", callback_data=f"mines_noop"))
                    else:
                        row.append(InlineKeyboardButton("✅", callback_data=f"mines_noop"))
                else:
                    row.append(InlineKeyboardButton("❓", callback_data=f"mines_reveal_{r}_{c}"))
            markup.add(*row)
        
        markup.row(
            InlineKeyboardButton("💵 Qabul qilish", callback_data="mines_cashout"),
            InlineKeyboardButton("⬅️ Chiqish", callback_data="mines_exit")
        )
        
        bet = users[uid].get("mines_bet", 0)
        multiplier = float(config.get("games", {}).get("mines", {}).get("multiplier", 2.2))
        current_payout = int(bet * (1 + (len(revealed) * 0.2)))
        
        text = (
            f"💣 <b>Mines</b>\n\n"
            f"💰 Stavka: {bet:,} so'm\n"
            f"🎯 Yulduzchalar: {len(revealed)} ta\n"
            f"💵 Hozirgi yutuq: {current_payout:,} so'm\n"
            f"⚠️ 3 ta mina bor. Minaga bossangiz yutqazasiz!"
        )
        safe_send_message(chat_id, text, reply_markup=markup)
    except Exception as e:
        logger.error(f"show_mines_field xato: {e}")

# =====================================
# REFFERAL LEVELS RENDER
# =====================================
def render_referral_levels():
    try:
        levels = config.get("referral_levels", DEFAULT_CONFIG["referral_levels"])
        text = "🔰 <b>Referal darajalari</b>\n\n"
        for level in levels:
            text += f"🔹 {level.get('level')}-daraja: {level.get('required')}+ referal → {level.get('bonus'):,} so'm bonus\n"
        return text
    except Exception:
        return "🔰 Referal darajalari mavjud emas."

# =====================================
# ADMIN STATS
# =====================================
def get_admin_stats() -> Dict[str, Any]:
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        total_wagered = sum(int(u.get("total_wagered", 0)) for u in users.values())
        total_game_payout = sum(int(u.get("total_won", 0)) for u in users.values())
        total_lottery_wins = sum(int(u.get("lottery_wins", 0)) for u in users.values())
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
            "total_lottery_wins": total_lottery_wins,
            "house_edge_result": total_wagered - total_game_payout,
            "active_lotteries": len(lottery_data.get("active", [])),
            "total_lotteries": len(lottery_data.get("history", [])),
        }
    except Exception as e:
        logger.error(f"get_admin_stats xato: {e}")
        return {}

# =====================================
# RENDER TOP
# =====================================
def _render_top(field: str, label: str, suffix: str):
    try:
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
    except Exception:
        return "🏆 Reytingni yuklashda xatolik."

def _user_rank(uid: str, field: str):
    try:
        ranking = [(u, d.get(field, 0)) for u, d in users.items()]
        ranking.sort(key=lambda x: x[1], reverse=True)
        for i, (u, val) in enumerate(ranking, start=1):
            if u == uid:
                return i, val
    except Exception:
        pass
    return None, 0

# =====================================
# EARN TASKS HELPERS
# =====================================
def _incomplete_tasks(uid: str):
    try:
        done = users[uid].get("completed_earn_tasks", [])
        return [t for t in config.get("earn_tasks", []) if t["id"] not in done]
    except Exception:
        return []

def show_earn_task(chat_id: int, task: Dict[str, Any]):
    try:
        kind_label = "📢 Kanal" if task["type"] == "channel" else "👁 Post"
        action_label = "➕ Obuna bo'lish" if task["type"] == "channel" else "👁 Ko'rish"
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton(action_label, url=task["link"]),
            InlineKeyboardButton("✅ Tekshirish", callback_data=f"check_earn_{task['id']}"),
            InlineKeyboardButton("⏭ Keyingi", callback_data=f"skip_earn_{task['id']}"),
        )
        send_loading_animation(chat_id, "⏳ Vazifa yuklanmoqda...")
        safe_send_message(chat_id, f"{kind_label}: {task.get('title', '')}\n{task['link']}\n\n💰 Mukofot: {task.get('reward', 0):,} so'm", reply_markup=markup)
    except Exception as e:
        logger.error(f"show_earn_task xato: {e}")

# =====================================
# UNSUBSCRIBE RECHECK
# =====================================
def unsubscribe_recheck_loop():
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
# TEXT EDITING HELPERS
# =====================================
EDITABLE_TEXT_KEYS = {
    "welcome": "Xush kelibsiz xabari",
    "not_subscribed": "Obuna talab xabari",
    "subscribe_bonus_text": "Obuna bonusi xabari",
    "join_chat_prompt": "Chatga qo'shilish taklif xabari",
    "game_menu": "O'yinlar menyusi xabari",
    "no_games": "O'yinlar mavjud emas xabari",
    "insufficient_balance": "Balans yetarli emas xabari",
    "invalid_bet": "Noto'g'ri stavka xabari",
    "daily_bonus_taken": "Kunlik bonus olingan xabari",
    "daily_bonus_given": "Kunlik bonus berilgan xabari",
    "profile_text": "Profil xabari",
    "referral_text": "Referal xabari",
    "lottery_no_active": "Lotareya mavjud emas xabari",
    "lottery_bought": "Lotareya chiptasi sotib olingan xabari",
    "lottery_not_enough_balance": "Lotareya uchun balans yetarli emas xabari",
    "lottery_already_bought": "Lotareya allaqachon sotib olingan xabari",
    "lottery_sold_out": "Lotareya to'lgan xabari",
    "game_result_win": "O'yin yutish xabari",
    "game_result_lose": "O'yin yutqazish xabari",
    "order_created": "Buyurtma yaratilgan xabari",
    "order_completed": "Buyurtma bajarilgan xabari",
    "order_rejected": "Buyurtma rad etilgan xabari",
    "admin_topup_notification": "Admin to'ldirish xabari",
    "promo_success": "Promokod muvaffaqiyatli xabari",
    "promo_already_used": "Promokod allaqachon ishlatilgan xabari",
    "promo_invalid": "Promokod noto'g'ri xabari",
    "promo_limit_exceeded": "Promokod limiti tugagan xabari",
    "admin_panel_text": "Admin panel matni",
    "group_welcome": "Guruhdagi xush kelibsiz xabari",
    "group_button_text": "Guruhdagi tugma matni",
}

# =====================================
# SERVICE CATEGORIES HELPERS
# =====================================
def _service_categories() -> List[str]:
    try:
        explicit = [c["name"] for c in config.get("service_categories", [])]
        if explicit:
            return explicit
        cats = []
        for s in config.get("services", []):
            if s["category"] not in cats:
                cats.append(s["category"])
        return cats
    except Exception:
        return []

# =====================================
# BROADCAST HELPERS
# =====================================
def _resolve_ad_chat_ids(target_mode: str) -> List[int]:
    try:
        targets = config.get("broadcast_targets", [])
        if target_mode == "users":
            return [int(uid) for uid in users.keys()]
        if target_mode == "channels":
            return [t["id"] for t in targets if t.get("type") == "channel"]
        if target_mode == "groups":
            return [t["id"] for t in targets if t.get("type") == "group"]
        if target_mode == "everything":
            return [int(uid) for uid in users.keys()] + [t["id"] for t in targets]
    except Exception:
        pass
    return []

def _forward_ad_content_safe(message, chat_id: int):
    try:
        if message.content_type == "text":
            return safe_send_message(chat_id, message.text)
        elif message.content_type == "photo":
            return safe_send_photo(chat_id, message.photo[-1].file_id, caption=message.caption)
        elif message.content_type == "video":
            return safe_call(bot.send_video, chat_id, message.video.file_id, caption=message.caption)
        elif message.content_type == "audio":
            return safe_call(bot.send_audio, chat_id, message.audio.file_id, caption=message.caption)
        elif message.content_type == "voice":
            return safe_call(bot.send_voice, chat_id, message.voice.file_id, caption=message.caption)
        elif message.content_type == "document":
            return safe_call(bot.send_document, chat_id, message.document.file_id, caption=message.caption)
        elif message.content_type == "animation":
            return safe_call(bot.send_animation, chat_id, message.animation.file_id, caption=message.caption)
        elif message.content_type == "video_note":
            return safe_call(bot.send_video_note, chat_id, message.video_note.file_id)
        elif message.content_type == "sticker":
            return safe_call(bot.send_sticker, chat_id, message.sticker.file_id)
        else:
            return safe_send_message(chat_id, "📢 Yangi e'lon")
    except Exception as e:
        logger.error(f"_forward_ad_content_safe xato: {e}")
        return None

# =====================================
# BOT HANDLERS - START / HELP
# =====================================
@bot.message_handler(commands=["start"])
def start(message):
    try:
        if is_group_chat(message.chat.type):
            return
        
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
                f"{get_text('welcome')}\n\n"
                f"💰 Ro'yxatdan o'tish bonusi: +{welcome_bonus} so'm\n"
                f"⚖️ Balans: {users[user_id]['balance']} so'm\n"
                f"🔰 Referal darajangiz: {get_referral_level(0).get('level')}",
                reply_markup=_menu_for(message.from_user.id),
            )
            return

        save_db()
        safe_send_message(
            message.chat.id,
            f"{get_text('welcome')}\n\n"
            f"💰 Balans: {users[user_id]['balance']} so'm\n"
            f"👥 Referallar: {users[user_id].get('referrals_count', 0)} ta\n"
            f"🔰 Daraja: {get_referral_level(users[user_id].get('referrals_count', 0)).get('level')}",
            reply_markup=_menu_for(message.from_user.id),
        )
    except Exception as e:
        logger.error(f"/start xato: {e}", exc_info=True)
        safe_send_message(message.chat.id, "⚠️ Botni ishga tushirishda xatolik. Qaytadan /start bosing.")

@bot.message_handler(commands=["help"])
def help_command(message):
    try:
        if is_group_chat(message.chat.type):
            return
        safe_send_message(
            message.chat.id,
            "🤖 <b>Bot yordami</b>\n\n"
            "📊 <b>Asosiy menyu:</b>\n"
            "• 💸 Pul ishlash - Bonus, referal, promokod va vazifalar\n"
            "• 📊 Hisobim - Balans, profil va sozlamalar\n"
            "• 🛍 Xizmatlar - Do'kon\n"
            "• 🏆 Reyting - Eng yaxshi foydalanuvchilar\n"
            "• 🎮 O'yinlar - Mini o'yinlar\n"
            "• 🎰 Lotareya - Lotareyalar\n\n"
            "💡 Savol yoki muammo bo'lsa, adminga yozing: /contact",
            reply_markup=_menu_for(message.from_user.id)
        )
    except Exception as e:
        logger.error(f"/help xato: {e}")

@bot.message_handler(commands=["contact"])
def contact_command(message):
    try:
        if is_group_chat(message.chat.type):
            return
        msg = safe_send_message(message.chat.id, "📩 Xabaringizni yozing:", reply_markup=back_menu())
        if msg:
            bot.register_next_step_handler(msg, send_to_admin)
    except Exception as e:
        logger.error(f"/contact xato: {e}")

# =====================================
# GROUP HANDLERS
# =====================================
@bot.message_handler(func=lambda m: is_group_chat(m.chat.type) and m.reply_to_message and m.reply_to_message.from_user and m.reply_to_message.from_user.is_bot)
@group_handler
def group_reply_handler(message):
    try:
        bot_username = get_bot_username()
        if bot_username and bot_username in str(message.text or ""):
            btn_text = config.get("group_button_text", DEFAULT_MESSAGES["group_button_text"])
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton(btn_text, url=f"https://t.me/{bot_username}"))
            
            welcome_text = config.get("group_welcome", DEFAULT_MESSAGES["group_welcome"]).format(bot_username=bot_username)
            safe_send_message(
                message.chat.id,
                welcome_text,
                reply_to_message_id=message.message_id,
                reply_markup=markup
            )
    except Exception as e:
        logger.error(f"group_reply_handler xato: {e}")

@bot.message_handler(func=lambda m: is_group_chat(m.chat.type) and m.text and get_bot_username() in m.text)
@group_handler
def group_mention_handler(message):
    try:
        bot_username = get_bot_username()
        btn_text = config.get("group_button_text", DEFAULT_MESSAGES["group_button_text"])
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(btn_text, url=f"https://t.me/{bot_username}"))
        
        welcome_text = config.get("group_welcome", DEFAULT_MESSAGES["group_welcome"]).format(bot_username=bot_username)
        safe_send_message(
            message.chat.id,
            welcome_text,
            reply_to_message_id=message.message_id,
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"group_mention_handler xato: {e}")

# =====================================
# NAVIGATION
# =====================================
@bot.message_handler(func=lambda m: m.text == "⬅️ Asosiy menyu")
def to_main_menu(message):
    try:
        if is_group_chat(message.chat.type):
            return
        safe_send_message(message.chat.id, "🔙 Asosiy menyu", reply_markup=_menu_for(message.from_user.id))
    except Exception as e:
        logger.error(f"to_main_menu xato: {e}")

@bot.message_handler(func=lambda m: m.text == "⬅️ Ortga")
def back(message):
    try:
        if is_group_chat(message.chat.type):
            return
        safe_send_message(message.chat.id, "🔙 Orqaga", reply_markup=_menu_for(message.from_user.id))
    except Exception as e:
        logger.error(f"back xato: {e}")

# =====================================
# EARN HUB
# =====================================
@bot.message_handler(func=lambda m: m.text == "💸 Pul ishlash")
@subscription_required
def earn_hub(message):
    try:
        safe_send_message(message.chat.id, "💸 Pul ishlash bo'limi. Kerakli bo'limni tanlang:", reply_markup=earn_submenu())
    except Exception as e:
        logger.error(f"earn_hub xato: {e}")

# =====================================
# PROFILE
# =====================================
@bot.message_handler(func=lambda m: m.text == "📊 Hisobim")
@subscription_required
def profile_hub(message):
    try:
        uid = str(message.from_user.id)
        user = users[uid]
        lottery_wins = user.get("lottery_wins", 0)
        lottery_tickets = len(user.get("lottery_tickets", []))
        
        text = get_text("profile_text",
            user_id=uid,
            username=safe_username(message.from_user),
            join_date=user.get('join_date', 'Noma\'lum'),
            balance=user.get('balance', 0),
            referrals=user.get('referrals_count', 0),
            level=get_referral_level(user.get('referrals_count', 0)).get('level'),
            orders=user.get('orders_count', 0),
            games_played=user.get('games_played', 0),
            games_won=user.get('games_won', 0),
            lottery_tickets=lottery_tickets,
            lottery_wins=lottery_wins
        )
        safe_send_message(message.chat.id, text, reply_markup=profile_submenu())
    except Exception as e:
        logger.error(f"profile_hub xato: {e}")

# =====================================
# GAMES
# =====================================
@bot.message_handler(func=lambda m: m.text == "🎮 O'yinlar")
@subscription_required
def games_main_menu(message):
    try:
        active = [g for g in config.get("games", {}).values() if g.get("enabled", True)]
        if not active:
            safe_send_message(message.chat.id, get_text("no_games"), reply_markup=earn_submenu())
            return
        safe_send_message(message.chat.id, get_text("game_menu"), reply_markup=games_submenu())
    except Exception as e:
        logger.error(f"games_main_menu xato: {e}")

@bot.message_handler(func=lambda m: _game_key_from_text(m.text) is not None)
@subscription_required
def game_selected(message):
    try:
        key = _game_key_from_text(message.text)
        game = config["games"][key]
        if not game.get("enabled", True):
            safe_send_message(message.chat.id, "❌ Bu o'yin hozircha o'chirilgan.", reply_markup=games_submenu())
            return
        uid = str(message.from_user.id)
        users[uid]["pending_game"] = key
        save_db()
        
        text = (
            f"{game['name']}\n"
            f"📝 {game.get('description', '')}\n\n"
            f"💰 Balans: {users[uid]['balance']:,} so'm\n"
            f"🎯 Yutish ehtimoli: {game.get('win_chance', 0)}%\n"
            f"✖️ Koeffitsiyent: x{game.get('multiplier', 1)}\n"
            f"📉 Min stavka: {game.get('min_bet', 0):,} so'm\n"
            f"📈 Max stavka: {game.get('max_bet', 0):,} so'm\n\n"
            f"Stavka summasini kiriting:"
        )
        msg = safe_send_message(message.chat.id, text, reply_markup=back_menu())
        if msg:
            bot.register_next_step_handler(msg, process_game_bet, key)
    except Exception as e:
        logger.error(f"game_selected xato: {e}")

@safe_next_step
def process_game_bet(message, key: str):
    try:
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
            safe_send_message(message.chat.id, get_text("insufficient_balance"), reply_markup=games_submenu())
            return

        users[uid]["balance"] -= bet
        users[uid]["games_played"] = users[uid].get("games_played", 0) + 1
        users[uid]["total_wagered"] = users[uid].get("total_wagered", 0) + bet

        # Dice special
        if key == "dice":
            msg = safe_send_dice(message.chat.id, "🎲")
            if msg:
                dice_value = msg.dice.value
                win_chance = float(game.get("win_chance", 30))
                won = dice_value >= 5
                if won:
                    payout = int(bet * float(game.get("multiplier", 2.5)))
                    users[uid]["balance"] += payout
                    users[uid]["games_won"] = users[uid].get("games_won", 0) + 1
                    users[uid]["total_won"] = users[uid].get("total_won", 0) + payout
                    save_db()
                    safe_send_sticker(message.chat.id, "game_win")
                    safe_send_message(
                        message.chat.id,
                        get_text("game_result_win",
                            game_name=game['name'],
                            bet=bet,
                            payout=payout,
                            balance=users[uid]['balance']
                        ),
                        reply_markup=games_submenu(),
                    )
                else:
                    save_db()
                    safe_send_sticker(message.chat.id, "game_lose")
                    safe_send_message(
                        message.chat.id,
                        get_text("game_result_lose",
                            game_name=game['name'],
                            bet=bet,
                            balance=users[uid]['balance']
                        ),
                        reply_markup=games_submenu(),
                    )
                return

        # Wheel special
        if key == "wheel":
            send_loading_animation(message.chat.id, "🎡 Baraban aylanmoqda...")
            time.sleep(1.5)
            win_chance = float(game.get("win_chance", 25))
            won = random.uniform(0, 100) < win_chance
            if won:
                payout = int(bet * float(game.get("multiplier", 3.0)))
                users[uid]["balance"] += payout
                users[uid]["games_won"] = users[uid].get("games_won", 0) + 1
                users[uid]["total_won"] = users[uid].get("total_won", 0) + payout
                save_db()
                safe_send_sticker(message.chat.id, "game_win")
                safe_send_message(
                    message.chat.id,
                    get_text("game_result_win",
                        game_name=game['name'],
                        bet=bet,
                        payout=payout,
                        balance=users[uid]['balance']
                    ),
                    reply_markup=games_submenu(),
                )
            else:
                save_db()
                safe_send_sticker(message.chat.id, "game_lose")
                safe_send_message(
                    message.chat.id,
                    get_text("game_result_lose",
                        game_name=game['name'],
                        bet=bet,
                        balance=users[uid]['balance']
                    ),
                    reply_markup=games_submenu(),
                )
            return

        # Mines special
        if key == "mines":
            users[uid]["mines_bet"] = bet
            users[uid]["mines_count"] = 3
            users[uid]["mines_revealed"] = []
            field = [[0 for _ in range(5)] for _ in range(5)]
            mines = set()
            while len(mines) < 3:
                mines.add((random.randint(0, 4), random.randint(0, 4)))
            for r, c in mines:
                field[r][c] = -1
            users[uid]["mines_field"] = field
            save_db()
            show_mines_field(message.chat.id, uid)
            return

        # Generic game
        win_chance = float(game.get("win_chance", 50))
        multiplier = float(game.get("multiplier", 2))
        won = random.uniform(0, 100) < win_chance

        if won:
            payout = int(bet * multiplier)
            users[uid]["balance"] += payout
            users[uid]["games_won"] = users[uid].get("games_won", 0) + 1
            users[uid]["total_won"] = users[uid].get("total_won", 0) + payout
            save_db()
            safe_send_sticker(message.chat.id, "game_win")
            safe_send_message(
                message.chat.id,
                get_text("game_result_win",
                    game_name=game['name'],
                    bet=bet,
                    payout=payout,
                    balance=users[uid]['balance']
                ),
                reply_markup=games_submenu(),
            )
        else:
            save_db()
            safe_send_sticker(message.chat.id, "game_lose")
            safe_send_message(
                message.chat.id,
                get_text("game_result_lose",
                    game_name=game['name'],
                    bet=bet,
                    balance=users[uid]['balance']
                ),
                reply_markup=games_submenu(),
            )
    except Exception as e:
        logger.error(f"process_game_bet xato: {e}")
        safe_send_message(message.chat.id, "⚠️ Xatolik yuz berdi.", reply_markup=games_submenu())

# =====================================
# GAME CALLBACKS
# =====================================
@bot.callback_query_handler(func=lambda c: c.data.startswith("mines_reveal_"))
@safe_callback_handler
def mines_reveal(c):
    try:
        uid = str(c.from_user.id)
        _, _, r_str, c_str = c.data.split("_")
        r, c = int(r_str), int(c_str)
        
        field = users[uid].get("mines_field")
        if not field:
            safe_answer_callback_query(c.id, "❌ O'yin topilmadi")
            return
        
        revealed = users[uid].get("mines_revealed", [])
        if (r, c) in revealed:
            safe_answer_callback_query(c.id, "❌ Bu katak allaqachon ochilgan")
            return
        
        if field[r][c] == -1:
            safe_answer_callback_query(c.id, "💥 Minaga bosdingiz!")
            users[uid]["mines_field"] = None
            users[uid]["mines_revealed"] = []
            save_db()
            safe_send_sticker(c.message.chat.id, "game_lose")
            safe_send_message(
                c.message.chat.id,
                f"💥 Minaga bosdingiz!\n"
                f"💸 Stavka: -{users[uid].get('mines_bet', 0):,} so'm\n"
                f"⚖️ Balans: {users[uid]['balance']:,} so'm",
                reply_markup=games_submenu()
            )
            return
        
        revealed.append((r, c))
        users[uid]["mines_revealed"] = revealed
        save_db()
        
        safe_answer_callback_query(c.id, "✅ Katak ochildi")
        show_mines_field(c.message.chat.id, uid)
    except Exception as e:
        logger.error(f"mines_reveal xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "mines_cashout")
@safe_callback_handler
def mines_cashout(c):
    try:
        uid = str(c.from_user.id)
        field = users[uid].get("mines_field")
        if not field:
            safe_answer_callback_query(c.id, "❌ O'yin topilmadi")
            return
        
        revealed = users[uid].get("mines_revealed", [])
        bet = users[uid].get("mines_bet", 0)
        payout = int(bet * (1 + (len(revealed) * 0.2)))
        
        users[uid]["balance"] += payout
        users[uid]["games_won"] = users[uid].get("games_won", 0) + 1
        users[uid]["total_won"] = users[uid].get("total_won", 0) + payout
        users[uid]["mines_field"] = None
        users[uid]["mines_revealed"] = []
        save_db()
        
        safe_answer_callback_query(c.id, f"✅ {payout:,} so'm yutdingiz!")
        safe_send_sticker(c.message.chat.id, "game_win")
        safe_send_message(
            c.message.chat.id,
            f"🎉 Siz yutdingiz!\n"
            f"💣 Mines\n"
            f"🎯 {len(revealed)} ta yulduzcha\n"
            f"💰 Stavka: {bet:,} so'm\n"
            f"✅ Yutuq: +{payout:,} so'm\n"
            f"⚖️ Balans: {users[uid]['balance']:,} so'm",
            reply_markup=games_submenu()
        )
    except Exception as e:
        logger.error(f"mines_cashout xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "mines_exit")
@safe_callback_handler
def mines_exit(c):
    try:
        uid = str(c.from_user.id)
        users[uid]["mines_field"] = None
        users[uid]["mines_revealed"] = []
        save_db()
        safe_answer_callback_query(c.id, "⬅️ O'yindan chiqdingiz")
        safe_send_message(c.message.chat.id, "🔙 O'yindan chiqdingiz", reply_markup=games_submenu())
    except Exception as e:
        logger.error(f"mines_exit xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "mines_noop")
@safe_callback_handler
def mines_noop(c):
    safe_answer_callback_query(c.id)

# =====================================
# DAILY BONUS
# =====================================
@bot.message_handler(func=lambda m: m.text == "🎁 Kunlik bonus")
@subscription_required
def daily_bonus(message):
    try:
        uid = str(message.from_user.id)
        today = datetime.now().strftime("%Y-%m-%d")
        last_bonus = users[uid].get("last_daily_bonus")
        
        if last_bonus and last_bonus.startswith(today):
            next_time = datetime.strptime(today, "%Y-%m-%d") + timedelta(days=1)
            delta = next_time - datetime.now()
            hours = delta.seconds // 3600
            minutes = (delta.seconds % 3600) // 60
            safe_send_message(
                message.chat.id, 
                get_text("daily_bonus_taken", hours=hours, minutes=minutes)
            )
            return

        streak = users[uid].get("daily_streak", 0)
        if last_bonus:
            last_date = datetime.strptime(last_bonus[:10], "%Y-%m-%d")
            if (datetime.now() - last_date).days == 1:
                streak += 1
            else:
                streak = 0
        else:
            streak = 0
        
        min_bonus, max_bonus = config.get("daily_bonus_range", [100, 500])
        base_bonus = random.randint(int(min_bonus), int(max_bonus))
        streak_multiplier = 1 + (streak * 0.1)
        bonus = int(base_bonus * streak_multiplier)
        
        users[uid]["balance"] += bonus
        users[uid]["daily_streak"] = streak + 1
        users[uid]["last_daily_bonus"] = now_str()
        save_db()
        
        safe_send_sticker(message.chat.id, "money")
        send_loading_animation(message.chat.id, "🎉 Kunlik bonus hisoblanmoqda...")
        safe_send_message(
            message.chat.id,
            get_text("daily_bonus_given",
                bonus=bonus,
                streak=streak + 1,
                multiplier=streak_multiplier
            )
        )
    except Exception as e:
        logger.error(f"daily_bonus xato: {e}")

# =====================================
# REFERRAL
# =====================================
@bot.message_handler(func=lambda m: m.text == "👥 Referal")
@subscription_required
def referral_menu(message):
    try:
        uid = str(message.from_user.id)
        bot_username = get_bot_username()
        ref_link = f"https://t.me/{bot_username}?start={uid}"
        
        ref_list = users[uid].get("referrals_list", [])
        ref_text = ""
        if ref_list:
            ref_text = "\n\n👥 <b>Referallar ro'yxati:</b>\n"
            for i, ref in enumerate(ref_list[-10:], 1):
                ref_text += f"{i}. {ref.get('username', 'Noma\'lum')} - {ref.get('date', '')}\n"
            if len(ref_list) > 10:
                ref_text += f"\n... va yana {len(ref_list) - 10} ta"
        
        level = get_referral_level(users[uid].get('referrals_count', 0))
        next_level = None
        for l in config.get("referral_levels", []):
            if l.get("level") == level.get("level") + 1:
                next_level = l
                break
        
        next_required = next_level.get("required", 0) if next_level else 0
        
        text = get_text("referral_text",
            referrals=users[uid].get('referrals_count', 0),
            level=level.get('level'),
            bonus=level.get('bonus'),
            next_required=next_required,
            ref_link=ref_link
        ) + ref_text
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("📢 Do'stlarga yuborish", switch_inline_query=f"Taklif havolam: {ref_link}"))
        markup.add(InlineKeyboardButton("📊 Darajalar haqida", callback_data="show_referral_levels"))
        safe_send_message(message.chat.id, text, reply_markup=markup)
    except Exception as e:
        logger.error(f"referral_menu xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "show_referral_levels")
@safe_callback_handler
def show_referral_levels(c):
    try:
        text = render_referral_levels()
        safe_answer_callback_query(c.id)
        safe_send_message(c.message.chat.id, text)
    except Exception as e:
        logger.error(f"show_referral_levels xato: {e}")

# =====================================
# PROMO CODE
# =====================================
@bot.message_handler(func=lambda m: m.text == "🎟 Promokod")
@subscription_required
def promo_menu(message):
    try:
        msg = safe_send_message(message.chat.id, "🎟 Promokodni kiriting:", reply_markup=back_menu())
        if msg:
            bot.register_next_step_handler(msg, process_promo)
    except Exception as e:
        logger.error(f"promo_menu xato: {e}")

@safe_next_step
def process_promo(message):
    try:
        if message.text == "⬅️ Ortga":
            safe_send_message(message.chat.id, "🔙 Orqaga", reply_markup=earn_submenu())
            return
        uid = str(message.from_user.id)
        code = message.text.strip().upper()
        if code not in promo_codes:
            safe_send_message(message.chat.id, get_text("promo_invalid"), reply_markup=earn_submenu())
            return
        if code in users[uid].get("used_promo", []):
            safe_send_message(message.chat.id, get_text("promo_already_used"), reply_markup=earn_submenu())
            return
        limits = config.get("promo_limits", {}).get(code)
        if limits:
            max_uses = int(limits.get("max_uses", 0) or 0)
            used_count = int(limits.get("used_count", 0) or 0)
            if max_uses > 0 and used_count >= max_uses:
                safe_send_message(message.chat.id, get_text("promo_limit_exceeded"), reply_markup=earn_submenu())
                return
            limits["used_count"] = used_count + 1
        amount = int(promo_codes[code])
        users[uid].setdefault("used_promo", []).append(code)
        users[uid]["balance"] += amount
        save_db()
        safe_send_sticker(message.chat.id, "success")
        send_loading_animation(message.chat.id, "💰 Promokod qabul qilindi...")
        safe_send_message(message.chat.id, get_text("promo_success", amount=amount), reply_markup=earn_submenu())
    except Exception as e:
        logger.error(f"process_promo xato: {e}")

# =====================================
# EARN TASKS
# =====================================
@bot.message_handler(func=lambda m: m.text == "📋 Vazifalar")
@subscription_required
def earn_tasks_entry(message):
    try:
        uid = str(message.from_user.id)
        tasks_left = _incomplete_tasks(uid)
        if not tasks_left:
            safe_send_message(message.chat.id, "✅ Hozircha barcha topshiriqlar bajarilgan yoki mavjud emas.", reply_markup=earn_submenu())
            return
        show_earn_task(message.chat.id, tasks_left[0])
    except Exception as e:
        logger.error(f"earn_tasks_entry xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("check_earn_"))
@safe_callback_handler
def check_earn(c):
    try:
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
        safe_answer_callback_query(c.id, f"+{reward:,} so'm")
        remaining = _incomplete_tasks(uid)
        safe_call(bot.edit_message_reply_markup, c.message.chat.id, c.message.message_id, reply_markup=None)
        if remaining:
            show_earn_task(c.message.chat.id, remaining[0])
        else:
            safe_send_message(c.message.chat.id, "✅ Barcha topshiriqlar bajarildi", reply_markup=earn_submenu())
    except Exception as e:
        logger.error(f"check_earn xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("skip_earn_"))
@safe_callback_handler
def skip_earn(c):
    try:
        uid = str(c.from_user.id)
        current = int(c.data.split("_")[-1])
        remaining = [t for t in _incomplete_tasks(uid) if t["id"] != current]
        safe_call(bot.edit_message_reply_markup, c.message.chat.id, c.message.message_id, reply_markup=None)
        if not remaining:
            safe_answer_callback_query(c.id, "❌ Boshqa topshiriq yo'q")
            return
        show_earn_task(c.message.chat.id, remaining[0])
    except Exception as e:
        logger.error(f"skip_earn xato: {e}")

# =====================================
# SHOP / SERVICES
# =====================================
@bot.message_handler(func=lambda m: m.text == "🛍 Xizmatlar")
@subscription_required
def shop(message):
    try:
        cats = _service_categories()
        if not cats:
            safe_send_message(message.chat.id, "❌ Hozircha xizmatlar mavjud emas.")
            return
        markup = InlineKeyboardMarkup(row_width=1)
        for cat in cats:
            markup.add(InlineKeyboardButton(f"📦 {cat}", callback_data=f"shopcat_{cat}"))
        safe_send_message(message.chat.id, "🛍 Do'kon bo'limi:", reply_markup=markup)
    except Exception as e:
        logger.error(f"shop xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("shopcat_"))
@safe_callback_handler
def shop_category(c):
    try:
        category = c.data.split("_", 1)[1]
        items = [s for s in config.get("services", []) if s["category"] == category]
        markup = InlineKeyboardMarkup(row_width=1)
        for s in items:
            desc = f" - {s.get('description')}" if s.get("description") else ""
            markup.add(InlineKeyboardButton(f"{s['name']} — {s['price']:,} so'm{desc}", callback_data=f"buyserv_{s['id']}"))
        markup.add(InlineKeyboardButton("⬅️ Ortga", callback_data="shop_back"))
        text = f"🛍 {category}"
        if not items:
            text += "\n\nHozircha bu kategoriyada mahsulot yo'q"
        safe_edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=markup)
    except Exception as e:
        logger.error(f"shop_category xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "shop_back")
@safe_callback_handler
def shop_back(c):
    try:
        cats = _service_categories()
        markup = InlineKeyboardMarkup(row_width=1)
        for cat in cats:
            markup.add(InlineKeyboardButton(f"📦 {cat}", callback_data=f"shopcat_{cat}"))
        safe_edit_message_text("🛍 Do'kon bo'limi:", c.message.chat.id, c.message.message_id, reply_markup=markup)
    except Exception as e:
        logger.error(f"shop_back xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("buyserv_"))
@safe_callback_handler
def buy_service(c):
    try:
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
    except Exception as e:
        logger.error(f"buy_service xato: {e}")

@safe_next_step
def process_purchase_id(message):
    try:
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
            safe_send_message(message.chat.id, "❌ Balans yetarli emas", reply_markup=_menu_for(message.from_user.id))
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
        safe_send_message(
            message.chat.id,
            get_text("order_created",
                order_id=order_id,
                service_name=service["name"],
                price=service["price"]
            ),
            reply_markup=_menu_for(message.from_user.id)
        )
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
    except Exception as e:
        logger.error(f"process_purchase_id xato: {e}")

# =====================================
# TOP-UP
# =====================================
@bot.message_handler(func=lambda m: m.text == "➕ Hisobni to'ldirish")
@subscription_required
def topup_balance(message):
    try:
        cards = config.get("payment_cards", [])
        if not cards:
            safe_send_message(message.chat.id, "❌ Hozircha to'lov kartasi mavjud emas. Admin bilan bog'laning.")
            return
        markup = InlineKeyboardMarkup(row_width=1)
        for card in cards:
            markup.add(InlineKeyboardButton(f"💳 {card.get('bank', '')} — {card.get('holder', '')}", callback_data=f"topup_card_{card['id']}"))
        safe_send_message(message.chat.id, "💳 To'lov qilish uchun kartani tanlang:", reply_markup=markup)
    except Exception as e:
        logger.error(f"topup_balance xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("topup_card_"))
@safe_callback_handler
def topup_card_selected(c):
    try:
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
    except Exception as e:
        logger.error(f"topup_card_selected xato: {e}")

@safe_next_step
def process_topup_amount(message, card_id: int):
    try:
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
    except Exception as e:
        logger.error(f"process_topup_amount xato: {e}")

@safe_next_step
def process_topup_receipt(message):
    try:
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
                safe_send_photo(channel_id, receipt_file_id, caption=caption, reply_markup=kb)
                sent = True
            except Exception as e:
                logger.error(f"Payment kanaliga yuborishda xato: {e}")
        if not sent:
            for admin_id in list(ADMINS.keys()):
                try:
                    safe_send_photo(int(admin_id), receipt_file_id, caption=caption, reply_markup=kb)
                except Exception as e:
                    logger.debug(f"Admin fallback xato ({admin_id}): {e}")
    except Exception as e:
        logger.error(f"process_topup_receipt xato: {e}")

# =====================================
# PAYMENT ADMIN CALLBACKS
# =====================================
@bot.callback_query_handler(func=lambda c: c.data.startswith("payadm_"))
@safe_callback_handler
def payadm_action(c):
    try:
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
            safe_send_message(int(uid), get_text("order_admin_approved", order_id=order_id, amount=order.get('amount', 0)))
            safe_send_sticker(int(uid), "success")
            safe_answer_callback_query(c.id, "✅ Tasdiqlandi")
            new_caption = (c.message.caption or "") + f"\n\n✅ Bajarildi: {order['approved_by']}"
            safe_edit_message_caption(new_caption, c.message.chat.id, c.message.message_id, reply_markup=None)
        elif action == "reject":
            order["status"] = "rejected"
            order["rejected_by"] = safe_username(c.from_user)
            save_db()
            safe_send_message(int(order["user_id"]), get_text("order_rejected", amount=order.get('amount', 0)))
            safe_answer_callback_query(c.id, "❌ Rad etildi")
            new_caption = (c.message.caption or "") + f"\n\n❌ Rad etildi: {order['rejected_by']}"
            safe_edit_message_caption(new_caption, c.message.chat.id, c.message.message_id, reply_markup=None)
    except Exception as e:
        logger.error(f"payadm_action xato: {e}")

# =====================================
# ORDER CALLBACKS
# =====================================
@bot.callback_query_handler(func=lambda c: c.data.startswith("approve_order_") or c.data.startswith("reject_order_"))
@safe_callback_handler
def approve_reject_order(c):
    try:
        if not is_admin(c.from_user.id):
            safe_answer_callback_query(c.id, "❌ Ruxsat yo'q")
            return
        is_approve = c.data.startswith("approve_order_")
        order_id = int(c.data.split("_")[-1])
        order = find_order(order_id)
        if not order:
            safe_answer_callback_query(c.id, "❌ Buyurtma topilmadi")
            return
        if order.get("status") != "pending":
            safe_answer_callback_query(c.id, "❌ Buyurtma allaqachon ko'rilgan")
            return
        
        if is_approve:
            order["status"] = "completed"
            order["approved_by"] = safe_username(c.from_user)
            order["approved_date"] = datetime.now().isoformat()
            complete_order_stats(order["user_id"])
            save_db()
            safe_send_message(int(order["user_id"]), get_text("order_completed", order_id=order_id))
            safe_send_sticker(int(order["user_id"]), "success")
            safe_answer_callback_query(c.id, "✅ Tasdiqlandi")
            result = safe_edit_message_text(f"✅ Buyurtma #{order_id} tasdiqlandi", c.message.chat.id, c.message.message_id)
            if result is None:
                safe_edit_message_caption(f"✅ Buyurtma #{order_id} tasdiqlandi", c.message.chat.id, c.message.message_id)
        else:
            order["status"] = "rejected"
            order["rejected_by"] = safe_username(c.from_user)
            order["rejected_date"] = datetime.now().isoformat()
            users[order["user_id"]]["balance"] += int(order.get("amount", 0))
            save_db()
            safe_send_message(int(order["user_id"]), get_text("order_rejected", amount=order.get('amount', 0)))
            safe_answer_callback_query(c.id, "❌ Rad etildi")
            result = safe_edit_message_text(f"❌ Buyurtma #{order_id} rad etildi", c.message.chat.id, c.message.message_id)
            if result is None:
                safe_edit_message_caption(f"❌ Buyurtma #{order_id} rad etildi", c.message.chat.id, c.message.message_id)
    except Exception as e:
        logger.error(f"approve_reject_order xato: {e}")

# =====================================
# LEADERBOARD
# =====================================
@bot.message_handler(func=lambda m: m.text == "🏆 Reyting")
@subscription_required
def leaderboard_menu(message):
    try:
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton("👥 Referallar bo'yicha", callback_data="top_ref"))
        markup.add(InlineKeyboardButton("📦 Buyurtmalar bo'yicha", callback_data="top_orders"))
        markup.add(InlineKeyboardButton("💰 Balans bo'yicha", callback_data="top_balance"))
        markup.add(InlineKeyboardButton("🎮 O'yinlarda yutuq bo'yicha", callback_data="top_gamewin"))
        markup.add(InlineKeyboardButton("🎰 Lotareya yutuqlari bo'yicha", callback_data="top_lottery"))
        markup.add(InlineKeyboardButton("🎯 Mening o'rnim", callback_data="my_rank"))
        safe_send_message(message.chat.id, "🏆 Reyting turini tanlang:", reply_markup=markup)
    except Exception as e:
        logger.error(f"leaderboard_menu xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data in ["top_ref", "top_orders", "top_balance", "top_gamewin", "top_lottery", "my_rank"])
@safe_callback_handler
def leaderboard_callback(c):
    try:
        if c.data == "top_ref":
            text = _render_top("referrals_count", "TOP referallar", "ta")
        elif c.data == "top_orders":
            text = _render_top("orders_count", "TOP buyurtmalar", "ta")
        elif c.data == "top_gamewin":
            text = _render_top("total_won", "TOP o'yin yutuqlari", "so'm")
        elif c.data == "top_lottery":
            text = _render_top("lottery_wins", "TOP lotareya yutuqlari", "ta")
        elif c.data == "top_balance":
            text = _render_top("balance", "TOP balans", "so'm")
        else:  # my_rank
            uid = str(c.from_user.id)
            rank_bal, bal = _user_rank(uid, "balance")
            rank_ref, ref = _user_rank(uid, "referrals_count")
            rank_ord, ordc = _user_rank(uid, "orders_count")
            rank_lot, lot = _user_rank(uid, "lottery_wins")
            text = (
                f"🎯 <b>Sizning o'rningiz</b>\n\n"
                f"💰 Balans: #{rank_bal} ({bal:,} so'm)\n"
                f"👥 Referallar: #{rank_ref} ({ref} ta)\n"
                f"📦 Buyurtmalar: #{rank_ord} ({ordc} ta)\n"
                f"🎰 Lotareya: #{rank_lot} ({lot} ta yutuq)"
            )
        safe_answer_callback_query(c.id)
        safe_send_message(c.message.chat.id, text)
    except Exception as e:
        logger.error(f"leaderboard_callback xato: {e}")

# =====================================
# LOTTERY MENU
# =====================================
@bot.message_handler(func=lambda m: m.text == "🎰 Lotareya")
@subscription_required
def lottery_menu(message):
    try:
        active_lotteries = lottery_data.get("active", [])
        if not active_lotteries:
            safe_send_message(
                message.chat.id,
                get_text("lottery_no_active"),
                reply_markup=earn_submenu()
            )
            return
        
        markup = InlineKeyboardMarkup(row_width=1)
        for lottery in active_lotteries:
            if lottery["status"] == "active":
                ticket_text = f"🎟 {lottery['total_sold']}/{lottery['quantity']}"
                markup.add(
                    InlineKeyboardButton(
                        f"🎰 {lottery['name']} - {lottery['price']:,} so'm ({ticket_text})",
                        callback_data=f"lottery_view_{lottery['id']}"
                    )
                )
        
        markup.add(InlineKeyboardButton("📊 Lotareya tarixi", callback_data="lottery_history"))
        safe_send_message(message.chat.id, "🎰 <b>Faol lotareyalar</b>\n\nLotareyani tanlang va omadingizni sinab ko'ring:", reply_markup=markup)
    except Exception as e:
        logger.error(f"lottery_menu xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("lottery_view_"))
@safe_callback_handler
def lottery_view(c):
    try:
        lottery_id = int(c.data.split("_")[-1])
        lottery = find_active_lottery(lottery_id)
        if not lottery:
            safe_answer_callback_query(c.id, "❌ Lotareya topilmadi")
            return
        
        uid = str(c.from_user.id)
        has_ticket = uid in [t["user_id"] for t in lottery["tickets"]]
        
        text = (
            f"🎰 <b>{lottery['name']}</b>\n\n"
            f"💰 Narx: {lottery['price']:,} so'm\n"
            f"🎟 Chiptalar: {lottery['total_sold']}/{lottery['quantity']}\n"
            f"🏆 Yutuq: {lottery['prize']:,} so'm\n"
            f"📅 Yaratilgan: {lottery['created_at']}\n"
            f"📊 Holat: {'✅ Faol' if lottery['status'] == 'active' else '⏳ Yakunlanmoqda'}\n\n"
        )
        
        if has_ticket:
            text += "✅ Sizda bu lotareyaga chipta bor!"
            user_tickets = [t for t in lottery["tickets"] if t["user_id"] == uid]
            if user_tickets:
                text += f"\n🎟 Ticket #: {user_tickets[0]['ticket_number']}"
        else:
            text += f"🎟 Chipta narxi: {lottery['price']:,} so'm"
        
        # Limitni ko'rsatish
        limit = lottery.get("limit", 0)
        if limit > 0:
            user_tickets_count = sum(1 for t in lottery["tickets"] if t["user_id"] == uid)
            text += f"\n📊 Limit: {user_tickets_count}/{limit} chipta"
        
        markup = InlineKeyboardMarkup(row_width=2)
        if not has_ticket and lottery["total_sold"] < lottery["quantity"]:
            # Limit tekshirish
            limit = lottery.get("limit", 0)
            if limit == 0 or user_tickets_count < limit:
                markup.add(InlineKeyboardButton("🎟 Chipta sotib olish", callback_data=f"lottery_buy_{lottery_id}"))
        markup.add(InlineKeyboardButton("🔄 Yangilash", callback_data=f"lottery_view_{lottery_id}"))
        markup.add(InlineKeyboardButton("⬅️ Ortga", callback_data="lottery_back"))
        
        safe_answer_callback_query(c.id)
        safe_edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=markup)
    except Exception as e:
        logger.error(f"lottery_view xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("lottery_buy_"))
@safe_callback_handler
def lottery_buy(c):
    try:
        lottery_id = int(c.data.split("_")[-1])
        lottery = find_active_lottery(lottery_id)
        if not lottery:
            safe_answer_callback_query(c.id, "❌ Lotareya topilmadi")
            return
        
        uid = str(c.from_user.id)
        
        if uid in [t["user_id"] for t in lottery["tickets"]]:
            safe_answer_callback_query(c.id, get_text("lottery_already_bought"))
            return
        
        # Limit tekshirish
        limit = lottery.get("limit", 0)
        if limit > 0:
            user_tickets = [t for t in lottery["tickets"] if t["user_id"] == uid]
            if len(user_tickets) >= limit:
                safe_answer_callback_query(c.id, f"❌ Siz uchun limit: {limit} ta chipta")
                return
        
        if lottery["total_sold"] >= lottery["quantity"]:
            safe_answer_callback_query(c.id, get_text("lottery_sold_out"))
            return
        
        if users[uid]["balance"] < lottery["price"]:
            safe_answer_callback_query(c.id, get_text("lottery_not_enough_balance", price=lottery["price"]))
            return
        
        ticket = buy_lottery_ticket(uid, lottery_id)
        if not ticket:
            safe_answer_callback_query(c.id, "❌ Xatolik yuz berdi")
            return
        
        safe_answer_callback_query(c.id, get_text("lottery_bought", ticket_number=ticket["ticket_number"]))
        safe_send_sticker(c.message.chat.id, "success")
        
        lottery_view(c)
    except Exception as e:
        logger.error(f"lottery_buy xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "lottery_back")
@safe_callback_handler
def lottery_back(c):
    try:
        lottery_menu(c.message)
    except Exception as e:
        logger.error(f"lottery_back xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "lottery_history")
@safe_callback_handler
def lottery_history(c):
    try:
        history = lottery_data.get("history", [])[-10:]
        if not history:
            safe_answer_callback_query(c.id, "❌ Hali lotareya tarixi yo'q")
            return
        
        text = "📊 <b>Lotareya tarixi</b>\n\n"
        for lottery in reversed(history):
            text += (
                f"🎰 {lottery['name']}\n"
                f"   🎟 Sotilgan: {lottery['total_sold']} ta\n"
                f"   🏆 G'oliblar: {len(lottery.get('winners', []))} ta\n"
                f"   📅 {lottery['draw_date']}\n"
                f"   📊 Holat: {'✅ Tugagan' if lottery['status'] == 'completed' else '❌ Bekor qilingan'}\n\n"
            )
        
        safe_answer_callback_query(c.id)
        safe_send_message(c.message.chat.id, text, reply_markup=InlineKeyboardMarkup().add(
            InlineKeyboardButton("⬅️ Ortga", callback_data="lottery_back")
        ))
    except Exception as e:
        logger.error(f"lottery_history xato: {e}")

# =====================================
# SETTINGS
# =====================================
@bot.message_handler(func=lambda m: m.text == "⚙️ Sozlamalar")
@subscription_required
def settings(message):
    try:
        uid = str(message.from_user.id)
        status = "✅ Yoqilgan" if users[uid].get("notifications", True) else "❌ O'chirilgan"
        safe_send_message(message.chat.id, f"⚙️ <b>Sozlamalar</b>\n\n🔔 Bildirishnomalar: {status}", reply_markup=settings_submenu(uid))
    except Exception as e:
        logger.error(f"settings xato: {e}")

@bot.message_handler(func=lambda m: m.text and m.text.startswith(("🔔 Bildirishnoma", "🔕 Bildirishnoma")))
@subscription_required
def toggle_notifications(message):
    try:
        uid = str(message.from_user.id)
        users[uid]["notifications"] = not users[uid].get("notifications", True)
        save_db()
        safe_send_message(
            message.chat.id,
            f"✅ Holat: {'yoqildi' if users[uid]['notifications'] else 'o\'chirildi'}",
            reply_markup=settings_submenu(uid),
        )
    except Exception as e:
        logger.error(f"toggle_notifications xato: {e}")

@bot.message_handler(func=lambda m: m.text == "🌐 Til sozlamalari")
@subscription_required
def language_settings(message):
    try:
        safe_send_message(message.chat.id, "🌐 Hozircha faqat o'zbek tili qo'llab-quvvatlanadi. Tez orada boshqa tillar qo'shiladi.", reply_markup=settings_submenu(str(message.from_user.id)))
    except Exception as e:
        logger.error(f"language_settings xato: {e}")

@bot.message_handler(func=lambda m: m.text == "📄 Mening ma'lumotlarim")
@subscription_required
def my_data(message):
    try:
        uid = str(message.from_user.id)
        user = users[uid]
        lottery_tickets = len(user.get("lottery_tickets", []))
        text = (
            f"📄 <b>Mening ma'lumotlarim</b>\n\n"
            f"🆔 ID: <code>{uid}</code>\n"
            f"📛 Username: {safe_username(message.from_user)}\n"
            f"📅 Ro'yxatdan o'tgan sana: {user.get('join_date')}\n"
            f"⏱ Oxirgi faollik: {user.get('last_active')}\n"
            f"💰 Balans: {user.get('balance', 0):,} so'm\n"
            f"👥 Referallar: {user.get('referrals_count', 0)}\n"
            f"🔰 Daraja: {get_referral_level(user.get('referrals_count', 0)).get('level')}\n"
            f"📦 Buyurtmalar: {user.get('orders_count', 0)}\n"
            f"🎮 O'ynagan o'yinlar: {user.get('games_played', 0)}\n"
            f"🎰 Lotareya: {lottery_tickets} ta chipta, {user.get('lottery_wins', 0)} ta yutuq"
        )
        safe_send_message(message.chat.id, text, reply_markup=settings_submenu(uid))
    except Exception as e:
        logger.error(f"my_data xato: {e}")

@bot.message_handler(func=lambda m: m.text == "📜 Buyurtmalar tarixi")
@subscription_required
def order_history(message):
    try:
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
    except Exception as e:
        logger.error(f"order_history xato: {e}")

@bot.message_handler(func=lambda m: m.text == "📩 Adminga yozish")
@subscription_required
def contact_admin(message):
    try:
        msg = safe_send_message(message.chat.id, "📩 Xabaringizni yozing:", reply_markup=back_menu())
        if msg:
            bot.register_next_step_handler(msg, send_to_admin)
    except Exception as e:
        logger.error(f"contact_admin xato: {e}")

@safe_next_step
def send_to_admin(message):
    try:
        if message.text == "⬅️ Ortga":
            safe_send_message(message.chat.id, "🔙 Orqaga", reply_markup=profile_submenu())
            return
        uid = str(message.from_user.id)
        for admin_id in list(ADMINS.keys()):
            try:
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton("✏️ Javob yozish", callback_data=f"reply_user_{uid}"))
                if message.content_type == "text":
                    safe_send_message(int(admin_id), f"📩 Userdan xabar\n👤 {safe_username(message.from_user)}\n🆔 <code>{uid}</code>\n\n{message.text}", reply_markup=kb)
                elif message.content_type == "photo":
                    safe_send_photo(int(admin_id), message.photo[-1].file_id, caption=f"📩 Userdan rasm\n👤 {safe_username(message.from_user)}\n🆔 <code>{uid}</code>\n\n{message.caption or ''}", reply_markup=kb)
                elif message.content_type == "video":
                    safe_call(bot.send_video, int(admin_id), message.video.file_id, caption=f"📩 Userdan video\n👤 {safe_username(message.from_user)}\n🆔 <code>{uid}</code>\n\n{message.caption or ''}", reply_markup=kb)
                elif message.content_type == "document":
                    safe_call(bot.send_document, int(admin_id), message.document.file_id, caption=f"📩 Userdan fayl\n👤 {safe_username(message.from_user)}\n🆔 <code>{uid}</code>\n\n{message.caption or ''}", reply_markup=kb)
            except Exception as e:
                logger.error(f"Admin msg xato: {e}")
        safe_send_message(message.chat.id, "✅ Xabar yuborildi", reply_markup=profile_submenu())
    except Exception as e:
        logger.error(f"send_to_admin xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("reply_user_"))
@safe_callback_handler
def reply_user(c):
    try:
        if not is_admin(c.from_user.id):
            return
        uid = c.data.split("_")[-1]
        msg = safe_send_message(c.message.chat.id, f"User {uid} uchun javob yozing:")
        if msg:
            bot.register_next_step_handler(msg, lambda m: send_admin_reply(m, uid))
    except Exception as e:
        logger.error(f"reply_user xato: {e}")

@safe_next_step
def send_admin_reply(message, user_id: str):
    try:
        if message.content_type == "text":
            safe_send_message(int(user_id), f"📩 <b>Admin javobi:</b>\n\n{message.text}")
        elif message.content_type == "photo":
            safe_send_photo(int(user_id), message.photo[-1].file_id, caption=f"📩 <b>Admin javobi:</b>\n\n{message.caption or ''}")
        elif message.content_type == "video":
            safe_call(bot.send_video, int(user_id), message.video.file_id, caption=f"📩 <b>Admin javobi:</b>\n\n{message.caption or ''}")
        elif message.content_type == "document":
            safe_call(bot.send_document, int(user_id), message.document.file_id, caption=f"📩 <b>Admin javobi:</b>\n\n{message.caption or ''}")
        safe_send_message(message.chat.id, "✅ Javob yuborildi", reply_markup=admin_menu())
    except Exception as e:
        safe_send_message(message.chat.id, f"❌ Xato: {e}", reply_markup=admin_menu())

# =====================================
# CHAT JOIN
# =====================================
@bot.message_handler(func=lambda m: m.text and config.get("chat_link") and m.text == config.get("chat_title", "💬 Chatga qo'shilish"))
def join_chat_handler(message):
    try:
        if is_group_chat(message.chat.type):
            return
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

# =====================================
# CHECK SUBS CALLBACK
# =====================================
@bot.callback_query_handler(func=lambda call: call.data == "check_subs")
@safe_callback_handler
def check_subs_callback(call):
    try:
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
            safe_send_message(call.message.chat.id, "🔽 Asosiy menyu:", reply_markup=_menu_for(call.from_user.id))
        else:
            safe_answer_callback_query(call.id, "❌ Hali barcha kanallarga obuna bo'lmagansiz")
            show_required_channels(call.message.chat.id)
    except Exception as e:
        logger.error(f"check_subs_callback xato: {e}")

# =====================================
# ADMIN PANEL - STATS
# =====================================
@bot.message_handler(func=lambda m: m.text == "👨‍💻 Admin panel" and is_admin(m.from_user.id))
def admin_panel(message):
    try:
        s = get_admin_stats()
        text = get_text("admin_panel_text").format(
            total_users=s.get('total_users', 0),
            new_today=s.get('new_today', 0),
            active_today=s.get('active_today', 0),
            total_balance=s.get('total_balance', 0),
            pending_orders=s.get('pending_orders', 0),
            active_lotteries=s.get('active_lotteries', 0)
        )
        safe_send_message(message.chat.id, text, reply_markup=admin_menu())
    except Exception as e:
        logger.error(f"admin_panel xato: {e}", exc_info=True)
        safe_send_message(message.chat.id, "⚠️ Xatolik yuz berdi.")

@bot.message_handler(func=lambda m: m.text == "📊 Statistika" and is_admin(m.from_user.id))
@admin_required
def admin_stats(message):
    try:
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
            f"🏦 Bot foydasi (o'yinlardan): {s['house_edge_result']:,} so'm\n\n"
            f"🎰 Lotareyalar: {s['total_lotteries']} ta (faol: {s['active_lotteries']})",
            reply_markup=admin_menu()
        )
    except Exception as e:
        logger.error(f"admin_stats xato: {e}")

# =====================================
# ADMIN PANEL - ORDERS
# =====================================
@bot.message_handler(func=lambda m: m.text == "📦 Buyurtmalar" and is_admin(m.from_user.id))
@admin_required
def admin_orders(message):
    try:
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
    except Exception as e:
        logger.error(f"admin_orders xato: {e}")

def _render_orders_list(filtered: List[Dict[str, Any]], title: str):
    try:
        filtered = sorted(filtered, key=lambda x: x.get("date", ""), reverse=True)[:20]
        if not filtered:
            return f"📦 <b>{title}</b>\n\nBuyurtmalar topilmadi", None
        lines = [f"📦 <b>{title}</b> ({len(filtered)})"]
        markup = InlineKeyboardMarkup(row_width=1)
        for order in filtered:
            lines.append(f"\n#{order['id']} | {order.get('kind')} | {order.get('amount', 0):,} so'm | {order.get('status')} | user {order['user_id']}")
            markup.add(InlineKeyboardButton(f"Buyurtma #{order['id']}", callback_data=f"view_order_{order['id']}"))
        return "\n".join(lines), markup
    except Exception as e:
        logger.error(f"_render_orders_list xato: {e}")
        return "Xatolik", None

@bot.callback_query_handler(func=lambda c: c.data.startswith("ordf_"))
@safe_callback_handler
def order_filter(c):
    try:
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
    except Exception as e:
        logger.error(f"order_filter xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("view_order_"))
@safe_callback_handler
def view_order(c):
    try:
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
    except Exception as e:
        logger.error(f"view_order xato: {e}")

# =====================================
# ADMIN PANEL - USERS
# =====================================
@bot.message_handler(func=lambda m: m.text == "👤 Foydalanuvchilar" and is_admin(m.from_user.id))
@admin_required
def admin_users(message):
    try:
        s = get_admin_stats()
        kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        kb.add("🔍 Foydalanuvchi qidirish", "📋 So'nggi qo'shilganlar")
        kb.add("🚫 Bloklanganlar ro'yxati", "🏆 Eng faol userlar")
        kb.add("📊 Referal statistikasi", "⬅️ Ortga")
        safe_send_message(message.chat.id, f"👤 Foydalanuvchilar bo'limi\n\n👥 Jami: {s['total_users']} | 🆕 Bugun: {s['new_today']} | 🚫 Bloklangan: {s['blocked_users']}", reply_markup=kb)
    except Exception as e:
        logger.error(f"admin_users xato: {e}")

@bot.message_handler(func=lambda m: m.text == "📊 Referal statistikasi" and is_admin(m.from_user.id))
@admin_required
def referral_stats(message):
    try:
        stats = {}
        for uid, u in users.items():
            ref_by = u.get("referred_by")
            if ref_by:
                stats[ref_by] = stats.get(ref_by, 0) + 1
        
        if not stats:
            safe_send_message(message.chat.id, "❌ Hozircha referal statistikasi mavjud emas", reply_markup=admin_menu())
            return
        
        sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)[:20]
        text = "📊 <b>Referal statistikasi</b>\n\n"
        for i, (uid, count) in enumerate(sorted_stats, 1):
            text += f"{i}. {safe_username(uid)} — {count} ta referal\n"
        
        safe_send_message(message.chat.id, text, reply_markup=admin_menu())
    except Exception as e:
        logger.error(f"referral_stats xato: {e}")

@bot.message_handler(func=lambda m: m.text == "🔍 Foydalanuvchi qidirish" and is_admin(m.from_user.id))
@admin_required
def search_user(message):
    try:
        msg = safe_send_message(message.chat.id, "ID yoki username kiriting:", reply_markup=back_menu())
        if msg:
            bot.register_next_step_handler(msg, process_user_search)
    except Exception as e:
        logger.error(f"search_user xato: {e}")

@safe_next_step
def process_user_search(message):
    try:
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
    except Exception as e:
        logger.error(f"process_user_search xato: {e}")

@bot.message_handler(func=lambda m: m.text == "📋 So'nggi qo'shilganlar" and is_admin(m.from_user.id))
@admin_required
def recent_users(message):
    try:
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
    except Exception as e:
        logger.error(f"recent_users xato: {e}")

@bot.message_handler(func=lambda m: m.text == "🚫 Bloklanganlar ro'yxati" and is_admin(m.from_user.id))
@admin_required
def blocked_users_list(message):
    try:
        blocked = [uid for uid, u in users.items() if u.get("blocked")]
        if not blocked:
            safe_send_message(message.chat.id, "✅ Bloklangan foydalanuvchilar yo'q", reply_markup=admin_menu())
            return
        markup = InlineKeyboardMarkup(row_width=1)
        for uid in blocked[:20]:
            markup.add(InlineKeyboardButton(f"{safe_username(uid)}", callback_data=f"admin_show_user_{uid}"))
        safe_send_message(message.chat.id, f"🚫 Bloklangan foydalanuvchilar ({len(blocked)}):", reply_markup=markup)
    except Exception as e:
        logger.error(f"blocked_users_list xato: {e}")

@bot.message_handler(func=lambda m: m.text == "🏆 Eng faol userlar" and is_admin(m.from_user.id))
@admin_required
def most_active_users(message):
    try:
        ranked = sorted(users.items(), key=lambda x: x[1].get("orders_count", 0) + x[1].get("games_played", 0), reverse=True)[:10]
        markup = InlineKeyboardMarkup(row_width=1)
        lines = ["🏆 <b>Eng faol foydalanuvchilar</b>"]
        for uid, u in ranked:
            lines.append(f"\n{safe_username(uid)} | buyurtma: {u.get('orders_count', 0)} | o'yin: {u.get('games_played', 0)}")
            markup.add(InlineKeyboardButton(f"{safe_username(uid)}", callback_data=f"admin_show_user_{uid}"))
        safe_send_message(message.chat.id, "\n".join(lines), reply_markup=markup)
    except Exception as e:
        logger.error(f"most_active_users xato: {e}")

def show_user_info(chat_id: int, user_id: str):
    try:
        if user_id not in users:
            safe_send_message(chat_id, "❌ Foydalanuvchi topilmadi")
            return
        user = users[user_id]
        ref_list = user.get("referrals_list", [])
        ref_text = ""
        if ref_list:
            ref_text = "\n\n👥 <b>Referallari:</b>\n"
            for ref in ref_list[-5:]:
                ref_text += f"• {ref.get('username', 'Noma\'lum')} - {ref.get('date', '')}\n"
            if len(ref_list) > 5:
                ref_text += f"... va yana {len(ref_list) - 5} ta"
        
        lottery_tickets = len(user.get("lottery_tickets", []))
        
        text = (
            f"👤 <b>Foydalanuvchi</b>\n\n"
            f"ID: <code>{user_id}</code>\n"
            f"Username: {user.get('username', 'Noma\'lum')}\n"
            f"Ism: {user.get('first_name', '')} {user.get('last_name', '')}\n"
            f"📅 Ro'yxat: {user.get('join_date', 'Noma\'lum')}\n"
            f"⏱ Oxirgi faollik: {user.get('last_active', 'Noma\'lum')}\n\n"
            f"💰 Balans: {user.get('balance', 0):,} so'm\n"
            f"👥 Referallar: {user.get('referrals_count', 0)}\n"
            f"🔰 Daraja: {get_referral_level(user.get('referrals_count', 0)).get('level')}\n"
            f"🔗 Kim taklif qilgan: {safe_username(user.get('referred_by')) if user.get('referred_by') else '—'}\n"
            f"📦 Buyurtmalar: {user.get('orders_count', 0)}\n"
            f"🎮 O'yinlar: {user.get('games_played', 0)} (yutgan: {user.get('games_won', 0)})\n"
            f"🎯 Stavka jami: {user.get('total_wagered', 0):,} so'm\n"
            f"🎁 Yutuq jami: {user.get('total_won', 0):,} so'm\n"
            f"🎰 Lotareya: {lottery_tickets} ta chipta, {user.get('lottery_wins', 0)} ta yutuq\n"
            f"💵 Admin to'ldirishlar jami: {user.get('admin_topups_total', 0):,} so'm\n"
            f"🎟 Ishlatilgan promokodlar: {', '.join(user.get('used_promo', [])) or '—'}\n"
            f"🔔 Bildirishnoma: {'✅' if user.get('notifications', True) else '❌'}\n"
            f"🚫 Blocked: {'✅' if user.get('blocked') else '❌'}\n"
            f"👑 Admin: {'✅' if is_admin(int(user_id)) else '❌'}"
            f"{ref_text}"
        )
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(InlineKeyboardButton("💰 Balansni o'zgartirish", callback_data=f"admin_edit_balance_{user_id}"))
        markup.add(InlineKeyboardButton("🔒 Block/Unblock", callback_data=f"admin_toggle_block_{user_id}"))
        markup.add(InlineKeyboardButton("📦 Buyurtmalar tarixi", callback_data=f"admin_user_orders_{user_id}"))
        markup.add(InlineKeyboardButton("✉️ Xabar yuborish", callback_data=f"admin_msg_user_{user_id}"))
        markup.add(InlineKeyboardButton("🔄 Referalni tozalash", callback_data=f"admin_clear_ref_{user_id}"))
        markup.add(InlineKeyboardButton("🗑 Foydalanuvchini o'chirish", callback_data=f"admin_delete_user_{user_id}"))
        safe_send_message(chat_id, text, reply_markup=markup)
    except Exception as e:
        logger.error(f"show_user_info xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_show_user_"))
@safe_callback_handler
def admin_show_user(c):
    try:
        if not is_admin(c.from_user.id):
            return
        show_user_info(c.message.chat.id, c.data.split("_")[-1])
    except Exception as e:
        logger.error(f"admin_show_user xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_edit_balance_"))
@safe_callback_handler
def admin_edit_balance(c):
    try:
        if not is_admin(c.from_user.id):
            return
        user_id = c.data.split("_")[-1]
        if user_id not in users:
            safe_answer_callback_query(c.id, "❌ Foydalanuvchi topilmadi")
            return
        msg = safe_send_message(c.message.chat.id, f"Yangi balansni kiriting ({users[user_id].get('balance', 0):,}):")
        if msg:
            bot.register_next_step_handler(msg, lambda m: process_balance_edit(m, user_id))
    except Exception as e:
        logger.error(f"admin_edit_balance xato: {e}")

@safe_next_step
def process_balance_edit(message, user_id: str):
    try:
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
        safe_send_message(
            int(user_id),
            get_text("admin_topup_notification",
                sign="",
                amount=amount - old,
                new_balance=amount
            )
        )
    except Exception as e:
        logger.error(f"process_balance_edit xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_toggle_block_"))
@safe_callback_handler
def admin_toggle_block(c):
    try:
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
    except Exception as e:
        logger.error(f"admin_toggle_block xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_user_orders_"))
@safe_callback_handler
def admin_user_orders(c):
    try:
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
    except Exception as e:
        logger.error(f"admin_user_orders xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_msg_user_"))
@safe_callback_handler
def admin_msg_user(c):
    try:
        if not is_admin(c.from_user.id):
            return
        user_id = c.data.split("_")[-1]
        msg = safe_send_message(c.message.chat.id, f"✉️ {safe_username(user_id)} ga yubormoqchi bo'lgan xabarni yozing:")
        if msg:
            bot.register_next_step_handler(msg, lambda m: send_admin_reply(m, user_id))
    except Exception as e:
        logger.error(f"admin_msg_user xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_clear_ref_"))
@safe_callback_handler
def admin_clear_ref(c):
    try:
        if not is_admin(c.from_user.id):
            return
        user_id = c.data.split("_")[-1]
        if user_id not in users:
            safe_answer_callback_query(c.id, "❌ Foydalanuvchi topilmadi")
            return
        users[user_id]["referred_by"] = None
        users[user_id]["referrals_list"] = []
        users[user_id]["referrals_count"] = 0
        save_db()
        safe_answer_callback_query(c.id, "✅ Referal tozalandi")
        show_user_info(c.message.chat.id, user_id)
    except Exception as e:
        logger.error(f"admin_clear_ref xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_delete_user_"))
@safe_callback_handler
def admin_delete_user_confirm(c):
    try:
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
    except Exception as e:
        logger.error(f"admin_delete_user_confirm xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_delete_confirm_"))
@safe_callback_handler
def admin_delete_user(c):
    try:
        if not is_superadmin(c.from_user.id):
            safe_answer_callback_query(c.id, "❌ Faqat super admin o'chira oladi")
            return
        user_id = c.data.split("_", 1)[1]
        users.pop(user_id, None)
        save_db()
        safe_answer_callback_query(c.id, "✅ Foydalanuvchi o'chirildi")
        safe_edit_message_text(f"🗑 Foydalanuvchi <code>{user_id}</code> o'chirildi", c.message.chat.id, c.message.message_id)
    except Exception as e:
        logger.error(f"admin_delete_user xato: {e}")

# =====================================
# ADMIN PANEL - DIRECT TOPUP
# =====================================
@bot.message_handler(func=lambda m: m.text == "💵 Hisob to'ldirish (admin)" and is_admin(m.from_user.id))
@admin_required
def admin_direct_topup_entry(message):
    try:
        msg = safe_send_message(message.chat.id, "👤 Foydalanuvchi ID sini kiriting:", reply_markup=back_menu())
        if msg:
            bot.register_next_step_handler(msg, admin_direct_topup_userid)
    except Exception as e:
        logger.error(f"admin_direct_topup_entry xato: {e}")

@safe_next_step
def admin_direct_topup_userid(message):
    try:
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
    except Exception as e:
        logger.error(f"admin_direct_topup_userid xato: {e}")

@safe_next_step
def admin_direct_topup_amount(message, target_id: str):
    try:
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
            get_text("admin_topup_notification",
                sign=sign,
                amount=amount,
                new_balance=users[target_id]['balance']
            )
        )
    except Exception as e:
        logger.error(f"admin_direct_topup_amount xato: {e}")

# =====================================
# ADMIN PANEL - PAYMENT CARDS
# =====================================
@bot.message_handler(func=lambda m: m.text == "💳 To'lov (kartalar)" and is_admin(m.from_user.id))
@admin_required
def manage_cards(message):
    try:
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
    except Exception as e:
        logger.error(f"manage_cards xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "add_card")
@safe_callback_handler
def add_card(c):
    try:
        if not is_admin(c.from_user.id):
            return
        msg = safe_send_message(c.message.chat.id, "💳 Karta raqamini kiriting:")
        if msg:
            bot.register_next_step_handler(msg, process_add_card_number)
    except Exception as e:
        logger.error(f"add_card xato: {e}")

@safe_next_step
def process_add_card_number(message):
    try:
        number = message.text.strip()
        msg = safe_send_message(message.chat.id, "🏦 Bank nomini kiriting:")
        if msg:
            bot.register_next_step_handler(msg, process_add_card_bank, number)
    except Exception as e:
        logger.error(f"process_add_card_number xato: {e}")

@safe_next_step
def process_add_card_bank(message, number: str):
    try:
        bank = message.text.strip()
        msg = safe_send_message(message.chat.id, "👤 Karta egasining ismini kiriting:")
        if msg:
            bot.register_next_step_handler(msg, process_add_card_holder, number, bank)
    except Exception as e:
        logger.error(f"process_add_card_bank xato: {e}")

@safe_next_step
def process_add_card_holder(message, number: str, bank: str):
    try:
        holder = message.text.strip()
        cards = config.setdefault("payment_cards", [])
        cards.append({"id": new_id(cards), "number": number, "bank": bank, "holder": holder})
        save_db()
        safe_send_message(message.chat.id, "✅ Karta qo'shildi", reply_markup=admin_menu())
    except Exception as e:
        logger.error(f"process_add_card_holder xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "edit_card")
@safe_callback_handler
def edit_card(c):
    try:
        if not is_admin(c.from_user.id):
            return
        cards = config.get("payment_cards", [])
        markup = InlineKeyboardMarkup(row_width=1)
        for card in cards:
            markup.add(InlineKeyboardButton(f"{card['bank']} — {card['number']}", callback_data=f"editcard_{card['id']}"))
        safe_send_message(c.message.chat.id, "Tahrirlash uchun tanlang:", reply_markup=markup)
    except Exception as e:
        logger.error(f"edit_card xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("editcard_"))
@safe_callback_handler
def editcard_pick(c):
    try:
        if not is_admin(c.from_user.id):
            return
        card_id = int(c.data.split("_")[-1])
        msg = safe_send_message(c.message.chat.id, "Yangi karta raqamini kiriting:")
        if msg:
            bot.register_next_step_handler(msg, process_editcard_number, card_id)
    except Exception as e:
        logger.error(f"editcard_pick xato: {e}")

@safe_next_step
def process_editcard_number(message, card_id: int):
    try:
        number = message.text.strip()
        msg = safe_send_message(message.chat.id, "Yangi bank nomini kiriting:")
        if msg:
            bot.register_next_step_handler(msg, process_editcard_bank, card_id, number)
    except Exception as e:
        logger.error(f"process_editcard_number xato: {e}")

@safe_next_step
def process_editcard_bank(message, card_id: int, number: str):
    try:
        bank = message.text.strip()
        msg = safe_send_message(message.chat.id, "Yangi karta egasi ismini kiriting:")
        if msg:
            bot.register_next_step_handler(msg, process_editcard_holder, card_id, number, bank)
    except Exception as e:
        logger.error(f"process_editcard_bank xato: {e}")

@safe_next_step
def process_editcard_holder(message, card_id: int, number: str, bank: str):
    try:
        holder = message.text.strip()
        for c_ in config.get("payment_cards", []):
            if c_["id"] == card_id:
                c_.update({"number": number, "bank": bank, "holder": holder})
        save_db()
        safe_send_message(message.chat.id, "✅ Karta yangilandi", reply_markup=admin_menu())
    except Exception as e:
        logger.error(f"process_editcard_holder xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "remove_card")
@safe_callback_handler
def remove_card(c):
    try:
        if not is_admin(c.from_user.id):
            return
        cards = config.get("payment_cards", [])
        markup = InlineKeyboardMarkup(row_width=1)
        for card in cards:
            markup.add(InlineKeyboardButton(f"{card['bank']} — {card['number']}", callback_data=f"delete_card_{card['id']}"))
        safe_send_message(c.message.chat.id, "O'chirish uchun tanlang:", reply_markup=markup)
    except Exception as e:
        logger.error(f"remove_card xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("delete_card_"))
@safe_callback_handler
def delete_card(c):
    try:
        if not is_admin(c.from_user.id):
            return
        card_id = int(c.data.split("_")[-1])
        config["payment_cards"] = [x for x in config.get("payment_cards", []) if x["id"] != card_id]
        save_db()
        safe_answer_callback_query(c.id, "✅ O'chirildi")
    except Exception as e:
        logger.error(f"delete_card xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "set_payment_channel")
@safe_callback_handler
def set_payment_channel(c):
    try:
        if not is_admin(c.from_user.id):
            return
        msg = safe_send_message(c.message.chat.id, "📢 To'lov kanalidan istalgan xabarni forward qiling, yoki kanal ID sini yuboring (masalan -1001234567890). Bot shu kanalda admin bo'lishi shart.")
        if msg:
            bot.register_next_step_handler(msg, process_set_payment_channel)
    except Exception as e:
        logger.error(f"set_payment_channel xato: {e}")

@safe_next_step
def process_set_payment_channel(message):
    try:
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
    except Exception as e:
        logger.error(f"process_set_payment_channel xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "set_orders_channel")
@safe_callback_handler
def set_orders_channel(c):
    try:
        if not is_admin(c.from_user.id):
            return
        msg = safe_send_message(c.message.chat.id, "📢 Buyurtmalar (shop) kanalidan istalgan xabarni forward qiling, yoki kanal ID sini yuboring. Bot shu kanalda admin bo'lishi shart.")
        if msg:
            bot.register_next_step_handler(msg, process_set_orders_channel)
    except Exception as e:
        logger.error(f"set_orders_channel xato: {e}")

@safe_next_step
def process_set_orders_channel(message):
    try:
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
    except Exception as e:
        logger.error(f"process_set_orders_channel xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "set_min_topup")
@safe_callback_handler
def set_min_topup(c):
    try:
        if not is_admin(c.from_user.id):
            return
        msg = safe_send_message(c.message.chat.id, "💵 Minimal to'ldirish summasini kiriting:")
        if msg:
            bot.register_next_step_handler(msg, process_set_min_topup)
    except Exception as e:
        logger.error(f"set_min_topup xato: {e}")

@safe_next_step
def process_set_min_topup(message):
    try:
        amount = safe_int(message.text, default=None)
        if amount is None:
            safe_send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
            return
        config["min_topup"] = amount
        save_db()
        safe_send_message(message.chat.id, "✅ Saqlandi", reply_markup=admin_menu())
    except Exception as e:
        logger.error(f"process_set_min_topup xato: {e}")

# =====================================
# ADMIN PANEL - SERVICES
# =====================================
@bot.message_handler(func=lambda m: m.text == "🛠 Xizmatlar" and is_admin(m.from_user.id))
@admin_required
def manage_services(message):
    try:
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
    except Exception as e:
        logger.error(f"manage_services xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "add_category")
@safe_callback_handler
def add_category(c):
    try:
        if not is_admin(c.from_user.id):
            return
        msg = safe_send_message(c.message.chat.id, "📦 Yangi kategoriya nomini kiriting:")
        if msg:
            bot.register_next_step_handler(msg, process_add_category)
    except Exception as e:
        logger.error(f"add_category xato: {e}")

@safe_next_step
def process_add_category(message):
    try:
        name = message.text.strip()
        cats = config.setdefault("service_categories", [])
        if any(c["name"] == name for c in cats):
            safe_send_message(message.chat.id, "❌ Bu kategoriya allaqachon mavjud", reply_markup=admin_menu())
            return
        cats.append({"id": new_id(cats), "name": name})
        save_db()
        safe_send_message(message.chat.id, "✅ Kategoriya qo'shildi", reply_markup=admin_menu())
    except Exception as e:
        logger.error(f"process_add_category xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "edit_category")
@safe_callback_handler
def edit_category(c):
    try:
        if not is_admin(c.from_user.id):
            return
        cats = config.get("service_categories", [])
        markup = InlineKeyboardMarkup(row_width=1)
        for cat in cats:
            markup.add(InlineKeyboardButton(cat["name"], callback_data=f"editcat_{cat['id']}"))
        safe_send_message(c.message.chat.id, "Tahrirlash uchun tanlang:", reply_markup=markup)
    except Exception as e:
        logger.error(f"edit_category xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("editcat_"))
@safe_callback_handler
def editcat_pick(c):
    try:
        if not is_admin(c.from_user.id):
            return
        cat_id = int(c.data.split("_")[-1])
        msg = safe_send_message(c.message.chat.id, "Yangi kategoriya nomini kiriting:")
        if msg:
            bot.register_next_step_handler(msg, process_editcat, cat_id)
    except Exception as e:
        logger.error(f"editcat_pick xato: {e}")

@safe_next_step
def process_editcat(message, cat_id: int):
    try:
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
    except Exception as e:
        logger.error(f"process_editcat xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "remove_category")
@safe_callback_handler
def remove_category(c):
    try:
        if not is_admin(c.from_user.id):
            return
        cats = config.get("service_categories", [])
        markup = InlineKeyboardMarkup(row_width=1)
        for cat in cats:
            markup.add(InlineKeyboardButton(cat["name"], callback_data=f"delcat_{cat['id']}"))
        safe_send_message(c.message.chat.id, "O'chirish uchun tanlang (mahsulotlar ham o'chadi):", reply_markup=markup)
    except Exception as e:
        logger.error(f"remove_category xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("delcat_"))
@safe_callback_handler
def delcat(c):
    try:
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
    except Exception as e:
        logger.error(f"delcat xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "manage_products")
@safe_callback_handler
def manage_products(c):
    try:
        if not is_admin(c.from_user.id):
            return
        cats = config.get("service_categories", [])
        markup = InlineKeyboardMarkup(row_width=1)
        for cat in cats:
            markup.add(InlineKeyboardButton(f"📦 {cat['name']}", callback_data=f"prodcat_{cat['name']}"))
        safe_send_message(c.message.chat.id, "Qaysi kategoriya mahsulotlarini boshqarasiz?", reply_markup=markup)
    except Exception as e:
        logger.error(f"manage_products xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("prodcat_"))
@safe_callback_handler
def prodcat_view(c):
    try:
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
    except Exception as e:
        logger.error(f"prodcat_view xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("addprod_"))
@safe_callback_handler
def add_service(c):
    try:
        if not is_admin(c.from_user.id):
            return
        category = c.data.split("_", 1)[1]
        msg = safe_send_message(c.message.chat.id, "📝 Mahsulot nomini kiriting:")
        if msg:
            bot.register_next_step_handler(msg, process_add_service_name, category)
    except Exception as e:
        logger.error(f"add_service xato: {e}")

@safe_next_step
def process_add_service_name(message, category: str):
    try:
        name = message.text.strip()
        msg = safe_send_message(message.chat.id, "💰 Narxini kiriting (so'm):")
        if msg:
            bot.register_next_step_handler(msg, process_add_service_price, category, name)
    except Exception as e:
        logger.error(f"process_add_service_name xato: {e}")

@safe_next_step
def process_add_service_price(message, category: str, name: str):
    try:
        price = safe_int(message.text, default=None)
        if price is None:
            safe_send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
            return
        msg = safe_send_message(message.chat.id, "📝 Qo'shimcha izoh kiriting (ixtiyoriy, o'tkazib yuborish uchun '-' yozing):")
        if msg:
            bot.register_next_step_handler(msg, process_add_service_desc, category, name, price)
    except Exception as e:
        logger.error(f"process_add_service_price xato: {e}")

@safe_next_step
def process_add_service_desc(message, category: str, name: str, price: int):
    try:
        desc = message.text.strip()
        if desc == "-":
            desc = ""
        services = config.setdefault("services", [])
        services.append({"id": new_id(services), "category": category, "name": name, "price": price, "description": desc})
        if not any(cc["name"] == category for cc in config.get("service_categories", [])):
            config.setdefault("service_categories", []).append({"id": new_id(config["service_categories"]), "name": category})
        save_db()
        safe_send_message(message.chat.id, "✅ Mahsulot qo'shildi", reply_markup=admin_menu())
    except Exception as e:
        logger.error(f"process_add_service_desc xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("editprodmenu_"))
@safe_callback_handler
def editprodmenu(c):
    try:
        if not is_admin(c.from_user.id):
            return
        category = c.data.split("_", 1)[1]
        items = [s for s in config.get("services", []) if s["category"] == category]
        markup = InlineKeyboardMarkup(row_width=1)
        for s in items:
            markup.add(InlineKeyboardButton(f"{s['name']} ({s['price']:,})", callback_data=f"editprice_{s['id']}"))
        safe_send_message(c.message.chat.id, "Tahrirlash uchun tanlang:", reply_markup=markup)
    except Exception as e:
        logger.error(f"editprodmenu xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("editprice_"))
@safe_callback_handler
def editprice(c):
    try:
        if not is_admin(c.from_user.id):
            return
        service_id = int(c.data.split("_")[-1])
        msg = safe_send_message(c.message.chat.id, "📝 Yangi nomni kiriting (o'zgartirmaslik uchun '-'):")
        if msg:
            bot.register_next_step_handler(msg, process_editname, service_id)
    except Exception as e:
        logger.error(f"editprice xato: {e}")

@safe_next_step
def process_editname(message, service_id: int):
    try:
        name = message.text.strip()
        msg = safe_send_message(message.chat.id, "💰 Yangi narxni kiriting:")
        if msg:
            bot.register_next_step_handler(msg, process_editprice, service_id, name)
    except Exception as e:
        logger.error(f"process_editname xato: {e}")

@safe_next_step
def process_editprice(message, service_id: int, name: str):
    try:
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
    except Exception as e:
        logger.error(f"process_editprice xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("delprodmenu_"))
@safe_callback_handler
def delprodmenu(c):
    try:
        if not is_admin(c.from_user.id):
            return
        category = c.data.split("_", 1)[1]
        items = [s for s in config.get("services", []) if s["category"] == category]
        markup = InlineKeyboardMarkup(row_width=1)
        for s in items:
            markup.add(InlineKeyboardButton(f"{s['name']}", callback_data=f"delservice_{s['id']}"))
        safe_send_message(c.message.chat.id, "O'chirish uchun tanlang:", reply_markup=markup)
    except Exception as e:
        logger.error(f"delprodmenu xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("delservice_"))
@safe_callback_handler
def delservice(c):
    try:
        if not is_admin(c.from_user.id):
            return
        service_id = int(c.data.split("_")[-1])
        config["services"] = [s for s in config.get("services", []) if s["id"] != service_id]
        save_db()
        safe_answer_callback_query(c.id, "✅ O'chirildi")
    except Exception as e:
        logger.error(f"delservice xato: {e}")

# =====================================
# ADMIN PANEL - REQUIRED CHANNELS
# =====================================
@bot.message_handler(func=lambda m: m.text == "📝 Majburiy kanallar" and is_admin(m.from_user.id))
@admin_required
def manage_required_channels(message):
    try:
        required = config.get("required_channels", [])
        lines = ["🔐 <b>Majburiy kanallar</b>"]
        for i, ch in enumerate(required, start=1):
            thr = int(ch.get("auto_remove_at", 0) or 0)
            confirmed = int(ch.get("confirmed_count", 0))
            check_status = "✅" if ch.get("check_enabled", True) else "❌"
            if thr:
                remaining = max(0, thr - confirmed)
                progress = f"{confirmed}/{thr} tasdiqlangan (yana {remaining} tadan keyin o'chadi)"
            else:
                progress = f"{confirmed} ta tasdiqlangan (cheklanmagan)"
            lines.append(f"\n{i}. {ch.get('title')} - {ch.get('username')}\n   📊 {progress}\n   🔍 Tekshirish: {check_status}")
        if not required:
            lines.append("\nHozircha kanal yo'q")
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton("➕ Qo'shish", callback_data="add_required_channel"))
        if required:
            markup.add(InlineKeyboardButton("✏️ Tahrirlash", callback_data="edit_required_channel"))
            markup.add(InlineKeyboardButton("❌ O'chirish", callback_data="remove_required_channel"))
            markup.add(InlineKeyboardButton("🔢 Avto-o'chirish limitini sozlash", callback_data="set_autoremove"))
            markup.add(InlineKeyboardButton("🔄 Hisoblagichni nolga tushirish", callback_data="reset_channel_count"))
            markup.add(InlineKeyboardButton("🔍 Tekshirishni yoqish/o'chirish", callback_data="toggle_channel_check"))
        safe_send_message(message.chat.id, "\n".join(lines), reply_markup=markup)
    except Exception as e:
        logger.error(f"manage_required_channels xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "add_required_channel")
@safe_callback_handler
def add_required_channel(c):
    try:
        if not is_admin(c.from_user.id):
            return
        msg = safe_send_message(c.message.chat.id, "Format: @username - Title")
        if msg:
            bot.register_next_step_handler(msg, process_add_required_channel)
    except Exception as e:
        logger.error(f"add_required_channel xato: {e}")

@safe_next_step
def process_add_required_channel(message):
    try:
        raw = message.text.strip()
        parts = raw.split(" - ", 1)
        if len(parts) != 2:
            safe_send_message(message.chat.id, "❌ Format noto'g'ri", reply_markup=admin_menu())
            return
        username, title = parts[0].strip(), parts[1].strip()
        if not username.startswith("@"):
            username = "@" + username
        config.setdefault("required_channels", []).append({"username": username, "title": title, "auto_remove_at": 0, "confirmed_count": 0, "check_enabled": True})
        save_db()
        safe_send_message(message.chat.id, "✅ Qo'shildi", reply_markup=admin_menu())
    except Exception as e:
        logger.error(f"process_add_required_channel xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "edit_required_channel")
@safe_callback_handler
def edit_required_channel(c):
    try:
        if not is_admin(c.from_user.id):
            return
        required = config.get("required_channels", [])
        markup = InlineKeyboardMarkup(row_width=1)
        for i, ch in enumerate(required):
            markup.add(InlineKeyboardButton(f"{ch['title']}", callback_data=f"editreqch_{i}"))
        safe_send_message(c.message.chat.id, "Tahrirlash uchun tanlang:", reply_markup=markup)
    except Exception as e:
        logger.error(f"edit_required_channel xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("editreqch_"))
@safe_callback_handler
def editreqch_pick(c):
    try:
        if not is_admin(c.from_user.id):
            return
        idx = int(c.data.split("_")[-1])
        msg = safe_send_message(c.message.chat.id, "Yangi format: @username - Title")
        if msg:
            bot.register_next_step_handler(msg, process_editreqch, idx)
    except Exception as e:
        logger.error(f"editreqch_pick xato: {e}")

@safe_next_step
def process_editreqch(message, idx: int):
    try:
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
    except Exception as e:
        logger.error(f"process_editreqch xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "remove_required_channel")
@safe_callback_handler
def remove_required_channel(c):
    try:
        if not is_admin(c.from_user.id):
            return
        required = config.get("required_channels", [])
        markup = InlineKeyboardMarkup(row_width=1)
        for i, ch in enumerate(required):
            markup.add(InlineKeyboardButton(f"{ch['title']}", callback_data=f"delreqch_{i}"))
        safe_send_message(c.message.chat.id, "O'chirish uchun tanlang:", reply_markup=markup)
    except Exception as e:
        logger.error(f"remove_required_channel xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("delreqch_"))
@safe_callback_handler
def delreqch(c):
    try:
        if not is_admin(c.from_user.id):
            return
        idx = int(c.data.split("_")[-1])
        required = config.get("required_channels", [])
        if 0 <= idx < len(required):
            required.pop(idx)
            config["required_channels"] = required
            save_db()
        safe_answer_callback_query(c.id, "✅ O'chirildi")
    except Exception as e:
        logger.error(f"delreqch xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "set_autoremove")
@safe_callback_handler
def set_autoremove(c):
    try:
        if not is_admin(c.from_user.id):
            return
        required = config.get("required_channels", [])
        markup = InlineKeyboardMarkup(row_width=1)
        for i, ch in enumerate(required):
            markup.add(InlineKeyboardButton(f"{ch['title']}", callback_data=f"autoremove_{i}"))
        safe_send_message(c.message.chat.id, "Qaysi kanal uchun limit belgilaysiz?", reply_markup=markup)
    except Exception as e:
        logger.error(f"set_autoremove xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("autoremove_"))
@safe_callback_handler
def autoremove_pick(c):
    try:
        if not is_admin(c.from_user.id):
            return
        idx = int(c.data.split("_")[-1])
        msg = safe_send_message(c.message.chat.id, "Nechta tasdiqlangan obunachidan keyin kanal avtomatik o'chirilsin? (0 = cheksiz):")
        if msg:
            bot.register_next_step_handler(msg, process_autoremove, idx)
    except Exception as e:
        logger.error(f"autoremove_pick xato: {e}")

@safe_next_step
def process_autoremove(message, idx: int):
    try:
        threshold = safe_int(message.text, default=None)
        if threshold is None:
            safe_send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
            return
        required = config.get("required_channels", [])
        if 0 <= idx < len(required):
            required[idx]["auto_remove_at"] = threshold
            save_db()
        safe_send_message(message.chat.id, "✅ Saqlandi", reply_markup=admin_menu())
    except Exception as e:
        logger.error(f"process_autoremove xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "reset_channel_count")
@safe_callback_handler
def reset_channel_count(c):
    try:
        if not is_admin(c.from_user.id):
            return
        required = config.get("required_channels", [])
        markup = InlineKeyboardMarkup(row_width=1)
        for i, ch in enumerate(required):
            markup.add(InlineKeyboardButton(f"{ch['title']}", callback_data=f"resetcount_{i}"))
        safe_send_message(c.message.chat.id, "Qaysi kanal hisoblagichini nollaymiz?", reply_markup=markup)
    except Exception as e:
        logger.error(f"reset_channel_count xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("resetcount_"))
@safe_callback_handler
def resetcount(c):
    try:
        if not is_admin(c.from_user.id):
            return
        idx = int(c.data.split("_")[-1])
        required = config.get("required_channels", [])
        if 0 <= idx < len(required):
            required[idx]["confirmed_count"] = 0
            save_db()
        safe_answer_callback_query(c.id, "✅ Nollandi")
    except Exception as e:
        logger.error(f"resetcount xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "toggle_channel_check")
@safe_callback_handler
def toggle_channel_check(c):
    try:
        if not is_admin(c.from_user.id):
            return
        required = config.get("required_channels", [])
        markup = InlineKeyboardMarkup(row_width=1)
        for i, ch in enumerate(required):
            status = "✅" if ch.get("check_enabled", True) else "❌"
            markup.add(InlineKeyboardButton(f"{status} {ch['title']}", callback_data=f"togglecheck_{i}"))
        safe_send_message(c.message.chat.id, "Qaysi kanal uchun tekshirishni o'zgartirasiz?", reply_markup=markup)
    except Exception as e:
        logger.error(f"toggle_channel_check xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("togglecheck_"))
@safe_callback_handler
def togglecheck(c):
    try:
        if not is_admin(c.from_user.id):
            return
        idx = int(c.data.split("_")[-1])
        required = config.get("required_channels", [])
        if 0 <= idx < len(required):
            required[idx]["check_enabled"] = not required[idx].get("check_enabled", True)
            save_db()
            status = "yoqildi" if required[idx]["check_enabled"] else "o'chirildi"
            safe_answer_callback_query(c.id, f"✅ Tekshirish {status}")
    except Exception as e:
        logger.error(f"togglecheck xato: {e}")

# =====================================
# ADMIN PANEL - EARN TASKS
# =====================================
@bot.message_handler(func=lambda m: m.text == "💼 Pul ishlash vazifalari" and is_admin(m.from_user.id))
@admin_required
def manage_earn_tasks(message):
    try:
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
    except Exception as e:
        logger.error(f"manage_earn_tasks xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "add_earn_task")
@safe_callback_handler
def add_earn_task(c):
    try:
        if not is_admin(c.from_user.id):
            return
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("📢 Kanal", callback_data="earntype_channel"),
            InlineKeyboardButton("👁 Post", callback_data="earntype_post"),
        )
        safe_send_message(c.message.chat.id, "Vazifa turini tanlang:", reply_markup=markup)
    except Exception as e:
        logger.error(f"add_earn_task xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("earntype_"))
@safe_callback_handler
def earntype_pick(c):
    try:
        if not is_admin(c.from_user.id):
            return
        task_type = c.data.split("_")[-1]
        msg = safe_send_message(c.message.chat.id, "Sarlavha (nom) kiriting:")
        if msg:
            bot.register_next_step_handler(msg, process_earn_title, task_type)
    except Exception as e:
        logger.error(f"earntype_pick xato: {e}")

@safe_next_step
def process_earn_title(message, task_type: str):
    try:
        title = message.text.strip()
        msg = safe_send_message(message.chat.id, "Link kiriting (https://t.me/...):")
        if msg:
            bot.register_next_step_handler(msg, process_earn_link, task_type, title)
    except Exception as e:
        logger.error(f"process_earn_title xato: {e}")

@safe_next_step
def process_earn_link(message, task_type: str, title: str):
    try:
        link = message.text.strip()
        msg = safe_send_message(message.chat.id, "💰 Mukofot summasini kiriting (bajarganda beriladi):")
        if msg:
            bot.register_next_step_handler(msg, process_earn_reward, task_type, title, link)
    except Exception as e:
        logger.error(f"process_earn_link xato: {e}")

@safe_next_step
def process_earn_reward(message, task_type: str, title: str, link: str):
    try:
        reward = safe_int(message.text, default=None)
        if reward is None:
            safe_send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
            return
        msg = safe_send_message(message.chat.id, "⚠️ Agar kanal bo'lsa: keyinchalik obunadan chiqib ketsa qancha balansdan ayiriladi? (0 = ayirilmasin):")
        if msg:
            bot.register_next_step_handler(msg, process_earn_penalty, task_type, title, link, reward)
    except Exception as e:
        logger.error(f"process_earn_reward xato: {e}")

@safe_next_step
def process_earn_penalty(message, task_type: str, title: str, link: str, reward: int):
    try:
        penalty = safe_int(message.text, default=None)
        if penalty is None:
            safe_send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
            return
        tasks = config.setdefault("earn_tasks", [])
        tasks.append({"id": new_id(tasks), "type": task_type, "title": title, "link": link, "reward": reward, "penalty": penalty})
        save_db()
        safe_send_message(message.chat.id, "✅ Vazifa qo'shildi", reply_markup=admin_menu())
    except Exception as e:
        logger.error(f"process_earn_penalty xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "edit_earn_task")
@safe_callback_handler
def edit_earn_task(c):
    try:
        if not is_admin(c.from_user.id):
            return
        tasks = config.get("earn_tasks", [])
        markup = InlineKeyboardMarkup(row_width=1)
        for t in tasks:
            markup.add(InlineKeyboardButton(f"{t.get('title','')}", callback_data=f"editearn_{t['id']}"))
        safe_send_message(c.message.chat.id, "Tahrirlash uchun tanlang:", reply_markup=markup)
    except Exception as e:
        logger.error(f"edit_earn_task xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("editearn_"))
@safe_callback_handler
def editearn_pick(c):
    try:
        if not is_admin(c.from_user.id):
            return
        task_id = int(c.data.split("_")[-1])
        msg = safe_send_message(c.message.chat.id, "Yangi mukofot summasini kiriting:")
        if msg:
            bot.register_next_step_handler(msg, process_edit_earn_reward, task_id)
    except Exception as e:
        logger.error(f"editearn_pick xato: {e}")

@safe_next_step
def process_edit_earn_reward(message, task_id: int):
    try:
        reward = safe_int(message.text, default=None)
        if reward is None:
            safe_send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
            return
        for t in config.get("earn_tasks", []):
            if t["id"] == task_id:
                t["reward"] = reward
        save_db()
        safe_send_message(message.chat.id, "✅ Yangilandi", reply_markup=admin_menu())
    except Exception as e:
        logger.error(f"process_edit_earn_reward xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "remove_earn_task")
@safe_callback_handler
def remove_earn_task(c):
    try:
        if not is_admin(c.from_user.id):
            return
        tasks = config.get("earn_tasks", [])
        markup = InlineKeyboardMarkup(row_width=1)
        for t in tasks:
            markup.add(InlineKeyboardButton(f"{t.get('title','')}", callback_data=f"delearntask_{t['id']}"))
        safe_send_message(c.message.chat.id, "O'chirish uchun tanlang:", reply_markup=markup)
    except Exception as e:
        logger.error(f"remove_earn_task xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("delearntask_"))
@safe_callback_handler
def delearntask(c):
    try:
        if not is_admin(c.from_user.id):
            return
        task_id = int(c.data.split("_")[-1])
        config["earn_tasks"] = [t for t in config.get("earn_tasks", []) if t["id"] != task_id]
        save_db()
        safe_answer_callback_query(c.id, "✅ O'chirildi")
    except Exception as e:
        logger.error(f"delearntask xato: {e}")

# =====================================
# ADMIN PANEL - PROMO CODES
# =====================================
@bot.message_handler(func=lambda m: m.text == "🎟 Promokodlar" and is_admin(m.from_user.id))
@admin_required
def manage_promo(message):
    try:
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
    except Exception as e:
        logger.error(f"manage_promo xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "add_promo")
@safe_callback_handler
def add_promo(c):
    try:
        if not is_admin(c.from_user.id):
            return
        msg = safe_send_message(c.message.chat.id, "Format: KOD - summa (masalan: BONUS100 - 100)")
        if msg:
            bot.register_next_step_handler(msg, process_add_promo)
    except Exception as e:
        logger.error(f"add_promo xato: {e}")

@safe_next_step
def process_add_promo(message):
    try:
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
    except Exception as e:
        logger.error(f"process_add_promo xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "set_promo_limit")
@safe_callback_handler
def set_promo_limit(c):
    try:
        if not is_admin(c.from_user.id):
            return
        markup = InlineKeyboardMarkup(row_width=1)
        for code in promo_codes:
            markup.add(InlineKeyboardButton(code, callback_data=f"promolimit_{code}"))
        safe_send_message(c.message.chat.id, "Qaysi promokod uchun limit belgilaysiz?", reply_markup=markup)
    except Exception as e:
        logger.error(f"set_promo_limit xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("promolimit_"))
@safe_callback_handler
def promolimit_pick(c):
    try:
        if not is_admin(c.from_user.id):
            return
        code = c.data.split("_", 1)[1]
        msg = safe_send_message(c.message.chat.id, "Nechta marta ishlatilishi mumkinligini kiriting (0 = cheksiz):")
        if msg:
            bot.register_next_step_handler(msg, process_promolimit, code)
    except Exception as e:
        logger.error(f"promolimit_pick xato: {e}")

@safe_next_step
def process_promolimit(message, code: str):
    try:
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
    except Exception as e:
        logger.error(f"process_promolimit xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "remove_promo")
@safe_callback_handler
def remove_promo(c):
    try:
        if not is_admin(c.from_user.id):
            return
        markup = InlineKeyboardMarkup(row_width=1)
        for code in promo_codes:
            markup.add(InlineKeyboardButton(code, callback_data=f"delpromo_{code}"))
        safe_send_message(c.message.chat.id, "O'chirish uchun tanlang:", reply_markup=markup)
    except Exception as e:
        logger.error(f"remove_promo xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("delpromo_"))
@safe_callback_handler
def delpromo(c):
    try:
        if not is_admin(c.from_user.id):
            return
        code = c.data.split("_", 1)[1]
        promo_codes.pop(code, None)
        config.get("promo_limits", {}).pop(code, None)
        save_db()
        safe_answer_callback_query(c.id, "✅ O'chirildi")
    except Exception as e:
        logger.error(f"delpromo xato: {e}")

# =====================================
# ADMIN PANEL - MINI-GAMES SETTINGS
# =====================================
@bot.message_handler(func=lambda m: m.text == "🎮 Mini-o'yinlar sozlamalari" and is_admin(m.from_user.id))
@admin_required
def manage_games(message):
    try:
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
    except Exception as e:
        logger.error(f"manage_games xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("gamecfg_"))
@safe_callback_handler
def gamecfg(c):
    try:
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
        markup.add(InlineKeyboardButton("📝 Tavsifni o'zgartirish", callback_data=f"gset_desc_{key}"))
        safe_answer_callback_query(c.id)
        safe_send_message(
            c.message.chat.id,
            f"{g['name']}\n\n🎯 Yutish ehtimoli: {g.get('win_chance')}%\n✖️ Koeffitsiyent: x{g.get('multiplier')}\n"
            f"📉 Min: {g.get('min_bet'):,}\n📈 Max: {g.get('max_bet'):,}\n"
            f"📝 {g.get('description', '')}\nHolat: {status}",
            reply_markup=markup,
        )
    except Exception as e:
        logger.error(f"gamecfg xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("gset_toggle_"))
@safe_callback_handler
def gset_toggle(c):
    try:
        if not is_admin(c.from_user.id):
            return
        key = c.data.split("_", 2)[2]
        config["games"][key]["enabled"] = not config["games"][key].get("enabled", True)
        save_db()
        safe_answer_callback_query(c.id, "✅ Holat o'zgartirildi")
    except Exception as e:
        logger.error(f"gset_toggle xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("gset_chance_"))
@safe_callback_handler
def gset_chance(c):
    try:
        if not is_admin(c.from_user.id):
            return
        key = c.data.split("_", 2)[2]
        msg = safe_send_message(c.message.chat.id, "Yutish ehtimolini foizda kiriting (0-100):")
        if msg:
            bot.register_next_step_handler(msg, process_gset_chance, key)
    except Exception as e:
        logger.error(f"gset_chance xato: {e}")

@safe_next_step
def process_gset_chance(message, key: str):
    try:
        val = safe_float(message.text, default=None)
        if val is None:
            safe_send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
            return
        val = max(0, min(100, val))
        config["games"][key]["win_chance"] = val
        save_db()
        safe_send_message(message.chat.id, "✅ Saqlandi", reply_markup=admin_menu())
    except Exception as e:
        logger.error(f"process_gset_chance xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("gset_mult_"))
@safe_callback_handler
def gset_mult(c):
    try:
        if not is_admin(c.from_user.id):
            return
        key = c.data.split("_", 2)[2]
        msg = safe_send_message(c.message.chat.id, "Yangi koeffitsiyentni kiriting (masalan 2.5):")
        if msg:
            bot.register_next_step_handler(msg, process_gset_mult, key)
    except Exception as e:
        logger.error(f"gset_mult xato: {e}")

@safe_next_step
def process_gset_mult(message, key: str):
    try:
        val = safe_float(message.text, default=None)
        if val is None:
            safe_send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
            return
        config["games"][key]["multiplier"] = val
        save_db()
        safe_send_message(message.chat.id, "✅ Saqlandi", reply_markup=admin_menu())
    except Exception as e:
        logger.error(f"process_gset_mult xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("gset_min_"))
@safe_callback_handler
def gset_min(c):
    try:
        if not is_admin(c.from_user.id):
            return
        key = c.data.split("_", 2)[2]
        msg = safe_send_message(c.message.chat.id, "Yangi minimal stavkani kiriting:")
        if msg:
            bot.register_next_step_handler(msg, process_gset_min, key)
    except Exception as e:
        logger.error(f"gset_min xato: {e}")

@safe_next_step
def process_gset_min(message, key: str):
    try:
        val = safe_int(message.text, default=None)
        if val is None:
            safe_send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
            return
        config["games"][key]["min_bet"] = val
        save_db()
        safe_send_message(message.chat.id, "✅ Saqlandi", reply_markup=admin_menu())
    except Exception as e:
        logger.error(f"process_gset_min xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("gset_max_"))
@safe_callback_handler
def gset_max(c):
    try:
        if not is_admin(c.from_user.id):
            return
        key = c.data.split("_", 2)[2]
        msg = safe_send_message(c.message.chat.id, "Yangi maksimal stavkani kiriting:")
        if msg:
            bot.register_next_step_handler(msg, process_gset_max, key)
    except Exception as e:
        logger.error(f"gset_max xato: {e}")

@safe_next_step
def process_gset_max(message, key: str):
    try:
        val = safe_int(message.text, default=None)
        if val is None:
            safe_send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
            return
        config["games"][key]["max_bet"] = val
        save_db()
        safe_send_message(message.chat.id, "✅ Saqlandi", reply_markup=admin_menu())
    except Exception as e:
        logger.error(f"process_gset_max xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("gset_desc_"))
@safe_callback_handler
def gset_desc(c):
    try:
        if not is_admin(c.from_user.id):
            return
        key = c.data.split("_", 2)[2]
        msg = safe_send_message(c.message.chat.id, "Yangi tavsifni kiriting:")
        if msg:
            bot.register_next_step_handler(msg, process_gset_desc, key)
    except Exception as e:
        logger.error(f"gset_desc xato: {e}")

@safe_next_step
def process_gset_desc(message, key: str):
    try:
        desc = message.text.strip()
        config["games"][key]["description"] = desc
        save_db()
        safe_send_message(message.chat.id, "✅ Saqlandi", reply_markup=admin_menu())
    except Exception as e:
        logger.error(f"process_gset_desc xato: {e}")

# =====================================
# ADMIN PANEL - REFERRAL / BONUS SETTINGS
# =====================================
@bot.message_handler(func=lambda m: m.text == "💰 Referal/Bonuslar" and is_admin(m.from_user.id))
@admin_required
def referral_settings(message):
    try:
        levels = config.get("referral_levels", DEFAULT_CONFIG["referral_levels"])
        level_text = "\n".join([f"🔹 {l.get('level')}-daraja: {l.get('required')}+ referal → {l.get('bonus'):,} so'm" for l in levels])
        
        text = (
            f"💰 <b>Referal va bonus sozlamalari</b>\n\n"
            f"👥 Referal bonusi: {int(config.get('referral_bonus', 1000)):,} so'm\n"
            f"🎁 Ro'yxatdan o'tish bonusi: {int(config.get('welcome_bonus', 100)):,} so'm\n"
            f"✅ Obuna bonusi: {int(config.get('subscribe_bonus', 200)):,} so'm\n"
            f"📅 Kunlik bonus: {config.get('daily_bonus_range', [100,500])[0]:,} - {config.get('daily_bonus_range', [100,500])[1]:,} so'm\n\n"
            f"📊 <b>Referal darajalari:</b>\n{level_text}"
        )
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton("👥 Referal bonusini o'zgartirish", callback_data="edit_ref_bonus"))
        markup.add(InlineKeyboardButton("🎁 Ro'yxat bonusini o'zgartirish", callback_data="edit_welcome_bonus"))
        markup.add(InlineKeyboardButton("✅ Obuna bonusini o'zgartirish", callback_data="edit_subscribe_bonus"))
        markup.add(InlineKeyboardButton("📅 Kunlik bonusni o'zgartirish", callback_data="edit_daily_bonus"))
        markup.add(InlineKeyboardButton("📊 Referal darajalarini boshqarish", callback_data="manage_referral_levels"))
        safe_send_message(message.chat.id, text, reply_markup=markup)
    except Exception as e:
        logger.error(f"referral_settings xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "manage_referral_levels")
@safe_callback_handler
def manage_referral_levels(c):
    try:
        if not is_admin(c.from_user.id):
            return
        levels = config.get("referral_levels", DEFAULT_CONFIG["referral_levels"])
        markup = InlineKeyboardMarkup(row_width=1)
        for level in levels:
            markup.add(InlineKeyboardButton(f"🔹 {level.get('level')}-daraja", callback_data=f"edit_level_{level.get('level')}"))
        markup.add(InlineKeyboardButton("➕ Yangi daraja qo'shish", callback_data="add_level"))
        safe_send_message(c.message.chat.id, "📊 Referal darajalarini boshqarish:", reply_markup=markup)
    except Exception as e:
        logger.error(f"manage_referral_levels xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("edit_level_"))
@safe_callback_handler
def edit_level(c):
    try:
        if not is_admin(c.from_user.id):
            return
        level_num = int(c.data.split("_")[-1])
        msg = safe_send_message(c.message.chat.id, f"🔹 {level_num}-daraja uchun yangi bonus va talabni kiriting (format: bonus - talab, masalan 2000 - 5):")
        if msg:
            bot.register_next_step_handler(msg, process_edit_level, level_num)
    except Exception as e:
        logger.error(f"edit_level xato: {e}")

@safe_next_step
def process_edit_level(message, level_num: int):
    try:
        parts = message.text.strip().split(" - ")
        if len(parts) != 2:
            safe_send_message(message.chat.id, "❌ Format noto'g'ri", reply_markup=admin_menu())
            return
        bonus = safe_int(parts[0], default=None)
        required = safe_int(parts[1], default=None)
        if bonus is None or required is None:
            safe_send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
            return
        levels = config.get("referral_levels", [])
        for level in levels:
            if level.get("level") == level_num:
                level["bonus"] = bonus
                level["required"] = required
                break
        save_db()
        safe_send_message(message.chat.id, "✅ Yangilandi", reply_markup=admin_menu())
    except Exception as e:
        logger.error(f"process_edit_level xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "add_level")
@safe_callback_handler
def add_level(c):
    try:
        if not is_admin(c.from_user.id):
            return
        msg = safe_send_message(c.message.chat.id, "🔹 Yangi daraja uchun bonus va talabni kiriting (format: bonus - talab, masalan 5000 - 20):")
        if msg:
            bot.register_next_step_handler(msg, process_add_level)
    except Exception as e:
        logger.error(f"add_level xato: {e}")

@safe_next_step
def process_add_level(message):
    try:
        parts = message.text.strip().split(" - ")
        if len(parts) != 2:
            safe_send_message(message.chat.id, "❌ Format noto'g'ri", reply_markup=admin_menu())
            return
        bonus = safe_int(parts[0], default=None)
        required = safe_int(parts[1], default=None)
        if bonus is None or required is None:
            safe_send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
            return
        levels = config.get("referral_levels", [])
        new_level = max([l.get("level", 0) for l in levels]) + 1 if levels else 1
        levels.append({"level": new_level, "bonus": bonus, "required": required})
        save_db()
        safe_send_message(message.chat.id, f"✅ {new_level}-daraja qo'shildi", reply_markup=admin_menu())
    except Exception as e:
        logger.error(f"process_add_level xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "edit_ref_bonus")
@safe_callback_handler
def edit_ref_bonus(c):
    try:
        if not is_admin(c.from_user.id):
            return
        msg = safe_send_message(c.message.chat.id, "Yangi referal bonusini kiriting:")
        if msg:
            bot.register_next_step_handler(msg, lambda m: process_simple_config_int(m, "referral_bonus"))
    except Exception as e:
        logger.error(f"edit_ref_bonus xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "edit_welcome_bonus")
@safe_callback_handler
def edit_welcome_bonus(c):
    try:
        if not is_admin(c.from_user.id):
            return
        msg = safe_send_message(c.message.chat.id, "Yangi ro'yxatdan o'tish bonusini kiriting:")
        if msg:
            bot.register_next_step_handler(msg, lambda m: process_simple_config_int(m, "welcome_bonus"))
    except Exception as e:
        logger.error(f"edit_welcome_bonus xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "edit_subscribe_bonus")
@safe_callback_handler
def edit_subscribe_bonus(c):
    try:
        if not is_admin(c.from_user.id):
            return
        msg = safe_send_message(c.message.chat.id, "Yangi obuna bonusini kiriting:")
        if msg:
            bot.register_next_step_handler(msg, lambda m: process_simple_config_int(m, "subscribe_bonus"))
    except Exception as e:
        logger.error(f"edit_subscribe_bonus xato: {e}")

@safe_next_step
def process_simple_config_int(message, key: str):
    try:
        amount = safe_int(message.text, default=None)
        if amount is None:
            safe_send_message(message.chat.id, "❌ Son kiriting", reply_markup=admin_menu())
            return
        config[key] = amount
        save_db()
        safe_send_message(message.chat.id, "✅ Saqlandi", reply_markup=admin_menu())
    except Exception as e:
        logger.error(f"process_simple_config_int xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "edit_daily_bonus")
@safe_callback_handler
def edit_daily_bonus(c):
    try:
        if not is_admin(c.from_user.id):
            return
        msg = safe_send_message(c.message.chat.id, "Min va max qiymatlarni kiriting (masalan: 100 500):")
        if msg:
            bot.register_next_step_handler(msg, process_edit_daily_bonus)
    except Exception as e:
        logger.error(f"edit_daily_bonus xato: {e}")

@safe_next_step
def process_edit_daily_bonus(message):
    try:
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
    except Exception as e:
        logger.error(f"process_edit_daily_bonus xato: {e}")

# =====================================
# ADMIN PANEL - TEXTS
# =====================================
@bot.message_handler(func=lambda m: m.text == "✉️ Matnlar" and is_admin(m.from_user.id))
@admin_required
def manage_texts(message):
    try:
        markup = InlineKeyboardMarkup(row_width=1)
        for key, label in EDITABLE_TEXT_KEYS.items():
            markup.add(InlineKeyboardButton(f"✏️ {label}", callback_data=f"edittext_{key}"))
        safe_send_message(message.chat.id, "✉️ Tahrirlash uchun matnni tanlang:", reply_markup=markup)
    except Exception as e:
        logger.error(f"manage_texts xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("edittext_"))
@safe_callback_handler
def edittext(c):
    try:
        if not is_admin(c.from_user.id):
            return
        key = c.data.split("_", 1)[1]
        current = get_text(key)
        msg = safe_send_message(c.message.chat.id, f"Joriy matn:\n\n{current}\n\nYangi matnni yuboring (agar defaultga qaytarish uchun /reset yozing):")
        if msg:
            bot.register_next_step_handler(msg, process_edittext, key)
    except Exception as e:
        logger.error(f"edittext xato: {e}")

@safe_next_step
def process_edittext(message, key: str):
    try:
        if message.text == "/reset":
            config.setdefault("messages", {}).pop(key, None)
        else:
            config.setdefault("messages", {})[key] = message.text
        save_db()
        safe_send_message(message.chat.id, "✅ Saqlandi", reply_markup=admin_menu())
    except Exception as e:
        logger.error(f"process_edittext xato: {e}")

# =====================================
# ADMIN PANEL - ADMINS
# =====================================
@bot.message_handler(func=lambda m: m.text == "👨‍💻 Adminlar" and is_admin(m.from_user.id))
@admin_required
def manage_admins(message):
    try:
        lines = ["👨‍💻 <b>Adminlar</b>"]
        for uid, info in ADMINS.items():
            lines.append(f"\n{info.get('username','')} | <code>{uid}</code> | {info.get('role')} | qo'shilgan: {info.get('added_date', '')}")
        markup = InlineKeyboardMarkup(row_width=1)
        if is_superadmin(message.from_user.id):
            markup.add(InlineKeyboardButton("➕ Admin qo'shish", callback_data="add_admin"))
            markup.add(InlineKeyboardButton("❌ Adminni o'chirish", callback_data="remove_admin"))
        safe_send_message(message.chat.id, "\n".join(lines), reply_markup=markup)
    except Exception as e:
        logger.error(f"manage_admins xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "add_admin")
@safe_callback_handler
def add_admin(c):
    try:
        if not is_superadmin(c.from_user.id):
            safe_answer_callback_query(c.id, "❌ Faqat super admin")
            return
        msg = safe_send_message(c.message.chat.id, "Yangi admin ID sini kiriting:")
        if msg:
            bot.register_next_step_handler(msg, process_add_admin)
    except Exception as e:
        logger.error(f"add_admin xato: {e}")

@safe_next_step
def process_add_admin(message):
    try:
        if not message.text.strip().isdigit():
            safe_send_message(message.chat.id, "❌ Faqat ID (raqam) kiriting", reply_markup=admin_menu())
            return
        new_admin_id = message.text.strip()
        username = "Noma'lum"
        chat = safe_get_chat(int(new_admin_id))
        if chat:
            username = f"@{chat.username}" if chat.username else (chat.first_name or "Noma'lum")
        ADMINS[new_admin_id] = {"username": username, "role": "admin", "added_date": now_str()}
        save_db()
        safe_send_message(message.chat.id, f"✅ {username} admin qilib qo'shildi", reply_markup=admin_menu())
        safe_send_message(int(new_admin_id), "🎉 Siz botga admin etib tayinlandingiz!")
    except Exception as e:
        logger.error(f"process_add_admin xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "remove_admin")
@safe_callback_handler
def remove_admin(c):
    try:
        if not is_superadmin(c.from_user.id):
            safe_answer_callback_query(c.id, "❌ Faqat super admin")
            return
        markup = InlineKeyboardMarkup(row_width=1)
        for uid, info in ADMINS.items():
            if info.get("role") == "superadmin":
                continue
            markup.add(InlineKeyboardButton(f"{info.get('username','')} ({uid})", callback_data=f"deladmin_{uid}"))
        safe_send_message(c.message.chat.id, "O'chirish uchun tanlang:", reply_markup=markup)
    except Exception as e:
        logger.error(f"remove_admin xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("deladmin_"))
@safe_callback_handler
def deladmin(c):
    try:
        if not is_superadmin(c.from_user.id):
            return
        uid = c.data.split("_", 1)[1]
        if uid in ADMINS and ADMINS[uid].get("role") != "superadmin":
            ADMINS.pop(uid, None)
            save_db()
            safe_answer_callback_query(c.id, "✅ O'chirildi")
        else:
            safe_answer_callback_query(c.id, "❌ Bo'lmaydi")
    except Exception as e:
        logger.error(f"deladmin xato: {e}")

# =====================================
# ADMIN PANEL - SYSTEM SETTINGS
# =====================================
@bot.message_handler(func=lambda m: m.text == "🔧 Tizim sozlamalari" and is_admin(m.from_user.id))
@admin_required
def system_settings(message):
    try:
        maintenance = "✅ Yoqilgan" if config.get("maintenance_mode", False) else "❌ O'chirilgan"
        text = (
            f"🔧 <b>Tizim sozlamalari</b>\n\n"
            f"🔧 Texnik ishlar rejimi: {maintenance}\n"
            f"👥 Foydalanuvchilar: {len(users)}\n"
            f"📦 Buyurtmalar: {len(orders)}\n"
            f"🔄 So'nggi backup: so'nggi 24 soat ichida"
        )
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton(f"🔄 Texnik ishlar rejimi ({'O''chirish' if config.get('maintenance_mode', False) else 'Yoqish'})", callback_data="toggle_maintenance"))
        markup.add(InlineKeyboardButton("💾 Qo'lda backup yaratish", callback_data="manual_backup"))
        markup.add(InlineKeyboardButton("📊 Ma'lumotlarni qayta yuklash", callback_data="reload_data"))
        safe_send_message(message.chat.id, text, reply_markup=markup)
    except Exception as e:
        logger.error(f"system_settings xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "toggle_maintenance")
@safe_callback_handler
def toggle_maintenance(c):
    try:
        if not is_superadmin(c.from_user.id):
            safe_answer_callback_query(c.id, "❌ Faqat super admin")
            return
        config["maintenance_mode"] = not config.get("maintenance_mode", False)
        save_db()
        status = "yoqildi" if config["maintenance_mode"] else "o'chirildi"
        safe_answer_callback_query(c.id, f"✅ Texnik ishlar rejimi {status}")
    except Exception as e:
        logger.error(f"toggle_maintenance xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "manual_backup")
@safe_callback_handler
def manual_backup(c):
    try:
        if not is_admin(c.from_user.id):
            return
        Database.backup()
        safe_answer_callback_query(c.id, "✅ Backup yaratildi")
    except Exception as e:
        logger.error(f"manual_backup xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "reload_data")
@safe_callback_handler
def reload_data(c):
    try:
        if not is_superadmin(c.from_user.id):
            safe_answer_callback_query(c.id, "❌ Faqat super admin")
            return
        global users, orders, config, promo_codes, ADMINS, lottery_data
        users, orders, config, promo_codes, ADMINS, lottery_data = Database.load_all()
        safe_answer_callback_query(c.id, "✅ Ma'lumotlar qayta yuklandi")
    except Exception as e:
        logger.error(f"reload_data xato: {e}")

# =====================================
# ADMIN PANEL - BROADCAST (VAQT BELGILASH BILAN)
# =====================================
import threading
from datetime import datetime, timedelta
import time

@bot.message_handler(func=lambda m: m.text == "📢 Reklama" and is_admin(m.from_user.id))
@admin_required
def send_ad(message):
    try:
        targets = config.get("broadcast_targets", [])
        n_groups = sum(1 for t in targets if t.get("type") == "group")
        n_channels = sum(1 for t in targets if t.get("type") == "channel")
        
        # Kutilayotgan reklamalar
        scheduled = config.get("_scheduled_broadcasts", [])
        scheduled_count = len(scheduled)
        
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton(f"👥 Barcha foydalanuvchilarga ({len(users)})", callback_data="ad_target_users"))
        markup.add(InlineKeyboardButton(f"📢 Saqlangan kanallarga ({n_channels})", callback_data="ad_target_channels"))
        markup.add(InlineKeyboardButton(f"👨‍👩‍👧 Saqlangan guruhlarga ({n_groups})", callback_data="ad_target_groups"))
        markup.add(InlineKeyboardButton(f"🌐 Hammasiga (users + guruh + kanal)", callback_data="ad_target_everything"))
        markup.add(InlineKeyboardButton("⏰ Vaqt belgilab yuborish", callback_data="ad_schedule"))
        markup.add(InlineKeyboardButton("📋 Rejalashtirilgan reklamalar", callback_data="ad_scheduled_list"))
        markup.add(InlineKeyboardButton("➕ Yangi kanal/guruh qo'shish", callback_data="ad_add_target"))
        markup.add(InlineKeyboardButton("📋 Saqlangan manzillar ro'yxati", callback_data="ad_list_targets"))
        
        text = (
            "📢 <b>Reklama bo'limi</b>\n\n"
            "Reklamani qayerga yubormoqchisiz?\n\n"
            f"👤 Foydalanuvchilar: {len(users)}\n"
            f"📢 Kanallar: {n_channels}\n"
            f"👨‍👩‍👧 Guruhlar: {n_groups}\n"
            f"⏰ Rejalashtirilgan: {scheduled_count} ta"
        )
        safe_send_message(message.chat.id, text, reply_markup=markup)
    except Exception as e:
        logger.error(f"send_ad xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "ad_scheduled_list")
@safe_callback_handler
def ad_scheduled_list(c):
    try:
        if not is_admin(c.from_user.id):
            return
        scheduled = config.get("_scheduled_broadcasts", [])
        
        if not scheduled:
            safe_answer_callback_query(c.id, "❌ Rejalashtirilgan reklamalar yo'q")
            return
        
        lines = ["⏰ <b>Rejalashtirilgan reklamalar</b>"]
        markup = InlineKeyboardMarkup(row_width=1)
        for i, s in enumerate(scheduled):
            status = "✅" if s.get("status") == "pending" else "❌"
            time_str = s.get("scheduled_time", "Noma'lum")
            lines.append(f"\n{status} #{i+1} | {s.get('target_mode', 'Noma\'lum')} | {s.get('total', 0)} ta | {time_str}")
            markup.add(InlineKeyboardButton(f"❌ Bekor qilish #{i+1}", callback_data=f"ad_cancel_schedule_{i}"))
        
        markup.add(InlineKeyboardButton("⬅️ Ortga", callback_data="ad_back"))
        safe_answer_callback_query(c.id)
        safe_send_message(c.message.chat.id, "\n".join(lines), reply_markup=markup)
        
    except Exception as e:
        logger.error(f"ad_scheduled_list xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("ad_cancel_schedule_"))
@safe_callback_handler
def ad_cancel_schedule(c):
    try:
        if not is_admin(c.from_user.id):
            return
        idx = int(c.data.split("_")[-1])
        scheduled = config.get("_scheduled_broadcasts", [])
        
        if 0 <= idx < len(scheduled):
            removed = scheduled.pop(idx)
            config["_scheduled_broadcasts"] = scheduled
            save_db()
            safe_answer_callback_query(c.id, f"✅ Reklama bekor qilindi: {removed.get('target_mode', '')}")
        else:
            safe_answer_callback_query(c.id, "❌ Topilmadi")
            
    except Exception as e:
        logger.error(f"ad_cancel_schedule xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "ad_schedule")
@safe_callback_handler
def ad_schedule_menu(c):
    try:
        if not is_admin(c.from_user.id):
            return
        
        targets = config.get("broadcast_targets", [])
        n_groups = sum(1 for t in targets if t.get("type") == "group")
        n_channels = sum(1 for t in targets if t.get("type") == "channel")
        
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton(f"👥 Barcha foydalanuvchilarga ({len(users)})", callback_data="ad_sched_target_users"))
        markup.add(InlineKeyboardButton(f"📢 Saqlangan kanallarga ({n_channels})", callback_data="ad_sched_target_channels"))
        markup.add(InlineKeyboardButton(f"👨‍👩‍👧 Saqlangan guruhlarga ({n_groups})", callback_data="ad_sched_target_groups"))
        markup.add(InlineKeyboardButton(f"🌐 Hammasiga (users + guruh + kanal)", callback_data="ad_sched_target_everything"))
        markup.add(InlineKeyboardButton("⬅️ Ortga", callback_data="ad_back"))
        
        safe_edit_message_text(
            "⏰ <b>Vaqt belgilab reklama yuborish</b>\n\n"
            "Reklamani qaysi manzilga yubormoqchisiz?\n\n"
            "Keyingi qadamda vaqtni belgilaysiz.",
            c.message.chat.id,
            c.message.message_id,
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"ad_schedule_menu xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("ad_sched_target_"))
@safe_callback_handler
def ad_sched_target_selected(c):
    try:
        if not is_admin(c.from_user.id):
            return
        
        target_mode = c.data.replace("ad_sched_target_", "")
        chat_ids = _resolve_ad_chat_ids(target_mode)
        
        if not chat_ids:
            safe_answer_callback_query(c.id, "❌ Yuborish uchun manzil topilmadi")
            return
        
        safe_answer_callback_query(c.id)
        
        # Vaqt formatini tushuntirish
        markup = InlineKeyboardMarkup(row_width=2)
        now = datetime.now()
        for h in [1, 2, 3, 6, 12, 24]:
            future = now + timedelta(hours=h)
            time_str = future.strftime("%H:%M")
            markup.add(InlineKeyboardButton(f"{h} soat ({time_str})", callback_data=f"ad_sched_hour_{target_mode}_{h}"))
        
        markup.add(InlineKeyboardButton("✏️ O'zim vaqt kiritaman", callback_data=f"ad_sched_custom_{target_mode}"))
        markup.add(InlineKeyboardButton("⬅️ Ortga", callback_data="ad_schedule"))
        
        safe_edit_message_text(
            f"⏰ <b>Vaqt belgilash</b>\n\n"
            f"🎯 Manzil: <code>{target_mode}</code>\n"
            f"👥 Qabul qiluvchilar: {len(chat_ids)} ta\n\n"
            f"Reklamani qancha vaqtdan keyin yuborish kerak?\n\n"
            f"📌 Hozirgi vaqt: {now.strftime('%H:%M')}",
            c.message.chat.id,
            c.message.message_id,
            reply_markup=markup
        )
        
        # Ma'lumotlarni saqlash
        config["_sched_data"] = {
            "target_mode": target_mode,
            "chat_ids": chat_ids,
            "total": len(chat_ids)
        }
        save_db()
        
    except Exception as e:
        logger.error(f"ad_sched_target_selected xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("ad_sched_hour_"))
@safe_callback_handler
def ad_sched_hour(c):
    try:
        if not is_admin(c.from_user.id):
            return
        
        parts = c.data.split("_")
        target_mode = parts[3]
        hours = int(parts[4])
        
        sched_data = config.get("_sched_data", {})
        if sched_data.get("target_mode") != target_mode:
            safe_answer_callback_query(c.id, "❌ Ma'lumotlar eskirgan")
            return
        
        scheduled_time = datetime.now() + timedelta(hours=hours)
        _schedule_broadcast(c, target_mode, scheduled_time)
        
    except Exception as e:
        logger.error(f"ad_sched_hour xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("ad_sched_custom_"))
@safe_callback_handler
def ad_sched_custom(c):
    try:
        if not is_admin(c.from_user.id):
            return
        
        target_mode = c.data.replace("ad_sched_custom_", "")
        
        msg = safe_send_message(
            c.message.chat.id,
            f"✏️ Vaqtni kiriting (format: HH:MM)\n\n"
            f"🎯 Manzil: <code>{target_mode}</code>\n"
            f"📌 Masalan: 14:30 yoki 09:00\n\n"
            f"💡 Vaqt 24 soatlik formatda bo'lishi kerak.",
            reply_markup=back_menu()
        )
        if msg:
            bot.register_next_step_handler(msg, process_sched_custom_time, target_mode)
            
    except Exception as e:
        logger.error(f"ad_sched_custom xato: {e}")

@safe_next_step
def process_sched_custom_time(message, target_mode: str):
    try:
        if message.text == "⬅️ Ortga":
            safe_send_message(message.chat.id, "🔙 Orqaga", reply_markup=admin_menu())
            return
        
        time_str = message.text.strip()
        try:
            scheduled_time = datetime.strptime(time_str, "%H:%M")
            now = datetime.now()
            scheduled_time = scheduled_time.replace(year=now.year, month=now.month, day=now.day)
            
            if scheduled_time < now:
                scheduled_time += timedelta(days=1)
                
        except ValueError:
            safe_send_message(message.chat.id, "❌ Noto'g'ri format. HH:MM formatida kiriting (masalan: 14:30)", reply_markup=admin_menu())
            return
        
        sched_data = config.get("_sched_data", {})
        if sched_data.get("target_mode") != target_mode:
            safe_send_message(message.chat.id, "❌ Ma'lumotlar eskirgan", reply_markup=admin_menu())
            return
        
        _schedule_broadcast_from_msg(message, target_mode, scheduled_time)
        
    except Exception as e:
        logger.error(f"process_sched_custom_time xato: {e}")

def _schedule_broadcast(c, target_mode: str, scheduled_time: datetime):
    try:
        sched_data = config.get("_sched_data", {})
        chat_ids = sched_data.get("chat_ids", [])
        total = sched_data.get("total", 0)
        
        # Kontent yuborish bosqichi
        msg = safe_send_message(
            c.message.chat.id,
            f"📢 <b>Reklama kontentini yuboring</b>\n\n"
            f"🎯 Manzil: <code>{target_mode}</code>\n"
            f"👥 Qabul qiluvchilar: {total} ta\n"
            f"⏰ Yuborish vaqti: {scheduled_time.strftime('%d.%m.%Y %H:%M')}\n"
            f"⏳ Qolgan vaqt: {_time_until(scheduled_time)}\n\n"
            f"📤 Endi reklama kontentini yuboring:\n"
            f"Qabul qilinadi: ✉️ matn, 🖼 rasm, 🎥 video, 🎵 audio, 🎙 ovoz, 📄 fayl, 🔁 forward\n\n"
            f"⚠️ <b>DIQQAT!</b> Xabar yuborilgach rejaga qo'shiladi.",
            reply_markup=back_menu()
        )
        if msg:
            bot.register_next_step_handler(msg, process_sched_content, target_mode, scheduled_time, chat_ids, total)
            
    except Exception as e:
        logger.error(f"_schedule_broadcast xato: {e}")

def _schedule_broadcast_from_msg(message, target_mode: str, scheduled_time: datetime):
    try:
        sched_data = config.get("_sched_data", {})
        chat_ids = sched_data.get("chat_ids", [])
        total = sched_data.get("total", 0)
        
        # Kontent yuborish bosqichi
        msg = safe_send_message(
            message.chat.id,
            f"📢 <b>Reklama kontentini yuboring</b>\n\n"
            f"🎯 Manzil: <code>{target_mode}</code>\n"
            f"👥 Qabul qiluvchilar: {total} ta\n"
            f"⏰ Yuborish vaqti: {scheduled_time.strftime('%d.%m.%Y %H:%M')}\n"
            f"⏳ Qolgan vaqt: {_time_until(scheduled_time)}\n\n"
            f"📤 Endi reklama kontentini yuboring:\n"
            f"Qabul qilinadi: ✉️ matn, 🖼 rasm, 🎥 video, 🎵 audio, 🎙 ovoz, 📄 fayl, 🔁 forward\n\n"
            f"⚠️ <b>DIQQAT!</b> Xabar yuborilgach rejaga qo'shiladi.",
            reply_markup=back_menu()
        )
        if msg:
            bot.register_next_step_handler(msg, process_sched_content, target_mode, scheduled_time, chat_ids, total)
            
    except Exception as e:
        logger.error(f"_schedule_broadcast_from_msg xato: {e}")

def _time_until(dt: datetime) -> str:
    now = datetime.now()
    diff = dt - now
    if diff.total_seconds() < 0:
        return "Vaqt o'tgan"
    
    days = diff.days
    hours = diff.seconds // 3600
    minutes = (diff.seconds % 3600) // 60
    
    parts = []
    if days > 0:
        parts.append(f"{days} kun")
    if hours > 0:
        parts.append(f"{hours} soat")
    if minutes > 0:
        parts.append(f"{minutes} daqiqa")
    
    return " ".join(parts) or "0 daqiqa"

@safe_next_step
def process_sched_content(message, target_mode: str, scheduled_time: datetime, chat_ids: List[int], total: int):
    try:
        if message.text == "⬅️ Ortga":
            safe_send_message(message.chat.id, "🔙 Bekor qilindi", reply_markup=admin_menu())
            config.pop("_sched_data", None)
            save_db()
            return
        
        # Xabarni saqlash
        broadcast_msg = {
            "chat_id": message.chat.id,
            "message_id": message.message_id,
            "content_type": message.content_type,
            "text": message.text if message.content_type == "text" else None,
            "caption": message.caption if hasattr(message, "caption") else None,
            "photo": message.photo[-1].file_id if message.content_type == "photo" else None,
            "video": message.video.file_id if message.content_type == "video" else None,
            "audio": message.audio.file_id if message.content_type == "audio" else None,
            "voice": message.voice.file_id if message.content_type == "voice" else None,
            "document": message.document.file_id if message.content_type == "document" else None,
            "animation": message.animation.file_id if message.content_type == "animation" else None,
            "is_forward": message.forward_from is not None or message.forward_from_chat is not None,
        }
        
        # Rejaga qo'shish
        scheduled = config.setdefault("_scheduled_broadcasts", [])
        scheduled.append({
            "target_mode": target_mode,
            "chat_ids": chat_ids,
            "total": total,
            "scheduled_time": scheduled_time.isoformat(),
            "broadcast_msg": broadcast_msg,
            "status": "pending",
            "created_at": now_str(),
            "created_by": safe_username(message.from_user)
        })
        
        config.pop("_sched_data", None)
        save_db()
        
        # Vaqt bo'yicha ishga tushirish
        _start_schedule_checker()
        
        safe_send_message(
            message.chat.id,
            f"✅ Reklama rejalashtirildi!\n\n"
            f"🎯 Manzil: <code>{target_mode}</code>\n"
            f"👥 Qabul qiluvchilar: {total} ta\n"
            f"⏰ Yuborish vaqti: {scheduled_time.strftime('%d.%m.%Y %H:%M')}\n"
            f"⏳ Qolgan vaqt: {_time_until(scheduled_time)}\n"
            f"📅 Rejalashtirilgan: {now_str()}\n\n"
            f"📋 Rejalashtirilgan reklamalar ro'yxatini ko'rish uchun /ad_scheduled_list",
            reply_markup=admin_menu(),
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"process_sched_content xato: {e}")
        safe_send_message(message.chat.id, f"❌ Xato: {e}", reply_markup=admin_menu())

# Vaqt bo'yicha reklama yuborish checker
_schedule_checker_running = False

def _start_schedule_checker():
    global _schedule_checker_running
    if _schedule_checker_running:
        return
    _schedule_checker_running = True
    threading.Thread(target=_schedule_checker_loop, daemon=True).start()

def _schedule_checker_loop():
    global _schedule_checker_running
    while True:
        try:
            time.sleep(30)  # Har 30 soniyada tekshirish
            scheduled = config.get("_scheduled_broadcasts", [])
            if not scheduled:
                continue
            
            now = datetime.now()
            changed = False
            
            for i, s in enumerate(scheduled):
                if s.get("status") != "pending":
                    continue
                
                try:
                    sched_time = datetime.fromisoformat(s.get("scheduled_time", ""))
                    if sched_time <= now:
                        # Yuborish vaqti keldi
                        _execute_scheduled_broadcast(s, i)
                        changed = True
                except Exception as e:
                    logger.error(f"Schedule checker xato: {e}")
            
            if changed:
                save_db()
                
        except Exception as e:
            logger.error(f"_schedule_checker_loop xato: {e}")
    
    _schedule_checker_running = False

def _execute_scheduled_broadcast(sched: dict, idx: int):
    try:
        chat_ids = sched.get("chat_ids", [])
        broadcast_msg = sched.get("broadcast_msg", {})
        target_mode = sched.get("target_mode", "unknown")
        
        if not chat_ids or not broadcast_msg:
            sched["status"] = "failed"
            return
        
        # Yuborish
        sent, failed = 0, 0
        total = len(chat_ids)
        
        for cid in chat_ids:
            try:
                sent_msg = None
                if broadcast_msg.get("is_forward"):
                    sent_msg = safe_call(
                        bot.forward_message,
                        cid,
                        broadcast_msg.get("chat_id"),
                        broadcast_msg.get("message_id")
                    )
                else:
                    sent_msg = _send_broadcast_content(broadcast_msg, cid)
                
                if sent_msg:
                    sent += 1
                else:
                    failed += 1
                    
            except Exception as e:
                failed += 1
                logger.error(f"Scheduled broadcast xato ({cid}): {e}")
            
            time.sleep(0.5)  # Rate limit uchun
        
        sched["status"] = "completed"
        sched["sent"] = sent
        sched["failed"] = failed
        sched["executed_at"] = now_str()
        
        # Adminlarga xabar
        notify_admins(
            f"⏰ <b>Rejalashtirilgan reklama yuborildi!</b>\n"
            f"🎯 Manzil: <code>{target_mode}</code>\n"
            f"📤 Yuborildi: {sent}\n"
            f"❌ Xato: {failed}\n"
            f"📅 Vaqt: {sched.get('scheduled_time', '')}"
        )
        
    except Exception as e:
        logger.error(f"_execute_scheduled_broadcast xato: {e}")
        sched["status"] = "failed"
        sched["error"] = str(e)

# =====================================
# AD LIST TARGETS - YANGILANGAN
# =====================================
@bot.callback_query_handler(func=lambda c: c.data == "ad_list_targets")
@safe_callback_handler
def ad_list_targets(c):
    try:
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
        markup.add(InlineKeyboardButton("⬅️ Ortga", callback_data="ad_back"))
        
        safe_answer_callback_query(c.id)
        safe_edit_message_text("\n".join(lines), c.message.chat.id, c.message.message_id, reply_markup=markup)
    except Exception as e:
        logger.error(f"ad_list_targets xato: {e}")

# =====================================
# AD TARGET SELECTED - YANGILANGAN
# =====================================
@bot.callback_query_handler(func=lambda c: c.data.startswith("ad_target_"))
@safe_callback_handler
def ad_target_selected(c):
    try:
        if not is_admin(c.from_user.id):
            return
        
        target_mode = c.data.replace("ad_target_", "")
        chat_ids = _resolve_ad_chat_ids(target_mode)
        
        if not chat_ids:
            safe_answer_callback_query(c.id, "❌ Yuborish uchun manzil topilmadi")
            return
        
        safe_answer_callback_query(c.id)
        
        # Vaqt oralig'ini tanlash uchun tugmalar
        markup = InlineKeyboardMarkup(row_width=3)
        delays = [0, 1, 2, 3, 4, 5]
        row = []
        for d in delays:
            row.append(InlineKeyboardButton(f"{d}s", callback_data=f"ad_delay_{target_mode}_{d}"))
        markup.add(*row)
        markup.add(InlineKeyboardButton("⏰ Vaqt belgilash", callback_data=f"ad_sched_from_target_{target_mode}"))
        markup.add(InlineKeyboardButton("⬅️ Ortga", callback_data="ad_back"))
        
        safe_edit_message_text(
            f"📢 <b>Reklama kontenti</b>\n\n"
            f"🎯 Manzil: <code>{target_mode}</code>\n"
            f"👥 Qabul qiluvchilar: {len(chat_ids)} ta\n\n"
            f"Qabul qilinadi: ✉️ matn, 🖼 rasm, 🎥 video, 🎵 audio, 🎙 ovoz, 📄 fayl, 🔁 forward\n\n"
            f"⏰ Yuborish orasidagi pauzani tanlang yoki vaqt belgilang:",
            c.message.chat.id,
            c.message.message_id,
            reply_markup=markup
        )
        
        # Keyingi qadam uchun ma'lumotlarni saqlash
        config["_broadcast_data"] = {
            "target_mode": target_mode,
            "chat_ids": chat_ids,
            "total": len(chat_ids)
        }
        save_db()
        
    except Exception as e:
        logger.error(f"ad_target_selected xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("ad_sched_from_target_"))
@safe_callback_handler
def ad_sched_from_target(c):
    try:
        if not is_admin(c.from_user.id):
            return
        
        target_mode = c.data.replace("ad_sched_from_target_", "")
        broadcast_data = config.get("_broadcast_data", {})
        
        if broadcast_data.get("target_mode") != target_mode:
            safe_answer_callback_query(c.id, "❌ Ma'lumotlar eskirgan")
            return
        
        # Vaqt belgilash oynasiga o'tish
        markup = InlineKeyboardMarkup(row_width=2)
        now = datetime.now()
        for h in [1, 2, 3, 6, 12, 24]:
            future = now + timedelta(hours=h)
            time_str = future.strftime("%H:%M")
            markup.add(InlineKeyboardButton(f"{h} soat ({time_str})", callback_data=f"ad_sched_from_hour_{target_mode}_{h}"))
        
        markup.add(InlineKeyboardButton("✏️ O'zim vaqt kiritaman", callback_data=f"ad_sched_from_custom_{target_mode}"))
        markup.add(InlineKeyboardButton("⬅️ Ortga", callback_data=f"ad_target_{target_mode}"))
        
        safe_edit_message_text(
            f"⏰ <b>Vaqt belgilash</b>\n\n"
            f"🎯 Manzil: <code>{target_mode}</code>\n"
            f"👥 Qabul qiluvchilar: {broadcast_data.get('total', 0)} ta\n\n"
            f"Reklamani qancha vaqtdan keyin yuborish kerak?\n\n"
            f"📌 Hozirgi vaqt: {now.strftime('%H:%M')}",
            c.message.chat.id,
            c.message.message_id,
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"ad_sched_from_target xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("ad_sched_from_hour_"))
@safe_callback_handler
def ad_sched_from_hour(c):
    try:
        if not is_admin(c.from_user.id):
            return
        
        parts = c.data.split("_")
        target_mode = parts[4]
        hours = int(parts[5])
        
        broadcast_data = config.get("_broadcast_data", {})
        if broadcast_data.get("target_mode") != target_mode:
            safe_answer_callback_query(c.id, "❌ Ma'lumotlar eskirgan")
            return
        
        scheduled_time = datetime.now() + timedelta(hours=hours)
        _schedule_from_broadcast_data(c, target_mode, scheduled_time)
        
    except Exception as e:
        logger.error(f"ad_sched_from_hour xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("ad_sched_from_custom_"))
@safe_callback_handler
def ad_sched_from_custom(c):
    try:
        if not is_admin(c.from_user.id):
            return
        
        target_mode = c.data.replace("ad_sched_from_custom_", "")
        
        msg = safe_send_message(
            c.message.chat.id,
            f"✏️ Vaqtni kiriting (format: HH:MM)\n\n"
            f"🎯 Manzil: <code>{target_mode}</code>\n"
            f"📌 Masalan: 14:30 yoki 09:00\n\n"
            f"💡 Vaqt 24 soatlik formatda bo'lishi kerak.",
            reply_markup=back_menu()
        )
        if msg:
            bot.register_next_step_handler(msg, process_sched_custom_from_broadcast, target_mode)
            
    except Exception as e:
        logger.error(f"ad_sched_from_custom xato: {e}")

@safe_next_step
def process_sched_custom_from_broadcast(message, target_mode: str):
    try:
        if message.text == "⬅️ Ortga":
            safe_send_message(message.chat.id, "🔙 Orqaga", reply_markup=admin_menu())
            return
        
        time_str = message.text.strip()
        try:
            scheduled_time = datetime.strptime(time_str, "%H:%M")
            now = datetime.now()
            scheduled_time = scheduled_time.replace(year=now.year, month=now.month, day=now.day)
            
            if scheduled_time < now:
                scheduled_time += timedelta(days=1)
                
        except ValueError:
            safe_send_message(message.chat.id, "❌ Noto'g'ri format. HH:MM formatida kiriting (masalan: 14:30)", reply_markup=admin_menu())
            return
        
        _schedule_from_broadcast_data_from_msg(message, target_mode, scheduled_time)
        
    except Exception as e:
        logger.error(f"process_sched_custom_from_broadcast xato: {e}")

def _schedule_from_broadcast_data(c, target_mode: str, scheduled_time: datetime):
    try:
        broadcast_data = config.get("_broadcast_data", {})
        chat_ids = broadcast_data.get("chat_ids", [])
        total = broadcast_data.get("total", 0)
        
        # Kontent yuborish bosqichi
        msg = safe_send_message(
            c.message.chat.id,
            f"📢 <b>Reklama kontentini yuboring</b>\n\n"
            f"🎯 Manzil: <code>{target_mode}</code>\n"
            f"👥 Qabul qiluvchilar: {total} ta\n"
            f"⏰ Yuborish vaqti: {scheduled_time.strftime('%d.%m.%Y %H:%M')}\n"
            f"⏳ Qolgan vaqt: {_time_until(scheduled_time)}\n\n"
            f"📤 Endi reklama kontentini yuboring:\n"
            f"Qabul qilinadi: ✉️ matn, 🖼 rasm, 🎥 video, 🎵 audio, 🎙 ovoz, 📄 fayl, 🔁 forward\n\n"
            f"⚠️ <b>DIQQAT!</b> Xabar yuborilgach rejaga qo'shiladi.",
            reply_markup=back_menu()
        )
        if msg:
            bot.register_next_step_handler(msg, process_sched_content, target_mode, scheduled_time, chat_ids, total)
            
    except Exception as e:
        logger.error(f"_schedule_from_broadcast_data xato: {e}")

def _schedule_from_broadcast_data_from_msg(message, target_mode: str, scheduled_time: datetime):
    try:
        broadcast_data = config.get("_broadcast_data", {})
        chat_ids = broadcast_data.get("chat_ids", [])
        total = broadcast_data.get("total", 0)
        
        # Kontent yuborish bosqichi
        msg = safe_send_message(
            message.chat.id,
            f"📢 <b>Reklama kontentini yuboring</b>\n\n"
            f"🎯 Manzil: <code>{target_mode}</code>\n"
            f"👥 Qabul qiluvchilar: {total} ta\n"
            f"⏰ Yuborish vaqti: {scheduled_time.strftime('%d.%m.%Y %H:%M')}\n"
            f"⏳ Qolgan vaqt: {_time_until(scheduled_time)}\n\n"
            f"📤 Endi reklama kontentini yuboring:\n"
            f"Qabul qilinadi: ✉️ matn, 🖼 rasm, 🎥 video, 🎵 audio, 🎙 ovoz, 📄 fayl, 🔁 forward\n\n"
            f"⚠️ <b>DIQQAT!</b> Xabar yuborilgach rejaga qo'shiladi.",
            reply_markup=back_menu()
        )
        if msg:
            bot.register_next_step_handler(msg, process_sched_content, target_mode, scheduled_time, chat_ids, total)
            
    except Exception as e:
        logger.error(f"_schedule_from_broadcast_data_from_msg xato: {e}")

# =====================================
# AD DELAY - YANGILANGAN
# =====================================
@bot.callback_query_handler(func=lambda c: c.data.startswith("ad_delay_"))
@safe_callback_handler
def ad_delay_selected(c):
    try:
        if not is_admin(c.from_user.id):
            return
        
        parts = c.data.split("_")
        target_mode = parts[2]
        delay = int(parts[3])
        
        broadcast_data = config.get("_broadcast_data", {})
        if broadcast_data.get("target_mode") != target_mode:
            safe_answer_callback_query(c.id, "❌ Ma'lumotlar eskirgan, qaytadan boshlang")
            return
        
        safe_answer_callback_query(c.id, f"✅ Pauza: {delay} soniya")
        
        # Kontent yuborish bosqichi
        msg = safe_send_message(
            c.message.chat.id,
            f"📢 <b>Reklama kontentini yuboring</b>\n\n"
            f"🎯 Manzil: <code>{target_mode}</code>\n"
            f"⏱ Pauza: {delay} soniya\n"
            f"👥 Qabul qiluvchilar: {broadcast_data['total']} ta\n\n"
            f"Qabul qilinadi: ✉️ matn, 🖼 rasm, 🎥 video, 🎵 audio, 🎙 ovoz, 📄 fayl, 🔁 forward\n\n"
            f"⚠️ <b>DIQQAT!</b> Xabar yuborilgach darhol tarqatila boshlaydi.\n"
            f"❌ Bekor qilish uchun <b>⬅️ Ortga</b> tugmasini bosing.",
            reply_markup=back_menu()
        )
        if msg:
            bot.register_next_step_handler(msg, process_ad_content_direct, target_mode, delay)
            
    except Exception as e:
        logger.error(f"ad_delay_selected xato: {e}")

@safe_next_step
def process_ad_content_direct(message, target_mode: str, delay: int):
    try:
        if message.text == "⬅️ Ortga":
            safe_send_message(message.chat.id, "🔙 Bekor qilindi", reply_markup=admin_menu())
            config.pop("_broadcast_data", None)
            save_db()
            return
        
        chat_ids = _resolve_ad_chat_ids(target_mode)
        if not chat_ids:
            safe_send_message(message.chat.id, "❌ Yuborish uchun manzil topilmadi", reply_markup=admin_menu())
            return
        
        # Xabarni saqlash
        broadcast_msg = {
            "chat_id": message.chat.id,
            "message_id": message.message_id,
            "content_type": message.content_type,
            "text": message.text if message.content_type == "text" else None,
            "caption": message.caption if hasattr(message, "caption") else None,
            "photo": message.photo[-1].file_id if message.content_type == "photo" else None,
            "video": message.video.file_id if message.content_type == "video" else None,
            "audio": message.audio.file_id if message.content_type == "audio" else None,
            "voice": message.voice.file_id if message.content_type == "voice" else None,
            "document": message.document.file_id if message.content_type == "document" else None,
            "animation": message.animation.file_id if message.content_type == "animation" else None,
            "is_forward": message.forward_from is not None or message.forward_from_chat is not None,
        }
        
        safe_send_message(message.chat.id, f"✅ Yuborish boshlandi! ({len(chat_ids)} ta manzilga)")
        
        def _do_broadcast():
            sent, failed = 0, 0
            total = len(chat_ids)
            
            for i, cid in enumerate(chat_ids):
                try:
                    sent_msg = None
                    if broadcast_msg.get("is_forward"):
                        sent_msg = safe_call(
                            bot.forward_message,
                            cid,
                            broadcast_msg.get("chat_id"),
                            broadcast_msg.get("message_id")
                        )
                    else:
                        sent_msg = _send_broadcast_content(broadcast_msg, cid)
                    
                    if sent_msg:
                        sent += 1
                    else:
                        failed += 1
                        
                except Exception as e:
                    failed += 1
                    logger.error(f"Broadcast xato ({cid}): {e}")
                
                if delay > 0:
                    time.sleep(delay)
            
            safe_send_message(
                message.chat.id,
                f"✅ Reklama yuborish tugadi\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"📤 Yuborildi: <b>{sent}</b>\n"
                f"❌ Xato: <b>{failed}</b>\n"
                f"🎯 Manzil: <code>{target_mode}</code>\n"
                f"👥 Jami: {total} ta\n"
                f"⏱ Vaqt: {now_str()}",
                parse_mode="HTML",
                reply_markup=admin_menu()
            )
        
        config.pop("_broadcast_data", None)
        save_db()
        threading.Thread(target=_do_broadcast, daemon=True).start()
        
    except Exception as e:
        logger.error(f"process_ad_content_direct xato: {e}")
        safe_send_message(message.chat.id, f"❌ Xato: {e}", reply_markup=admin_menu())

# =====================================
# AD BACK - YANGILANGAN
# =====================================
@bot.callback_query_handler(func=lambda c: c.data == "ad_back")
@safe_callback_handler
def ad_back(c):
    try:
        if not is_admin(c.from_user.id):
            return
        safe_answer_callback_query(c.id)
        config.pop("_broadcast_data", None)
        config.pop("_sched_data", None)
        save_db()
        send_ad(c.message)
    except Exception as e:
        logger.error(f"ad_back xato: {e}")

# =====================================
# AD ADD TARGET - YANGILANGAN
# =====================================
@bot.callback_query_handler(func=lambda c: c.data == "ad_add_target")
@safe_callback_handler
def ad_add_target(c):
    try:
        if not is_admin(c.from_user.id):
            return
        
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton("📢 Forward qilish", callback_data="ad_add_target_forward"))
        markup.add(InlineKeyboardButton("✏️ ID kiritish", callback_data="ad_add_target_id"))
        markup.add(InlineKeyboardButton("⬅️ Ortga", callback_data="ad_back"))
        
        safe_edit_message_text(
            "➕ <b>Yangi kanal/guruh qo'shish</b>\n\n"
            "Bot bu kanal/guruhda admin bo'lishi shart!\n\n"
            "Qo'shish usulini tanlang:",
            c.message.chat.id,
            c.message.message_id,
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"ad_add_target xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "ad_add_target_forward")
@safe_callback_handler
def ad_add_target_forward(c):
    try:
        if not is_admin(c.from_user.id):
            return
        msg = safe_send_message(
            c.message.chat.id,
            "📢 Kanal/guruhdan istalgan xabarni <b>forward</b> qiling:\n\n"
            "💡 Bot bu kanal/guruhda admin bo'lishi shart!",
            reply_markup=back_menu()
        )
        if msg:
            bot.register_next_step_handler(msg, process_ad_add_target_forward)
    except Exception as e:
        logger.error(f"ad_add_target_forward xato: {e}")

@safe_next_step
def process_ad_add_target_forward(message):
    try:
        if message.text == "⬅️ Ortga":
            safe_send_message(message.chat.id, "🔙 Orqaga", reply_markup=admin_menu())
            return
        
        if not getattr(message, "forward_from_chat", None):
            safe_send_message(message.chat.id, "❌ Iltimos, kanal/guruhdan xabar forward qiling", reply_markup=admin_menu())
            return
        
        chat = message.forward_from_chat
        chat_type = "channel" if chat.type == "channel" else "group"
        targets = config.setdefault("broadcast_targets", [])
        
        if any(t["id"] == chat.id for t in targets):
            safe_send_message(message.chat.id, f"❌ Bu manzil allaqachon qo'shilgan: {chat.title}", reply_markup=admin_menu())
            return
        
        targets.append({"id": chat.id, "title": chat.title or str(chat.id), "type": chat_type})
        save_db()
        
        safe_send_message(
            message.chat.id,
            f"✅ Qo'shildi!\n"
            f"📢 {chat.title or chat.id}\n"
            f"📊 Turi: {chat_type}\n"
            f"🆔 ID: <code>{chat.id}</code>",
            reply_markup=admin_menu(),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"process_ad_add_target_forward xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "ad_add_target_id")
@safe_callback_handler
def ad_add_target_id(c):
    try:
        if not is_admin(c.from_user.id):
            return
        msg = safe_send_message(
            c.message.chat.id,
            "✏️ Kanal/guruh ID sini kiriting (masalan -1001234567890):\n\n"
            "💡 Kanal ID sini olish uchun botni kanalga admin qiling va /get_id buyrug'ini yuboring.",
            reply_markup=back_menu()
        )
        if msg:
            bot.register_next_step_handler(msg, process_ad_add_target_id)
    except Exception as e:
        logger.error(f"ad_add_target_id xato: {e}")

@safe_next_step
def process_ad_add_target_id(message):
    try:
        if message.text == "⬅️ Ortga":
            safe_send_message(message.chat.id, "🔙 Orqaga", reply_markup=admin_menu())
            return
        
        chat_id = safe_int(message.text.strip(), default=None)
        if not chat_id:
            safe_send_message(message.chat.id, "❌ Noto'g'ri ID. Iltimos, raqam kiriting.", reply_markup=admin_menu())
            return
        
        targets = config.setdefault("broadcast_targets", [])
        if any(t["id"] == chat_id for t in targets):
            safe_send_message(message.chat.id, f"❌ Bu ID allaqachon qo'shilgan: <code>{chat_id}</code>", reply_markup=admin_menu(), parse_mode="HTML")
            return
        
        # Chat ma'lumotlarini olish
        title = str(chat_id)
        chat_type = "group"
        try:
            chat = safe_get_chat(chat_id)
            if chat:
                title = chat.title or str(chat_id)
                chat_type = "channel" if chat.type == "channel" else "group"
        except Exception:
            pass
        
        targets.append({"id": chat_id, "title": title, "type": chat_type})
        save_db()
        
        safe_send_message(
            message.chat.id,
            f"✅ Qo'shildi!\n"
            f"📢 {title}\n"
            f"📊 Turi: {chat_type}\n"
            f"🆔 ID: <code>{chat_id}</code>",
            reply_markup=admin_menu(),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"process_ad_add_target_id xato: {e}")

# =====================================
# /get_id BUYRUG'I
# =====================================
@bot.message_handler(commands=["get_id"])
def get_chat_id(message):
    try:
        chat_id = message.chat.id
        chat_type = message.chat.type
        
        text = (
            f"📊 <b>Chat ma'lumotlari</b>\n\n"
            f"🆔 ID: <code>{chat_id}</code>\n"
            f"📊 Turi: {chat_type}\n"
            f"📝 Nomi: {message.chat.title or 'Shaxsiy chat'}"
        )
        
        if is_admin(message.from_user.id):
            text += f"\n\n💡 Bu ID ni reklama manzillari uchun ishlatishingiz mumkin."
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("➕ Manzilga qo'shish", callback_data=f"ad_add_this_{chat_id}"))
            safe_send_message(message.chat.id, text, reply_markup=markup)
        else:
            safe_send_message(message.chat.id, text)
            
    except Exception as e:
        logger.error(f"get_chat_id xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("ad_add_this_"))
@safe_callback_handler
def ad_add_this(c):
    try:
        if not is_admin(c.from_user.id):
            return
        chat_id = int(c.data.replace("ad_add_this_", ""))
        chat = safe_get_chat(chat_id)
        if not chat:
            safe_answer_callback_query(c.id, "❌ Chat topilmadi")
            return
        
        chat_type = "channel" if chat.type == "channel" else "group"
        targets = config.setdefault("broadcast_targets", [])
        
        if any(t["id"] == chat.id for t in targets):
            safe_answer_callback_query(c.id, "❌ Allaqachon qo'shilgan")
            return
        
        targets.append({"id": chat.id, "title": chat.title or str(chat.id), "type": chat_type})
        save_db()
        safe_answer_callback_query(c.id, f"✅ Qo'shildi: {chat.title}")
        
    except Exception as e:
        logger.error(f"ad_add_this xato: {e}")
# =====================================
# ADMIN PANEL - SWITCH TO USER MODE
# =====================================
@bot.message_handler(func=lambda m: m.text == "⬅️ Foydalanuvchi rejimi" and is_admin(m.from_user.id))
@admin_required
def switch_to_user_mode(message):
    try:
        safe_send_message(message.chat.id, "🔙 Foydalanuvchi rejimiga o'tdingiz", reply_markup=admin_as_user_menu())
    except Exception as e:
        logger.error(f"switch_to_user_mode xato: {e}")

# =====================================
# ADMIN PANEL - CHAT SETTINGS
# =====================================
@bot.message_handler(func=lambda m: m.text == "💬 Chat sozlamalari" and is_admin(m.from_user.id))
@admin_required
def admin_chat_settings(message):
    try:
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
    except Exception as e:
        logger.error(f"admin_chat_settings xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "chat_set_link")
@safe_callback_handler
def chat_set_link(c):
    try:
        if not is_admin(c.from_user.id):
            return
        msg = safe_send_message(c.message.chat.id, "🔗 Chat havolasini kiriting (masalan https://t.me/+AbCdEf yoki @username):")
        if msg:
            bot.register_next_step_handler(msg, process_chat_set_link)
    except Exception as e:
        logger.error(f"chat_set_link xato: {e}")

@safe_next_step
def process_chat_set_link(message):
    try:
        link = message.text.strip()
        if link.startswith("@"):
            link = f"https://t.me/{link[1:]}"
        config["chat_link"] = link
        save_db()
        safe_send_message(message.chat.id, "✅ Chat havolasi saqlandi", reply_markup=admin_menu())
    except Exception as e:
        logger.error(f"process_chat_set_link xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "chat_set_title")
@safe_callback_handler
def chat_set_title(c):
    try:
        if not is_admin(c.from_user.id):
            return
        msg = safe_send_message(c.message.chat.id, "📝 Yangi tugma nomini kiriting (masalan: 💬 Chatga qo'shilish):")
        if msg:
            bot.register_next_step_handler(msg, process_chat_set_title)
    except Exception as e:
        logger.error(f"chat_set_title xato: {e}")

@safe_next_step
def process_chat_set_title(message):
    try:
        config["chat_title"] = message.text.strip()
        save_db()
        safe_send_message(message.chat.id, "✅ Tugma nomi saqlandi", reply_markup=admin_menu())
    except Exception as e:
        logger.error(f"process_chat_set_title xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "chat_toggle")
@safe_callback_handler
def chat_toggle(c):
    try:
        if not is_admin(c.from_user.id):
            return
        config["chat_enabled"] = not config.get("chat_enabled", True)
        save_db()
        safe_answer_callback_query(c.id, "✅ Holat o'zgartirildi")
    except Exception as e:
        logger.error(f"chat_toggle xato: {e}")

# =====================================
# ADMIN PANEL - LOTTERY MANAGEMENT
# =====================================
@bot.message_handler(func=lambda m: m.text == "🎰 Lotareya boshqaruvi" and is_admin(m.from_user.id))
@admin_required
def admin_lottery_menu(message):
    try:
        active = lottery_data.get("active", [])
        history = lottery_data.get("history", [])
        
        text = (
            f"🎰 <b>Lotareya boshqaruvi</b>\n\n"
            f"🎯 Faol lotareyalar: {len(active)}\n"
            f"📊 Tugagan: {len(history)}\n"
            f"🎟 Jami chiptalar: {sum(l.get('total_sold', 0) for l in active + history)}\n"
        )
        
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton("➕ Yangi lotareya yaratish", callback_data="lottery_create"))
        if active:
            markup.add(InlineKeyboardButton("📋 Faol lotareyalar", callback_data="lottery_admin_list_active"))
        if history:
            markup.add(InlineKeyboardButton("📋 Tugagan lotareyalar", callback_data="lottery_admin_list_history"))
        
        safe_send_message(message.chat.id, text, reply_markup=markup)
    except Exception as e:
        logger.error(f"admin_lottery_menu xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "lottery_create")
@safe_callback_handler
def lottery_create_step1(c):
    try:
        if not is_admin(c.from_user.id):
            return
        msg = safe_send_message(c.message.chat.id, "📝 Lotareya nomini kiriting:")
        if msg:
            bot.register_next_step_handler(msg, lottery_create_step2)
    except Exception as e:
        logger.error(f"lottery_create_step1 xato: {e}")

@safe_next_step
def lottery_create_step2(message):
    try:
        name = message.text.strip()
        msg = safe_send_message(message.chat.id, "💰 Chipta narxini kiriting (so'm):")
        if msg:
            bot.register_next_step_handler(msg, lottery_create_step3, name)
    except Exception as e:
        logger.error(f"lottery_create_step2 xato: {e}")

@safe_next_step
def lottery_create_step3(message, name: str):
    try:
        price = safe_int(message.text, default=None)
        if price is None or price <= 0:
            safe_send_message(message.chat.id, "❌ Noto'g'ri summa", reply_markup=admin_menu())
            return
        msg = safe_send_message(message.chat.id, "🎟 Chiptalar sonini kiriting:")
        if msg:
            bot.register_next_step_handler(msg, lottery_create_step4, name, price)
    except Exception as e:
        logger.error(f"lottery_create_step3 xato: {e}")

@safe_next_step
def lottery_create_step4(message, name: str, price: int):
    try:
        quantity = safe_int(message.text, default=None)
        if quantity is None or quantity <= 0:
            safe_send_message(message.chat.id, "❌ Noto'g'ri son", reply_markup=admin_menu())
            return
        msg = safe_send_message(message.chat.id, "📊 Bir foydalanuvchi uchun limit (necha marta sotib olish mumkin, 0 = cheksiz):")
        if msg:
            bot.register_next_step_handler(msg, lottery_create_step5, name, price, quantity)
    except Exception as e:
        logger.error(f"lottery_create_step4 xato: {e}")

@safe_next_step
def lottery_create_step5(message, name: str, price: int, quantity: int):
    try:
        limit = safe_int(message.text, default=1)
        msg = safe_send_message(message.chat.id, "🏆 Yutuq summasini kiriting (so'm):")
        if msg:
            bot.register_next_step_handler(msg, lottery_create_step6, name, price, quantity, limit)
    except Exception as e:
        logger.error(f"lottery_create_step5 xato: {e}")

@safe_next_step
def lottery_create_step6(message, name: str, price: int, quantity: int, limit: int):
    try:
        prize = safe_int(message.text, default=None)
        if prize is None or prize <= 0:
            safe_send_message(message.chat.id, "❌ Noto'g'ri summa", reply_markup=admin_menu())
            return
        
        lottery = create_lottery(str(message.from_user.id), name, price, quantity, limit, prize)
        save_db()
        
        safe_send_message(
            message.chat.id,
            f"✅ Lotareya yaratildi!\n\n"
            f"🎰 {lottery['name']}\n"
            f"💰 Narx: {lottery['price']:,} so'm\n"
            f"🎟 Chiptalar: {lottery['quantity']} ta\n"
            f"🏆 Yutuq: {lottery['prize']:,} so'm\n"
            f"📊 ID: #{lottery['id']}",
            reply_markup=admin_menu()
        )
    except Exception as e:
        logger.error(f"lottery_create_step6 xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "lottery_admin_list_active")
@safe_callback_handler
def lottery_admin_list_active(c):
    try:
        if not is_admin(c.from_user.id):
            return
        active = lottery_data.get("active", [])
        if not active:
            safe_answer_callback_query(c.id, "❌ Faol lotareyalar yo'q")
            return
        
        markup = InlineKeyboardMarkup(row_width=1)
        for lottery in active:
            if lottery["status"] == "active":
                markup.add(
                    InlineKeyboardButton(
                        f"🎰 {lottery['name']} ({lottery['total_sold']}/{lottery['quantity']})",
                        callback_data=f"lottery_admin_view_{lottery['id']}"
                    )
                )
        
        safe_answer_callback_query(c.id)
        safe_send_message(c.message.chat.id, "📋 <b>Faol lotareyalar</b>", reply_markup=markup)
    except Exception as e:
        logger.error(f"lottery_admin_list_active xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "lottery_admin_list_history")
@safe_callback_handler
def lottery_admin_list_history(c):
    try:
        if not is_admin(c.from_user.id):
            return
        history = lottery_data.get("history", [])[-10:]
        if not history:
            safe_answer_callback_query(c.id, "❌ Tugagan lotareyalar yo'q")
            return
        
        markup = InlineKeyboardMarkup(row_width=1)
        for lottery in reversed(history):
            status = "✅" if lottery["status"] == "completed" else "❌"
            markup.add(
                InlineKeyboardButton(
                    f"{status} {lottery['name']} ({lottery['total_sold']} chipta)",
                    callback_data=f"lottery_admin_view_{lottery['id']}"
                )
            )
        
        safe_answer_callback_query(c.id)
        safe_send_message(c.message.chat.id, "📋 <b>Tugagan lotareyalar</b>", reply_markup=markup)
    except Exception as e:
        logger.error(f"lottery_admin_list_history xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("lottery_admin_view_"))
@safe_callback_handler
def lottery_admin_view(c):
    try:
        if not is_admin(c.from_user.id):
            return
        lottery_id = int(c.data.split("_")[-1])
        lottery = find_lottery(lottery_id)
        if not lottery:
            safe_answer_callback_query(c.id, "❌ Lotareya topilmadi")
            return
        
        text = (
            f"🎰 <b>{lottery['name']}</b> (ID: #{lottery['id']})\n\n"
            f"💰 Narx: {lottery['price']:,} so'm\n"
            f"🎟 Chiptalar: {lottery['total_sold']}/{lottery['quantity']}\n"
            f"🏆 Yutuq: {lottery['prize']:,} so'm\n"
            f"📅 Yaratilgan: {lottery['created_at']}\n"
            f"📊 Holat: {lottery['status']}\n"
        )
        
        if lottery["status"] == "active":
            text += f"\n🎟 Sotilmagan: {lottery['quantity'] - lottery['total_sold']} ta"
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(
                InlineKeyboardButton("🏆 G'oliblarni aniqlash", callback_data=f"lottery_draw_{lottery_id}"),
                InlineKeyboardButton("❌ Bekor qilish", callback_data=f"lottery_cancel_{lottery_id}"),
            )
            if lottery["tickets"]:
                markup.add(InlineKeyboardButton("📋 Chiptalar ro'yxati", callback_data=f"lottery_tickets_{lottery_id}"))
        elif lottery["status"] == "completed":
            text += f"\n📅 Tugagan: {lottery['draw_date']}"
            text += f"\n🏆 G'oliblar: {len(lottery.get('winners', []))} ta"
            markup = InlineKeyboardMarkup(row_width=1)
            if lottery.get("winners"):
                markup.add(InlineKeyboardButton("🏆 G'oliblar ro'yxati", callback_data=f"lottery_winners_{lottery_id}"))
        else:
            markup = InlineKeyboardMarkup(row_width=1)
        
        markup.add(InlineKeyboardButton("🔄 Yangilash", callback_data=f"lottery_admin_view_{lottery_id}"))
        markup.add(InlineKeyboardButton("⬅️ Ortga", callback_data="lottery_admin_list_active"))
        
        safe_answer_callback_query(c.id)
        safe_edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=markup)
    except Exception as e:
        logger.error(f"lottery_admin_view xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("lottery_draw_"))
@safe_callback_handler
def lottery_draw_step1(c):
    try:
        if not is_admin(c.from_user.id):
            return
        lottery_id = int(c.data.split("_")[-1])
        lottery = find_active_lottery(lottery_id)
        if not lottery:
            safe_answer_callback_query(c.id, "❌ Lotareya topilmadi")
            return
        
        if lottery["total_sold"] < 1:
            safe_answer_callback_query(c.id, "❌ Lotareyada hech kim qatnashmagan")
            return
        
        msg = safe_send_message(
            c.message.chat.id,
            f"🏆 <b>G'oliblarni aniqlash</b>\n\n"
            f"🎰 {lottery['name']}\n"
            f"🎟 Sotilgan: {lottery['total_sold']} ta\n"
            f"🏆 Yutuq: {lottery['prize']:,} so'm\n\n"
            f"📊 O'rin va foizlarni kiriting (masalan: 1:50,2:30,3:20)\n"
            f"⚠️ O'rinlar soni chiptalar sonidan oshmasligi kerak",
            reply_markup=back_menu()
        )
        if msg:
            bot.register_next_step_handler(msg, lottery_draw_step2, lottery_id)
    except Exception as e:
        logger.error(f"lottery_draw_step1 xato: {e}")

@safe_next_step
def lottery_draw_step2(message, lottery_id: int):
    try:
        if message.text == "⬅️ Ortga":
            safe_send_message(message.chat.id, "🔙 Orqaga", reply_markup=admin_menu())
            return
        
        prize_distribution = {}
        for part in message.text.strip().split(","):
            place, percentage = part.strip().split(":")
            prize_distribution[int(place)] = int(percentage)
        
        total_percentage = sum(prize_distribution.values())
        if total_percentage != 100:
            safe_send_message(message.chat.id, "❌ Foizlar yig'indisi 100 ga teng bo'lishi kerak!", reply_markup=admin_menu())
            return
        
        winners = draw_lottery(lottery_id, prize_distribution)
        if not winners:
            safe_send_message(message.chat.id, "❌ Xatolik yuz berdi", reply_markup=admin_menu())
            return
        
        text = f"🏆 <b>Lotareya natijalari</b>\n\n🎰 {find_lottery(lottery_id)['name']}\n\n"
        for winner in winners:
            text += f"🥇 {winner['place']}-o'rin: {winner['username']} — {winner['prize']:,} so'm\n"
        
        safe_send_message(message.chat.id, text, reply_markup=admin_menu())
    except Exception as e:
        safe_send_message(message.chat.id, f"❌ Xato: {e}\nFormat: 1:50,2:30,3:20", reply_markup=admin_menu())

@bot.callback_query_handler(func=lambda c: c.data.startswith("lottery_cancel_"))
@safe_callback_handler
def lottery_cancel(c):
    try:
        if not is_admin(c.from_user.id):
            return
        lottery_id = int(c.data.split("_")[-1])
        
        if cancel_lottery(lottery_id):
            safe_answer_callback_query(c.id, "✅ Lotareya bekor qilindi va pul qaytarildi")
            safe_edit_message_text("❌ Lotareya bekor qilindi", c.message.chat.id, c.message.message_id)
        else:
            safe_answer_callback_query(c.id, "❌ Xatolik yuz berdi")
    except Exception as e:
        logger.error(f"lottery_cancel xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("lottery_tickets_"))
@safe_callback_handler
def lottery_tickets(c):
    try:
        if not is_admin(c.from_user.id):
            return
        lottery_id = int(c.data.split("_")[-1])
        lottery = find_lottery(lottery_id)
        if not lottery:
            safe_answer_callback_query(c.id, "❌ Lotareya topilmadi")
            return
        
        tickets = lottery.get("tickets", [])
        if not tickets:
            safe_answer_callback_query(c.id, "❌ Chiptalar yo'q")
            return
        
        text = f"📋 <b>Chiptalar ro'yxati</b>\n\n🎰 {lottery['name']}\n\n"
        for i, ticket in enumerate(tickets[:50], 1):
            text += f"{i}. {ticket['username']} - Ticket #{ticket['ticket_number']}\n"
        
        if len(tickets) > 50:
            text += f"\n... va yana {len(tickets) - 50} ta chipta"
        
        safe_answer_callback_query(c.id)
        safe_send_message(c.message.chat.id, text)
    except Exception as e:
        logger.error(f"lottery_tickets xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("lottery_winners_"))
@safe_callback_handler
def lottery_winners(c):
    try:
        if not is_admin(c.from_user.id):
            return
        lottery_id = int(c.data.split("_")[-1])
        lottery = find_lottery(lottery_id)
        if not lottery:
            safe_answer_callback_query(c.id, "❌ Lotareya topilmadi")
            return
        
        winners = lottery.get("winners", [])
        if not winners:
            safe_answer_callback_query(c.id, "❌ G'oliblar yo'q")
            return
        
        text = f"🏆 <b>G'oliblar ro'yxati</b>\n\n🎰 {lottery['name']}\n\n"
        for winner in sorted(winners, key=lambda x: x["place"]):
            text += f"🥇 {winner['place']}-o'rin: {winner['username']} — {winner['prize']:,} so'm\n"
        
        safe_answer_callback_query(c.id)
        safe_send_message(c.message.chat.id, text)
    except Exception as e:
        logger.error(f"lottery_winners xato: {e}")

# =====================================
# OWNER PANEL
# =====================================
@bot.message_handler(func=lambda m: m.text == "👑 Owner panel" and is_owner(m.from_user.id))
@owner_required
def owner_panel(message):
    try:
        owner_id = config.get("owner_id")
        transfer_enabled = config.get("transfer_enabled", False)
        transfer_request = config.get("transfer_request")
        
        text = (
            f"👑 <b>Bot egasi paneli</b>\n\n"
            f"🔑 Hozirgi egasi: <code>{owner_id if owner_id else 'O\'rnatilmagan'}</code>\n"
            f"🔄 Botni o'tkazish: {'✅ Yoqilgan' if transfer_enabled else '❌ O\'chirilgan'}\n"
        )
        if transfer_request:
            text += f"\n📩 O'tkazish so'rovi:\n{transfer_request}"
        
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton("🔄 Botni o'tkazish", callback_data="owner_transfer"))
        markup.add(InlineKeyboardButton("🔒 O'tkazishni bloklash", callback_data="owner_transfer_lock"))
        markup.add(InlineKeyboardButton("🔓 O'tkazishni yoqish", callback_data="owner_transfer_unlock"))
        
        safe_send_message(message.chat.id, text, reply_markup=markup)
    except Exception as e:
        logger.error(f"owner_panel xato: {e}")

@bot.message_handler(func=lambda m: m.text == "🔄 Botni o'tkazish" and is_owner(m.from_user.id))
@owner_required
def transfer_bot(message):
    try:
        if not config.get("transfer_enabled", False):
            safe_send_message(message.chat.id, "❌ Botni o'tkazish hozircha bloklangan. Avval owner panelda yoqing.")
            return
        
        msg = safe_send_message(
            message.chat.id,
            "🔄 Botni o'tkazish\n\n"
            "⚠️ <b>DIQQAT!</b> Bu amal bot egasini o'zgartiradi.\n"
            "Yangi egasining Telegram ID sini kiriting (raqam):",
            reply_markup=back_menu()
        )
        if msg:
            bot.register_next_step_handler(msg, process_transfer_request)
    except Exception as e:
        logger.error(f"transfer_bot xato: {e}")

@safe_next_step
def process_transfer_request(message):
    try:
        if message.text == "⬅️ Ortga":
            safe_send_message(message.chat.id, "🔙 Orqaga", reply_markup=owner_menu())
            return
        
        if not message.text.strip().isdigit():
            safe_send_message(message.chat.id, "❌ ID raqam bo'lishi kerak!", reply_markup=owner_menu())
            return
        
        new_owner_id = message.text.strip()
        
        if new_owner_id == str(message.from_user.id):
            safe_send_message(message.chat.id, "❌ Siz o'zingizga o'tkaza olmaysiz!", reply_markup=owner_menu())
            return
        
        config["transfer_request"] = f"🔄 {safe_username(message.from_user)} dan {safe_username(new_owner_id)} ga o'tkazish so'rovi yuborildi.\nID: {new_owner_id}\nSana: {now_str()}"
        config["transfer_request_data"] = {
            "from": str(message.from_user.id),
            "to": new_owner_id,
            "date": now_str()
        }
        save_db()
        
        try:
            safe_send_message(
                int(new_owner_id),
                f"👑 Sizga bot egasi bo'lish taklifi yuborildi!\n"
                f"👤 Taklif qilgan: {safe_username(message.from_user)}\n"
                f"📅 Sana: {now_str()}\n\n"
                f"✅ Qabul qilish uchun /accept_ownership buyrug'ini yuboring."
            )
        except Exception as e:
            logger.error(f"Owner transfer xatolik: {e}")
        
        safe_send_message(
            message.chat.id,
            f"✅ O'tkazish so'rovi yuborildi!\n"
            f"👤 Yangi egasi: {safe_username(new_owner_id)}\n"
            f"📅 Sana: {now_str()}\n\n"
            f"⚠️ Yangi egasi /accept_ownership buyrug'ini yuborsa, siz egasi bo'lishni to'xtatasiz.",
            reply_markup=owner_menu()
        )
    except Exception as e:
        logger.error(f"process_transfer_request xato: {e}")

@bot.message_handler(commands=["accept_ownership"])
def accept_ownership(message):
    try:
        transfer_data = config.get("transfer_request_data")
        if not transfer_data:
            safe_send_message(message.chat.id, "❌ Hech qanday o'tkazish so'rovi mavjud emas.")
            return
        
        if str(message.from_user.id) != transfer_data.get("to"):
            safe_send_message(message.chat.id, "❌ Bu siz uchun so'rov emas.")
            return
        
        old_owner = transfer_data.get("from")
        new_owner = transfer_data.get("to")
        
        config["owner_id"] = new_owner
        config["transfer_request"] = None
        config["transfer_request_data"] = None
        
        if new_owner not in ADMINS:
            ADMINS[new_owner] = {
                "username": safe_username(message.from_user),
                "role": "superadmin",
                "added_date": now_str(),
            }
        
        save_db()
        
        safe_send_message(
            message.chat.id,
            f"✅ Siz botning yangi egasiga aylandingiz!\n"
            f"👑 Bot egasi: <code>{new_owner}</code>\n"
            f"📅 Sana: {now_str()}"
        )
        
        if old_owner:
            try:
                safe_send_message(
                    int(old_owner),
                    f"👑 Siz bot egasi bo'lishni to'xtatdingiz.\n"
                    f"✅ Yangi egasi: {safe_username(new_owner)}\n"
                    f"📅 Sana: {now_str()}"
                )
            except Exception:
                pass
        
        notify_admins(
            f"👑 <b>Bot egasi o'zgardi!</b>\n"
            f"👤 Yangi egasi: {safe_username(new_owner)}\n"
            f"📅 Sana: {now_str()}"
        )
    except Exception as e:
        logger.error(f"accept_ownership xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "owner_transfer")
@safe_callback_handler
def owner_transfer_callback(c):
    try:
        if not is_owner(c.from_user.id):
            safe_answer_callback_query(c.id, "❌ Ruxsat yo'q")
            return
        safe_answer_callback_query(c.id)
        transfer_bot(c.message)
    except Exception as e:
        logger.error(f"owner_transfer_callback xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "owner_transfer_lock")
@safe_callback_handler
def owner_transfer_lock(c):
    try:
        if not is_owner(c.from_user.id):
            safe_answer_callback_query(c.id, "❌ Ruxsat yo'q")
            return
        config["transfer_enabled"] = False
        save_db()
        safe_answer_callback_query(c.id, "✅ O'tkazish bloklandi")
    except Exception as e:
        logger.error(f"owner_transfer_lock xato: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "owner_transfer_unlock")
@safe_callback_handler
def owner_transfer_unlock(c):
    try:
        if not is_owner(c.from_user.id):
            safe_answer_callback_query(c.id, "❌ Ruxsat yo'q")
            return
        config["transfer_enabled"] = True
        save_db()
        safe_answer_callback_query(c.id, "✅ O'tkazish yoqildi")
    except Exception as e:
        logger.error(f"owner_transfer_unlock xato: {e}")

@bot.message_handler(func=lambda m: m.text == "👑 Bot egasi sozlamalari" and is_owner(m.from_user.id))
@owner_required
def owner_settings(message):
    try:
        owner_id = config.get("owner_id")
        current_owner = f"<code>{owner_id if owner_id else 'O\'rnatilmagan'}</code>"
        if owner_id:
            current_owner += f" ({safe_username(owner_id)})"
        
        text = (
            f"👑 <b>Bot egasi sozlamalari</b>\n\n"
            f"🔑 Hozirgi egasi: {current_owner}\n"
            f"🔄 O'tkazish holati: {'✅ Yoqilgan' if config.get('transfer_enabled', False) else '❌ O\'chirilgan'}\n"
            f"👥 Adminlar soni: {len(ADMINS)}\n"
            f"👤 Foydalanuvchilar: {len(users)}\n"
            f"📅 Sana: {now_str()}"
        )
        safe_send_message(message.chat.id, text, reply_markup=owner_menu())
    except Exception as e:
        logger.error(f"owner_settings xato: {e}")

# =====================================
# FALLBACK HANDLER
# =====================================
@bot.message_handler(func=lambda m: True, content_types=["text"])
def unknown(message):
    try:
        if is_group_chat(message.chat.type):
            return
        ensure_user(message)
        if user_blocked(str(message.from_user.id)):
            safe_send_message(message.chat.id, "❌ Siz bloklangansiz.")
            return
        safe_send_message(message.chat.id, "❌ Noto'g'ri buyruq. Menyudan tanlang.", reply_markup=_menu_for(message.from_user.id))
    except Exception as e:
        logger.error(f"unknown handler xato: {e}", exc_info=True)

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

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        json_str = request.get_data().decode('UTF-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return "OK", 200
    except Exception as e:
        logger.error(f"Webhook xato: {e}")
        return "Error", 500

def run_web():
    try:
        app.run(host="0.0.0.0", port=PORT)
    except Exception as e:
        logger.error(f"Web server xato: {e}")

def keep_alive():
    t = threading.Thread(target=run_web, daemon=True)
    t.start()

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
        config["bot_username"] = me.username
        save_db()
    except Exception as e:
        print(f"❌ Bot ma'lumotini olishda xato: {e}")
    print(f"👥 Foydalanuvchilar: {len(users)}")
    print(f"📦 Buyurtmalar: {len(orders)}")
    print(f"👨‍💻 Adminlar: {len(ADMINS)}")
    print(f"👑 Bot egasi: {config.get('owner_id', 'O\'rnatilmagan')}")
    print(f"🎰 Faol lotareyalar: {len(lottery_data.get('active', []))}")
    print("=" * 50)
    logger.info("Bot ishga tushdi")

    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)
            break
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
