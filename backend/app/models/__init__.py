"""ORM 模型包：import 所有模型，保证 Base.metadata 完整（Alembic 迁移依赖这里）。"""
from .admin import Admin
from .diagnosis import DiagnosisRecord
from .disease import Disease
from .feedback import Feedback
from .quota import QuotaUsage
from .user import User

__all__ = [
    "Admin",
    "DiagnosisRecord",
    "Disease",
    "Feedback",
    "QuotaUsage",
    "User",
]
