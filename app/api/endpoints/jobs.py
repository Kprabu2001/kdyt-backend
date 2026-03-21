# app/api/endpoints/jobs.py — audio only, uses video_id
import asyncio, logging, os, shutil, uuid
from enum import Enum
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.core.config import get_settings
from app.core.limiter import limiter
from app.services.innertube import get_best_audio_url, get_video_info
from app.services.audio import prepare_mp3_file
from app.utils.validators import sanitize_filename

logger = logging.getLogger(__name__)
router = APIRouter()


class JobStatus(str, Enum):
    PENDING   = "pending"
    PREPARING = "preparing"
    READY     = "ready"
    ERROR     = "error"


class Job(BaseModel):
    id:       str
    status:   JobStatus = JobStatus.PENDING
    progress: int = 0
    error:    str = ""
    tmpdir:   str = ""
    out_path: str = ""
    filesize: int = 0
    filename: str = "audio"


_jobs: dict[str, Job] = {}


async def _run_audio_job(job_id: str, video_id: str, quality_id: str) -> None:
    job = _jobs.get(job_id)
    if not job: return
    job.status = JobStatus.PREPARING
    job.progress = 5
    try:
        try:
            info = await get_video_info(video_id)
            job.filename = sanitize_filename(info["title"])
        except Exception:
            job.filename = "audio"
        job.progress = 15

        audio_url, audio_mime = await get_best_audio_url(video_id)
        job.progress = 25

        cfg = get_settings()
        tmpdir, out_path, filesize = await asyncio.wait_for(
            prepare_mp3_file(audio_url, audio_mime, quality_id, job.filename),
            timeout=cfg.audio_job_timeout,
        )
        job.tmpdir = tmpdir; job.out_path = out_path
        job.filesize = filesize; job.progress = 100
        job.status = JobStatus.READY
    except asyncio.TimeoutError:
        job.status = JobStatus.ERROR; job.error = "Audio conversion timed out."
        if job.tmpdir: shutil.rmtree(job.tmpdir, ignore_errors=True)
    except Exception as exc:
        logger.error(f"[job {job_id}] {exc}")
        job.status = JobStatus.ERROR; job.error = str(exc)[:300]
        if job.tmpdir: shutil.rmtree(job.tmpdir, ignore_errors=True)


@router.post("/jobs", tags=["jobs"])
@limiter.limit("25/hour")
async def create_job(
    request:          Request,
    background_tasks: BackgroundTasks,
    video_id:  str = Query(..., min_length=11, max_length=11),
    format_id: str = Query(...),
    type:      str = Query(..., pattern="^(video|audio)$"),
):
    import re
    if not re.match(r'^[0-9A-Za-z_-]{11}$', video_id):
        raise HTTPException(status_code=400, detail="Invalid video ID.")
    if type != "audio":
        raise HTTPException(status_code=400, detail="Jobs are audio only.")

    job_id = str(uuid.uuid4())
    _jobs[job_id] = Job(id=job_id)
    background_tasks.add_task(_run_audio_job, job_id, video_id, format_id)
    return {"job_id": job_id}


@router.get("/jobs/{job_id}", tags=["jobs"])
async def get_job(job_id: str):
    job = _jobs.get(job_id)
    if not job: raise HTTPException(status_code=404, detail="Job not found.")
    return {"job_id": job.id, "status": job.status, "progress": job.progress,
            "error": job.error, "filesize": job.filesize}


@router.get("/jobs/{job_id}/file", tags=["jobs"])
async def download_job_file(job_id: str):
    job = _jobs.get(job_id)
    if not job: raise HTTPException(status_code=404, detail="Job not found.")
    if job.status != JobStatus.READY: raise HTTPException(status_code=409, detail="Not ready.")
    if not os.path.exists(job.out_path): raise HTTPException(status_code=410, detail="File expired.")

    cfg = get_settings()

    async def _stream():
        try:
            with open(job.out_path, "rb") as fh:
                while chunk := fh.read(cfg.chunk_size):
                    yield chunk
        finally:
            shutil.rmtree(job.tmpdir, ignore_errors=True)
            _jobs.pop(job_id, None)

    return StreamingResponse(_stream(), media_type="audio/mpeg", headers={
        "Content-Disposition":           f'attachment; filename="{job.filename}.mp3"',
        "Content-Length":                str(job.filesize),
        "Cache-Control":                 "no-cache, no-store, must-revalidate",
        "Access-Control-Expose-Headers": "Content-Length, Content-Disposition, Content-Type",
    })