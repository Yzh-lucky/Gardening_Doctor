"""反馈相关 Schema（API接口文档 3.9 / 2.5）。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.utils.timeutil import to_iso

FeedbackType = Literal["like", "dislike", "wrong"]


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    record_id: int = Field(ge=1, description="关联的诊断记录 ID，必须是本人记录")
    type: FeedbackType = Field(description="like / dislike / wrong")
    correct_name: str | None = Field(default=None, max_length=64, description="type=wrong 时的正确病名")
    comment: str | None = Field(default=None, max_length=200, description="补充说明，最长 200 字")


class FeedbackData(BaseModel):
    """POST /feedback 的 data（API接口文档 3.9）。"""

    feedback_id: str
    record_status: str


class FeedbackItem(BaseModel):
    """后台查询用的反馈条目。"""

    id: str
    record_id: str
    user_id: str
    type: str
    correct_name: str | None = None
    comment: str | None = None
    created_at: str | None = None


def feedback_item_out(row) -> FeedbackItem:
    return FeedbackItem(
        id=str(row.id),
        record_id=str(row.record_id),
        user_id=str(row.user_id),
        type=row.type,
        correct_name=row.correct_name,
        comment=row.comment,
        created_at=to_iso(row.created_at),
    )
