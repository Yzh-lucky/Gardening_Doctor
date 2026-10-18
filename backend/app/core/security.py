"""Token 签发与校验 + 后台密码哈希。

用户 token：7 天；后台 token：12 小时；两者用 payload 里的 typ 区分，不能混用。
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from .config import settings
from .response import BizError, Code

ALGORITHM = "HS256"

TOKEN_TYPE_USER = "user"
TOKEN_TYPE_ADMIN = "admin"


def create_token(subject: str | int, token_type: str, expires_in: timedelta) -> tuple[str, int]:
    """返回 (token, 有效期秒数)。"""
    now = datetime.now(timezone.utc)
    expire = now + expires_in
    payload = {
        "sub": str(subject),
        "typ": token_type,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)
    return token, int(expires_in.total_seconds())


def create_user_token(user_id: int | str) -> tuple[str, int]:
    return create_token(user_id, TOKEN_TYPE_USER, timedelta(days=settings.USER_TOKEN_EXPIRE_DAYS))


def create_admin_token(admin_id: int | str) -> tuple[str, int]:
    return create_token(admin_id, TOKEN_TYPE_ADMIN, timedelta(hours=settings.ADMIN_TOKEN_EXPIRE_HOURS))


def decode_token(token: str, expected_type: str) -> dict:
    """解析并校验 token；过期返回 1002，非法 1001，类型不符 1003。

    类型不符（拿后台 token 调用户接口、或普通用户 token 摸后台）说明"身份是真的、但没这个权限"，
    按 API接口文档 5.1 的 1003 / HTTP 403 返回，而不是当成"未登录"。
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise BizError(Code.TOKEN_EXPIRED) from exc
    except jwt.InvalidTokenError as exc:
        raise BizError(Code.UNAUTHORIZED) from exc

    if payload.get("typ") != expected_type:
        raise BizError(Code.FORBIDDEN)
    return payload


# ---------- 后台管理员密码（PBKDF2-HMAC-SHA256，标准库实现，不引第三方依赖） ----------

_ITERATIONS = 120_000


def hash_password(raw: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", raw.encode("utf-8"), salt.encode("utf-8"), _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${salt}${digest.hex()}"


def verify_password(raw: str, stored: str) -> bool:
    try:
        algo, iterations, salt, expected = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", raw.encode("utf-8"), salt.encode("utf-8"), int(iterations))
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(digest.hex(), expected)
