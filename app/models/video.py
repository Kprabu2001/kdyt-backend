# app/models/video.py
# Pydantic models that define the JSON shapes returned by the API.
# These are the contract between backend and frontend — change carefully.

from typing import Optional

from pydantic import BaseModel, HttpUrl


class VideoFormat(BaseModel):
    """A single downloadable format option (e.g. 1080p MP4 or 320kbps MP3)."""

    format_id: str            # yt-dlp internal format ID, passed back to /api/download
    quality:   str            # Human-readable label shown in the UI, e.g. "1080p", "320 kbps"
    ext:       str            # File extension: "mp4" or "mp3"
    filesize:  Optional[str] = None  # Human-readable size string, e.g. "128 MB" — may be None


class VideoInfo(BaseModel):
    """Full metadata + available formats for a YouTube video."""

    title:          str
    channel:        str
    thumbnail:      str               # Direct URL to the video thumbnail image
    duration:       str               # Formatted string, e.g. "3:45" or "1:02:30"
    views:          str               # Formatted string, e.g. "1.4M" or "823K"
    video_formats:  list[VideoFormat] # MP4 options, sorted highest quality first
    audio_formats:  list[VideoFormat] # MP3 options (fixed set: 320/192/128 kbps)


class HealthResponse(BaseModel):
    """Response body for GET /api/health."""

    status: str
