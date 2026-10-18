"""通用 Schema：健康检查、错误明细等跨模块结构。"""
from pydantic import BaseModel


class HealthData(BaseModel):
    status: str = "up"
    db: str = "up"
    llm: str = "up"
