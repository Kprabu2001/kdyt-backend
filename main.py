# main.py
import asyncio
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
from app.core.config import get_settings, write_cookies_from_env
from app.core.limiter import limiter

logger = logging.getLogger(__name__)

# ── Settings ──────────────────────────────────────────────────────
cfg = get_settings()

origins_list = [
    "http://localhost:5173",
    "https://kdyt.vercel.app"
]

# ── App factory ───────────────────────────────────────────────────
app = FastAPI(
    title="KDYT API",
    description="YouTube video & MP3 downloader — REST API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# ── Rate limiter ──────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Middleware (order matters — outermost runs last) ──────────────
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins_list,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ── Cookie refresh background task ───────────────────────────────
_COOKIE_REFRESH_INTERVAL = int(os.environ.get("COOKIE_REFRESH_INTERVAL", 3600))  # seconds

async def _cookie_refresh_loop():
    """Re-write cookies from YTDLP_COOKIES_B64 every COOKIE_REFRESH_INTERVAL seconds."""
    while True:
        await asyncio.sleep(_COOKIE_REFRESH_INTERVAL)
        result = write_cookies_from_env()
        if result:
            logger.info(f"[cookies] Auto-refreshed → {result}")
        else:
            logger.debug("[cookies] No YTDLP_COOKIES_B64 set, skipping refresh.")

@app.on_event("startup")
async def startup_event():
    # Write cookies immediately on startup
    path = write_cookies_from_env()
    if path:
        logger.info(f"[startup] Cookies written to {path}")
    else:
        logger.warning("[startup] YTDLP_COOKIES_B64 not set — running without cookie auth.")
    # Start periodic refresh
    asyncio.create_task(_cookie_refresh_loop())

# ── Admin: manual cookie refresh endpoint ────────────────────────
@app.get("/admin/refresh-cookies", include_in_schema=False)
async def refresh_cookies():
    """Re-decode YTDLP_COOKIES_B64 and overwrite the runtime cookie file."""
    path = write_cookies_from_env()
    if path:
        return JSONResponse({"status": "ok", "cookies_path": path})
    return JSONResponse({"status": "skipped", "reason": "YTDLP_COOKIES_B64 not set"}, status_code=200)

# ── API routes ────────────────────────────────────────────────────
app.include_router(api_router)

# ── Static frontend (serves React build if present) ───────────────
_DIST = os.path.join(os.path.dirname(__file__), "frontend", "dist")

if os.path.isdir(_DIST):
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(_DIST, "assets")),
        name="static-assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        index = os.path.join(_DIST, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)
        return JSONResponse({"detail": "Frontend not found."}, status_code=404)

else:
    @app.get("/", include_in_schema=False)
    async def root():
        return JSONResponse({
            "message": "KDYT API is running.",
            "docs": "/api/docs",
            "note": "Build the React frontend and place it in frontend/dist/ to serve the UI.",
        })


# ── Settings ──────────────────────────────────────────────────────
cfg = get_settings()

origins_list = [
    "http://localhost:5173",
    "https://kdyt.vercel.app"
]

# ── App factory ───────────────────────────────────────────────────
app = FastAPI(
    title="KDYT API",
    description="YouTube video & MP3 downloader — REST API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# ── Rate limiter ──────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ── Middleware (order matters — outermost runs last) ──────────────
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins_list,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ── API routes ────────────────────────────────────────────────────
app.include_router(api_router)

# ── Static frontend (serves React build if present) ───────────────
_DIST = os.path.join(os.path.dirname(__file__), "frontend", "dist")

if os.path.isdir(_DIST):
    # Serve /assets/* directly (JS, CSS, images)
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(_DIST, "assets")),
        name="static-assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        """Return index.html for every non-API path so React Router works."""
        index = os.path.join(_DIST, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)
        return JSONResponse({"detail": "Frontend not found."}, status_code=404)

else:
    @app.get("/", include_in_schema=False)
    async def root():
        return JSONResponse({
            "message": "KDYT API is running.",
            "docs": "/api/docs",
            "note": "Build the React frontend and place it in frontend/dist/ to serve the UI.",
        })