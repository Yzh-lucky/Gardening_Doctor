"""统一响应包装与业务码。

约定（见 API接口文档 1.2 / 5）：
- 所有接口返回 {code, message, data, trace_id}
- HTTP 200 承载业务成败；仅 401/403/413/429/500 用对应 HTTP 状态码
- 业务判断一律以 code 为准
"""
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

from .context import get_trace_id

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "ok"
    data: Optional[T] = None
    trace_id: str = Field(default_factory=get_trace_id)

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class PageData(BaseModel, Generic[T]):
    """分页出参统一结构（1.4 通用参数与格式）。"""

    list: List[T] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    has_more: bool = False


class Code:
    OK = 0
    # 通用与鉴权
    UNAUTHORIZED = 1001
    TOKEN_EXPIRED = 1002
    FORBIDDEN = 1003
    # 登录
    WECHAT_CODE_INVALID = 1101
    WECHAT_UNAVAILABLE = 1102
    # 参数与图片
    PARAM_INVALID = 2001
    IMAGE_FORMAT_UNSUPPORTED = 2002
    IMAGE_TOO_LARGE = 2003
    CONTENT_UNSAFE = 2004
    # 额度
    QUOTA_EXHAUSTED = 3001
    COST_CIRCUIT_OPEN = 3002
    # 记录
    RECORD_NOT_FOUND = 4001
    RECORD_FORBIDDEN = 4002
    # 服务
    SERVER_ERROR = 5000
    DEGRADED = 5001
    # 后台
    ADMIN_LOGIN_FAILED = 6001
    DISEASE_NAME_EXISTS = 6002


MESSAGES: dict[int, str] = {
    Code.OK: "ok",
    Code.UNAUTHORIZED: "请先登录",
    Code.TOKEN_EXPIRED: "登录已过期",
    Code.FORBIDDEN: "无权限访问",
    Code.WECHAT_CODE_INVALID: "微信凭证已失效",
    Code.WECHAT_UNAVAILABLE: "微信服务不可用",
    Code.PARAM_INVALID: "参数不合法",
    Code.IMAGE_FORMAT_UNSUPPORTED: "图片格式不支持",
    Code.IMAGE_TOO_LARGE: "图片过大或数量超限",
    Code.CONTENT_UNSAFE: "图片内容不合规",
    Code.QUOTA_EXHAUSTED: "今日免费次数已用完",
    Code.COST_CIRCUIT_OPEN: "当前使用人数较多",
    Code.RECORD_NOT_FOUND: "记录不存在",
    Code.RECORD_FORBIDDEN: "无权访问该记录",
    Code.SERVER_ERROR: "服务开小差了",
    Code.DEGRADED: "识别已降级",
    Code.ADMIN_LOGIN_FAILED: "账号或密码错误",
    Code.DISEASE_NAME_EXISTS: "病害名称已存在",
}

# 需要走非 200 HTTP 状态码的业务码
HTTP_STATUS: dict[int, int] = {
    Code.UNAUTHORIZED: 401,
    Code.TOKEN_EXPIRED: 401,
    Code.FORBIDDEN: 403,
    Code.IMAGE_TOO_LARGE: 413,
    Code.QUOTA_EXHAUSTED: 429,
    Code.COST_CIRCUIT_OPEN: 429,
    Code.SERVER_ERROR: 500,
}


def message_of(code: int) -> str:
    return MESSAGES.get(code, "请求失败")


def http_status_of(code: int) -> int:
    return HTTP_STATUS.get(code, 200)


class BizError(Exception):
    """业务异常：抛出后由全局异常处理统一转成标准响应。

    用法：raise BizError(Code.QUOTA_EXHAUSTED) 或 raise BizError(Code.PARAM_INVALID, "图片张数不能超过 3 张")
    """

    def __init__(
        self,
        code: int,
        message: str | None = None,
        http_status: int | None = None,
        data: object = None,
    ) -> None:
        self.code = code
        self.message = message or message_of(code)
        self.http_status = http_status or http_status_of(code)
        self.data = data
        super().__init__(self.message)


def ok(data: object = None, message: str = "ok") -> ApiResponse:
    return ApiResponse(code=Code.OK, message=message, data=data)


def fail(code: int, message: str | None = None, data: object = None) -> ApiResponse:
    return ApiResponse(code=code, message=message or message_of(code), data=data)
