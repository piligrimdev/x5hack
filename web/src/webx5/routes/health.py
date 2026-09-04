from fastapi import APIRouter

from webx5.schemas.health import HealthResponse

health_router = APIRouter(prefix="/health", tags=["Health"])


@health_router.get("", response_model=HealthResponse)
def get_health() -> HealthResponse:
    return HealthResponse(status="ok")
