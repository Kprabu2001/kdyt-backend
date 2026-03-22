# app/services/innertube.py
# Uses yt-dlp to extract video info and stream URLs reliably.

import base64
import logging
import os
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_OEMBED_URL = "https://www.youtube.com/oembed"

# ── Cookie support ────────────────────────────────────────────────
def _get_cookies_file() -> Optional[str]:
    """Return path to a valid cookies.txt file, or None."""
    # Method 1: explicit file path
    path = os.environ.get("YOUTUBE_COOKIES_FILE", "")
    if path and os.path.isfile(path):
        return path

    # Method 2: base64 env var → write to temp file
    b64 = os.environ.get("YOUTUBE_COOKIES_B64", "").strip()
    if b64:
        try:
            import tempfile
            txt = base64.b64decode(b64).decode("utf-8")
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w")
            tmp.write(txt)
            tmp.close()
            logger.info(f"[cookies] Wrote cookies from B64 env to {tmp.name}")
            return tmp.name
        except Exception as e:
            logger.warning(f"[cookies] B64 decode failed: {e}")

    # Method 3: cookies.txt in working directory
    if os.path.isfile("cookies.txt"):
        return "cookies.txt"

    return None

# ── Helpers ───────────────────────────────────────────────────────
def _extract_video_id(text: str) -> Optional[str]:
    if re.match(r'^[0-9A-Za-z_-]{11}$', text): return text
    for p in [r"[?&]v=([0-9A-Za-z_-]{11})", r"youtu\.be/([0-9A-Za-z_-]{11})",
              r"shorts/([0-9A-Za-z_-]{11})", r"embed/([0-9A-Za-z_-]{11})"]:
        m = re.search(p, text)
        if m: return m.group(1)
    return None

def _extract_playlist_id(text: str) -> Optional[str]:
    m = re.search(r"[?&]list=([0-9A-Za-z_-]+)", text)
    return m.group(1) if m else None

def _fmt_duration(s) -> str:
    try: s = int(s or 0)
    except: return "0:00"
    h, r = divmod(s, 3600); m, sec = divmod(r, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"

def _fmt_views(n) -> str:
    try: n = int(n or 0)
    except: return "0"
    if n >= 1_000_000_000: return f"{n/1e9:.1f}B"
    if n >= 1_000_000:     return f"{n/1e6:.1f}M"
    if n >= 1_000:         return f"{n/1e3:.1f}K"
    return str(n)

def _fmt_size(b) -> str:
    try: b = int(b or 0)
    except: return ""
    if not b: return ""
    if b >= 1_073_741_824: return f"{b/1_073_741_824:.1f} GB"
    if b >= 1_048_576:     return f"{b/1_048_576:.1f} MB"
    if b >= 1_024:         return f"{b/1_024:.1f} KB"
    return f"{b} B"

# ── yt-dlp extractor ──────────────────────────────────────────────
def _ydl_opts(cookies_file: Optional[str] = None) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "skip_download": True,
        "noplaylist": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        },
    }
    if cookies_file:
        opts["cookiefile"] = cookies_file
        logger.info(f"[yt-dlp] Using cookies: {cookies_file}")
    return opts

def _extract_with_ytdlp(video_id: str) -> dict:
    import yt_dlp
    cookies_file = _get_cookies_file()
    url = f"https://www.youtube.com/watch?v={video_id}"
    opts = _ydl_opts(cookies_file)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return info

def _parse_ytdlp_formats(info: dict) -> tuple[list[dict], list[dict]]:
    vfmts: list[dict] = []
    afmts: list[dict] = []
    seen:  set[str]   = set()

    for f in info.get("formats", []):
        url     = f.get("url")
        if not url: continue
        vcodec  = f.get("vcodec", "none")
        acodec  = f.get("acodec", "none")
        is_v    = vcodec != "none"
        is_a    = acodec != "none"
        height  = f.get("height")
        fps     = int(f.get("fps") or 0)
        bitrate = int(f.get("tbr") or 0) * 1000
        fsize   = f.get("filesize") or f.get("filesize_approx") or None
        ext     = f.get("ext", "mp4")
        fmt_id  = str(f.get("format_id", ""))

        if is_v and height:
            lbl = f"{height}p" + (f"{fps}fps" if fps >= 48 else "")
            if lbl in seen: continue
            seen.add(lbl)
            has_audio = is_a and acodec != "none"
            vfmts.append({
                "format_id": fmt_id,
                "quality":   lbl,
                "ext":       ext,
                "height":    height,
                "fps":       fps,
                "bitrate":   bitrate,
                "filesize":  _fmt_size(fsize),
                "filesize_bytes": fsize,
                "url":       url,
                "has_audio": has_audio,
                "mime":      f"video/{ext}",
            })
        elif not is_v and is_a:
            abr = int(f.get("abr") or 0) * 1000
            afmts.append({
                "format_id": fmt_id,
                "quality":   f"{round(abr/1000)} kbps" if abr else "audio",
                "ext":       ext,
                "bitrate":   abr,
                "filesize":  _fmt_size(fsize),
                "filesize_bytes": fsize,
                "url":       url,
                "mime":      f"audio/{ext}",
            })

    vfmts.sort(key=lambda x: -(x.get("height") or 0))
    afmts.sort(key=lambda x: -(x.get("bitrate") or 0))
    return vfmts, afmts

# ── oEmbed fallback ───────────────────────────────────────────────
async def _fetch_oembed(video_id: str, http: httpx.AsyncClient) -> dict:
    for url_tmpl in [
        f"https://www.youtube.com/watch?v={video_id}",
        f"https://www.youtube.com/shorts/{video_id}",
    ]:
        try:
            r = await http.get(_OEMBED_URL,
                params={"url": url_tmpl, "format": "json"},
                headers={"User-Agent": "Mozilla/5.0"}, timeout=10.0)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            logger.warning(f"[oembed] {e}")
    return {}

# ── Public API ────────────────────────────────────────────────────
async def get_video_info(video_id: str) -> dict:
    if not re.match(r'^[0-9A-Za-z_-]{11}$', video_id):
        video_id = _extract_video_id(video_id)
    if not video_id:
        raise ValueError("Invalid YouTube video ID or URL.")

    import asyncio
    loop = asyncio.get_event_loop()
    try:
        info = await loop.run_in_executor(None, _extract_with_ytdlp, video_id)
    except Exception as e:
        err = str(e)
        logger.error(f"[yt-dlp] {err[:300]}")
        if "private" in err.lower() or "removed" in err.lower():
            raise RuntimeError("Video not found, private, or deleted.")
        if "sign in" in err.lower() or "login" in err.lower():
            raise RuntimeError("Age-restricted or members-only video.")
        raise RuntimeError(f"Could not fetch stream URLs for this video.")

    title     = info.get("title", "Untitled")
    channel   = info.get("uploader", info.get("channel", "Unknown"))
    thumbnail = info.get("thumbnail", "")
    duration  = _fmt_duration(info.get("duration", 0))
    views     = _fmt_views(info.get("view_count", 0))

    if not title:
        raise RuntimeError("Video not found, private, or deleted.")

    logger.info(f"[yt-dlp] ✓ '{title[:50]}' by {channel}")

    vf, af = _parse_ytdlp_formats(info)

    return {
        "video_id":      video_id,
        "title":         title,
        "channel":       channel,
        "thumbnail":     thumbnail,
        "duration":      duration,
        "views":         views,
        "video_formats": vf,
        "audio_formats": [
            {"format_id": "320kbps", "quality": "320 kbps", "ext": "mp3"},
            {"format_id": "192kbps", "quality": "192 kbps", "ext": "mp3"},
            {"format_id": "128kbps", "quality": "128 kbps", "ext": "mp3"},
        ],
        "_raw_audio": af,
    }


async def get_best_audio_url(video_id: str) -> tuple[str, str]:
    if not re.match(r'^[0-9A-Za-z_-]{11}$', video_id):
        video_id = _extract_video_id(video_id)
    if not video_id:
        raise ValueError("Invalid video ID.")

    import asyncio
    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(None, _extract_with_ytdlp, video_id)
    _, af = _parse_ytdlp_formats(info)
    if not af: raise RuntimeError("No audio formats found.")
    m4a = next((a for a in af if "m4a" in a.get("ext", "") or "mp4a" in a.get("mime", "")), None)
    best = m4a or af[0]
    return best["url"], best["mime"]


async def get_playlist_videos(playlist_id: str) -> list[dict]:
    import asyncio, yt_dlp
    cookies_file = _get_cookies_file()

    def _fetch():
        opts = {
            **_ydl_opts(cookies_file),
            "extract_flat": True,
            "noplaylist": False,
        }
        url = f"https://www.youtube.com/playlist?list={playlist_id}"
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    loop = asyncio.get_event_loop()
    try:
        info = await loop.run_in_executor(None, _fetch)
    except Exception as e:
        raise RuntimeError(f"Failed to fetch playlist: {e}")

    videos: list[dict] = []
    for entry in info.get("entries", []):
        if not entry: continue
        vid_id = entry.get("id", "")
        if not vid_id: continue
        videos.append({
            "video_id":  vid_id,
            "title":     entry.get("title", ""),
            "thumbnail": entry.get("thumbnail", ""),
            "duration":  _fmt_duration(entry.get("duration", 0)),
            "channel":   entry.get("uploader", entry.get("channel", "")),
        })

    if not videos:
        raise RuntimeError("No videos found in playlist. It may be private or empty.")
    return videos