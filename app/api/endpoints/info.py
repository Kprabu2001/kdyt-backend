# app/api/endpoints/info.py

import logging

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.limiter import limiter
from app.models.video import VideoInfo
from app.services import ytdlp
from app.utils.validators import is_valid_youtube_url

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/info",
    response_model=VideoInfo,
    tags=["downloader"],
    summary="Fetch video info",
)
@limiter.limit("30/15minutes")
async def get_info(
    request: Request,
    url: str = Query(..., description="Full YouTube video URL"),
) -> VideoInfo:
    if not is_valid_youtube_url(url):
        raise HTTPException(
            status_code=400,
            detail="Invalid URL. Only YouTube links (youtube.com, youtu.be) are accepted.",
        )

    try:
        return await ytdlp.get_video_info(url)

    except RuntimeError as exc:
        msg = str(exc).strip()
        logger.error(f"yt-dlp error: {repr(msg)}")
        msg_lower = msg.lower()

        if "private video" in msg_lower:
            raise HTTPException(status_code=400, detail="This video is private.")
        if "video unavailable" in msg_lower or "not available" in msg_lower:
            raise HTTPException(status_code=400, detail="This video is unavailable.")
        if "age" in msg_lower and "restricted" in msg_lower:
            raise HTTPException(status_code=400, detail="Age-restricted videos are not supported.")

        # Show the real yt-dlp error so it's visible in the UI for debugging
        detail = f"yt-dlp error: {msg[:500]}" if msg else (
            "YouTube is blocking requests from this server. "
            "Make sure yt-dlp is up to date: pip install -U yt-dlp"
        )
        raise HTTPException(status_code=502, detail=detail)

    except TimeoutError:
        raise HTTPException(status_code=504, detail="Request timed out. Please try again.")

    except Exception as exc:
        logger.error(f"Unexpected error: {repr(exc)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(exc)[:500]}")