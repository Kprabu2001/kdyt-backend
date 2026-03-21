# app/core/config.py
import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    host:  str = "0.0.0.0"
    port:  int = 8000

    allowed_origins: str = "http://localhost:5173,https://kdyt.vercel.app"

    # Rate limits
    rate_limit_info:     str = "30/15minutes"
    rate_limit_tunnel:   str = "60/15minutes"
    rate_limit_download: str = "25/hour"

    # Processing
    chunk_size:          int = 65536
    innertube_timeout:   int = 20
    audio_job_timeout:   int = 300

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
