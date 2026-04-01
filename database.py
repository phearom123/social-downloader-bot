import sqlite3
import os
from datetime import datetime, date, timedelta

class Database:
    def __init__(self, db_path="bot_database.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self._create_tables()
        self._upgrade_db()

    def _create_tables(self):
        # Users Table
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, first_name TEXT,
            language TEXT DEFAULT 'km', bonus_downloads INTEGER DEFAULT 0, is_banned INTEGER DEFAULT 0,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        # Downloads Table
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER, platform TEXT, 
            media_type TEXT, status TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, file_path TEXT
        )''')
        # External Promo Links
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS external_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT, label TEXT, url TEXT
        )''')
        # Settings
        self.cursor.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
        self.conn.commit()

    def _upgrade_db(self):
        # Add columns if they don't exist for older versions
        try: self.cursor.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'km'")
        except: pass
        self.conn.commit()

    def upsert_user(self, uid, username, full_name, first_name):
        self.cursor.execute('''INSERT INTO users (telegram_id, username, full_name, first_name, last_active) 
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP) 
            ON CONFLICT(telegram_id) DO UPDATE SET last_active=excluded.last_active''', 
            (uid, username, full_name, first_name))
        self.conn.commit()

    def is_banned(self, uid):
        self.cursor.execute("SELECT is_banned FROM users WHERE telegram_id = ?", (uid,))
        res = self.cursor.fetchone()
        return res['is_banned'] == 1 if res else False

    def get_user_lang(self, uid):
        self.cursor.execute("SELECT language FROM users WHERE telegram_id = ?", (uid,))
        res = self.cursor.fetchone()
        return res['language'] if res else 'km'

    def set_user_lang(self, uid, lang):
        self.cursor.execute("UPDATE users SET language = ? WHERE telegram_id = ?", (lang, uid))
        self.conn.commit()

    def count_user_downloads_today(self, uid):
        today = date.today().strftime("%Y-%m-%d")
        self.cursor.execute("SELECT COUNT(*) FROM downloads WHERE telegram_id=? AND status='done' AND date(timestamp)=?", (uid, today))
        return self.cursor.fetchone()[0]

    def add_download(self, uid, platform, mtype, status, path=""):
        self.cursor.execute("INSERT INTO downloads (telegram_id, platform, media_type, status, file_path) VALUES (?, ?, ?, ?, ?)", 
                            (uid, platform, mtype, status, path))
        self.conn.commit()

    def get_setting(self, key, default=""):
        self.cursor.execute("SELECT value FROM settings WHERE key=?", (key,))
        res = self.cursor.fetchone()
        return res['value'] if res else default

    def set_setting(self, key, val):
        self.cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, val))
        self.conn.commit()

    def get_external_links(self):
        self.cursor.execute("SELECT * FROM external_links")
        return self.cursor.fetchall()

    def add_external_link(self, label, url):
        self.cursor.execute("INSERT INTO external_links (label, url) VALUES (?, ?)", (label, url))
        self.conn.commit()

    def delete_external_link(self, lid):
        self.cursor.execute("DELETE FROM external_links WHERE id=?", (lid,))
        self.conn.commit()
