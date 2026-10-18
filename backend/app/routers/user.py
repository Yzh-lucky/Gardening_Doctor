"""用户接口：当前用户信息（带今日额度）、更新昵称头像。"""
from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import CurrentUserId, DbSession
from app.core.response import ApiResponse, BizError, Code, ok
from app.models.user import User
from app.schemas.user import ProfileOut, UpdateProfileRequest, UserOut, quota_out, user_out
from app.services.quota import get_or_create_quota

router = APIRouter(prefix="/user", tags=["user"])


def _load_user(db: Session, user_id: int) -> User:
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        # token 合法但用户被删了，按未登录处理
        raise BizError(Code.UNAUTHORIZED)
    return user


@router.get("/profile", response_model=ApiResponse[ProfileOut], summary="当前用户信息")
async def get_profile(user_id: CurrentUserId, db: DbSession) -> ApiResponse[ProfileOut]:
    user = _load_user(db, user_id)
    quota = get_or_create_quota(db, user_id)
    data = ProfileOut(**user_out(user).model_dump(), quota=quota_out(quota))
    return ok(data)


@router.put("/profile", response_model=ApiResponse[UserOut], summary="更新昵称头像")
async def update_profile(
    payload: UpdateProfileRequest, user_id: CurrentUserId, db: DbSession
) -> ApiResponse[UserOut]:
    user = _load_user(db, user_id)
    if payload.nickname is not None:
        user.nickname = payload.nickname
    if payload.avatar_url is not None:
        user.avatar_url = payload.avatar_url
    db.commit()
    db.refresh(user)
    return ok(user_out(user))
