# app/utils/validators.py
import re

_YT_HOSTS = {"youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com",
             "youtube-nocookie.com", "www.youtube-nocookie.com"}

def is_valid_youtube_url(url: str) -> bool:
    try:
        from urllib.parse import urlparse
        p = urlparse(url)
        if p.hostname not in _YT_HOSTS:
            return False
        return bool(
            re.search(r"[?&]v=([0-9A-Za-z_-]{11})", url) or
            re.search(r"/shorts/([0-9A-Za-z_-]{11})", url) or
            re.search(r"/embed/([0-9A-Za-z_-]{11})", url) or
            (p.hostname == "youtu.be" and re.search(r"/([0-9A-Za-z_-]{11})", p.path))
        )
    except Exception:
        return False

def sanitize_filename(name: str) -> str:
    import re
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:100] or "download"
