"""后台管理相关 Schema（API接口文档 3.10）。

后台接口的 ID 同样以字符串返回（1.4 通用约定），入参用 int 方便校验。
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.diagnosis import PlanL1, PlanL2, PlanL3
from app.utils.timeutil import to_iso


class AdminLoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class AdminLoginData(BaseModel):
    token: str
    expires_in: int


# ---------- 知识库 CRUD（T3.5） ----------


class DiseaseUpdateRequest(BaseModel):
    """PUT /admin/diseases/{id}：部分更新，只改传上来的字段。"""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=64)
    aliases: str | None = Field(default=None, max_length=255)
    category: str | None = Field(default=None, max_length=32)
    symptoms: str | None = None
    causes: str | None = None
    plan_l1: PlanL1 | None = None
    plan_l2: PlanL2 | None = None
    plan_l3: PlanL3 | None = None
    safety_notes: str | None = None
    confused_with: str | None = Field(default=None, max_length=255)


class DiseaseCreateRequest(DiseaseUpdateRequest):
    """POST /admin/diseases：name 必填且唯一。"""

    name: str = Field(min_length=1, max_length=64)


class DiseaseWriteData(BaseModel):
    """新增/修改的返回：只回 id 与版本号（API接口文档 3.10）。"""

    id: str
    version: int


class DiseaseAdminItem(BaseModel):
    """后台知识库条目：含 version 与时间，字段与表结构对齐。"""

    id: str
    name: str
    aliases: str | None = None
    category: str | None = None
    symptoms: str | None = None
    causes: str | None = None
    plan_l1: PlanL1 | None = None
    plan_l2: PlanL2 | None = None
    plan_l3: PlanL3 | None = None
    safety_notes: str | None = None
    confused_with: str | None = None
    version: int = 1
    created_at: str | None = None
    updated_at: str | None = None


def disease_admin_out(row) -> DiseaseAdminItem:
    def _plan(value, model):
        # 库里可能是老版本结构或空值，解析不了就当没填，不让后台列表整页报错
        if not isinstance(value, dict):
            return None
        try:
            return model.model_validate(value)
        except Exception:  # noqa: BLE001 - 展示层不因脏数据崩
            return None

    return DiseaseAdminItem(
        id=str(row.id),
        name=row.name,
        aliases=row.aliases,
        category=row.category,
        symptoms=row.symptoms,
        causes=row.causes,
        plan_l1=_plan(row.plan_l1, PlanL1),
        plan_l2=_plan(row.plan_l2, PlanL2),
        plan_l3=_plan(row.plan_l3, PlanL3),
        safety_notes=row.safety_notes,
        confused_with=row.confused_with,
        version=int(row.version or 1),
        created_at=to_iso(row.created_at),
        updated_at=to_iso(row.updated_at),
    )


# ---------- 诊断记录查询（T3.5） ----------


class AdminRecordItem(BaseModel):
    id: str
    user_id: str
    status: str
    disease_name: str | None = None
    confidence: float | None = None
    image_urls: list[str] = Field(default_factory=list)
    cost_tokens: int = 0
    latency_ms: int = 0
    created_at: str | None = None


def admin_record_out(row) -> AdminRecordItem:
    return AdminRecordItem(
        id=str(row.id),
        user_id=str(row.user_id),
        status=row.status,
        disease_name=row.disease_name,
        confidence=float(row.confidence) if row.confidence is not None else None,
        image_urls=list(row.image_urls or []),
        cost_tokens=int(row.cost_tokens or 0),
        latency_ms=int(row.latency_ms or 0),
        created_at=to_iso(row.created_at),
    )


# ---------- 数据看板（T3.7） ----------


class DayStat(BaseModel):
    """按日聚合的一天运营数据（API接口文档 3.10 stats）。"""

    stat_date: str
    total_calls: int = 0
    success_calls: int = 0
    degraded_calls: int = 0
    failed_calls: int = 0
    success_rate: float = 0.0
    avg_latency_ms: int = 0
    p95_latency_ms: int = 0
    total_cost_cny: float = 0.0
    new_users: int = 0


class StatsSummary(BaseModel):
    total_calls: int = 0
    success_rate: float = 0.0
    total_cost_cny: float = 0.0


class StatsData(BaseModel):
    days: list[DayStat] = Field(default_factory=list)
    summary: StatsSummary = Field(default_factory=StatsSummary)
