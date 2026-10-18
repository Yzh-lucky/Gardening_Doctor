"""诊断记录表（准备文档 3.5.2）。

比文档原始 SQL 多一个 deleted_at：文档要求 DELETE /diagnosis/{id} 走软删除，
但没有设计删除标记列，这里补一个可空字段，其余字段严格对齐。
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Numeric, String
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.utils.timeutil import now_cn


class DiagnosisRecord(Base):
    __tablename__ = "diagnosis_records"
    __table_args__ = (
        Index("idx_user_time", "user_id", "created_at"),
        Index("idx_hash", "image_hash"),
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    image_urls: Mapped[list] = mapped_column(JSON, nullable=False, comment="图片地址数组")
    image_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="首图 sha256，用于缓存命中")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="created",
        comment="created/recognizing/success/degraded/failed/corrected",
    )
    prompt_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    disease_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="结构化识别结果")
    cost_tokens: Mapped[int] = mapped_column(nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_cn)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="软删除时间")
