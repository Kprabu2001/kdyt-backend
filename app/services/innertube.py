# app/services/innertube.py
# Uses cookies for Shorts (required by YouTube for server IPs)
# Regular videos work without cookies.

import asyncio
import base64
import logging
import os
import re
import tempfile
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_PLAYER_URL = "https://www.youtube.com/youtubei/v1/player"
_OEMBED_URL = "https://www.youtube.com/oembed"

# ── Cookie support ────────────────────────────────────────────────
# Set YOUTUBE_COOKIES env var to base64-encoded Netscape cookies.txt
# OR set YOUTUBE_COOKIES_FILE to a path of cookies.txt
# Get cookies: install "Get cookies.txt LOCALLY" Chrome extension
#              → export cookies for youtube.com → save as cookies.txt

def _get_cookie_header() -> dict:
    """
    Read cookies.txt (Netscape format) and return as Cookie header dict.
    Tries: YOUTUBE_COOKIES_FILE env → YOUTUBE_COOKIES_B64 env → cookies.txt in cwd
    """
    txt = ""

    # Method 1: file path
    path = os.environ.get("YOUTUBE_COOKIES_FILE", "")
    if path and os.path.isfile(path):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            txt = f.read()

    # Method 2: base64 env var
    if not txt:
        b64 = os.environ.get("YOUTUBE_COOKIES_B64", "").strip()
        if b64:
            try:
                txt = base64.b64decode(b64).decode("utf-8")
            except Exception:
                pass

    # Method 3: cookies.txt in working directory
    if not txt and os.path.isfile("cookies.txt"):
        with open("cookies.txt", "r", encoding="utf-8", errors="replace") as f:
            txt = f.read()

    if not txt:
        return {}

    # Parse Netscape cookies.txt → Cookie header string
    cookies = {}
    for line in txt.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            name  = parts[5]
            value = parts[6]
            cookies[name] = value

    if not cookies:
        return {}

    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
    logger.info(f"[cookies] Loaded {len(cookies)} cookies")
    return {"Cookie": cookie_str}


# Cache cookies so we don't re-read file on every request
_COOKIE_HEADER: Optional[dict] = None
_COOKIE_LOADED = False

def _cookies() -> dict:
    global _COOKIE_HEADER, _COOKIE_LOADED
    if not _COOKIE_LOADED:
        _COOKIE_HEADER = _get_cookie_header()
        _COOKIE_LOADED = True
        if _COOKIE_HEADER:
            logger.info("[cookies] Cookie header ready")
        else:
            logger.warning("[cookies] No cookies found — Shorts may fail")
    return _COOKIE_HEADER or {}


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


# ── oEmbed ────────────────────────────────────────────────────────
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


# ── InnerTube strategies ──────────────────────────────────────────
async def _try_player(video_id: str, http: httpx.AsyncClient) -> Optional[dict]:
    cookie_hdr = _cookies()
    has_cookies = bool(cookie_hdr)

    strategies = []

    # ── IOS — bypasses PO token, works on datacenter/server IPs ──
    strategies.append({
        "name": "IOS",
        "url":  f"{_PLAYER_URL}?key=AIzaSyB-63vPrdThhKuerbB2N_l7Kwwcxj6yUAc&prettyPrint=false",
        "payload": {
            "videoId": video_id,
            "context": {"client": {
                "hl": "en", "gl": "US",
                "clientName": "IOS",
                "clientVersion": "19.29.1",
                "deviceModel": "iPhone16,2",
                "userAgent": "com.google.ios.youtube/19.29.1 (iPhone16,2; U; CPU iOS 17_5_1 like Mac OS X;)",
                "osName": "iPhone",
                "osVersion": "17.5.1.21F90",
            }},
            "contentCheckOk": True,
            "racyCheckOk": True,
        },
        "headers": {
            "Content-Type": "application/json",
            "User-Agent": "com.google.ios.youtube/19.29.1 (iPhone16,2; U; CPU iOS 17_5_1 like Mac OS X;)",
            "X-YouTube-Client-Name": "5",
            "X-YouTube-Client-Version": "19.29.1",
            "Origin": "https://www.youtube.com",
        },
    })

    # ── ANDROID — another strong fallback for server IPs ─────────
    strategies.append({
        "name": "ANDROID",
        "url":  f"{_PLAYER_URL}?key=AIzaSyA8eiZmM1lafRM_YTQ1z2Ud2G_3cNPF9E0&prettyPrint=false",
        "payload": {
            "videoId": video_id,
            "context": {"client": {
                "hl": "en", "gl": "US",
                "clientName": "ANDROID",
                "clientVersion": "19.29.37",
                "androidSdkVersion": 34,
                "userAgent": "com.google.android.youtube/19.29.37(Linux; U; Android 14) gzip",
                "osName": "Android",
                "osVersion": "14",
            }},
            "contentCheckOk": True,
            "racyCheckOk": True,
        },
        "headers": {
            "Content-Type": "application/json",
            "User-Agent": "com.google.android.youtube/19.29.37(Linux; U; Android 14) gzip",
            "X-YouTube-Client-Name": "3",
            "X-YouTube-Client-Version": "19.29.37",
            "Origin": "https://www.youtube.com",
        },
    })

    # ── WEB+cookies — works if cookies are fresh ─────────────────
    if has_cookies:
        strategies.append({
            "name": "WEB+cookies",
            "url":  _PLAYER_URL,
            "payload": {
                "videoId": video_id,
                "context": {"client": {
                    "hl": "en", "gl": "US",
                    "clientName": "WEB",
                    "clientVersion": "2.20240726.00.00",
                    "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36,gzip(gfe)",
                }},
                "contentCheckOk": True,
                "racyCheckOk":    True,
            },
            "headers": {
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "X-YouTube-Client-Name": "1",
                "X-YouTube-Client-Version": "2.20240726.00.00",
                "Origin":  "https://www.youtube.com",
                "Referer": f"https://www.youtube.com/watch?v={video_id}",
                "Accept-Language": "en-US,en;q=0.9",
                **cookie_hdr,
            },
        })

    # ── WEB_EMBEDDED ──────────────────────────────────────────────
    strategies.append({
        "name": "WEB_EMBEDDED",
        "url":  _PLAYER_URL,
        "payload": {
            "videoId": video_id,
            "context": {
                "client": {"hl":"en","gl":"US","clientName":"WEB_EMBEDDED_PLAYER","clientVersion":"2.20231219.01.00"},
                "thirdParty": {"embedUrl": "https://www.youtube.com/"},
            },
            "contentCheckOk": True, "racyCheckOk": True,
        },
        "headers": {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
            "X-YouTube-Client-Name": "56",
            "X-YouTube-Client-Version": "2.20231219.01.00",
            "Origin":  "https://www.youtube.com",
            "Referer": f"https://www.youtube.com/shorts/{video_id}",
            **cookie_hdr,
        },
    })

    # ── TV_EMBEDDED ───────────────────────────────────────────────
    strategies.append({
        "name": "TV_EMBEDDED",
        "url":  _PLAYER_URL,
        "payload": {
            "videoId": video_id,
            "context": {
                "client": {"hl":"en","gl":"US","clientName":"TVHTML5_SIMPLY_EMBEDDED_PLAYER","clientVersion":"2.0"},
                "thirdParty": {"embedUrl": "https://www.youtube.com/"},
            },
            "contentCheckOk": True, "racyCheckOk": True,
        },
        "headers": {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (SMART-TV; LINUX; Tizen 6.0) AppleWebKit/538.1 Version/6.0 TV Safari/538.1",
            "X-YouTube-Client-Name": "85",
            "X-YouTube-Client-Version": "2.0",
            "Origin":  "https://www.youtube.com",
            "Referer": f"https://www.youtube.com/shorts/{video_id}",
            **cookie_hdr,
        },
    })

    # ── ANDROID_VR ───────────────────────────────────────────────
    strategies.append({
        "name": "ANDROID_VR",
        "url":  f"{_PLAYER_URL}?key=AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8&prettyPrint=false",
        "payload": {
            "videoId": video_id,
            "context": {"client": {"hl":"en","gl":"US","clientName":"ANDROID_VR","clientVersion":"1.57.29","androidSdkVersion":32}},
            "contentCheckOk": True, "racyCheckOk": True,
        },
        "headers": {
            "Content-Type": "application/json",
            "User-Agent": "com.google.android.apps.youtube.vr.oculus/1.57.29 (Linux; U; Android 12L; eureka-user Build/SQ3A.220605.009.A1) gzip",
            "X-YouTube-Client-Name": "28",
            "X-YouTube-Client-Version": "1.57.29",
            "Origin":  "https://www.youtube.com",
            "Referer": f"https://www.youtube.com/shorts/{video_id}",
        },
    })

    # ── ANDROID_MUSIC ────────────────────────────────────────────
    strategies.append({
        "name": "ANDROID_MUSIC",
        "url":  f"{_PLAYER_URL}?key=AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8&prettyPrint=false",
        "payload": {
            "videoId": video_id,
            "context": {"client": {"hl":"en","gl":"US","clientName":"ANDROID_MUSIC","clientVersion":"6.42.52","androidSdkVersion":30}},
            "contentCheckOk": True, "racyCheckOk": True,
        },
        "headers": {
            "Content-Type": "application/json",
            "User-Agent": "com.google.android.apps.youtube.music/6.42.52 (Linux; U; Android 11) gzip",
            "X-YouTube-Client-Name": "21",
            "X-YouTube-Client-Version": "6.42.52",
            "Origin":  "https://www.youtube.com",
            "Referer": f"https://www.youtube.com/shorts/{video_id}",
        },
    })

    for s in strategies:
        try:
            r = await http.post(s["url"], json=s["payload"], headers=s["headers"], timeout=15.0)
            if r.status_code != 200:
                logger.warning(f"[{s['name']}] HTTP {r.status_code}")
                continue
            data   = r.json()
            status = data.get("playabilityStatus", {}).get("status", "")
            logger.info(f"[{s['name']}] status={status}")
            if status == "OK":
                vf, af = _parse_formats(data)
                if vf or af:
                    logger.info(f"[{s['name']}] ✓ {len(vf)}V + {len(af)}A")
                    return data
                logger.warning(f"[{s['name']}] OK but no plain URLs (PO token required)")
        except Exception as e:
            logger.warning(f"[{s['name']}] {e}")

    return None


def _parse_formats(data: dict) -> tuple[list[dict], list[dict]]:
    sd    = data.get("streamingData", {})
    fmts  = sd.get("formats", []) + sd.get("adaptiveFormats", [])
    vfmts: list[dict] = []
    afmts: list[dict] = []
    seen:  set[str]   = set()
    for f in fmts:
        url = f.get("url")
        if not url: continue
        mime    = f.get("mimeType", "")
        is_v    = "video/" in mime
        is_a    = "audio/" in mime
        itag    = f.get("itag", 0)
        height  = f.get("height")
        fps     = int(f.get("fps") or 0)
        bitrate = int(f.get("bitrate") or 0)
        fsize   = int(f.get("contentLength") or 0) or None
        if is_v and height:
            lbl = f"{height}p" + (f"{fps}fps" if fps >= 48 else "")
            if lbl in seen: continue
            seen.add(lbl)
            vfmts.append({"format_id":str(itag),"quality":lbl,
                "ext":"mp4" if "mp4" in mime else "webm","height":height,
                "fps":fps,"bitrate":bitrate,"filesize":_fmt_size(fsize),
                "filesize_bytes":fsize,"url":url,"has_audio":False,"mime":mime})
        elif is_v and not height:
            lbl = {22:"720p",18:"360p",17:"240p",36:"240p"}.get(itag,"360p")
            if lbl in seen: continue
            seen.add(lbl)
            vfmts.append({"format_id":str(itag),"quality":lbl,"ext":"mp4",
                "height":int(lbl[:-1]),"fps":fps,"bitrate":bitrate,
                "filesize":_fmt_size(fsize),"filesize_bytes":fsize,
                "url":url,"has_audio":True,"mime":mime})
        elif is_a:
            abr = int(f.get("averageBitrate") or bitrate or 0)
            afmts.append({"format_id":str(itag),
                "quality":f"{round(abr/1000)} kbps" if abr else "audio",
                "ext":"m4a" if "mp4a" in mime else "webm","bitrate":abr,
                "filesize":_fmt_size(fsize),"filesize_bytes":fsize,
                "url":url,"mime":mime})
    vfmts.sort(key=lambda x: -(x.get("height") or 0))
    afmts.sort(key=lambda x: -(x.get("bitrate") or 0))
    return vfmts, afmts


# ── Public API ────────────────────────────────────────────────────
async def get_video_info(video_id: str) -> dict:
    if not re.match(r'^[0-9A-Za-z_-]{11}$', video_id):
        video_id = _extract_video_id(video_id)
    if not video_id:
        raise ValueError("Invalid YouTube video ID or URL.")

    async with httpx.AsyncClient(follow_redirects=True) as http:
        oembed    = await _fetch_oembed(video_id, http)
        title     = oembed.get("title", "")
        channel   = oembed.get("author_name", "")
        thumbnail = oembed.get("thumbnail_url", "")
        if not title:
            raise RuntimeError("Video not found, private, or deleted.")
        logger.info(f"[oembed] '{title[:50]}' by {channel}")

        data = await _try_player(video_id, http)
        if not data:
            raise RuntimeError(
                "Could not fetch stream URLs. "
                "For Shorts: add YouTube cookies to cookies.txt in the backend folder."
            )

        det      = data.get("videoDetails", {})
        duration = _fmt_duration(det.get("lengthSeconds", 0))
        views    = _fmt_views(det.get("viewCount", 0))
        thumbs   = det.get("thumbnail", {}).get("thumbnails", [])
        if thumbs: thumbnail = thumbs[-1]["url"]
        vf, af   = _parse_formats(data)

        return {
            "video_id":      video_id,
            "title":         title or det.get("title", "Untitled"),
            "channel":       channel or det.get("author", "Unknown"),
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
    async with httpx.AsyncClient(follow_redirects=True) as http:
        data = await _try_player(video_id, http)
        if not data: raise RuntimeError("Could not resolve audio stream.")
        _, af = _parse_formats(data)
        if not af: raise RuntimeError("No audio formats found.")
        m4a  = next((a for a in af if "mp4a" in a.get("mime", "")), None)
        return (m4a or af[0])["url"], (m4a or af[0])["mime"]


async def get_playlist_videos(playlist_id: str) -> list[dict]:
    async with httpx.AsyncClient(follow_redirects=True) as http:
        cookie_hdr = _cookies()
        payload = {
            "browseId": f"VL{playlist_id}",
            "context":  {"client": {"hl":"en","gl":"US","clientName":"WEB","clientVersion":"2.20240726.00.00"}},
        }
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
            "X-YouTube-Client-Name": "1",
            "X-YouTube-Client-Version": "2.20240726.00.00",
            "Origin":  "https://www.youtube.com",
            "Referer": "https://www.youtube.com/",
            **cookie_hdr,
        }
        try:
            r = await http.post(
                "https://www.youtube.com/youtubei/v1/browse",
                json=payload, headers=headers, timeout=20.0)
            if r.status_code != 200:
                raise RuntimeError(f"YouTube returned {r.status_code}")
            data = r.json()
        except Exception as e:
            raise RuntimeError(f"Failed to fetch playlist: {e}")

        videos: list[dict] = []
        try:
            contents = (
                data.get("contents", {})
                    .get("twoColumnBrowseResultsRenderer", {})
                    .get("tabs", [{}])[0]
                    .get("tabRenderer", {})
                    .get("content", {})
                    .get("sectionListRenderer", {})
                    .get("contents", [{}])[0]
                    .get("itemSectionRenderer", {})
                    .get("contents", [{}])[0]
                    .get("playlistVideoListRenderer", {})
                    .get("contents", [])
            )
            for item in contents:
                v = item.get("playlistVideoRenderer", {})
                if not v: continue
                vid_id = v.get("videoId", "")
                if not vid_id: continue
                title  = v.get("title", {}).get("runs", [{}])[0].get("text", "")
                thumbs = v.get("thumbnail", {}).get("thumbnails", [])
                thumb  = thumbs[-1]["url"] if thumbs else ""
                length = v.get("lengthSeconds", "0")
                owner  = (v.get("shortBylineText", {}).get("runs", [{}]) or [{}])[0].get("text", "")
                videos.append({"video_id":vid_id,"title":title,
                    "thumbnail":thumb,"duration":_fmt_duration(length),"channel":owner})
        except Exception as e:
            logger.warning(f"[playlist parse] {e}")

        if not videos:
            raise RuntimeError("No videos found in playlist. It may be private or empty.")
        return videos