"""结构化日志：一行一条 JSON，自动带上当前请求的 trace_id，方便按 trace_id 捞全链路。"""
import json
import logging
import sys

from .context import get_trace_id

_RESERVED = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename", "module",
    "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created", "msecs",
    "relativeCreated", "thread", "threadName", "processName", "process", "taskName",
    "message", "asctime", "trace_id",
}


class _TraceIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = get_trace_id()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "trace_id": getattr(record, "trace_id", "-"),
            "msg": record.getMessage(),
        }
        # 业务代码用 logger.info("...", extra={"key": value}) 传的附加字段一并输出
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str | None = None) -> None:
    """初始化根 logger。多次调用不会重复加 handler。"""
    root = logging.getLogger()
    root.setLevel(level or logging.INFO)

    if not any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        handler.addFilter(_TraceIdFilter())
        root.handlers = [handler]

    # uvicorn 默认自带 handler 且 propagate=False，这里收编，统一走我们的 JSON 格式
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True

    # httpx 会以 INFO 级别打印完整请求 URL，而微信接口的 URL 里带着 AppSecret，压到 WARNING 避免密钥落进日志
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
