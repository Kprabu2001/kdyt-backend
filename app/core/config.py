# app/core/config.py

import logging
import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


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