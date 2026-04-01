# placeholder
import os
import uuid
import queue
import threading
import traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import (
    BOT_TOKEN,
    ADMIN_IDS,
    ADMIN_LOG_CHAT_ID,
    DB_PATH,
    DOWNLOAD_DIR,
    BASE_DAILY_LIMIT,
    REFERRAL_BONUS_PER_SUCCESS,
    DEFAULT_FORCE_JOIN_ENABLED,
    DEFAULT_FORCE_JOIN_MODE,
    DEFAULT_REQUIRED_CHANNEL,
    DEFAULT_REQUIRED_GROUP,
    DEFAULT_JOIN_MESSAGE_KH,
    DEFAULT_JOIN_MESSAGE_EN,
    MIN_SECONDS_BETWEEN_USER_REQUESTS,
    MAX_PENDING_PER_USER,
    RANDOM_EXTRA_BUTTONS_COUNT,
)
from texts import t
from database import (
    get_conn,
    init_db,
    ensure_default_settings,
    get_setting,
    set_setting,
    upsert_user,
    set_user_language,
    get_user_language,
    mark_join_verified,
    add_download_log,
    count_user_success_today,
    count_pending_for_user,
    get_recent_downloads,
    get_recent_users,
    search_users,
    get_user_downloads,
    stats,
    top_platforms,
    top_users,
    is_user_banned,
    set_user_ban,
    add_promo_button,
    clear_promo_buttons,
    list_promo_buttons,
    create_referral,
    mark_referral_success,
    get_referral_count,
    get_daily_limit,
    update_last_request,
    get_last_request,
)
from force_join import normalize_chat_ref, check_force_join
from downloader import ytdlp_extract, normalize_info, detect_platform, download
from keyboards import (
    main_menu,
    language_menu,
    force_join_buttons,
    preview_menu,
    quality_menu,
    admin_menu,
    force_join_admin_menu,
    links_admin_menu,
    buttons_admin_menu,
    ban_admin_menu,
)
from utils import (
    is_valid_url,
    supported_domain,
    pick_random_buttons,
    compress_video_ffmpeg,
    should_compress,
)
from scheduler_jobs import start_scheduler

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
conn = get_conn(DB_PATH)
init_db(conn)
ensure_default_settings(
    conn,
    {
        "force_join_enabled": str(DEFAULT_FORCE_JOIN_ENABLED),
        "force_join_mode": DEFAULT_FORCE_JOIN_MODE,
        "required_channel": DEFAULT_REQUIRED_CHANNEL,
        "required_group": DEFAULT_REQUIRED_GROUP,
        "join_message_kh": DEFAULT_JOIN_MESSAGE_KH,
        "join_message_en": DEFAULT_JOIN_MESSAGE_EN,
    },
)

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

PREVIEWS = {}
USER_STATE = {}
JOB_QUEUE = queue.Queue()


def is_admin(user_id):
    return user_id in ADMIN_IDS


def admin_targets():
    return [ADMIN_LOG_CHAT_ID] if ADMIN_LOG_CHAT_ID else ADMIN_IDS


def notify_admins(text):
    for chat_id in admin_targets():
        try:
            bot.send_message(chat_id, text)
        except Exception:
            pass


def get_lang(user_id):
    return get_user_language(conn, user_id, "kh")


def set_lang(user_id, lang):
    set_user_language(conn, user_id, lang)


def user_limit(user_id):
    return get_daily_limit(conn, user_id, BASE_DAILY_LIMIT, REFERRAL_BONUS_PER_SUCCESS)


def user_usage_text(user_id, lang):
    used = count_user_success_today(conn, user_id)
    limit = user_limit(user_id)
    refs = get_referral_count(conn, user_id)
    return f"<b>{t(lang, 'usage_today')}</b>\n{used}/{limit}\n{t(lang, 'my_referrals')}: {refs}"


def stats_text():
    s = stats(conn)
    lines = [
        f"<b>{t('kh', 'bot_stats')}</b>",
        f"Total downloads: {s['total']}",
        f"Today downloads: {s['today']}",
        f"Videos only: {s['videos']}",
        f"Images only: {s['images']}",
        f"Captions only: {s['captions']}",
        f"Audios only: {s['audios']}",
        f"Failed downloads: {s['failed']}",
        f"Total users: {s['users']}",
        f"New users today: {s['new_users_today']}",
        "",
        f"<b>{t('kh', 'top_platforms')}</b>",
    ]
    tp = top_platforms(conn, 5)
    lines += [f"- {r['platform']}: {r['c']}" for r in tp] or ["- No data"]
    lines += ["", f"<b>{t('kh', 'top_users')}</b>"]
    tu = top_users(conn, 5)
    lines += [f"- ID {r['telegram_id']} | @{r['username'] or '-'} | {r['total_downloads']}" for r in tu] or ["- No data"]
    return "\n".join(lines)


def format_download_row(r):
    return f"#{r['id']} | ID {r['telegram_id']} | {r['platform'] or '-'} | {r['media_type'] or '-'} | {r['status']}"


def format_user_row(r):
    return f"ID {r['telegram_id']} | @{r['username'] or '-'} | {r['full_name'] or '-'} | total={r['total_downloads'] or 0}"


def normalize_public_link_for_button(value):
    if not value:
        return ""
    value = value.strip()
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if value.startswith("@"):
        return f"https://t.me/{value.lstrip('@')}"
    return value


def force_join_required(user_id):
    enabled = str(get_setting(conn, "force_join_enabled", "False")).lower() == "true"
    if not enabled:
        return False

    mode = get_setting(conn, "force_join_mode", "both")
    channel_ref = normalize_chat_ref(get_setting(conn, "required_channel", "") or "")
    group_ref = normalize_chat_ref(get_setting(conn, "required_group", "") or "")
    return not check_force_join(bot, user_id, mode, channel_ref, group_ref)


def send_force_join_prompt(chat_id, user_id):
    lang = get_lang(user_id)
    ch = normalize_public_link_for_button(get_setting(conn, "required_channel", "") or "")
    gr = normalize_public_link_for_button(get_setting(conn, "required_group", "") or "")
    join_msg = get_setting(conn, f"join_message_{lang}", "") or t(lang, "force_join_title")
    bot.send_message(
        chat_id,
        f"<b>{t(lang, 'force_join_title')}</b>\n\n{join_msg}",
        reply_markup=force_join_buttons(lang, ch, gr),
    )


def get_referral_link(user_id):
    me = bot.get_me()
    return f"https://t.me/{me.username}?start=ref_{user_id}"


def attach_random_promo_buttons(base_markup=None):
    rows = list_promo_buttons(conn)
    picked = pick_random_buttons(rows, RANDOM_EXTRA_BUTTONS_COUNT)
    markup = base_markup or InlineKeyboardMarkup()
    for r in picked:
        markup.add(InlineKeyboardButton(r["title"], url=r["url"]))
    return markup


def extract_referral(start_payload):
    if start_payload and start_payload.startswith("ref_"):
        ref_id = start_payload[4:]
        if ref_id.isdigit():
            return int(ref_id)
    return None


def anti_spam_block(user_id):
    last = get_last_request(conn, user_id)
    if not last:
        return False
    try:
        last_dt = datetime.fromisoformat(last)
        return (datetime.utcnow() - last_dt).total_seconds() < MIN_SECONDS_BETWEEN_USER_REQUESTS
    except Exception:
        return False


def enqueue_job(job):
    pos = JOB_QUEUE.qsize() + 1
    job["queue_position"] = pos

    add_download_log(
        conn,
        {
            "telegram_id": job["user_id"],
            "username": job["username"],
            "full_name": job["full_name"],
            "source_url": job["url"],
            "platform": detect_platform(job["url"]),
            "media_type": job["mode"],
            "title": None,
            "caption": None,
            "local_file_name": None,
            "file_path": None,
            "file_size": None,
            "status": "QUEUED",
            "error_message": None,
            "quality": job.get("quality", "high"),
            "queue_position": pos,
        },
    )

    JOB_QUEUE.put(job)
    return pos


def worker():
    while True:
        job = JOB_QUEUE.get()
        try:
            process_job(job)
        except Exception:
            traceback.print_exc()
        finally:
            JOB_QUEUE.task_done()


def process_job(job):
    user_id = job["user_id"]
    chat_id = job["chat_id"]
    lang = get_lang(user_id)
    url = job["url"]
    mode = job["mode"]
    quality = job.get("quality", "high")
    user_dir = os.path.join(DOWNLOAD_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    try:
        bot.send_message(chat_id, t(lang, "job_started"))

        if mode == "caption":
            info = ytdlp_extract(url)
            norm = normalize_info(info)
            caption = (norm.get("caption") or "").strip()

            bot.send_message(
                chat_id,
                f"<b>{t(lang, 'caption_only')}</b>\n\n{caption or '-'}",
                reply_markup=attach_random_promo_buttons(),
            )

            add_download_log(
                conn,
                {
                    "telegram_id": user_id,
                    "username": job["username"],
                    "full_name": job["full_name"],
                    "source_url": url,
                    "platform": detect_platform(url),
                    "media_type": "caption",
                    "title": norm.get("title"),
                    "caption": caption,
                    "local_file_name": None,
                    "file_path": None,
                    "file_size": None,
                    "status": "DONE",
                    "error_message": None,
                    "quality": quality,
                    "queue_position": job["queue_position"],
                },
            )

            notify_admins(f"📥 ID {user_id} | Platform {detect_platform(url)} | Status DONE")

            inviter = mark_referral_success(conn, user_id)
            if inviter:
                try:
                    bot.send_message(inviter, t(get_lang(inviter), "ref_success"))
                except Exception:
                    pass
            return

        result = download(url, user_dir, mode=mode, quality=quality)
        file_path = result.get("file_path")
        platform = result.get("platform") or detect_platform(url)
        caption = (result.get("caption") or "").strip()
        title = result.get("title") or ""
        media_type = result.get("media_type") or mode

        if not file_path or not os.path.exists(file_path):
            raise RuntimeError("Downloaded file not found")

        if should_compress(file_path) and media_type == "video":
            bot.send_message(chat_id, t(lang, "compressing"))
            compressed_path = os.path.splitext(file_path)[0] + "_compressed.mp4"
            if compress_video_ffmpeg(file_path, compressed_path):
                file_path = compressed_path

        send_caption = caption[:900] if caption else title or "Done"
        markup = attach_random_promo_buttons()

        with open(file_path, "rb") as f:
            if media_type == "image":
                bot.send_photo(chat_id, f, caption=send_caption, reply_markup=markup)
            elif media_type == "audio":
                bot.send_audio(chat_id, f, caption=send_caption, reply_markup=markup)
            else:
                bot.send_video(chat_id, f, caption=send_caption, reply_markup=markup)

        add_download_log(
            conn,
            {
                "telegram_id": user_id,
                "username": job["username"],
                "full_name": job["full_name"],
                "source_url": url,
                "platform": platform,
                "media_type": media_type,
                "title": title,
                "caption": caption,
                "local_file_name": os.path.basename(file_path),
                "file_path": file_path,
                "file_size": os.path.getsize(file_path),
                "status": "DONE",
                "error_message": None,
                "quality": quality,
                "queue_position": job["queue_position"],
            },
        )

        notify_admins(f"📥 ID {user_id} | Platform {platform} | Status DONE")

        inviter = mark_referral_success(conn, user_id)
        if inviter:
            try:
                bot.send_message(inviter, t(get_lang(inviter), "ref_success"))
            except Exception:
                pass

    except Exception as e:
        traceback.print_exc()

        add_download_log(
            conn,
            {
                "telegram_id": user_id,
                "username": job["username"],
                "full_name": job["full_name"],
                "source_url": url,
                "platform": detect_platform(url),
                "media_type": mode,
                "title": None,
                "caption": None,
                "local_file_name": None,
                "file_path": None,
                "file_size": None,
                "status": "FAILED",
                "error_message": str(e),
                "quality": quality,
                "queue_position": job["queue_position"],
            },
        )

        notify_admins(f"📥 ID {user_id} | Platform {detect_platform(url)} | Status FAILED")
        bot.send_message(chat_id, f"{t(lang, 'job_failed')}\n{str(e)[:250]}")


def start_workers():
    threading.Thread(target=worker, daemon=True).start()


@bot.message_handler(commands=["start"])
def cmd_start(message):
    payload = ""
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        payload = parts[1].strip()

    upsert_user(conn, message.from_user)

    if is_user_banned(conn, message.from_user.id):
        return bot.send_message(message.chat.id, t(get_lang(message.from_user.id), "you_are_banned"))

    ref_id = extract_referral(payload)
    if ref_id:
        create_referral(conn, ref_id, message.from_user.id)

    lang = get_lang(message.from_user.id)
    ref_link = get_referral_link(message.from_user.id)
    text = f"{t(lang, 'welcome')}\n\n{t(lang, 'new_referral_link')}:\n{ref_link}\n{t(lang, 'invite_friends')}"
    bot.send_message(message.chat.id, text, reply_markup=main_menu(lang, is_admin(message.from_user.id)))


@bot.callback_query_handler(func=lambda c: c.data.startswith("lang:"))
def cb_lang(call):
    lang = call.data.split(":")[1]
    set_lang(call.from_user.id, lang)
    bot.answer_callback_query(call.id, t(lang, "lang_changed"))
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(call.message.chat.id, t(lang, "lang_changed"), reply_markup=main_menu(lang, is_admin(call.from_user.id)))


@bot.callback_query_handler(func=lambda c: c.data == "force:recheck")
def cb_recheck(call):
    lang = get_lang(call.from_user.id)
    if force_join_required(call.from_user.id):
        return bot.answer_callback_query(call.id, t(lang, "blocked"), show_alert=True)

    mark_join_verified(conn, call.from_user.id)
    notify_admins(f"✅ Join verified | ID {call.from_user.id}")
    bot.answer_callback_query(call.id, t(lang, "join_verified"))
    bot.send_message(call.message.chat.id, t(lang, "join_verified"), reply_markup=main_menu(lang, is_admin(call.from_user.id)))


@bot.callback_query_handler(func=lambda c: c.data.startswith("preview:"))
def cb_preview(call):
    _, preview_id, action = call.data.split(":")
    preview = PREVIEWS.get(preview_id)

    if not preview or preview["user_id"] != call.from_user.id:
        return bot.answer_callback_query(call.id, "Expired", show_alert=True)

    lang = get_lang(call.from_user.id)

    if action == "cancel":
        bot.answer_callback_query(call.id, t(lang, "cancelled"))
        return bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)

    if action == "caption":
        pos = enqueue_job(
            {
                "user_id": call.from_user.id,
                "chat_id": call.message.chat.id,
                "url": preview["url"],
                "mode": "caption",
                "quality": "high",
                "preview_id": preview_id,
                "username": call.from_user.username,
                "full_name": ((call.from_user.first_name or "") + (" " + call.from_user.last_name if call.from_user.last_name else "")).strip(),
            }
        )
        return bot.answer_callback_query(call.id, t(lang, "queue_added", pos=pos))

    if action == "video":
        bot.answer_callback_query(call.id)
        return bot.send_message(call.message.chat.id, t(lang, "choose_quality"), reply_markup=quality_menu(lang, preview_id))

    if action in {"image", "audio"}:
        pos = enqueue_job(
            {
                "user_id": call.from_user.id,
                "chat_id": call.message.chat.id,
                "url": preview["url"],
                "mode": action,
                "quality": "high",
                "preview_id": preview_id,
                "username": call.from_user.username,
                "full_name": ((call.from_user.first_name or "") + (" " + call.from_user.last_name if call.from_user.last_name else "")).strip(),
            }
        )
        bot.answer_callback_query(call.id, t(lang, "queue_added", pos=pos))


@bot.callback_query_handler(func=lambda c: c.data.startswith("quality:"))
def cb_quality(call):
    _, preview_id, quality = call.data.split(":")
    preview = PREVIEWS.get(preview_id)

    if not preview or preview["user_id"] != call.from_user.id:
        return bot.answer_callback_query(call.id, "Expired", show_alert=True)

    lang = get_lang(call.from_user.id)
    pos = enqueue_job(
        {
            "user_id": call.from_user.id,
            "chat_id": call.message.chat.id,
            "url": preview["url"],
            "mode": "video",
            "quality": quality,
            "preview_id": preview_id,
            "username": call.from_user.username,
            "full_name": ((call.from_user.first_name or "") + (" " + call.from_user.last_name if call.from_user.last_name else "")).strip(),
        }
    )
    bot.answer_callback_query(call.id, t(lang, "queue_added", pos=pos))


@bot.callback_query_handler(func=lambda c: c.data.startswith("admin:"))
def cb_admin(call):
    if not is_admin(call.from_user.id):
        return bot.answer_callback_query(call.id, t(get_lang(call.from_user.id), "admin_only"), show_alert=True)

    lang = get_lang(call.from_user.id)
    enabled = str(get_setting(conn, "force_join_enabled", "False")).lower() == "true"
    mode = get_setting(conn, "force_join_mode", "both")
    data = call.data

    if data == "admin:home":
        bot.edit_message_text(
            f"<b>{t(lang, 'admin_title')}</b>\n\n{stats_text()}",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=admin_menu(lang),
        )

    elif data == "admin:force_join":
        ch = get_setting(conn, "required_channel", "") or "-"
        gr = get_setting(conn, "required_group", "") or "-"
        txt = f"<b>{t(lang, 'admin_force_join')}</b>\nStatus: {'ON' if enabled else 'OFF'}\nMode: {mode}\nChannel: {ch}\nGroup: {gr}"
        bot.edit_message_text(
            txt,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=force_join_admin_menu(lang, enabled, mode),
        )

    elif data == "admin:toggle_force_join":
        set_setting(conn, "force_join_enabled", str(not enabled))
        bot.answer_callback_query(call.id, t(lang, "saved"))
        return cb_admin(type("obj", (), {"from_user": call.from_user, "message": call.message, "data": "admin:force_join", "id": call.id}))

    elif data == "admin:cycle_mode":
        modes = ["channel", "group", "both"]
        idx = modes.index(mode) if mode in modes else 2
        set_setting(conn, "force_join_mode", modes[(idx + 1) % len(modes)])
        bot.answer_callback_query(call.id, t(lang, "saved"))
        return cb_admin(type("obj", (), {"from_user": call.from_user, "message": call.message, "data": "admin:force_join", "id": call.id}))

    elif data == "admin:set_channel":
        USER_STATE[call.from_user.id] = {"action": "set_channel"}
        bot.send_message(call.message.chat.id, t(lang, "send_channel"))

    elif data == "admin:set_group":
        USER_STATE[call.from_user.id] = {"action": "set_group"}
        bot.send_message(call.message.chat.id, t(lang, "send_group"))

    elif data == "admin:set_join_msg":
        USER_STATE[call.from_user.id] = {"action": "set_join_msg", "lang": lang}
        bot.send_message(call.message.chat.id, t(lang, "send_join_msg"))

    elif data == "admin:logs":
        rows = get_recent_downloads(conn, 15)
        txt = f"<b>{t(lang, 'recent_downloads')}</b>\n" + ("\n".join(format_download_row(r) for r in rows) if rows else "-")
        bot.edit_message_text(txt, call.message.chat.id, call.message.message_id, reply_markup=links_admin_menu(lang))

    elif data == "admin:logs_video":
        rows = get_recent_downloads(conn, 15, media_type="video")
        txt = f"<b>{t(lang, 'recent_videos')}</b>\n" + ("\n".join(format_download_row(r) for r in rows) if rows else "-")
        bot.edit_message_text(txt, call.message.chat.id, call.message.message_id, reply_markup=links_admin_menu(lang))

    elif data == "admin:logs_image":
        rows = get_recent_downloads(conn, 15, media_type="image")
        txt = f"<b>{t(lang, 'recent_images')}</b>\n" + ("\n".join(format_download_row(r) for r in rows) if rows else "-")
        bot.edit_message_text(txt, call.message.chat.id, call.message.message_id, reply_markup=links_admin_menu(lang))

    elif data == "admin:users":
        rows = get_recent_users(conn, 15)
        txt = f"<b>{t(lang, 'user_activity')}</b>\n" + ("\n".join(format_user_row(r) for r in rows) if rows else "-")
        bot.edit_message_text(
            txt,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton(t(lang, "admin_back"), callback_data="admin:home")),
        )

    elif data == "admin:search":
        USER_STATE[call.from_user.id] = {"action": "search_user"}
        bot.send_message(call.message.chat.id, t(lang, "send_search"))

    elif data == "admin:stats":
        bot.edit_message_text(stats_text(), call.message.chat.id, call.message.message_id, reply_markup=admin_menu(lang))

    elif data == "admin:buttons":
        rows = list_promo_buttons(conn)
        listed = "\n".join([f"- {r['title']} | {r['url']}" for r in rows]) if rows else "-"
        txt = f"<b>{t(lang, 'current_buttons')}</b>\n{listed}\n\n{t(lang, 'manage_buttons_help')}"
        bot.edit_message_text(txt, call.message.chat.id, call.message.message_id, reply_markup=buttons_admin_menu(lang))

    elif data == "admin:add_button":
        USER_STATE[call.from_user.id] = {"action": "add_button"}
        bot.send_message(call.message.chat.id, t(lang, "manage_buttons_help"))

    elif data == "admin:clear_buttons":
        clear_promo_buttons(conn)
        bot.answer_callback_query(call.id, t(lang, "extra_buttons_saved"))
        return cb_admin(type("obj", (), {"from_user": call.from_user, "message": call.message, "data": "admin:buttons", "id": call.id}))

    elif data == "admin:ban":
        bot.edit_message_text(
            f"<b>{t(lang, 'admin_ban')}</b>",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=ban_admin_menu(lang),
        )

    elif data == "admin:ban_user":
        USER_STATE[call.from_user.id] = {"action": "ban_user"}
        bot.send_message(call.message.chat.id, t(lang, "send_ban_id"))

    elif data == "admin:unban_user":
        USER_STATE[call.from_user.id] = {"action": "unban_user"}
        bot.send_message(call.message.chat.id, t(lang, "send_ban_id"))

    elif data == "admin:referral":
        rows = top_users(conn, 10)
        txt = "<b>Referral / Top users</b>\n" + ("\n".join([format_user_row(r) for r in rows]) if rows else "-")
        bot.edit_message_text(
            txt,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton(t(lang, "admin_back"), callback_data="admin:home")),
        )

    bot.answer_callback_query(call.id)


@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_text(message):
    upsert_user(conn, message.from_user)
    user_id = message.from_user.id
    lang = get_lang(user_id)
    text = (message.text or "").strip()

    if is_user_banned(conn, user_id):
        return bot.send_message(message.chat.id, t(lang, "you_are_banned"))

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
            set_setting(conn, f"join_message_{state.get('lang', 'kh')}", text)
            USER_STATE.pop(user_id, None)
            return bot.send_message(message.chat.id, t(lang, "saved"))

        elif action == "search_user":
            USER_STATE.pop(user_id, None)
            rows = search_users(conn, text)
            if not rows:
                return bot.send_message(message.chat.id, t(lang, "not_found"))

            parts = [f"<b>{t(lang, 'search_results')}</b>"]
            for r in rows[:10]:
                parts.append(format_user_row(r))
                for d in get_user_downloads(conn, r["telegram_id"], 5):
                    parts.append("  - " + format_download_row(d))
            return bot.send_message(message.chat.id, "\n".join(parts))

        elif action == "add_button":
            USER_STATE.pop(user_id, None)
            if "|" not in text:
                return bot.send_message(message.chat.id, t(lang, "manage_buttons_help"))
            title, url = [x.strip() for x in text.split("|", 1)]
            add_promo_button(conn, title, url)
            return bot.send_message(message.chat.id, t(lang, "extra_buttons_saved"))

        elif action == "ban_user":
            USER_STATE.pop(user_id, None)
            if text.isdigit():
                set_user_ban(conn, int(text), True)
                return bot.send_message(message.chat.id, t(lang, "banned"))
            return bot.send_message(message.chat.id, t(lang, "not_found"))

        elif action == "unban_user":
            USER_STATE.pop(user_id, None)
            if text.isdigit():
                set_user_ban(conn, int(text), False)
                return bot.send_message(message.chat.id, t(lang, "unbanned"))
            return bot.send_message(message.chat.id, t(lang, "not_found"))

    if text in {t(lang, "menu_download"), "📥 Download", "📥 ទាញយក"}:
        return bot.send_message(message.chat.id, t(lang, "ask_link"))

    if text in {t(lang, "menu_how"), "📘 How to Use", "📘 របៀបប្រើ"}:
        return bot.send_message(message.chat.id, t(lang, "how_to"), reply_markup=main_menu(lang, is_admin(user_id)))

    if text in {t(lang, "menu_lang"), "🌐 Language", "🌐 ភាសា"}:
        return bot.send_message(message.chat.id, t(lang, "choose_language"), reply_markup=language_menu())

    if text in {t(lang, "menu_usage"), "📊 My Usage", "📊 ការប្រើប្រាស់របស់ខ្ញុំ"}:
        return bot.send_message(message.chat.id, user_usage_text(user_id, lang), reply_markup=main_menu(lang, is_admin(user_id)))

    if text in {t(lang, "menu_admin"), "🛠 Admin Dashboard", "🛠 ផ្ទាំងគ្រប់គ្រង"}:
        if not is_admin(user_id):
            return bot.send_message(message.chat.id, t(lang, "admin_only"))
        return bot.send_message(message.chat.id, f"<b>{t(lang, 'admin_title')}</b>\n\n{stats_text()}", reply_markup=admin_menu(lang))

    if not is_valid_url(text):
        return bot.send_message(message.chat.id, t(lang, "welcome"), reply_markup=main_menu(lang, is_admin(user_id)))

    if anti_spam_block(user_id):
        return bot.send_message(message.chat.id, t(lang, "anti_spam_wait"))

    update_last_request(conn, user_id)

    if force_join_required(user_id):
        return send_force_join_prompt(message.chat.id, user_id)

    if count_pending_for_user(conn, user_id) >= MAX_PENDING_PER_USER:
        return bot.send_message(message.chat.id, t(lang, "too_many_pending"))

    used = count_user_success_today(conn, user_id)
    limit = user_limit(user_id)
    if used >= limit:
        return bot.send_message(message.chat.id, t(lang, "daily_limit_hit", used=used, limit=limit))

    if not supported_domain(text):
        return bot.send_message(message.chat.id, t(lang, "unsupported_platform"))

    wait_msg = bot.send_message(message.chat.id, t(lang, "processing"))

    try:
        info = ytdlp_extract(text)
        norm = normalize_info(info)
    except Exception:
        return bot.edit_message_text(t(lang, "login_required"), message.chat.id, wait_msg.message_id)

    preview_id = uuid.uuid4().hex[:10]
    PREVIEWS[preview_id] = {
        "user_id": user_id,
        "url": text,
        "title": norm.get("title"),
        "caption": norm.get("caption"),
        "platform": norm.get("platform"),
        "media_type": norm.get("media_type"),
    }

    preview_caption = (norm.get("caption") or "")[:500] or "-"
    msg_text = (
        f"<b>{t(lang, 'preview_title')}</b>\n"
        f"{t(lang, 'preview_platform')}: {norm.get('platform')}\n"
        f"{t(lang, 'preview_type')}: {norm.get('media_type')}\n"
        f"{t(lang, 'preview_title_label')}: {norm.get('title') or '-'}\n"
        f"{t(lang, 'preview_caption')}: {preview_caption}\n\n"
        f"{t(lang, 'preview_choose')}"
    )

    markup = attach_random_promo_buttons(preview_menu(lang, preview_id))

    try:
        bot.edit_message_text(msg_text, message.chat.id, wait_msg.message_id, reply_markup=markup)
    except Exception:
        bot.send_message(message.chat.id, msg_text, reply_markup=markup)


def run_health_server():
    port = int(os.environ.get("PORT", 10000))

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Bot is running")

        def log_message(self, format, *args):
            return

    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()


start_workers()
_scheduler = start_scheduler(bot, conn, admin_targets)

if __name__ == "__main__":
    threading.Thread(target=run_health_server, daemon=True).start()
    print("Bot is running...")
    bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)
