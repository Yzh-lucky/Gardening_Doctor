"""用户 / 登录 / 额度相关 Schema。

约定：ID 一律序列化成字符串（避免 JS Number 精度丢失，见 API接口文档 1.4）。
"""
from pydantic import BaseModel, ConfigDict, Field

from app.utils.timeutil import next_midnight_cn, to_date_str, to_iso


class LoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    code: str = Field(min_length=1, max_length=128, description="wx.login() 返回的临时凭证，5 分钟有效且只能用一次")
    nickname: str | None = Field(default=None, max_length=64)
    avatar_url: str | None = Field(default=None, max_length=512)


class UpdateProfileRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    nickname: str | None = Field(default=None, max_length=64)
    avatar_url: str | None = Field(default=None, max_length=512)


class UserOut(BaseModel):
    id: str
    nickname: str | None = None
    avatar_url: str | None = None
    created_at: str | None = None
    last_login_at: str | None = None


class QuotaOut(BaseModel):
    stat_date: str
    limit_count: int
    used_count: int
    remaining: int
    reset_at: str


class ProfileOut(UserOut):
    quota: QuotaOut


class LoginData(BaseModel):
    token: str
    expires_in: int
    is_new_user: bool
    user: UserOut


def user_out(user) -> UserOut:
    return UserOut(
        id=str(user.id),
        nickname=user.nickname,
        avatar_url=user.avatar_url,
        created_at=to_iso(user.created_at),
        last_login_at=to_iso(user.last_login_at),
    )


def quota_out(quota) -> QuotaOut:
    used = int(quota.used_count)
    limit = int(quota.limit_count)
    return QuotaOut(
        stat_date=to_date_str(quota.stat_date),
        limit_count=limit,
        used_count=used,
        remaining=max(limit - used, 0),
        reset_at=next_midnight_cn().isoformat(),
    )
