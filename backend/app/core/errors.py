"""全局异常处理：任何异常都转成 {code, message, data, trace_id} 统一结构。"""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from .logging import get_logger
from .response import ApiResponse, BizError, Code, http_status_of, message_of

logger = get_logger("app.error")

# HTTP 状态码 → 业务码（非业务异常时的兜底映射）
_HTTP_TO_CODE = {
    400: Code.PARAM_INVALID,
    401: Code.UNAUTHORIZED,
    403: Code.FORBIDDEN,
    404: Code.RECORD_NOT_FOUND,
    413: Code.IMAGE_TOO_LARGE,
    429: Code.QUOTA_EXHAUSTED,
}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BizError)
    async def _handle_biz_error(request: Request, exc: BizError) -> JSONResponse:
        # 业务异常是预期内的，用 info 级别，避免污染错误日志
        logger.info("biz_error", extra={"code": exc.code, "path": request.url.path, "detail": exc.message})
        return JSONResponse(
            status_code=exc.http_status,
            content=ApiResponse(code=exc.code, message=exc.message, data=exc.data).to_dict(),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "field": ".".join(str(x) for x in err.get("loc", []) if x != "body"),
                "message": err.get("msg", ""),
            }
            for err in exc.errors()
        ]
        logger.info("param_invalid", extra={"path": request.url.path, "errors": errors})
        return JSONResponse(
            status_code=200,  # 参数问题走 200 + 业务码 2001，前端按 code 判断
            content=ApiResponse(
                code=Code.PARAM_INVALID, message=message_of(Code.PARAM_INVALID), data={"errors": errors}
            ).to_dict(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_TO_CODE.get(exc.status_code, Code.SERVER_ERROR)
        message = exc.detail if isinstance(exc.detail, str) and exc.detail else message_of(code)
        return JSONResponse(
            status_code=exc.status_code,
            content=ApiResponse(code=code, message=message).to_dict(),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", extra={"path": request.url.path, "type": type(exc).__name__})
        return JSONResponse(
            status_code=500,
            content=ApiResponse(code=Code.SERVER_ERROR, message=message_of(Code.SERVER_ERROR)).to_dict(),
        )
