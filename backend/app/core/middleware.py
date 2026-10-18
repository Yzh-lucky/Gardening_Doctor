"""trace_id 中间件：为每个请求分配 trace_id，写进日志上下文、响应头和响应体。"""
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from .context import set_trace_id
from .logging import get_logger

logger = get_logger("app.access")


class TraceIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex[:16]
        set_trace_id(trace_id)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # 不在这里吞异常：交给全局异常处理器输出统一结构，只补一条失败日志
            logger.exception(
                "request_error",
                extra={"method": request.method, "path": request.url.path},
            )
            raise

        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        response.headers["X-Trace-Id"] = trace_id
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response
