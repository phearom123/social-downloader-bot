BOT_TOKEN = "8466894355:AAHWyAtSeTYHjFbSezrwcDBMKk-hBhkMW5g"

# Put your Telegram numeric ID(s)
ADMIN_IDS = [5137640997]

# Optional: send admin announcements to a channel/group/chat ID.
# Leave None to send announcements to all admins.
ADMIN_LOG_CHAT_ID = None

# Downloads
DOWNLOAD_DIR = "downloads"
DB_PATH = "data/bot.db"
MAX_DOWNLOADS_PER_DAY = 10

# Force-join defaults (can be changed in admin dashboard)
DEFAULT_FORCE_JOIN_ENABLED = False
DEFAULT_FORCE_JOIN_MODE = "both"   # one of: channel, group, both
DEFAULT_REQUIRED_CHANNEL = ""      # @channelusername or https://t.me/...
DEFAULT_REQUIRED_GROUP = ""        # @groupusername or https://t.me/...
DEFAULT_JOIN_MESSAGE_EN = "Please join the required channel/group before using this bot."
DEFAULT_JOIN_MESSAGE_KH = "សូមចូល Channel/Group ដែលកំណត់ជាមុនសិន មុននឹងប្រើ bot នេះ។"

# yt-dlp
YTDLP_FORMAT = "bv*+ba/b"
MAX_CAPTION_PREVIEW = 600
