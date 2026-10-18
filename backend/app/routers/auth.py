"""登录接口：微信 code2session → 建/查用户 → 签发 token。"""
from fastapi import APIRouter
from sqlalchemy import select

from app.core.deps import DbSession
from app.core.logging import get_logger
from app.core.response import ApiResponse, BizError, Code, ok
from app.core.security import create_user_token
from app.models.user import User
from app.schemas.user import LoginData, LoginRequest, user_out
from app.services.wechat import code2session
from app.utils.timeutil import now_cn

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger("app.auth")


@router.post("/login", response_model=ApiResponse[LoginData], summary="微信登录")
async def login(payload: LoginRequest, db: DbSession) -> ApiResponse[LoginData]:
    session = await code2session(payload.code)

    user = db.scalar(select(User).where(User.openid == session.openid))
    is_new_user = user is None
    if user is None:
        user = User(
            openid=session.openid,
            unionid=session.unionid,
            nickname=payload.nickname,
            avatar_url=payload.avatar_url,
            last_login_at=now_cn(),
        )
        db.add(user)
    else:
        # 每次登录都刷新最后登录时间；昵称头像只在这次带了值时才覆盖
        user.last_login_at = now_cn()
        if session.unionid:
            user.unionid = session.unionid
        if payload.nickname:
            user.nickname = payload.nickname
        if payload.avatar_url:
            user.avatar_url = payload.avatar_url

    db.commit()
    db.refresh(user)

    token, expires_in = create_user_token(user.id)
    logger.info("user_login", extra={"user_id": user.id, "is_new_user": is_new_user})

    return ok(
        LoginData(
            token=token,
            expires_in=expires_in,
            is_new_user=is_new_user,
            user=user_out(user),
        )
    )
