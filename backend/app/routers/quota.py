"""额度接口：查询今日剩余次数。"""
from fastapi import APIRouter

from app.core.deps import CurrentUserId, DbSession
from app.core.response import ApiResponse, ok
from app.schemas.user import QuotaOut, quota_out
from app.services.quota import get_or_create_quota

router = APIRouter(tags=["quota"])


@router.get("/quota", response_model=ApiResponse[QuotaOut], summary="今日剩余额度")
async def get_quota(user_id: CurrentUserId, db: DbSession) -> ApiResponse[QuotaOut]:
    quota = get_or_create_quota(db, user_id)
    return ok(quota_out(quota))
