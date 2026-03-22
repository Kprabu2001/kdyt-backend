# app/api/endpoints/info.py
import logging
from fastapi import APIRouter, HTTPException, Query, Request
from app.core.limiter import limiter
from app.services.innertube import get_video_info

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/info", tags=["downloader"])
@limiter.limit("30/15minutes")
async def get_info(
    request:  Request,
    video_id: str = Query(..., min_length=11, max_length=11),
):
    import re
    if not re.match(r'^[0-9A-Za-z_-]{11}$', video_id):
        raise HTTPException(status_code=400, detail="Invalid video ID.")
    try:
        data = await get_video_info(video_id)
        return {
            "video_id":      data["video_id"],
            "title":         data["title"],
            "channel":       data["channel"],
            "thumbnail":     data["thumbnail"],
            "duration":      data["duration"],
            "views":         data["views"],
            "video_formats": data["video_formats"],
            "audio_formats": data["audio_formats"],
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        msg = str(exc)
        logger.error(f"[info] {msg[:200]}")
        ml = msg.lower()
        if "private" in ml or "deleted" in ml or "not found" in ml:
            raise HTTPException(status_code=400, detail="Video not found, private, or deleted.")
        if "login" in ml or "age" in ml or "restricted" in ml or "sign in" in ml or "bot" in ml:
            raise HTTPException(status_code=503, detail="YouTube blocked this request (bot detection). Try again or refresh cookies.")
        raise HTTPException(status_code=502, detail="Unable to fetch video. Please try again later.")
    except Exception as exc:
        logger.error(f"[info] unexpected: {repr(exc)}")
        raise HTTPException(status_code=500, detail=str(exc)[:200])