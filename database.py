import sqlite3
import os
from datetime import datetime, date, timedelta

class Database:
    def __init__(self, db_path="bot_database.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self._create_tables()
        self._ensure_new_columns_exist()

    def _create_tables(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                first_name TEXT,
                join_verified INTEGER DEFAULT 0,
                join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                language TEXT DEFAULT 'km',
                bonus_downloads INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                username TEXT,
                full_name TEXT,
                source_url TEXT,
                platform TEXT,
                media_type TEXT,
                caption_text TEXT,
                local_file_name TEXT,
                file_path TEXT,
                file_size INTEGER,
                status TEXT,
                error_text TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        self.conn.commit()

    def _ensure_new_columns_exist(self):
        columns_to_add = [
            ("language", "TEXT DEFAULT 'km'"),
            ("bonus_downloads", "INTEGER DEFAULT 0"),
            ("is_banned", "INTEGER DEFAULT 0")
        ]
        for col_name, col_type in columns_to_add:
            try:
                self.cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                pass # Column already exists
        self.conn.commit()

    # ==========================================
    # USER MANAGEMENT
    # ==========================================
    def upsert_user(self, telegram_id, username, full_name, first_name):
        self.cursor.execute('''
            INSERT INTO users (telegram_id, username, full_name, first_name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username=excluded.username,
                full_name=excluded.full_name,
                first_name=excluded.first_name
        ''', (telegram_id, username, full_name, first_name))
        self.conn.commit()

    def mark_join_verified(self, telegram_id):
        self.cursor.execute("UPDATE users SET join_verified = 1 WHERE telegram_id = ?", (telegram_id,))
        self.conn.commit()

    def is_banned(self, telegram_id):
        self.cursor.execute("SELECT is_banned FROM users WHERE telegram_id = ?", (telegram_id,))
        row = self.cursor.fetchone()
        return bool(row['is_banned']) if row else False

    # ==========================================
    # SETTINGS MANAGEMENT
    # ==========================================
    def get_setting(self, key, default=""):
        self.cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = self.cursor.fetchone()
        return row['value'] if row else default

    def set_setting(self, key, value):
        self.cursor.execute('''
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        ''', (key, value))
        self.conn.commit()

    # ==========================================
    # DOWNLOAD MANAGEMENT
    # ==========================================
    def count_user_downloads_today(self, telegram_id):
        today_str = date.today().strftime("%Y-%m-%d")
        self.cursor.execute('''
            SELECT COUNT(*) FROM downloads 
            WHERE telegram_id = ? AND status = 'done' AND date(timestamp) = ?
        ''', (telegram_id, today_str))
        return self.cursor.fetchone()[0]

    def get_lifetime_downloads(self, telegram_id):
        self.cursor.execute("SELECT COUNT(*) FROM downloads WHERE telegram_id = ? AND status = 'done'", (telegram_id,))
        return self.cursor.fetchone()[0]

    def add_download(self, telegram_id, username, full_name, source_url, platform, 
                     media_type, caption_text, local_file_name, file_path, file_size, 
                     status, error_text=""):
        self.cursor.execute('''
            INSERT INTO downloads (
                telegram_id, username, full_name, source_url, platform, 
                media_type, caption_text, local_file_name, file_path, file_size, 
                status, error_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (telegram_id, username, full_name, source_url, platform, media_type, 
              caption_text, local_file_name, file_path, file_size, status, error_text))
        self.conn.commit()
        return self.cursor.lastrowid

    # ==========================================
    # MULTI-LANGUAGE & REFERRALS
    # ==========================================
    def get_user_lang(self, telegram_id: int) -> str:
        self.cursor.execute("SELECT language FROM users WHERE telegram_id = ?", (telegram_id,))
        row = self.cursor.fetchone()
        return row['language'] if row and 'language' in row.keys() else 'km'

    def set_user_lang(self, telegram_id: int, lang: str):
        self.cursor.execute("UPDATE users SET language = ? WHERE telegram_id = ?", (lang, telegram_id))
        self.conn.commit()

    def get_bonus_downloads(self, telegram_id: int) -> int:
        self.cursor.execute("SELECT bonus_downloads FROM users WHERE telegram_id = ?", (telegram_id,))
        row = self.cursor.fetchone()
        return int(row['bonus_downloads']) if row and 'bonus_downloads' in row.keys() else 0

    def add_bonus_download(self, telegram_id: int, amount: int = 1):
        current = self.get_bonus_downloads(telegram_id)
        self.cursor.execute("UPDATE users SET bonus_downloads = ? WHERE telegram_id = ?", (current + amount, telegram_id))
        self.conn.commit()

    # ==========================================
    # BACKGROUND SCHEDULER & ADMIN STATS
    # ==========================================
    def get_today_stats(self):
        today_str = date.today().strftime("%Y-%m-%d")
        
        self.cursor.execute("SELECT COUNT(*) FROM downloads WHERE date(timestamp) = ? AND status = 'done'", (today_str,))
        total = self.cursor.fetchone()[0]
        
        self.cursor.execute("SELECT COUNT(*) FROM downloads WHERE date(timestamp) = ? AND status = 'failed'", (today_str,))
        failed = self.cursor.fetchone()[0]
        
        self.cursor.execute("SELECT COUNT(*) FROM users WHERE date(join_date) = ?", (today_str,))
        new_users = self.cursor.fetchone()[0]
        
        return {"total": total, "failed": failed, "new_users": new_users}

    def delete_old_files(self, days=30):
        """Finds and deletes files older than X days to save server space"""
        cutoff_date = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff_date.strftime("%Y-%m-%d %H:%M:%S")
        
        self.cursor.execute("SELECT id, file_path FROM downloads WHERE timestamp < ? AND file_path != ''", (cutoff_str,))
        files_to_delete = self.cursor.fetchall()
        
        for f in files_to_delete:
            try:
                if os.path.exists(f['file_path']):
                    os.remove(f['file_path'])
            except Exception:
                pass
                
        # Clear the file path from DB so we don't try to delete it again
        self.cursor.execute("UPDATE downloads SET file_path = '' WHERE timestamp < ?", (cutoff_str,))
        self.conn.commit()
