# main.py
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.middleware import SecurityHeadersMiddleware
from app.api.router import api_router
from app.core.config import get_settings
from app.core.limiter import limiter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

cfg = get_settings()

app = FastAPI(
    title="KDYT API",
    description="YouTube downloader — pure InnerTube, no yt-dlp, no cookies",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.origins_list,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    expose_headers=["Content-Length", "Content-Disposition", "Content-Type"],
)

app.include_router(api_router)

# Serve React build if present
_DIST = os.path.join(os.path.dirname(__file__), "frontend", "dist")

if os.path.isdir(_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(_DIST, "assets")), name="static")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        index = os.path.join(_DIST, "index.html")
        return FileResponse(index) if os.path.isfile(index) else JSONResponse({"detail": "Not found"}, 404)

else:
    @app.get("/", include_in_schema=False)
    async def root():
        return JSONResponse({"message": "KDYT API v2 — InnerTube engine", "docs": "/api/docs"})
