"""反馈接口（API接口文档 3.9）：用户对某条识别结果点赞 / 报错 / 纠错。

纠错闭环：type=wrong 时把记录状态改成 corrected，后台可据此统计模型准确率。
like / dislike 只落库不改状态——"结果有帮助"并不意味着这条结果被纠正过。
"""
from fastapi import APIRouter

from app.core.deps import CurrentUserId, DbSession
from app.core.logging import get_logger
from app.core.response import ApiResponse, ok
from app.models.feedback import Feedback
from app.schemas.feedback import FeedbackData, FeedbackRequest
from app.services.records import load_owned_record

router = APIRouter(prefix="/feedback", tags=["feedback"])
logger = get_logger("app.feedback")


@router.post("", response_model=ApiResponse[FeedbackData], summary="提交反馈")
async def create_feedback(
    payload: FeedbackRequest,
    user_id: CurrentUserId,
    db: DbSession,
) -> ApiResponse[FeedbackData]:
    # 越权/不存在直接抛 4002 / 4001，和查询详情保持同一口径
    record = load_owned_record(db, payload.record_id, user_id)

    feedback = Feedback(
        record_id=record.id,
        user_id=user_id,
        type=payload.type,
        correct_name=payload.correct_name,
        comment=payload.comment,
    )
    db.add(feedback)

    if payload.type == "wrong":
        record.status = "corrected"

    db.commit()
    db.refresh(feedback)

    logger.info(
        "feedback_submitted",
        extra={
            "feedback_id": feedback.id,
            "record_id": record.id,
            "user_id": user_id,
            "type": payload.type,
            "has_correct_name": bool(payload.correct_name),
        },
    )
    return ok(FeedbackData(feedback_id=str(feedback.id), record_status=record.status))
