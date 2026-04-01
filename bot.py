import threading
import queue
import random
import os
from flask import Flask
import telebot
from telebot import types
from database import Database
from downloader import SocialDownloader, extract_first_url
from config import BOT_TOKEN, ADMIN_IDS, DAILY_DOWNLOAD_LIMIT, MAX_SEND_SIZE_BYTES

# --- Initialization ---
app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
db = Database()
sd = SocialDownloader()
download_queue = queue.Queue()

# --- Translations ---
TEXTS = {
    'km': {
        'start': "👋 <b>សូមស្វាគមន៍មកកាន់ SaveKH!</b>\n\nផ្ញើតំណភ្ជាប់ដើម្បីទាញយកវីដេអូ ឬរូបភាព។\n📊 ប្រើប្រាស់ថ្ងៃនេះ: {used}/{limit}",
        'how': "📘 <b>របៀបប្រើ:</b>\n1. ចម្លង Link\n2. ផ្ញើមកកាន់ Bot\n3. រង់ចាំទាញយក",
        'usage': "📊 <b>ស្ថិតិប្រើប្រាស់:</b>\nទាញយកថ្ងៃនេះ: {used}/{limit}\nទាញយកសរុប: {total}",
        'downloading': "⏳ កំពុងដំណើរការ... សូមរង់ចាំ!",
        'failed': "❌ ការទាញយកបរាជ័យ!",
        'limit': "🚫 អ្នកអស់ចំនួនទាញយកសម្រាប់ថ្ងៃនេះហើយ!",
        'btns': ["📥 ទាញយក", "📘 របៀបប្រើ", "🌐 English", "📊 ការប្រើប្រាស់"]
    },
    'en': {
        'start': "👋 <b>Welcome to SaveKH!</b>\n\nSend a link to download media.\n📊 Used today: {used}/{limit}",
        'how': "📘 <b>How to use:</b>\n1. Copy Link\n2. Send to Bot\n3. Wait for download",
        'usage': "📊 <b>Usage Stats:</b>\nUsed today: {used}/{limit}\nTotal lifetime: {total}",
        'downloading': "⏳ Processing... please wait!",
        'failed': "❌ Download failed!",
        'limit': "🚫 Daily limit reached!",
        'btns': ["📥 Download", "📘 How to Use", "🌐 ភាសាខ្មែរ", "📊 Usage"]
    }
}

# --- Dummy Web Server for Render ---
@app.route('/')
def home(): return "SaveKH Bot is Online"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# --- Logic ---
def get_txt(uid, key, **kwargs):
    lang = db.get_user_lang(uid)
    return TEXTS[lang].get(key, "").format(**kwargs)

def main_markup(uid):
    lang = db.get_user_lang(uid)
    btns = TEXTS[lang]['btns']
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(*[types.KeyboardButton(b) for b in btns])
    return markup

def promo_markup():
    markup = types.InlineKeyboardMarkup()
    links = db.get_external_links()
    if links:
        selected = random.sample(list(links), min(len(links), 2))
        for l in selected:
            markup.add(types.InlineKeyboardButton(text=l['label'], url=l['url']))
    return markup

# --- Queue Worker ---
def worker():
    while True:
        task = download_queue.get()
        uid, url, mtype, msg_id = task
        try:
            res = sd.download(url, uid, mtype)
            with open(res['path'], 'rb') as f:
                if mtype == 'video': bot.send_video(uid, f, caption=res['title'], reply_markup=promo_markup())
                else: bot.send_audio(uid, f, caption=res['title'], reply_markup=promo_markup())
            db.add_download(uid, res['platform'], mtype, 'done')
            os.remove(res['path'])
        except Exception:
            bot.send_message(uid, get_txt(uid, 'failed'))
            db.add_download(uid, "Unknown", mtype, 'failed')
        bot.delete_message(uid, msg_id)
        download_queue.task_done()

# --- Handlers ---
@bot.message_handler(commands=['start'])
def start(m):
    db.upsert_user(m.from_user.id, m.from_user.username, m.from_user.first_name, m.from_user.last_name)
    used = db.count_user_downloads_today(m.from_user.id)
    bot.send_message(m.chat.id, get_txt(m.from_user.id, 'start', used=used, limit=DAILY_DOWNLOAD_LIMIT), reply_markup=main_markup(m.from_user.id))

@bot.message_handler(func=lambda m: True)
def handle_msg(m):
    uid = m.from_user.id
    if m.text in [TEXTS['km']['btns'][2], TEXTS['en']['btns'][2]]:
        new_lang = 'en' if db.get_user_lang(uid) == 'km' else 'km'
        db.set_user_lang(uid, new_lang)
        return bot.send_message(m.chat.id, "✅ Done", reply_markup=main_markup(uid))

    url = extract_first_url(m.text)
    if url and sd.is_supported(url):
        used = db.count_user_downloads_today(uid)
        if used >= DAILY_DOWNLOAD_LIMIT: return bot.send_message(m.chat.id, get_txt(uid, 'limit'))
        
        info = sd.get_info(url)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🎥 Video", callback_data=f"dl_video_{url}"),
                   types.InlineKeyboardButton("🎵 MP3", callback_data=f"dl_audio_{url}"))
        bot.send_message(m.chat.id, f"🎬 <b>{info['title']}</b>\nPlatform: {info['platform']}", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith('dl_'))
def handle_dl(c):
    _, mtype, url = c.data.split('_', 2)
    msg = bot.send_message(c.from_user.id, get_txt(c.from_user.id, 'downloading'))
    download_queue.put((c.from_user.id, url, mtype, msg.message_id))
    bot.answer_callback_query(c.id)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=worker, daemon=True).start()
    print("SaveKH Bot Started...")
    bot.infinity_polling()
