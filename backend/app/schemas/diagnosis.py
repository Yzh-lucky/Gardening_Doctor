"""识别相关 Schema：DiseaseResult（大模型输出契约，见 API接口文档 2.3）+ 接口出入参。

DiseaseResult 是**三方共用的冻结契约**：大模型输出 → 后端校验落库 → 前端结果页渲染。
改任何一个字段都要同步改 Prompt、后端 Schema、前端渲染，所以这里保持严格：
- 必需字段缺失 / 类型不对 / 枚举值越界 / confidence 超出 0–1 → 校验失败（触发重试或降级）。
- 只对**语义上不能含糊**的字段开严格模式（severity 枚举、confidence 区间）；
  category 用宽松字符串，因为模型偶尔会给出"生理性病害"之外的合理表述，不必因此重试。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.utils.timeutil import to_iso

Severity = Literal["mild", "moderate", "severe"]


class ConfusedItem(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    key_difference: str = Field(min_length=1)


class PlanL1(BaseModel):
    """家庭零风险处置：items 是纯文本步骤。"""

    title: str = Field(min_length=1)
    items: list[str] = Field(default_factory=list)


class PlanL2Item(BaseModel):
    """低毒合规处置的单条药剂：必须带用法（含安全间隔期）。"""

    name: str = Field(min_length=1, max_length=64)
    usage: str = Field(min_length=1)


class PlanL2(BaseModel):
    title: str = Field(min_length=1)
    items: list[PlanL2Item] = Field(default_factory=list)
    note: str | None = None


class PlanL3(BaseModel):
    title: str = Field(min_length=1)
    items: list[str] = Field(default_factory=list)
    risk_note: str | None = None


class DiseaseResult(BaseModel):
    """大模型输出契约（API接口文档 2.3），字段不可随意增删。"""

    model_config = ConfigDict(extra="ignore")  # 模型多吐的字段直接忽略，不因多余字段判定失败

    disease_name: str = Field(min_length=1, max_length=64)
    aliases: list[str] = Field(default_factory=list)
    category: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    severity: Severity
    symptom_summary: str = Field(min_length=1)
    confirm_points: list[str] = Field(default_factory=list)
    confused_with: list[ConfusedItem] = Field(default_factory=list)
    plan_l1_safe: PlanL1
    plan_l2_low_toxicity: PlanL2
    plan_l3_professional: PlanL3
    safety_notes: list[str] = Field(default_factory=list)
    need_more_info: bool = False
    followup_questions: list[str] = Field(default_factory=list)


# ---------- 接口出入参 ----------


class DiagnosisData(BaseModel):
    """POST /diagnosis 的 data（API接口文档 3.4）。"""

    record_id: str
    status: str  # success / degraded
    degraded: bool = False
    latency_ms: int = 0
    remaining_quota: int = 0
    result: DiseaseResult | None = None


class DiagnosisDetail(BaseModel):
    """GET /diagnosis/{id} 的 data（API接口文档 3.5）。"""

    id: str
    image_urls: list[str] = Field(default_factory=list)
    status: str
    result: DiseaseResult | None = None
    confidence: float | None = None
    disease_name: str | None = None
    latency_ms: int = 0
    created_at: str | None = None


class DiagnosisListItem(BaseModel):
    """GET /diagnosis 列表项：只给摘要 + 缩略图，不带完整 result（API接口文档 3.6）。"""

    id: str
    image_urls: list[str] = Field(default_factory=list)
    disease_name: str | None = None
    confidence: float | None = None
    status: str
    thumbnail: str | None = None
    created_at: str | None = None


def _parse_result(raw: dict | None) -> DiseaseResult | None:
    """把库里的 result_json 还原成 DiseaseResult；解析不了就返回 None（老数据/异常数据不炸接口）。"""
    if not raw:
        return None
    try:
        return DiseaseResult.model_validate(raw)
    except Exception:  # noqa: BLE001 - 展示层不因历史脏数据报错
        return None


def detail_out(record) -> DiagnosisDetail:
    return DiagnosisDetail(
        id=str(record.id),
        image_urls=list(record.image_urls or []),
        status=record.status,
        result=_parse_result(record.result_json),
        confidence=float(record.confidence) if record.confidence is not None else None,
        disease_name=record.disease_name,
        latency_ms=int(record.latency_ms or 0),
        created_at=to_iso(record.created_at),
    )


def list_item_out(record) -> DiagnosisListItem:
    urls = list(record.image_urls or [])
    return DiagnosisListItem(
        id=str(record.id),
        image_urls=urls,
        disease_name=record.disease_name,
        confidence=float(record.confidence) if record.confidence is not None else None,
        status=record.status,
        # MVP 阶段直接复用原图当缩略图；正式版应生成 _thumb 派生图（API接口文档 3.6）
        thumbnail=urls[0] if urls else None,
        created_at=to_iso(record.created_at),
    )
