# app/api/endpoints/tunnel.py
import logging
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from app.core.limiter import limiter
from app.services.innertube import get_video_info
from app.utils.validators import sanitize_filename

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/tunnel", tags=["tunnel"])
@limiter.limit("60/15minutes")
async def get_tunnel_url(
    request:   Request,
    video_id:  str = Query(..., min_length=11, max_length=11),
    format_id: str = Query(...),
    type:      str = Query(..., pattern="^(video|audio)$"),
):
    import re
    if not re.match(r'^[0-9A-Za-z_-]{11}$', video_id):
        raise HTTPException(status_code=400, detail="Invalid video ID.")

    if type == "audio":
        return {"type": "audio_job"}

    try:
        info = await get_video_info(video_id)
        fmt  = next((f for f in info["video_formats"] if f["format_id"] == format_id), None)
        if not fmt:
            raise HTTPException(status_code=404, detail=f"Format '{format_id}' not found.")

        video_url = fmt["url"]
        if not video_url:
            raise HTTPException(status_code=502, detail="No CDN URL for this format.")

        raw_audio = info.get("_raw_audio", [])
        audio_url = ""
        if raw_audio and not fmt.get("has_audio"):
            m4a = next((a for a in raw_audio if "mp4a" in a.get("mime", "")), None)
            audio_url = (m4a or raw_audio[0])["url"] if (m4a or raw_audio) else ""

        filename = sanitize_filename(info["title"])

        # If video has its own audio (has_audio=True), redirect directly — like vidssave
        if fmt.get("has_audio") or not audio_url:
            return RedirectResponse(
                url=video_url,
                status_code=302,
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}.mp4"',
                    "Access-Control-Allow-Origin": "*",
                }
            )

        # Split video+audio — return URLs for frontend to handle muxing
        return {
            "type":      "split",
            "url":       video_url,
            "audio_url": audio_url,
            "filename":  filename,
            "filesize":  fmt.get("filesize_bytes") or 0,
            "quality":   fmt["quality"],
            "needs_mux": True,
        }

    except HTTPException:
        raise
    except RuntimeError as exc:
        msg = str(exc)
        logger.error(f"[tunnel] {msg[:200]}")
        raise HTTPException(status_code=502, detail=f"YouTube error: {msg[:300]}")
    except Exception as exc:
        logger.error(f"[tunnel] unexpected: {repr(exc)}")
        raise HTTPException(status_code=500, detail=str(exc)[:200])