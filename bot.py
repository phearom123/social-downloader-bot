import os
import traceback
from telebot import TeleBot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from config import (
    BOT_TOKEN, ADMIN_IDS, ADMIN_LOG_CHAT_ID, DOWNLOAD_DIR, DB_PATH,
    MAX_DOWNLOADS_PER_DAY, DEFAULT_FORCE_JOIN_ENABLED, DEFAULT_FORCE_JOIN_MODE,
    DEFAULT_REQUIRED_CHANNEL, DEFAULT_REQUIRED_GROUP,
    DEFAULT_JOIN_MESSAGE_EN, DEFAULT_JOIN_MESSAGE_KH, YTDLP_FORMAT, MAX_CAPTION_PREVIEW
)
from texts import t
from database import (
    get_conn, init_db, ensure_default_settings, get_setting, set_setting, upsert_user, set_user_language,
    get_user_language, mark_join_verified, add_download_log, count_user_downloads_today, get_stats,
    get_recent_downloads, get_recent_users, search_user, get_user_downloads
)
from downloader import download_media, detect_platform
from force_join import normalize_chat_ref, check_force_join, can_verify
from admin import admin_menu, force_join_menu

bot = TeleBot(BOT_TOKEN, parse_mode="HTML")
conn = get_conn(DB_PATH)
init_db(conn)
ensure_default_settings(conn, {
    "force_join_enabled": str(DEFAULT_FORCE_JOIN_ENABLED),
    "force_join_mode": DEFAULT_FORCE_JOIN_MODE,
    "required_channel": DEFAULT_REQUIRED_CHANNEL,
    "required_group": DEFAULT_REQUIRED_GROUP,
    "join_message_en": DEFAULT_JOIN_MESSAGE_EN,
    "join_message_kh": DEFAULT_JOIN_MESSAGE_KH,
})

USER_STATE = {}

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def admin_targets():
    if ADMIN_LOG_CHAT_ID:
        return [ADMIN_LOG_CHAT_ID]
    return ADMIN_IDS

def notify_admins(text: str):
    for chat_id in admin_targets():
        try:
            bot.send_message(chat_id, text)
        except Exception:
            pass

def get_lang(user_id: int) -> str:
    return get_user_language(conn, user_id, "en")

def set_lang(user_id: int, lang: str):
    set_user_language(conn, user_id, lang)

def main_menu(lang: str, user_id: int):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton(t(lang, "menu_download")), KeyboardButton(t(lang, "menu_how")))
    kb.row(KeyboardButton(t(lang, "menu_lang")), KeyboardButton(t(lang, "menu_stats")))
    if is_admin(user_id):
        kb.row(KeyboardButton(t(lang, "menu_admin")))
    return kb

def lang_menu():
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("English", callback_data="lang:en"),
        InlineKeyboardButton("ខ្មែរ", callback_data="lang:kh")
    )
    return kb

def force_join_buttons(lang: str):
    m = InlineKeyboardMarkup(row_width=1)
    req_channel = get_setting(conn, "required_channel", "") or ""
    req_group = get_setting(conn, "required_group", "") or ""
    if req_channel:
        m.add(InlineKeyboardButton(t(lang, "join_channel"), url=req_channel if req_channel.startswith("http") else f"https://t.me/{req_channel.lstrip('@')}"))
    if req_group:
        m.add(InlineKeyboardButton(t(lang, "join_group"), url=req_group if req_group.startswith("http") else f"https://t.me/{req_group.lstrip('@')}"))
    m.add(InlineKeyboardButton(t(lang, "recheck"), callback_data="force:recheck"))
    return m

def force_join_required(user_id: int):
    enabled = str(get_setting(conn, "force_join_enabled", "False")).lower() == "true"
    if not enabled:
        return False
    mode = get_setting(conn, "force_join_mode", "both")
    channel_ref = normalize_chat_ref(get_setting(conn, "required_channel", "") or "")
    group_ref = normalize_chat_ref(get_setting(conn, "required_group", "") or "")
    return not check_force_join(bot, user_id, mode, channel_ref, group_ref)

def send_force_join_prompt(chat_id: int, user_id: int):
    lang = get_lang(user_id)
    join_msg = get_setting(conn, f"join_message_{lang}", "") or t(lang, "force_join_title")
    bot.send_message(chat_id, f"🔒 <b>{t(lang, 'force_join_title')}</b>\n\n{join_msg}", reply_markup=force_join_buttons(lang))

def stats_text():
    s = get_stats(conn)
    return (
        f"<b>Bot Stats</b>\n"
        f"Total downloads: {s['total']}\n"
        f"Today downloads: {s['today']}\n"
        f"Videos only: {s['videos']}\n"
        f"Images only: {s['images']}\n"
        f"Captions only: {s['captions']}\n"
        f"Failed downloads: {s['failed']}\n"
        f"Users: {s['users']}"
    )

def user_usage_text(user_id: int, lang: str):
    used = count_user_downloads_today(conn, user_id)
    return f"<b>{t(lang, 'usage_title')}</b>\n{used}/{MAX_DOWNLOADS_PER_DAY}"

def admin_force_join_text():
    enabled = str(get_setting(conn, "force_join_enabled", "False")).lower() == "true"
    mode = get_setting(conn, "force_join_mode", "both")
    channel = get_setting(conn, "required_channel", "") or "-"
    group = get_setting(conn, "required_group", "") or "-"
    return (
        f"<b>Force Join Settings</b>\n"
        f"Status: {'ON' if enabled else 'OFF'}\n"
        f"Mode: {mode}\n"
        f"Channel: {channel}\n"
        f"Group: {group}"
    )

def format_download_row(r):
    return f"#{r['id']} | ID {r['telegram_id']} | {r['platform'] or '-'} | {r['media_type'] or '-'} | {r['status']}"

def format_user_row(r):
    return f"ID {r['telegram_id']} | @{r['username'] or '-'} | {r['full_name'] or '-'} | downloads={r['total_downloads'] or 0}"

@bot.message_handler(commands=["start"])
def start(message):
    upsert_user(conn, message.from_user)
    lang = get_lang(message.from_user.id)
    bot.send_message(message.chat.id, t(lang, "welcome"), reply_markup=main_menu(lang, message.from_user.id))

@bot.message_handler(commands=["admin"])
def admin_cmd(message):
    if not is_admin(message.from_user.id):
        return bot.reply_to(message, t(get_lang(message.from_user.id), "admin_only"))
    lang = get_lang(message.from_user.id)
    bot.send_message(message.chat.id, f"<b>{t(lang, 'admin_title')}</b>\n\n{stats_text()}", reply_markup=admin_menu(lang))

@bot.callback_query_handler(func=lambda c: c.data.startswith("lang:"))
def on_lang(call):
    lang = call.data.split(":")[1]
    set_lang(call.from_user.id, lang)
    bot.answer_callback_query(call.id, "OK")
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(call.message.chat.id, t(lang, "lang_set_en") if lang=="en" else t(lang, "lang_set_kh"), reply_markup=main_menu(lang, call.from_user.id))

@bot.callback_query_handler(func=lambda c: c.data == "force:recheck")
def recheck_join(call):
    upsert_user(conn, call.from_user)
    lang = get_lang(call.from_user.id)
    if force_join_required(call.from_user.id):
        bot.answer_callback_query(call.id, t(lang, "blocked"), show_alert=True)
        return
    mark_join_verified(conn, call.from_user.id)
    notify_admins(f"✅ Join verified | ID {call.from_user.id}")
    bot.answer_callback_query(call.id, "OK", show_alert=False)
    bot.send_message(call.message.chat.id, "✅ Verified.", reply_markup=main_menu(lang, call.from_user.id))

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin:"))
def on_admin_cb(call):
    if not is_admin(call.from_user.id):
        return bot.answer_callback_query(call.id, "Admin only", show_alert=True)
    lang = get_lang(call.from_user.id)
    enabled = str(get_setting(conn, "force_join_enabled", "False")).lower() == "true"
    mode = get_setting(conn, "force_join_mode", "both")
    data = call.data

    if data == "admin:home":
        bot.edit_message_text(f"<b>{t(lang, 'admin_title')}</b>\n\n{stats_text()}",
                              call.message.chat.id, call.message.message_id, reply_markup=admin_menu(lang))
    elif data == "admin:forcejoin":
        bot.edit_message_text(admin_force_join_text(), call.message.chat.id, call.message.message_id,
                              reply_markup=force_join_menu(lang, enabled, mode))
    elif data == "admin:toggle_forcejoin":
        set_setting(conn, "force_join_enabled", str(not enabled))
        enabled = not enabled
        bot.edit_message_text(admin_force_join_text(), call.message.chat.id, call.message.message_id,
                              reply_markup=force_join_menu(lang, enabled, mode))
    elif data == "admin:cycle_mode":
        modes = ["channel", "group", "both"]
        mode = modes[(modes.index(mode) + 1) % len(modes)] if mode in modes else "both"
        set_setting(conn, "force_join_mode", mode)
        bot.edit_message_text(admin_force_join_text(), call.message.chat.id, call.message.message_id,
                              reply_markup=force_join_menu(lang, enabled, mode))
    elif data == "admin:set_channel":
        USER_STATE[call.from_user.id] = {"action": "set_channel"}
        bot.send_message(call.message.chat.id, t(lang, "admin_send_channel"))
    elif data == "admin:set_group":
        USER_STATE[call.from_user.id] = {"action": "set_group"}
        bot.send_message(call.message.chat.id, t(lang, "admin_send_group"))
    elif data == "admin:set_join_msg":
        USER_STATE[call.from_user.id] = {"action": "set_join_msg", "lang": lang}
        bot.send_message(call.message.chat.id, t(lang, "admin_send_join_msg"))
    elif data == "admin:logs":
        rows = get_recent_downloads(conn, 15)
        txt = "<b>Latest Downloads</b>\n" + ("\n".join(format_download_row(r) for r in rows) if rows else "-")
        bot.edit_message_text(txt, call.message.chat.id, call.message.message_id,
                              reply_markup=InlineKeyboardMarkup().add(
                                  InlineKeyboardButton("🎬 Videos", callback_data="admin:logs_video"),
                                  InlineKeyboardButton("🖼 Images", callback_data="admin:logs_image"),
                                  InlineKeyboardButton(t(lang, "admin_back"), callback_data="admin:home")
                              ))
    elif data == "admin:logs_video":
        rows = get_recent_downloads(conn, 15, media_type="video")
        txt = "<b>Latest Videos</b>\n" + ("\n".join(format_download_row(r) for r in rows) if rows else "-")
        bot.edit_message_text(txt, call.message.chat.id, call.message.message_id,
                              reply_markup=InlineKeyboardMarkup().add(
                                  InlineKeyboardButton(t(lang, "admin_back"), callback_data="admin:logs")
                              ))
    elif data == "admin:logs_image":
        rows = get_recent_downloads(conn, 15, media_type="image")
        txt = "<b>Latest Images</b>\n" + ("\n".join(format_download_row(r) for r in rows) if rows else "-")
        bot.edit_message_text(txt, call.message.chat.id, call.message.message_id,
                              reply_markup=InlineKeyboardMarkup().add(
                                  InlineKeyboardButton(t(lang, "admin_back"), callback_data="admin:logs")
                              ))
    elif data == "admin:users":
        rows = get_recent_users(conn, 15)
        txt = "<b>Recent Users</b>\n" + ("\n".join(format_user_row(r) for r in rows) if rows else "-")
        bot.edit_message_text(txt, call.message.chat.id, call.message.message_id,
                              reply_markup=InlineKeyboardMarkup().add(
                                  InlineKeyboardButton(t(lang, "admin_back"), callback_data="admin:home")
                              ))
    elif data == "admin:search":
        USER_STATE[call.from_user.id] = {"action": "search_user"}
        bot.send_message(call.message.chat.id, t(lang, "admin_send_search"))
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: True, content_types=["text"])
def on_text(message):
    upsert_user(conn, message.from_user)
    user_id = message.from_user.id
    lang = get_lang(user_id)
    text = (message.text or "").strip()

    # pending admin actions
    state = USER_STATE.get(user_id)
    if state and is_admin(user_id):
        action = state.get("action")
        if action == "set_channel":
            set_setting(conn, "required_channel", text)
            USER_STATE.pop(user_id, None)
            return bot.send_message(message.chat.id, t(lang, "saved"))
        elif action == "set_group":
            set_setting(conn, "required_group", text)
            USER_STATE.pop(user_id, None)
            return bot.send_message(message.chat.id, t(lang, "saved"))
        elif action == "set_join_msg":
            set_setting(conn, f"join_message_{state.get('lang','en')}", text)
            USER_STATE.pop(user_id, None)
            return bot.send_message(message.chat.id, t(lang, "saved"))
        elif action == "search_user":
            USER_STATE.pop(user_id, None)
            rows = search_user(conn, text)
            if not rows:
                return bot.send_message(message.chat.id, t(lang, "not_found"))
            parts = []
            for r in rows[:10]:
                parts.append(format_user_row(r))
                dls = get_user_downloads(conn, r["telegram_id"], 5)
                if dls:
                    parts.extend([f"  - {format_download_row(d)}" for d in dls])
            return bot.send_message(message.chat.id, "<b>Search Results</b>\n" + "\n".join(parts))

    # menu actions
    if text in {t(lang, "menu_download"), "📥 Download", "📥 ទាញយក"}:
        return bot.send_message(message.chat.id, t(lang, "ask_link"))
    if text in {t(lang, "menu_how"), "📘 How to Use", "📘 របៀបប្រើ"}:
        return bot.send_message(message.chat.id, t(lang, "how_to"), reply_markup=main_menu(lang, user_id))
    if text in {t(lang, "menu_lang"), "🌐 Language", "🌐 ភាសា"}:
        return bot.send_message(message.chat.id, "Choose language / ជ្រើសរើសភាសា", reply_markup=lang_menu())
    if text in {t(lang, "menu_stats"), "📊 My Usage", "📊 ការប្រើប្រាស់របស់ខ្ញុំ"}:
        return bot.send_message(message.chat.id, user_usage_text(user_id, lang), reply_markup=main_menu(lang, user_id))
    if text in {t(lang, "menu_admin"), "🛠 Admin Dashboard", "🛠 ផ្ទាំងគ្រប់គ្រង"}:
        if not is_admin(user_id):
            return bot.send_message(message.chat.id, t(lang, "admin_only"))
        return bot.send_message(message.chat.id, f"<b>{t(lang, 'admin_title')}</b>\n\n{stats_text()}",
                                reply_markup=admin_menu(lang))

    # treat as URL
    if text.startswith("http://") or text.startswith("https://"):
        if force_join_required(user_id):
            send_force_join_prompt(message.chat.id, user_id)
            return
        used = count_user_downloads_today(conn, user_id)
        if used >= MAX_DOWNLOADS_PER_DAY:
            return bot.send_message(message.chat.id, t(lang, "limit_reached", limit=MAX_DOWNLOADS_PER_DAY))
        msg = bot.send_message(message.chat.id, t(lang, "checking"))
        user_dir = os.path.join(DOWNLOAD_DIR, str(user_id))
        os.makedirs(user_dir, exist_ok=True)
        try:
            result = download_media(text, user_dir, YTDLP_FORMAT)
            file_path = result.get("file_path")
            platform = result.get("platform") or detect_platform(text)
            media_type = result.get("media_type") or "video"
            caption = (result.get("caption") or "").strip()
            preview = caption[:MAX_CAPTION_PREVIEW]
            if file_path and os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    if media_type == "image":
                        bot.send_photo(message.chat.id, f, caption=(preview or t(lang, "download_done")))
                    else:
                        bot.send_video(message.chat.id, f, caption=(preview or t(lang, "download_done")))
                add_download_log(conn, {
                    "telegram_id": user_id,
                    "username": message.from_user.username,
                    "full_name": (message.from_user.first_name or "") + (" " + message.from_user.last_name if message.from_user.last_name else ""),
                    "source_url": text,
                    "platform": platform,
                    "media_type": media_type,
                    "caption": caption,
                    "local_file_name": result.get("local_file_name"),
                    "file_path": file_path,
                    "file_size": result.get("file_size"),
                    "status": "DONE",
                    "error_message": None,
                })
                notify_admins(f"📥 ID {user_id} | Platform {platform} | Status DONE")
                try:
                    bot.delete_message(message.chat.id, msg.message_id)
                except Exception:
                    pass
            else:
                raise RuntimeError("Downloaded file not found.")
        except Exception as e:
            add_download_log(conn, {
                "telegram_id": user_id,
                "username": message.from_user.username,
                "full_name": (message.from_user.first_name or "") + (" " + message.from_user.last_name if message.from_user.last_name else ""),
                "source_url": text,
                "platform": detect_platform(text),
                "media_type": "video",
                "caption": None,
                "local_file_name": None,
                "file_path": None,
                "file_size": None,
                "status": "FAILED",
                "error_message": str(e),
            })
            notify_admins(f"📥 ID {user_id} | Platform {detect_platform(text)} | Status FAILED")
            try:
                bot.edit_message_text(t(lang, "download_failed"), message.chat.id, msg.message_id)
            except Exception:
                bot.send_message(message.chat.id, t(lang, "download_failed"))
            print("ERROR:", e)
            traceback.print_exc()
        return

    bot.send_message(message.chat.id, t(lang, "welcome"), reply_markup=main_menu(lang, user_id))

if __name__ == "__main__":
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    print("Bot is running...")
    bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)
