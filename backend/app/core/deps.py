"""FastAPI 依赖注入：当前用户 / 管理员 / 分页参数。"""
from typing import Annotated

from fastapi import Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .response import BizError, Code
from .security import TOKEN_TYPE_ADMIN, TOKEN_TYPE_USER, decode_token

# auto_error=False：缺 token 时不让 FastAPI 直接抛 403，而是交给业务码处理（1001）
_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def _extract_token(credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials is None or not credentials.credentials:
        raise BizError(Code.UNAUTHORIZED)
    return credentials.credentials


def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> int:
    """返回当前登录用户 id。token 缺失/过期分别抛 1001 / 1002。"""
    payload = decode_token(_extract_token(credentials), TOKEN_TYPE_USER)
    try:
        return int(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise BizError(Code.UNAUTHORIZED) from exc


def get_current_admin_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> int:
    """返回当前后台管理员 id；非管理员 token 返回 1003。"""
    payload = decode_token(_extract_token(credentials), TOKEN_TYPE_ADMIN)
    try:
        return int(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise BizError(Code.FORBIDDEN) from exc


def get_page_params(
    page: Annotated[int, Query(ge=1, description="页码，从 1 开始")] = 1,
    page_size: Annotated[int, Query(ge=1, le=50, description="每页条数，最大 50")] = 20,
) -> tuple[int, int]:
    return page, page_size


CurrentUserId = Annotated[int, Depends(get_current_user_id)]
CurrentAdminId = Annotated[int, Depends(get_current_admin_id)]
PageParams = Annotated[tuple[int, int], Depends(get_page_params)]
