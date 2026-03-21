# app/services/audio.py
#
# Audio transcoding: fetch best native audio stream URL (via InnerTube),
# then pipe through ffmpeg to produce MP3 at the requested bitrate.
# No yt-dlp involved at all.

import asyncio
import logging
import os
import tempfile
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

_QUALITY_MAP = {"320kbps": "0", "192kbps": "3", "128kbps": "5"}

_CHUNK = 65536


async def stream_mp3(
    audio_url: str,
    audio_mime: str,
    quality_id: str,
) -> AsyncGenerator[bytes, None]:
    """
    Stream MP3 audio by piping the native audio URL through ffmpeg.
    audio_url  : direct CDN URL from InnerTube (m4a or webm/opus)
    audio_mime : MIME type of the stream (used to choose ffmpeg input format)
    quality_id : "320kbps" | "192kbps" | "128kbps"
    """
    q = _QUALITY_MAP.get(quality_id, "0")

    # ffmpeg reads from the CDN URL directly via -i <url>
    # This means ffmpeg makes the HTTP request — not our server
    ffmpeg_args = [
        "ffmpeg",
        "-loglevel", "error",
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "5",
        "-i", audio_url,       # direct CDN URL
        "-vn",                 # no video
        "-acodec", "libmp3lame",
        "-q:a", q,
        "-f", "mp3",
        "pipe:1",              # output to stdout
    ]

    proc = await asyncio.create_subprocess_exec(
        *ffmpeg_args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        while chunk := await proc.stdout.read(_CHUNK):
            yield chunk
    except asyncio.CancelledError:
        proc.kill()
        raise
    finally:
        try:
            proc.kill()
        except ProcessLookupError:
            pass


async def prepare_mp3_file(
    audio_url: str,
    audio_mime: str,
    quality_id: str,
    filename: str,
) -> tuple[str, str, int]:
    """
    Download and transcode to MP3, save to temp file.
    Returns (tmpdir, file_path, file_size_bytes).
    Caller must clean up tmpdir.
    """
    q = _QUALITY_MAP.get(quality_id, "0")
    tmpdir   = tempfile.mkdtemp()
    out_path = os.path.join(tmpdir, f"{filename}.mp3")

    ffmpeg_args = [
        "ffmpeg",
        "-loglevel", "error",
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "5",
        "-i", audio_url,
        "-vn",
        "-acodec", "libmp3lame",
        "-q:a", q,
        out_path,
        "-y",
    ]

    proc = await asyncio.create_subprocess_exec(
        *ffmpeg_args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
    except asyncio.TimeoutError:
        proc.kill()
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise RuntimeError("ffmpeg timed out during audio conversion")

    if proc.returncode != 0 or not os.path.exists(out_path):
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
        err = stderr.decode(errors="replace").strip()
        raise RuntimeError(f"ffmpeg failed: {err[:300]}")

    return tmpdir, out_path, os.path.getsize(out_path)
