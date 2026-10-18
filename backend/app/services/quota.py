"""额度服务：按"用户 + 日期"维护每日免费次数。

T3.3 会在此基础上补限流与成本熔断，这里先把读取/初始化能力做出来，
因为登录后的 /quota 与 /user/profile 都要用它。
"""
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.quota import QuotaUsage
from app.utils.timeutil import today_cn


def get_or_create_quota(db: Session, user_id: int, stat_date: date | None = None) -> QuotaUsage:
    """取当天额度记录，没有就建一条。并发下靠唯一键 (user_id, stat_date) 兜底。"""
    day = stat_date or today_cn()
    quota = db.scalar(
        select(QuotaUsage).where(QuotaUsage.user_id == user_id, QuotaUsage.stat_date == day)
    )
    if quota:
        return quota

    quota = QuotaUsage(
        user_id=user_id,
        stat_date=day,
        used_count=0,
        limit_count=settings.DAILY_FREE_QUOTA,
    )
    db.add(quota)
    try:
        db.commit()
    except IntegrityError:
        # 说明另一个请求刚插进去了，回滚后重新读
        db.rollback()
        quota = db.scalar(
            select(QuotaUsage).where(QuotaUsage.user_id == user_id, QuotaUsage.stat_date == day)
        )
    return quota
