"""用户表（准备文档 3.5.2）。"""
from datetime import datetime

from sqlalchemy import String
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.utils.timeutil import now_cn


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    openid: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, comment="微信 openid")
    unionid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=now_cn)
    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)
