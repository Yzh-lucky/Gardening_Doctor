"""数据库引擎与会话。SQLAlchemy 2.x 风格，Session 通过依赖注入给路由使用。"""
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    pool_pre_ping=True,   # 连接失效自动重连，避免 MySQL 8h 超时断连报错
    pool_recycle=3600,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,  # 提交后对象仍可读，避免返回响应时触发额外查询
)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类，Alembic 靠 Base.metadata 生成迁移。"""


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ping_db() -> bool:
    """健康检查用：SELECT 1 探测数据库连通性。"""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - 健康检查只关心通不通，不需要具体异常
        return False
