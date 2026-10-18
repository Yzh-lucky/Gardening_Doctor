"""T3.3 两道护栏：双维度限流 + 全站成本熔断。

位置约定：
- 限流在最前面拦（不打数据库，最便宜的关卡）；
- 成本熔断放在"要真调大模型"之前——命中缓存的请求不烧 Token，不该被熔断挡掉。

实现说明：计数器放进程内存，单实例部署够用且无额外依赖。多副本部署时每个进程各算一份，
限流阈值会被放大 N 倍，那时候要换 Redis 计数（见 _user_hits 的注释）。
"""
from __future__ import annotations

import time
from collections import deque
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.core.response import BizError, Code
from app.models.diagnosis import DiagnosisRecord
from app.utils.timeutil import today_cn

logger = get_logger("app.guard")

_WINDOW_USER = 60.0  # 每用户窗口：1 分钟
_WINDOW_GLOBAL = 1.0  # 全局窗口：1 秒（即 QPS）

# 多副本部署时这里要换成 Redis 计数器，否则每个进程各限各的，等于阈值翻倍
_user_hits: dict[str, deque[float]] = {}
_global_hits: deque[float] = deque()


def _prune(dq: deque[float], window: float, now: float) -> None:
    while dq and now - dq[0] >= window:
        dq.popleft()


def reset_rate_limiter() -> None:
    """清空计数窗口（测试用）。"""
    _user_hits.clear()
    _global_hits.clear()


def check_rate_limit(user_id: int) -> None:
    """每用户每分钟 + 全局每秒，两个维度都放行才继续。

    超限统一抛 3002 / HTTP 429：按 API接口文档 5.1，限流与熔断对客户端是同一件事
    （提示稍后重试，且不扣额度）。
    """
    now = time.monotonic()

    dq = _user_hits.setdefault(str(user_id), deque())
    _prune(dq, _WINDOW_USER, now)
    if len(dq) >= settings.RATE_LIMIT_USER_PER_MINUTE:
        logger.warning(
            "rate_limited", extra={"scope": "user", "user_id": user_id, "hits": len(dq)}
        )
        raise BizError(Code.COST_CIRCUIT_OPEN, "操作太频繁，请稍后再试")
    dq.append(now)

    _prune(_global_hits, _WINDOW_GLOBAL, now)
    if len(_global_hits) >= settings.RATE_LIMIT_GLOBAL_QPS:
        logger.warning("rate_limited", extra={"scope": "global", "hits": len(_global_hits)})
        raise BizError(Code.COST_CIRCUIT_OPEN, "当前使用人数较多，请稍后再试")
    _global_hits.append(now)

    # 顺手回收长期不活跃的用户窗口，避免字典无限增长
    if len(_user_hits) > 1000:
        stale = [k for k, v in _user_hits.items() if not v or now - v[-1] >= _WINDOW_USER]
        for key in stale:
            _user_hits.pop(key, None)


def today_cost_cny(db: Session) -> float:
    """今日已烧掉的成本（元）：按记录里的 token 数折算，熔断只看真金白银。"""
    since = datetime.combine(today_cn(), datetime.min.time())
    tokens = db.scalar(
        select(func.coalesce(func.sum(DiagnosisRecord.cost_tokens), 0)).where(
            DiagnosisRecord.created_at >= since
        )
    )
    return float(tokens or 0) / 1000.0 * settings.LLM_PRICE_PER_1K_TOKENS


def check_cost_circuit(db: Session) -> float:
    """成本超上限就熔断，直接拒掉这次模型调用（不落库、不扣额度）。"""
    cost = today_cost_cny(db)
    if cost >= settings.DAILY_COST_LIMIT_CNY:
        logger.error(
            "cost_circuit_open",
            extra={"today_cost_cny": round(cost, 4), "limit_cny": settings.DAILY_COST_LIMIT_CNY},
        )
        raise BizError(Code.COST_CIRCUIT_OPEN, "当前使用人数较多，请稍后再试")
    return cost
