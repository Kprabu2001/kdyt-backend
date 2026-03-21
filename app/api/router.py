# app/api/router.py
from fastapi import APIRouter
from app.api.endpoints import health, info, tunnel, jobs, playlist

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(info.router)
api_router.include_router(tunnel.router)
api_router.include_router(jobs.router)
api_router.include_router(playlist.router)