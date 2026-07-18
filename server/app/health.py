from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from .config import Settings, get_settings

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    service: str
    version: str
    environment: str


@router.get("/health", response_model=HealthResponse)
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.version,
        environment=settings.environment,
    )
