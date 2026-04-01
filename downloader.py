import yt_dlp
import os
import re

class SocialDownloader:
    def __init__(self):
        self.tmp = "downloads"
        if not os.path.exists(self.tmp): os.makedirs(self.tmp)

    def is_supported(self, url):
        supported = ['tiktok.com', 'instagram.com', 'facebook.com', 'youtube.com', 'youtu.be', 'twitter.com', 'x.com']
        return any(x in url for x in supported)

    def get_info(self, url):
        with yt_dlp.YoutubeDL({'quiet': True, 'noplaylist': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                'title': info.get('title', 'Video'),
                'platform': info.get('extractor_key', 'Social'),
                'duration': info.get('duration', 0)
            }

    def download(self, url, uid, mtype='video'):
        path = os.path.join(self.tmp, f"{uid}_{mtype}.%(ext)s")
        ydl_opts = {
            'outtmpl': path,
            'format': 'best' if mtype == 'video' else 'bestaudio/best',
            'quiet': True,
        }
        if mtype == 'audio':
            ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            fpath = ydl.prepare_filename(info)
            if mtype == 'audio': fpath = fpath.rsplit('.', 1)[0] + '.mp3'
            return {'path': fpath, 'platform': info.get('extractor_key'), 'title': info.get('title')}

def extract_first_url(text):
    match = re.search(r'(https?://\S+)', text)
    return match.group(1) if match else None
