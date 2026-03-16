# app/api/endpoints/download.py
# GET /api/download — stream an MP4 or MP3 file directly to the client.
# No temp files are created; everything is piped through from yt-dlp.

import logging

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.core.limiter import limiter
from app.services import ytdlp
from app.utils.validators import is_valid_youtube_url

logger = logging.getLogger(__name__)

router = APIRouter()

# Map type param → (file extension, MIME type)
_FORMAT_META: dict[str, tuple[str, str]] = {
    "video": ("mp4", "video/mp4"),
    "audio": ("mp3", "audio/mpeg"),
}


@router.get(
    "/download",
    tags=["downloader"],
    summary="Download video or audio",
    description=(
        "Stream an MP4 video or MP3 audio file directly to the browser. "
        "The file is never stored on the server — it is piped in real time. "
        "Rate-limited to 25 downloads per hour per IP."
    ),
)
@limiter.limit("25/hour")
async def download(
    request:   Request,
    url:       str = Query(..., description="Full YouTube video URL"),
    format_id: str = Query(..., description="yt-dlp format ID from /api/info"),
    type:      str = Query(..., pattern="^(video|audio)$", description="'video' or 'audio'"),
) -> StreamingResponse:

    if not is_valid_youtube_url(url):
        raise HTTPException(status_code=400, detail="Invalid URL.")

    if type not in _FORMAT_META:
        raise HTTPException(status_code=400, detail="type must be 'video' or 'audio'.")

    ext, mime = _FORMAT_META[type]

    filename = await ytdlp.get_safe_filename(url)

    headers = {
        "Content-Disposition":    f'attachment; filename="{filename}.{ext}"',
        "Cache-Control":          "no-cache, no-store, must-revalidate",
        "X-Content-Type-Options": "nosniff",
        "Access-Control-Expose-Headers": "Content-Length, Content-Type, Content-Disposition",
    }

    if type == "audio":
        # Audio is transcoded by ffmpeg — size unknown until complete,
        # so no Content-Length (indeterminate progress bar on frontend)
        generator = ytdlp.stream_audio(url, format_id)

    else:
        # Video is downloaded to a temp file before streaming, so we
        # know the exact final size — send real Content-Length for
        # true progress percentage on the frontend
        tmpdir, out_path, filesize = await ytdlp.prepare_video(url, format_id)
        headers["Content-Length"] = str(filesize)
        generator = ytdlp.stream_video(tmpdir, out_path)

    return StreamingResponse(
        generator,
        media_type=mime,
        headers=headers,
    )