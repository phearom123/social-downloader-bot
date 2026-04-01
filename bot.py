import html
import os
import threading
import queue
import time
import schedule
from datetime import datetime
from typing import Optional

from flask import Flask
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Local modules (Ensure these are updated to match the new DB requirements)
from config import ADMIN_IDS, BOT_TOKEN, DAILY_DOWNLOAD_LIMIT, MAX_SEND_SIZE_BYTES
from database import Database
from downloader import SocialDownloader, DownloaderError, extract_first_url
from force_join import check_force_join

if not BOT_TOKEN or BOT_TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE":
    raise RuntimeError("Please set BOT_TOKEN in config.py")

# ==========================================
# SYSTEM INITIALIZATION
# ==========================================
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
db = Database()
downloader = SocialDownloader()

# Download Queue System to prevent freezing
download_queue = queue.Queue()

# Anti-spam tracker: {user_id: last_message_timestamp}
user_spam_cache = {}
SPAM_DELAY_SECONDS = 3

# ==========================================
# DUMMY WEB SERVER (FOR RENDER)
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Enterprise Bot is alive and running!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ==========================================
# FULL TRANSLATIONS (Khmer Default)
# ==========================================
LANG = {
    "km": {
        # User UI
        "welcome": "👋 <b>សូមស្វាគមន៍មកកាន់ SaveKH Bot!</b> 🤖✨\n\nទាញយកវីដេអូ និងរូបភាពពីគ្រប់បណ្ដាញសង្គមដោយលឿន ឥតគិតថ្លៃ និងគ្មាន Watermark!\n\n📊 <b>កំណត់ប្រចាំថ្ងៃ៖</b> {used}/{total} ដង\n\n👇 សូមជ្រើសរើសជម្រើសខាងក្រោម៖",
        "limit_reached": "🚫 <b>ដល់កំណត់ប្រចាំថ្ងៃហើយ! ({used}/{total})</b>\n\n🎁 <b>ទទួលបានការទាញយកបន្ថែម៖</b>\nណែនាំមិត្តភក្ដិ ១ នាក់ ទទួលបានការទាញយក +១ ជារៀងរហូត! ចែករំលែកតំណនេះ៖",
        "ref_link_msg": "<code>{link}</code>",
        "new_referral": "🎉 <b>អបអរសាទរ!</b>\nមានអ្នកចូលរួមតាមតំណរបស់អ្នក។ អ្នកទទួលបានការទាញយក +១ បន្ថែម!",
        "invalid_link": "❌ សូមផ្ញើតំណភ្ជាប់បណ្ដាញសង្គមដែលត្រឹមត្រូវ (TikTok, FB, IG, YouTube...)។",
        "unsupported_link": "⚠️ <b>មិនគាំទ្រ!</b>\nសុំទោស យើងមិនទាន់គាំទ្រគេហទំព័រនេះនៅឡើយទេ។",
        "fetching_preview": "🔍 កំពុងទាញយកព័ត៌មានលម្អិត... សូមរង់ចាំ!",
        "preview_text": "🎬 <b>ប្រភព៖</b> {platform}\n📁 <b>ប្រភេទ៖</b> {media_type}\n📝 <b>ចំណងជើង៖</b> {title}\n\n👇 តើអ្នកចង់ទាញយកមួយណា?",
        "queue_added": "⏳ បានដាក់ចូលក្នុងបញ្ជីរង់ចាំ! ទីតាំងរបស់អ្នកគឺ៖ <b>#{pos}</b>",
        "downloading": "⬇️ កំពុងដំណើរការទាញយក...",
        "large_file": "✅ ទាញយកជោគជ័យ តែឯកសារធំជាង {limit}MB។\nរក្សាទុកជា៖ <code>{local_file}</code>",
        "download_failed": "❌ ការទាញយកបរាជ័យ៖\n<code>{error}</code>",
        "spam_warning": "⚠️ សូមរង់ចាំ {sec} វិនាទី មុនពេលផ្ញើសារម្ដងទៀត!",
        "banned": "⛔️ គណនីរបស់អ្នកត្រូវបានបិទមិនឱ្យប្រើប្រាស់ Bot នេះទេ។",
        "how_to_use": "🆘 <b>របៀបប្រើប្រាស់៖</b>\n១. ចូលទៅកាន់វីដេអូដែលអ្នកចង់បាន\n២. ចុច 'Copy Link' (ចម្លងតំណភ្ជាប់)\n៣. ផ្ញើតំណភ្ជាប់នោះមកទីនេះ\n៤. ជ្រើសរើសប្រភេទ (វីដេអូ, រូបភាព, សំឡេង)",
        "my_usage": "📊 <b>ការប្រើប្រាស់របស់អ្នក៖</b>\n- ប្រើថ្ងៃនេះ៖ {used}/{total}\n- ទាញយកសរុប៖ {lifetime}\n- មិត្តដែលបានណែនាំ៖ {refs}",
        "lang_changed": "✅ ភាសាត្រូវបានប្ដូរទៅជាភាសាខ្មែរ។",
        
        # Buttons
        "btn_dl": "📥 ទាញយក",
        "btn_how": "📘 របៀបប្រើ",
        "btn_lang": "🌐 English",
        "btn_usage": "📊 ការប្រើប្រាស់",
        "btn_vid": "🎥 វីដេអូ",
        "btn_img": "🖼 រូបភាព",
        "btn_audio": "🎵 សំឡេង (Audio)",
        "btn_cap": "📝 អត្ថបទ (Caption)",
        "btn_cancel": "❌ បោះបង់",
        
        # Force Join
        "fj_msg": "🔒 សូមចូលរួមឆានែលរបស់យើងសិន ដើម្បីអាចប្រើប្រាស់ Bot នេះបាន!",
        "fj_verify": "✅ ខ្ញុំបានចូលរួមហើយ",
        "fj_verified": "✅ ផ្ទៀងផ្ទាត់ជោគជ័យ! អ្នកអាចប្រើ Bot បានហើយ។",
        "fj_missing": "❌ អ្នកមិនទាន់បានចូលរួមគ្រប់ឆានែលនៅឡើយទេ។",
        
        # Admin
        "admin_title": "🛠 <b>ផ្ទាំងគ្រប់គ្រង (Admin Dashboard)</b>",
        "admin_stats": "📊 ទិន្នន័យទូទៅ",
        "admin_fj": "🔐 Force Join",
        "admin_logs": "📥 ប្រវត្តិទាញយក",
        "admin_users": "👤 សកម្មភាពអ្នកប្រើ",
        "admin_search": "🔎 ស្វែងរក",
        "admin_bans": "🚫 គ្រប់គ្រងបម្រាម (Bans)"
    },
    "en": {
        "welcome": "👋 <b>Welcome to SaveKH Bot!</b> 🤖✨\n\nDownload videos & images fast, free, and without watermarks!\n\n📊 <b>Daily Limit:</b> {used}/{total}\n\n👇 Please choose an option:",
        "limit_reached": "🚫 <b>Daily Limit Reached! ({used}/{total})</b>\n\n🎁 <b>Get more:</b>\nRefer 1 friend to get +1 daily limit forever! Share link:",
        "ref_link_msg": "<code>{link}</code>",
        "new_referral": "🎉 <b>Congrats!</b>\nSomeone joined using your link. You earned +1 bonus limit!",
        "invalid_link": "❌ Please send a valid public social media link.",
        "unsupported_link": "⚠️ <b>Unsupported!</b>\nSorry, we do not support this platform yet.",
        "fetching_preview": "🔍 Fetching media details... please wait!",
        "preview_text": "🎬 <b>Platform:</b> {platform}\n📁 <b>Type:</b> {media_type}\n📝 <b>Title:</b> {title}\n\n👇 What do you want to download?",
        "queue_added": "⏳ Added to queue! Your position: <b>#{pos}</b>",
        "downloading": "⬇️ Processing your download...",
        "large_file": "✅ Downloaded, but file is larger than {limit}MB.\nSaved on server: <code>{local_file}</code>",
        "download_failed": "❌ Download failed:\n<code>{error}</code>",
        "spam_warning": "⚠️ Please wait {sec} seconds before sending another message!",
        "banned": "⛔️ Your account is banned from using this bot.",
        "how_to_use": "🆘 <b>How to use:</b>\n1. Find the video you want\n2. Click 'Copy Link'\n3. Paste the link here\n4. Choose Video, Image, or Audio",
        "my_usage": "📊 <b>Your Usage:</b>\n- Used today: {used}/{total}\n- Lifetime DLs: {lifetime}\n- Friends referred: {refs}",
        "lang_changed": "✅ Language changed to English.",
        
        "btn_dl": "📥 Download",
        "btn_how": "📘 How to Use",
        "btn_lang": "🌐 ភាសាខ្មែរ",
        "btn_usage": "📊 My Usage",
        "btn_vid": "🎥 Video",
        "btn_img": "🖼 Image",
        "btn_audio": "🎵 Audio Only",
        "btn_cap": "📝 Caption",
        "btn_cancel": "❌ Cancel",
        
        "fj_msg": "🔒 Please join our channels to use this bot!",
        "fj_verify": "✅ I have joined",
        "fj_verified": "✅ Verified! You can use the bot now.",
        "fj_missing": "❌ You haven't joined all required channels.",
        
        "admin_title": "🛠 <b>Admin Dashboard</b>",
        "admin_stats": "📊 Overall Stats",
        "admin_fj": "🔐 Force Join",
        "admin_logs": "📥 Download Logs",
        "admin_users": "👤 User Activity",
        "admin_search": "🔎 Search User",
        "admin_bans": "🚫 Manage Bans"
    }
}

def get_text(uid, key, **kwargs):
    lang_code = db.get_user_lang(uid)
    if lang_code not in LANG: lang_code = "km"
    return LANG[lang_code].get(key, LANG["km"][key]).format(**kwargs)

# ==========================================
# UI BUILDERS
# ==========================================
def build_main_menu(uid):
    lang = db.get_user_lang(uid)
    toggle = "en" if lang == "km" else "km"
    markup = InlineKeyboardMarkup(row_width=2)
    markup.row(
        InlineKeyboardButton(get_text(uid, "btn_how"), callback_data="menu_how"),
        InlineKeyboardButton(get_text(uid, "btn_usage"), callback_data="menu_usage")
    )
    markup.row(InlineKeyboardButton(get_text(uid, "btn_lang"), callback_data=f"setlang_{toggle}"))
    return markup

def build_preview_menu(uid, url, platform):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.row(
        InlineKeyboardButton(get_text(uid, "btn_vid"), callback_data=f"dl_vid_{url}"),
        InlineKeyboardButton(get_text(uid, "btn_audio"), callback_data=f"dl_aud_{url}")
    )
    markup.row(
        InlineKeyboardButton(get_text(uid, "btn_img"), callback_data=f"dl_img_{url}"),
        InlineKeyboardButton(get_text(uid, "btn_cap"), callback_data=f"dl_cap_{url}")
    )
    markup.row(InlineKeyboardButton(get_text(uid, "btn_cancel"), callback_data="dl_cancel"))
    return markup

def build_admin_dashboard(uid):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.row(InlineKeyboardButton(get_text(uid, "admin_stats"), callback_data="ad_stats"),
               InlineKeyboardButton(get_text(uid, "admin_fj"), callback_data="ad_fj"))
    markup.row(InlineKeyboardButton(get_text(uid, "admin_logs"), callback_data="ad_logs"),
               InlineKeyboardButton(get_text(uid, "admin_users"), callback_data="ad_users"))
    markup.row(InlineKeyboardButton(get_text(uid, "admin_search"), callback_data="ad_search"),
               InlineKeyboardButton(get_text(uid, "admin_bans"), callback_data="ad_bans"))
    return markup

# ==========================================
# BACKGROUND WORKERS & SCHEDULERS
# ==========================================
def process_download_queue():
    """Worker thread that processes downloads one by one to prevent freezing"""
    while True:
        task = download_queue.get()
        user_id, url, format_type, message_id, chat_id = task
        
        try:
            bot.edit_message_text(get_text(user_id, "downloading"), chat_id, message_id)
            
            # Execute download (Pass format_type to your downloader so it knows to grab video or audio)
            result = downloader.download(url, user_id, format=format_type)
            
            # Save to database
            dl_id = db.add_download(
                telegram_id=user_id, username="", full_name="", source_url=url,
                platform=result["platform"], media_type=format_type, caption_text=result["caption"],
                local_file_name=result["local_file_name"], file_path=result["file_path"],
                file_size=result["file_size"], status="done"
            )

            send_text = f"<b>{html.escape(result['platform'])}</b>\nID: <code>{dl_id}</code>\n\n{html.escape(result['caption'][:500])}"

            # Auto-compress/Warning logic
            if result["file_size"] > MAX_SEND_SIZE_BYTES:
                bot.send_message(chat_id, get_text(user_id, "large_file", limit=MAX_SEND_SIZE_BYTES/1024/1024, local_file=result['local_file_name']))
            else:
                with open(result["file_path"], "rb") as f:
                    if format_type == "video": bot.send_video(chat_id, f, caption=send_text)
                    elif format_type == "audio": bot.send_audio(chat_id, f, caption=send_text)
                    else: bot.send_photo(chat_id, f, caption=send_text)

            # Admin Notification
            if db.get_setting("announce_downloads", "1") == "1":
                bot.send_message(ADMIN_IDS[0], f"📥 ID {user_id} | Platform {result['platform']} | Status DONE")
                
            bot.delete_message(chat_id, message_id)
            
        except Exception as e:
            db.add_download(telegram_id=user_id, source_url=url, platform="Unknown", status="failed", error_text=str(e))
            bot.edit_message_text(get_text(user_id, "download_failed", error=str(e)), chat_id, message_id)
            if db.get_setting("announce_downloads", "1") == "1":
                bot.send_message(ADMIN_IDS[0], f"📥 ID {user_id} | Status FAILED | Err: {str(e)[:50]}")
                
        finally:
            download_queue.task_done()

def daily_maintenance():
    """Runs once a day to send summaries and clean files"""
    # 1. Send Admin Summary
    today_stats = db.get_today_stats() # Assumes this returns dict of counts
    summary = f"📈 <b>Daily Summary</b>\nTotal DLs: {today_stats['total']}\nFailed: {today_stats['failed']}\nNew Users: {today_stats['new_users']}"
    for admin in ADMIN_IDS:
        try: bot.send_message(admin, summary)
        except: pass
        
    # 2. Cleanup files older than 30 days
    db.delete_old_files(days=30) 

def schedule_loop():
    schedule.every().day.at("23:59").do(daily_maintenance)
    while True:
        schedule.run_pending()
        time.sleep(60)

# ==========================================
# MIDDLEWARE & HELPERS
# ==========================================
def check_spam(user_id):
    now = time.time()
    last = user_spam_cache.get(user_id, 0)
    if now - last < SPAM_DELAY_SECONDS:
        return False
    user_spam_cache[user_id] = now
    return True

# ==========================================
# COMMAND HANDLERS
# ==========================================
@bot.message_handler(commands=["start"])
def start_cmd(message):
    uid = message.from_user.id
    if db.is_banned(uid): return bot.reply_to(message, get_text(uid, "banned"))
    
    # Handle Referrals
    if len(message.text.split()) > 1:
        payload = message.text.split()[1]
        if payload.startswith("ref_"):
            try:
                referrer_id = int(payload.split("_")[1])
                if referrer_id != uid and db.count_user_downloads_today(uid) == 0:
                    db.add_bonus_download(referrer_id, 1)
                    bot.send_message(referrer_id, get_text(referrer_id, "new_referral"))
            except ValueError: pass

    db.upsert_user(uid, message.from_user.username, message.from_user.first_name, message.from_user.last_name)
    
    used = db.count_user_downloads_today(uid)
    total = DAILY_DOWNLOAD_LIMIT + db.get_bonus_downloads(uid)
    
    bot.reply_to(message, get_text(uid, "welcome", used=used, total=total), reply_markup=build_main_menu(uid))

@bot.message_handler(commands=["admin"])
def admin_cmd(message):
    if not is_admin(message.from_user.id, ADMIN_IDS): return
    bot.reply_to(message, get_text(message.from_user.id, "admin_title"), reply_markup=build_admin_dashboard(message.from_user.id))

# ==========================================
# MAIN LINK HANDLER
# ==========================================
@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_link(message):
    uid = message.from_user.id
    if db.is_banned(uid): return
    
    if not check_spam(uid):
        return bot.reply_to(message, get_text(uid, "spam_warning", sec=SPAM_DELAY_SECONDS))

    url = extract_first_url(message.text)
    if not url: return 

    # Supported Platform Check
    if not downloader.is_supported(url):
        return bot.reply_to(message, get_text(uid, "unsupported_link"))

    # Force Join Check
    ok, missing = check_force_join(bot, db, uid)
    if not ok:
        msg = db.get_setting("force_join_message", get_text(uid, "fj_msg"))
        # Using build_force_join_menu from your previous code
        return bot.reply_to(message, msg) # Add reply_markup=build_force_join_menu(db)

    # Limit Check
    used = db.count_user_downloads_today(uid)
    total = DAILY_DOWNLOAD_LIMIT + db.get_bonus_downloads(uid)
    if used >= total:
        ref_link = f"https://t.me/{bot.get_me().username}?start=ref_{uid}"
        return bot.reply_to(message, f"{get_text(uid, 'limit_reached', used=used, total=total)}\n\n{get_text(uid, 'ref_link_msg', link=ref_link)}")

    # Fetch Preview
    wait_msg = bot.reply_to(message, get_text(uid, "fetching_preview"))
    try:
        # Assumes downloader.get_info() extracts metadata quickly without downloading
        info = downloader.get_info(url) 
        preview = get_text(uid, "preview_text", platform=info['platform'], media_type="Video/Audio", title=html.escape(info['title'][:50]))
        bot.edit_message_text(preview, message.chat.id, wait_msg.message_id, reply_markup=build_preview_menu(uid, url, info['platform']))
    except Exception as e:
        bot.edit_message_text(get_text(uid, "download_failed", error=str(e)), message.chat.id, wait_msg.message_id)

# ==========================================
# CALLBACK HANDLERS
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("dl_"))
def process_download_choice(call):
    uid = call.from_user.id
    action = call.data.split("_")[1]
    
    if action == "cancel":
        return bot.delete_message(call.message.chat.id, call.message.message_id)
        
    url = call.data.replace(f"dl_{action}_", "")
    format_type = "video" if action == "vid" else "audio" if action == "aud" else "image"
    
    # Queue the task
    pos = download_queue.qsize() + 1
    bot.edit_message_text(get_text(uid, "queue_added", pos=pos), call.message.chat.id, call.message.message_id)
    
    download_queue.put((uid, url, format_type, call.message.message_id, call.message.chat.id))

@bot.callback_query_handler(func=lambda call: call.data.startswith("menu_") or call.data.startswith("setlang_"))
def user_menus(call):
    uid = call.from_user.id
    if call.data.startswith("setlang_"):
        new_lang = call.data.split("_")[1]
        db.set_user_lang(uid, new_lang)
        bot.answer_callback_query(call.id, get_text(uid, "lang_changed"))
        # Refresh menu
        used = db.count_user_downloads_today(uid)
        total = DAILY_DOWNLOAD_LIMIT + db.get_bonus_downloads(uid)
        bot.edit_message_text(get_text(uid, "welcome", used=used, total=total), call.message.chat.id, call.message.message_id, reply_markup=build_main_menu(uid))
        
    elif call.data == "menu_how":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, get_text(uid, "how_to_use"))
        
    elif call.data == "menu_usage":
        bot.answer_callback_query(call.id)
        used = db.count_user_downloads_today(uid)
        total = DAILY_DOWNLOAD_LIMIT + db.get_bonus_downloads(uid)
        lifetime = db.get_lifetime_downloads(uid)
        refs = db.get_bonus_downloads(uid) # assuming 1 ref = 1 bonus
        bot.send_message(call.message.chat.id, get_text(uid, "my_usage", used=used, total=total, lifetime=lifetime, refs=refs))

# ==========================================
# START APPLICATION
# ==========================================
if __name__ == "__main__":
    print("Starting Background Workers...")
    
    # Start Web Server (For Render)
    threading.Thread(target=run_web_server, daemon=True).start()
    
    # Start Queue Worker
    threading.Thread(target=process_download_queue, daemon=True).start()
    
    # Start Maintenance Scheduler
    threading.Thread(target=schedule_loop, daemon=True).start()
    
    print("Bot is running with full Queue, Previews, and Admin Systems...")
    bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)
