"""用户反馈表（准备文档 3.5.2）。"""
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.utils.timeutil import now_cn


class Feedback(Base):
    __tablename__ = "feedbacks"
    __table_args__ = (Index("idx_record", "record_id"),)

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    record_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    user_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False, comment="like/dislike/wrong")
    correct_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_cn)
