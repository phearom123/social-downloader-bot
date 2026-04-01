import os
import sqlite3
from datetime import datetime

def get_conn(db_path: str):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(conn):
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        first_name TEXT,
        language TEXT DEFAULT 'en',
        first_seen TEXT,
        last_active TEXT,
        total_downloads INTEGER DEFAULT 0,
        join_verified_at TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS downloads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER,
        username TEXT,
        full_name TEXT,
        source_url TEXT,
        platform TEXT,
        media_type TEXT,
        caption TEXT,
        local_file_name TEXT,
        file_path TEXT,
        file_size INTEGER,
        status TEXT,
        error_message TEXT,
        created_at TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    conn.commit()

def set_setting(conn, key, value):
    conn.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )
    conn.commit()

def get_setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default

def ensure_default_settings(conn, defaults: dict):
    for k, v in defaults.items():
        if get_setting(conn, k) is None:
            set_setting(conn, k, v)

def upsert_user(conn, user, language="en"):
    now = datetime.utcnow().isoformat(timespec="seconds")
    telegram_id = user.id
    username = getattr(user, "username", None)
    first_name = getattr(user, "first_name", "") or ""
    last_name = getattr(user, "last_name", "") or ""
    full_name = (first_name + " " + last_name).strip()
    cur = conn.execute("SELECT telegram_id FROM users WHERE telegram_id=?", (telegram_id,))
    exists = cur.fetchone() is not None
    if exists:
        conn.execute(
            "UPDATE users SET username=?, full_name=?, first_name=?, last_active=? WHERE telegram_id=?",
            (username, full_name, first_name, now, telegram_id),
        )
    else:
        conn.execute(
            "INSERT INTO users(telegram_id, username, full_name, first_name, language, first_seen, last_active) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (telegram_id, username, full_name, first_name, language, now, now),
        )
    conn.commit()

def set_user_language(conn, telegram_id, lang):
    conn.execute("UPDATE users SET language=? WHERE telegram_id=?", (lang, telegram_id))
    conn.commit()

def get_user_language(conn, telegram_id, default="en"):
    row = conn.execute("SELECT language FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
    return row["language"] if row and row["language"] else default

def mark_join_verified(conn, telegram_id):
    now = datetime.utcnow().isoformat(timespec="seconds")
    conn.execute("UPDATE users SET join_verified_at=? WHERE telegram_id=?", (now, telegram_id))
    conn.commit()

def add_download_log(conn, data: dict):
    conn.execute("""
    INSERT INTO downloads(
        telegram_id, username, full_name, source_url, platform, media_type, caption,
        local_file_name, file_path, file_size, status, error_message, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("telegram_id"),
        data.get("username"),
        data.get("full_name"),
        data.get("source_url"),
        data.get("platform"),
        data.get("media_type"),
        data.get("caption"),
        data.get("local_file_name"),
        data.get("file_path"),
        data.get("file_size"),
        data.get("status"),
        data.get("error_message"),
        datetime.utcnow().isoformat(timespec="seconds"),
    ))
    if data.get("status") == "DONE":
        conn.execute("UPDATE users SET total_downloads = COALESCE(total_downloads,0) + 1 WHERE telegram_id=?", (data.get("telegram_id"),))
    conn.commit()

def count_user_downloads_today(conn, telegram_id):
    day = datetime.utcnow().strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM downloads WHERE telegram_id=? AND status='DONE' AND substr(created_at,1,10)=?",
        (telegram_id, day),
    ).fetchone()
    return int(row["c"] if row else 0)

def get_stats(conn):
    day = datetime.utcnow().strftime("%Y-%m-%d")
    cur = conn.cursor()
    total = cur.execute("SELECT COUNT(*) c FROM downloads").fetchone()["c"]
    today = cur.execute("SELECT COUNT(*) c FROM downloads WHERE substr(created_at,1,10)=?", (day,)).fetchone()["c"]
    videos = cur.execute("SELECT COUNT(*) c FROM downloads WHERE lower(media_type)='video'").fetchone()["c"]
    images = cur.execute("SELECT COUNT(*) c FROM downloads WHERE lower(media_type)='image'").fetchone()["c"]
    captions = cur.execute("SELECT COUNT(*) c FROM downloads WHERE lower(media_type)='caption'").fetchone()["c"]
    failed = cur.execute("SELECT COUNT(*) c FROM downloads WHERE status='FAILED'").fetchone()["c"]
    users = cur.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    return {
        "total": total, "today": today, "videos": videos, "images": images,
        "captions": captions, "failed": failed, "users": users
    }

def get_recent_downloads(conn, limit=15, media_type=None):
    if media_type:
        rows = conn.execute(
            "SELECT * FROM downloads WHERE lower(media_type)=? ORDER BY id DESC LIMIT ?",
            (media_type.lower(), limit)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM downloads ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return rows

def get_recent_users(conn, limit=15):
    return conn.execute("SELECT * FROM users ORDER BY last_active DESC LIMIT ?", (limit,)).fetchall()

def search_user(conn, q: str):
    if q.isdigit():
        rows = conn.execute("SELECT * FROM users WHERE telegram_id=?", (int(q),)).fetchall()
    else:
        q = q.lstrip("@")
        rows = conn.execute("SELECT * FROM users WHERE username LIKE ? OR full_name LIKE ?", (f"%{q}%", f"%{q}%")).fetchall()
    return rows

def get_user_downloads(conn, telegram_id, limit=20):
    return conn.execute("SELECT * FROM downloads WHERE telegram_id=? ORDER BY id DESC LIMIT ?", (telegram_id, limit)).fetchall()
