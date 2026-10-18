"""健康检查接口：部署探活 + systemd/Nginx 健康检查用。"""
from fastapi import APIRouter

from app.core.database import ping_db
from app.core.response import ApiResponse, ok
from app.schemas.common import HealthData
from app.services.llm import get_llm_provider

router = APIRouter(tags=["health"])


@router.get("/health", response_model=ApiResponse[HealthData], summary="健康检查")
async def health() -> ApiResponse[HealthData]:
    db_up = ping_db()
    llm_status = get_llm_provider().health()
    return ok(
        HealthData(
            status="up",
            db="up" if db_up else "down",
            llm=llm_status,
        )
    )
