# app/api/endpoints/jobs.py
# Job-based download system:
#   POST /api/jobs          — create a job, start background preparation
#   GET  /api/jobs/{id}     — poll status (pending → preparing → ready → error)
#   GET  /api/jobs/{id}/file — stream the prepared file (only when ready)

import asyncio
import logging
import os
import shutil
import uuid
from enum import Enum
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.limiter import limiter
from app.services import ytdlp
from app.utils.validators import is_valid_youtube_url

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Job store (in-memory) ─────────────────────────────────────────
class JobStatus(str, Enum):
    PENDING    = "pending"
    PREPARING  = "preparing"
    READY      = "ready"
    ERROR      = "error"

class Job(BaseModel):
    id:        str
    status:    JobStatus = JobStatus.PENDING
    progress:  int       = 0          # 0-100 preparation progress
    error:     str       = ""
    tmpdir:    str       = ""
    out_path:  str       = ""
    filesize:  int       = 0
    filename:  str       = "download"
    mime:      str       = "application/octet-stream"
    ext:       str       = "mp4"

_jobs: dict[str, Job] = {}

_FORMAT_META = {
    "video": ("mp4", "video/mp4"),
    "audio": ("mp3", "audio/mpeg"),
}

# ── Background task ───────────────────────────────────────────────
async def _prepare(job_id: str, url: str, format_id: str, type_: str) -> None:
    job = _jobs.get(job_id)
    if not job:
        return

    job.status   = JobStatus.PREPARING
    job.progress = 5

    try:
        cfg = get_settings()

        # Get filename
        job.filename = await ytdlp.get_safe_filename(url)
        job.progress = 10

        if type_ == "audio":
            # Audio: use ffmpeg pump pipeline, collect all bytes into temp file
            job.progress = 15
            tmpdir   = shutil.os.path.join(shutil.os.path.dirname(
                           shutil.os.path.abspath(__file__)), "..", "..", "..", "tmp")
            import tempfile
            tmpdir   = tempfile.mkdtemp()
            out_path = os.path.join(tmpdir, f"{job.filename}.mp3")

            chunks = []
            async for chunk in ytdlp.stream_audio(url, format_id):
                chunks.append(chunk)
                # fake progress 15→90 while collecting
                job.progress = min(90, job.progress + 1)

            with open(out_path, "wb") as fh:
                for c in chunks:
                    fh.write(c)

            job.tmpdir   = tmpdir
            job.out_path = out_path
            job.filesize = os.path.getsize(out_path)
            job.mime     = "audio/mpeg"
            job.ext      = "mp3"

        else:
            # Video: prepare_video downloads to temp file with real progress
            job.progress = 20
            tmpdir, out_path, filesize = await ytdlp.prepare_video(url, format_id)
            job.tmpdir   = tmpdir
            job.out_path = out_path
            job.filesize = filesize
            job.mime     = "video/mp4"
            job.ext      = "mp4"
            job.progress = 95

        job.progress = 100
        job.status   = JobStatus.READY

    except Exception as exc:
        logger.error(f"Job {job_id} failed: {exc}")
        job.status = JobStatus.ERROR
        job.error  = str(exc)[:300]
        # cleanup
        if job.tmpdir and os.path.isdir(job.tmpdir):
            shutil.rmtree(job.tmpdir, ignore_errors=True)


# ── Endpoints ─────────────────────────────────────────────────────

class CreateJobRequest(BaseModel):
    url:       str
    format_id: str
    type:      str  # "video" | "audio"

@router.post("/jobs", tags=["jobs"])
@limiter.limit("25/hour")
async def create_job(
    request:          Request,
    background_tasks: BackgroundTasks,
    url:       str = Query(...),
    format_id: str = Query(...),
    type:      str = Query(..., pattern="^(video|audio)$"),
):
    if not is_valid_youtube_url(url):
        raise HTTPException(status_code=400, detail="Invalid URL.")
    if type not in _FORMAT_META:
        raise HTTPException(status_code=400, detail="type must be video or audio.")

    job_id      = str(uuid.uuid4())
    _jobs[job_id] = Job(id=job_id)

    background_tasks.add_task(_prepare, job_id, url, format_id, type)

    return {"job_id": job_id}


@router.get("/jobs/{job_id}", tags=["jobs"])
async def get_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {
        "job_id":   job.id,
        "status":   job.status,
        "progress": job.progress,
        "error":    job.error,
        "filesize": job.filesize,
    }


@router.get("/jobs/{job_id}/file", tags=["jobs"])
async def download_job_file(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status != JobStatus.READY:
        raise HTTPException(status_code=409, detail="File not ready yet.")
    if not os.path.exists(job.out_path):
        raise HTTPException(status_code=410, detail="File expired.")

    cfg = get_settings()

    async def _stream():
        try:
            with open(job.out_path, "rb") as fh:
                while chunk := fh.read(cfg.chunk_size):
                    yield chunk
        finally:
            shutil.rmtree(job.tmpdir, ignore_errors=True)
            _jobs.pop(job_id, None)

    return StreamingResponse(
        _stream(),
        media_type=job.mime,
        headers={
            "Content-Disposition":           f'attachment; filename="{job.filename}.{job.ext}"',
            "Content-Length":                str(job.filesize),
            "Cache-Control":                 "no-cache, no-store, must-revalidate",
            "Access-Control-Expose-Headers": "Content-Length, Content-Disposition, Content-Type",
        },
    )