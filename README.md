# Social Downloader Bot - FULL VERSION (FINAL)

This project is a Telegram bot with:
- Button-based workflow
- Khmer / English language
- Force Join (channel / group / both)
- Daily limit: 10 successful downloads per user
- Admin dashboard
- Download logging to SQLite
- Admin announcements
- Search user / recent logs / recent users
- yt-dlp based downloading

## Files
- `bot.py`
- `admin.py`
- `database.py`
- `downloader.py`
- `force_join.py`
- `config.py`
- `texts.py`
- `requirements.txt`

## Step-by-step setup (Windows PowerShell)

### 1) Extract ZIP
Extract the ZIP to a folder, for example:
`C:\Users\ASUS\Desktop\social_downloader_bot_full_final`

### 2) Open PowerShell in the folder
```powershell
cd "C:\Users\ASUS\Desktop\social_downloader_bot_full_final"
```

### 3) Install Python packages
```powershell
python -m pip install -r requirements.txt
```

### 4) Install FFmpeg (recommended)
yt-dlp works better when FFmpeg is installed.
- Download FFmpeg build for Windows
- Add FFmpeg `bin` to PATH
- Test:
```powershell
ffmpeg -version
```

### 5) Configure the bot
Open config:
```powershell
notepad config.py
```

Set:
- `BOT_TOKEN`
- `ADMIN_IDS`
- optionally `ADMIN_LOG_CHAT_ID`

Example:
```python
BOT_TOKEN = "123456:ABC..."
ADMIN_IDS = [123456789]
ADMIN_LOG_CHAT_ID = -1001234567890
```

### 6) Run the bot
```powershell
python bot.py
```

## First admin setup in Telegram
Start your bot and use:
- `/start`
- Tap `🛠 Admin Dashboard`

Then in the dashboard:
- Force Join → enable / disable
- Set Channel
- Set Group
- Set Join Message
- Cycle mode: `channel`, `group`, `both`

## Important force-join notes
For membership verification to work:
- The bot should be in the target channel/group
- The bot needs permission to read member status
- Public usernames like `@mychannel` are easiest
- Private invite links can be shown as buttons, but membership recheck may fail because Telegram does not let bots verify private invite links directly

## Admin announcements
On successful download, admin receives:
- user ID
- platform
- status only

When join is verified, admin receives:
- user ID

## Daily limit
Each user can successfully download only 10 items per day.
One successful send = one count.

## Admin features
- View all downloads
- View latest video/image downloads
- View recent users
- Search by user ID or username
- Refresh stats

## Notes
- Works best with public URLs
- Some private / login-only / DRM content will fail
- Large files may fail if Telegram cannot upload them
