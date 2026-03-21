# app/api/endpoints/playlist.py
# GET /api/playlist?list_id=PLxxxxxx
# Returns playlist title + list of videos

import logging
import re
from fastapi import APIRouter, HTTPException, Query, Request
from app.core.limiter import limiter
from app.services.innertube import get_playlist_videos

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/playlist", tags=["playlist"])
@limiter.limit("20/15minutes")
async def get_playlist(
    request: Request,
    list_id: str = Query(..., description="YouTube playlist ID"),
):
    if not re.match(r'^[0-9A-Za-z_-]+$', list_id) or len(list_id) > 50:
        raise HTTPException(status_code=400, detail="Invalid playlist ID.")
    try:
        videos = await get_playlist_videos(list_id)
        return {"list_id": list_id, "count": len(videos), "videos": videos}
    except RuntimeError as exc:
        msg = str(exc)
        logger.error(f"[playlist] {msg[:200]}")
        raise HTTPException(status_code=502, detail=msg[:300])
    except Exception as exc:
        logger.error(f"[playlist] unexpected: {repr(exc)}")
        raise HTTPException(status_code=500, detail=str(exc)[:200])