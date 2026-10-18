"""病虫害知识库表（准备文档 3.5.2）。"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.utils.timeutil import now_cn


class Disease(Base):
    __tablename__ = "diseases"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    aliases: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="真菌性/细菌性/病毒性/虫害/生理性")
    symptoms: Mapped[str | None] = mapped_column(Text, nullable=True)
    causes: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan_l1: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="家庭安全处置")
    plan_l2: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="低毒合规处置")
    plan_l3: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="专业干预")
    safety_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    confused_with: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_cn)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_cn, onupdate=now_cn)
