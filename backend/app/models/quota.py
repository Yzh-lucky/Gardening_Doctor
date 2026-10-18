"""每日额度表（准备文档 3.5.2）。"""
from datetime import date

from sqlalchemy import Date, UniqueConstraint
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class QuotaUsage(Base):
    __tablename__ = "quota_usages"
    __table_args__ = (UniqueConstraint("user_id", "stat_date", name="uk_user_date"),)

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    stat_date: Mapped[date] = mapped_column(Date, nullable=False)
    used_count: Mapped[int] = mapped_column(nullable=False, default=0)
    limit_count: Mapped[int] = mapped_column(nullable=False, default=10)
