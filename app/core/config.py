# app/core/config.py

import base64
import logging
import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Path where we write cookies decoded from the env-var
_RUNTIME_COOKIES_PATH = "/tmp/yt_cookies.txt"


def write_cookies_from_env() -> str | None:
    """
    Decode YTDLP_COOKIES_B64 (base64-encoded Netscape cookies.txt) and write
    it to _RUNTIME_COOKIES_PATH.  Returns the path on success, None otherwise.
    Call this at startup AND periodically to keep the file fresh.
    """
    b64 = os.environ.get("YTDLP_COOKIES_B64", "").strip()
    if not b64:
        return None
    try:
        decoded = base64.b64decode(b64).decode("utf-8")
        os.makedirs(os.path.dirname(_RUNTIME_COOKIES_PATH), exist_ok=True)
        with open(_RUNTIME_COOKIES_PATH, "w", encoding="utf-8") as fh:
            fh.write(decoded)
        logger.info(f"[cookies] Written {len(decoded)} bytes → {_RUNTIME_COOKIES_PATH}")
        return _RUNTIME_COOKIES_PATH
    except Exception as exc:
        logger.error(f"[cookies] Failed to decode/write YTDLP_COOKIES_B64: {exc}")
        return None


def _find_ytdlp() -> str:
    import sys
    candidates = [
        os.path.join(os.path.dirname(sys.executable), "Scripts", "yt-dlp.exe"),
        os.path.join(os.path.dirname(sys.executable), "yt-dlp.exe"),
        os.path.expanduser(r"~\AppData\Local\Programs\Python\Python312\Scripts\yt-dlp.exe"),
        os.path.expanduser(r"~\AppData\Local\Programs\Python\Python311\Scripts\yt-dlp.exe"),
        os.path.expanduser(r"~\AppData\Local\Programs\Python\Python310\Scripts\yt-dlp.exe"),
        os.path.expanduser(r"~\AppData\Roaming\Python\Python312\Scripts\yt-dlp.exe"),
        os.path.expanduser(r"~\AppData\Roaming\Python\Python311\Scripts\yt-dlp.exe"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            logger.info(f"Auto-detected yt-dlp at: {path}")
            return path
    logger.warning("yt-dlp not found in common paths, falling back to 'yt-dlp'")
    return "yt-dlp"


class Settings(BaseSettings):
    # ── Server ────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000

    # ── CORS ──────────────────────────────────────────────────────
    allowed_origins: str = "*"

    # ── yt-dlp ────────────────────────────────────────────────────
    ytdlp_binary:           str = ""
    ytdlp_timeout:          int = 45
    ytdlp_download_timeout: int = 600
    ytdlp_proxy:            str = ""   # optional: "socks5://127.0.0.1:1080"
    ytdlp_cookies_file:     str = ""   # Explicit file path (overrides b64)
    ytdlp_cookies_b64:      str = ""   # Base64-encoded cookies.txt (for Render)
    ytdlp_cookies_browser:  str = ""   # Local dev:  "chrome" or "firefox"

    # ── Rate limits ───────────────────────────────────────────────
    rate_limit_info:     str = "30/15minutes"
    rate_limit_download: str = "25/hour"

    # ── Processing ────────────────────────────────────────────────
    max_video_formats: int = 6
    chunk_size:        int = 65536

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def resolved_cookies_file(self) -> str:
        """
        Priority:
        1. YTDLP_COOKIES_FILE – explicit path that already exists on disk
        2. YTDLP_COOKIES_B64  – decode to /tmp and return that path
        3. /app/cookies.txt   – bundled fallback inside the Docker image
        """
        if self.ytdlp_cookies_file and os.path.isfile(self.ytdlp_cookies_file):
            return self.ytdlp_cookies_file
        if os.environ.get("YTDLP_COOKIES_B64", "").strip():
            path = write_cookies_from_env()
            if path:
                return path
        bundled = "/app/cookies.txt"
        if os.path.isfile(bundled):
            return bundled
        return ""

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def resolved_ytdlp_binary(self) -> str:
        if self.ytdlp_binary and os.path.isfile(self.ytdlp_binary):
            return self.ytdlp_binary
        if self.ytdlp_binary and self.ytdlp_binary != "yt-dlp":
            logger.warning(
                f"YTDLP_BINARY='{self.ytdlp_binary}' not found — auto-detecting."
            )
        return _find_ytdlp()


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    logger.warning(f"[config] ytdlp_binary (raw)     = '{s.ytdlp_binary}'")
    logger.warning(f"[config] ytdlp_binary (resolved) = '{s.resolved_ytdlp_binary}'")
    logger.warning(f"[config] proxy                   = '{s.ytdlp_proxy}'")
    return s