# app/api/endpoints/health.py
# System health check — used by load balancers and uptime monitors.

from fastapi import APIRouter

from app.models.video import HealthResponse

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["system"],
    summary="Health check",
    description="Returns `{status: ok}` when the API is running.",
)
async def health_check() -> HealthResponse:
    return HealthResponse(status="ok")
