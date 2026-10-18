"""病虫害科普接口 Schema（API接口文档 3.8 / 2.4）。

科普接口面向小程序端「常见病虫害科普」浏览与搜索，免鉴权，只读知识库：
- 列表 `GET /diseases` 返回精简字段（id/name/category/symptoms 摘要），便于卡片式展示；
- 详情 `GET /diseases/{id}` 返回完整 Disease（2.4），含三档方案与安全提示。

`plan_l1/l2/l3` 直接复用识别结果的 PlanL1/PlanL2/PlanL3 结构（2.3），
保证科普页展示的方案与识别结果页完全一致。
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.diagnosis import PlanL1, PlanL2, PlanL3

# 列表里症状只给摘要：卡片放不下长文，截断长度和省略号在这里统一约定
BRIEF_SYMPTOM_LEN = 60


class DiseaseBrief(BaseModel):
    """列表元素：精简字段（API接口文档 3.8）。"""

    id: str
    name: str
    category: str | None = None
    symptoms: str | None = None


class DiseaseDetail(BaseModel):
    """详情：完整 Disease（API接口文档 2.4）。"""

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


def _symptom_summary(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = text.strip()
    return cleaned if len(cleaned) <= BRIEF_SYMPTOM_LEN else cleaned[:BRIEF_SYMPTOM_LEN] + "…"


def _plan_out(value, model):
    """库里可能是空值或老结构，解析不了就当没填，不让科普列表整页报错。"""
    if not isinstance(value, dict):
        return None
    try:
        return model.model_validate(value)
    except Exception:  # noqa: BLE001 - 展示层不因脏数据崩
        return None


def disease_brief_out(row) -> DiseaseBrief:
    return DiseaseBrief(
        id=str(row.id),
        name=row.name,
        category=row.category,
        symptoms=_symptom_summary(row.symptoms),
    )


def disease_detail_out(row) -> DiseaseDetail:
    return DiseaseDetail(
        id=str(row.id),
        name=row.name,
        aliases=row.aliases,
        category=row.category,
        symptoms=row.symptoms,
        causes=row.causes,
        plan_l1=_plan_out(row.plan_l1, PlanL1),
        plan_l2=_plan_out(row.plan_l2, PlanL2),
        plan_l3=_plan_out(row.plan_l3, PlanL3),
        safety_notes=row.safety_notes,
        confused_with=row.confused_with,
        version=int(row.version or 1),
    )
