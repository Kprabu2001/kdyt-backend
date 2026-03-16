# app/api/router.py

from fastapi import APIRouter
from app.api.endpoints import download, health, info, jobs

api_router = APIRouter(prefix="/api")

api_router.include_router(health.router)
api_router.include_router(info.router)
api_router.include_router(download.router)
api_router.include_router(jobs.router)