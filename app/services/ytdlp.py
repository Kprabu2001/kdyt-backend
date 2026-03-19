# services/ytdlp.py

import asyncio
import json
import logging
import os
import tempfile
from typing import AsyncGenerator

from app.core.config import get_settings
from app.models.video import VideoFormat, VideoInfo
from app.utils.formatters import (
    format_duration,
    format_filesize,
    format_views,
    sanitize_filename,
)

logger = logging.getLogger(__name__)

_AUDIO_QUALITY_MAP: dict[str, str] = {
    "320kbps": "0",
    "192kbps": "3",
    "128kbps": "5",
}

_STATIC_AUDIO_FORMATS: list[VideoFormat] = [
    VideoFormat(format_id="320kbps", quality="320 kbps", ext="mp3"),
    VideoFormat(format_id="192kbps", quality="192 kbps", ext="mp3"),
    VideoFormat(format_id="128kbps", quality="128 kbps", ext="mp3"),
]


def _base_args() -> list[str]:
    """
    bgutil-ytdlp-pot-provider plugin auto-supplies PO tokens via HTTP server
    running on 127.0.0.1:4416 — no manual extractor-args needed.
    """
    cfg = get_settings()
    args = [
        "--no-check-certificates",
        "--no-warnings",
        "--add-header",
        "User-Agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "--extractor-args", "youtube:player_client=android",
        "--sleep-interval", "3",
        "--max-sleep-interval", "6",
    ]
     # optional cookies
    if getattr(cfg, "use_cookies", False) and cfg.resolved_cookies_file:
        args += ["--cookies", cfg.resolved_cookies_file]

    return args
    # if cfg.resolved_cookies_file and os.path.isfile(cfg.resolved_cookies_file):
    #     args += ["--cookies", cfg.resolved_cookies_file]
    # if cfg.ytdlp_proxy:
    #     args += ["--proxy", cfg.ytdlp_proxy]
    # return args


async def _run(*args: str, timeout: int | None = None) -> str:
    cfg    = get_settings()
    binary = cfg.resolved_ytdlp_binary
    t      = timeout or cfg.ytdlp_timeout

    proc = await asyncio.create_subprocess_exec(
        binary, *_base_args(), *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=t)
    except asyncio.TimeoutError:
        proc.kill()
        raise

    out_msg = stdout.decode(errors="replace").strip()
    err_msg = stderr.decode(errors="replace").strip()

    if err_msg:
        logger.warning(f"yt-dlp stderr: {err_msg[:400]}")

    if proc.returncode != 0 or not out_msg:
        raise RuntimeError(err_msg or out_msg or f"yt-dlp exited with code {proc.returncode} and no output")

    return out_msg


async def _stream_subprocess(args: list[str]) -> AsyncGenerator[bytes, None]:
    cfg  = get_settings()
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        while chunk := await proc.stdout.read(cfg.chunk_size):
            yield chunk
    except asyncio.CancelledError:
        proc.kill()
        raise
    finally:
        try:
            proc.kill()
        except ProcessLookupError:
            pass


async def get_video_info(url: str) -> VideoInfo:
    raw  = await _run("--dump-json", "--no-playlist",
                      "--format", "bestvideo+bestaudio/best",
                      url)
    info = json.loads(raw)

    seen:          set[str]          = set()
    video_formats: list[VideoFormat] = []
    cfg = get_settings()

    for fmt in sorted(info.get("formats", []), key=lambda f: -(f.get("height") or 0)):
        has_video = fmt.get("vcodec", "none") != "none"
        height    = fmt.get("height")

        if not (has_video and height):
            continue

        # Skip formats that require a protocol not available on server
        protocol = fmt.get("protocol", "")
        if protocol in ("rtmp", "rtmpe", "m3u8_native") :
            continue

        fps       = fmt.get("fps") or 0
        fps_label = str(int(fps)) if fps >= 48 else ""
        label     = f"{height}p{fps_label}"

        if label not in seen:
            seen.add(label)
            video_formats.append(VideoFormat(
                format_id=f"{fmt['format_id']}|{height}",
                quality=label,
                ext="mp4",
                filesize=format_filesize(fmt.get("filesize") or fmt.get("filesize_approx")),
            ))

        if len(video_formats) >= cfg.max_video_formats:
            break

    if not video_formats:
        video_formats = [VideoFormat(
            format_id="bestvideo+bestaudio/best",
            quality="Best",
            ext="mp4",
        )]

    return VideoInfo(
        title=info.get("title", "Untitled"),
        channel=info.get("uploader") or info.get("channel", "Unknown"),
        thumbnail=info.get("thumbnail", ""),
        duration=format_duration(info.get("duration")),
        views=format_views(info.get("view_count")),
        video_formats=video_formats,
        audio_formats=_STATIC_AUDIO_FORMATS,
    )


async def get_safe_filename(url: str) -> str:
    try:
        title = await asyncio.wait_for(_run("--get-title", url), timeout=15)
        return sanitize_filename(title)
    except Exception:
        return "download"


async def prepare_video(url: str, format_id: str) -> tuple[str, str, int]:
    """
    Download video+audio to a temp file.
    Returns (tmp_dir_path, file_path, file_size_bytes).
    Caller must delete the temp directory when done.
    """
    cfg    = get_settings()
    raw_id = format_id.split("|")[0]
    height = format_id.split("|")[1] if "|" in format_id else None

    if height:
        fmt_selector = (
            f"{raw_id}+bestaudio[ext=m4a]/"
            f"{raw_id}+bestaudio/"
            f"bestvideo[height={height}]+bestaudio[ext=m4a]/"
            f"bestvideo[height={height}]+bestaudio/"
            f"best[height={height}]/best"
        )
    else:
        fmt_selector = f"{raw_id}+bestaudio[ext=m4a]/{raw_id}+bestaudio/best"

    tmpdir   = tempfile.mkdtemp()
    out_path = os.path.join(tmpdir, "video.mp4")

    args = [
        cfg.resolved_ytdlp_binary,
        *_base_args(),
        "-f", fmt_selector,
        "--merge-output-format", "mp4",
        "-o", out_path,
        "--no-playlist",
        "--quiet",
        "--no-part",
        url,
    ]

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )

    _, stderr = await asyncio.wait_for(
        proc.communicate(),
        timeout=cfg.ytdlp_download_timeout,
    )

    if proc.returncode != 0 or not os.path.exists(out_path):
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
        err = stderr.decode(errors="replace").strip()
        raise RuntimeError(f"yt-dlp failed: {err[:300]}")

    return tmpdir, out_path, os.path.getsize(out_path)


async def stream_video(tmpdir: str, out_path: str) -> AsyncGenerator[bytes, None]:
    """Stream a prepared video file and clean up the temp dir when done."""
    cfg = get_settings()
    try:
        with open(out_path, "rb") as fh:
            while chunk := fh.read(cfg.chunk_size):
                yield chunk
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


async def stream_audio(url: str, format_id: str) -> AsyncGenerator[bytes, None]:
    """
    Windows-compatible two-process pipeline.

    On Linux/macOS you can pass ytdlp_proc.stdout directly as ffmpeg stdin,
    but on Windows asyncio StreamReader has no .fileno() so that fails.
    Instead we use asyncio.subprocess.PIPE for ffmpeg stdin and pump data
    between the two processes manually via a background writer task.
    """
    cfg     = get_settings()
    quality = _AUDIO_QUALITY_MAP.get(format_id, "0")

    ytdlp_args = [
        cfg.resolved_ytdlp_binary,
        *_base_args(),
        "-f", "bestaudio/best",
        "-o", "-",
        "--no-playlist",
        "--quiet",
        url,
    ]

    ffmpeg_args = [
        "ffmpeg",
        "-loglevel", "error",
        "-i", "pipe:0",
        "-vn",
        "-acodec", "libmp3lame",
        "-q:a", quality,
        "-f", "mp3",
        "pipe:1",
    ]

    ytdlp_proc = await asyncio.create_subprocess_exec(
        *ytdlp_args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )

    # Use asyncio.subprocess.PIPE for stdin — works on Windows
    ffmpeg_proc = await asyncio.create_subprocess_exec(
        *ffmpeg_args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )

    async def _pump() -> None:
        """Read yt-dlp stdout and write it into ffmpeg stdin."""
        try:
            while True:
                chunk = await ytdlp_proc.stdout.read(cfg.chunk_size)
                if not chunk:
                    break
                ffmpeg_proc.stdin.write(chunk)
                await ffmpeg_proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            try:
                ffmpeg_proc.stdin.close()
            except Exception:
                pass

    pump_task = asyncio.create_task(_pump())

    try:
        while chunk := await ffmpeg_proc.stdout.read(cfg.chunk_size):
            yield chunk
    except asyncio.CancelledError:
        pump_task.cancel()
        ytdlp_proc.kill()
        ffmpeg_proc.kill()
        raise
    finally:
        pump_task.cancel()
        for proc in (ytdlp_proc, ffmpeg_proc):
            try:
                proc.kill()
            except ProcessLookupError:
                pass

async def get_filesize(url: str, format_id: str, type: str) -> int | None:
    """Return the best-effort byte size of a format, or None if unavailable."""
    try:
        if type == "audio":
            fmt = "bestaudio/best"
        else:
            # Strip the |height suffix before passing to yt-dlp
            raw_id = format_id.split("|")[0]
            height = format_id.split("|")[1] if "|" in format_id else None
            if height:
                fmt = (
                    f"{raw_id}+bestaudio[ext=m4a]/"
                    f"{raw_id}+bestaudio/"
                    f"bestvideo[height={height}]+bestaudio/best"
                )
            else:
                fmt = f"{raw_id}+bestaudio/best"

        raw = await asyncio.wait_for(
            _run(
                "--no-playlist",
                "-f", fmt,
                "--print", "%(filesize,filesize_approx)s",
                url,
            ),
            timeout=12,
        )
        size = int(raw.strip().split("\n")[0])
        return size if size > 0 else None
    except Exception:
        return None