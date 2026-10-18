"""trace_id 上下文：用 contextvars 让日志、响应体、异常处理都能拿到同一个 trace_id。

之所以不用请求对象层层传参，是因为日志函数（logger.info 等）拿不到 Request，
contextvars 在 asyncio 下是请求隔离的，天然适合做这种"隐式上下文"。
"""
import contextvars

_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")


def set_trace_id(trace_id: str) -> None:
    _trace_id_var.set(trace_id)


def get_trace_id() -> str:
    return _trace_id_var.get()


def new_trace_id() -> str:
    """生成 16 位十六进制 trace_id。"""
    import uuid

    return uuid.uuid4().hex[:16]
