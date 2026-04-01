import os
import re
from urllib.parse import urlparse
import yt_dlp

def detect_platform(url: str) -> str:
    host = (urlparse(url).netloc or "").lower()
    mapping = {
        "tiktok": "TikTok",
        "instagram": "Instagram",
        "facebook": "Facebook",
        "fb.watch": "Facebook",
        "youtu": "YouTube",
        "youtube": "YouTube",
        "twitter": "X",
        "x.com": "X",
        "threads": "Threads",
        "pinterest": "Pinterest",
        "snapchat": "Snapchat",
    }
    for k, v in mapping.items():
        if k in host:
            return v
    return host or "Unknown"

def safe_filename(name: str) -> str:
    name = name or "download"
    name = re.sub(r'[\\/:*?"<>|\n\r\t]+', "_", name)
    return name[:120].strip(" ._") or "download"

def extract_info(url: str):
    opts = {"quiet": True, "skip_download": True, "noplaylist": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return info

def download_media(url: str, output_dir: str, ytdlp_format: str = "bv*+ba/b"):
    os.makedirs(output_dir, exist_ok=True)
    info = extract_info(url)
    title = safe_filename(info.get("title") or "download")
    outtmpl = os.path.join(output_dir, f"{title}.%(ext)s")

    # choose type
    requested = info.get("requested_downloads") or []
    entries = info.get("entries")
    media_type = "video"
    if info.get("_type") == "playlist" and entries:
        # keep first entry only for simplicity
        info = entries[0]
    ext = info.get("ext")

    if not info.get("vcodec") or info.get("vcodec") == "none":
        if info.get("thumbnails") or info.get("ext") in {"jpg", "jpeg", "png", "webp"}:
            media_type = "image"
        else:
            media_type = "video"

    opts = {
        "quiet": True,
        "noplaylist": True,
        "outtmpl": outtmpl,
        "format": ytdlp_format,
        "merge_output_format": "mp4",
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.extract_info(url, download=True)

    # locate file
    file_path = None
    for name in os.listdir(output_dir):
        if name.startswith(title + "."):
            file_path = os.path.join(output_dir, name)
            break
    if not file_path:
        # fallback: latest file
        files = [os.path.join(output_dir, f) for f in os.listdir(output_dir)]
        if files:
            file_path = max(files, key=os.path.getmtime)

    caption = info.get("description") or info.get("caption") or info.get("title") or ""
    platform = detect_platform(url)
    return {
        "platform": platform,
        "media_type": media_type,
        "caption": caption,
        "file_path": file_path,
        "local_file_name": os.path.basename(file_path) if file_path else None,
        "file_size": os.path.getsize(file_path) if file_path and os.path.exists(file_path) else None,
        "title": info.get("title"),
    }
