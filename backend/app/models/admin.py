"""后台管理员表（准备文档 3.5.2）。"""
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.utils.timeutil import now_cn


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now_cn)
