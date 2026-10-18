"""诊断记录的公共读取逻辑。

`GET /diagnosis/{id}`、`POST /feedback`、后台查询都要做同一件事：
按 id 取记录 + 校验归属。抽到这里，避免各路由各写一份，归属校验口径不一致。
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.response import BizError, Code
from app.models.diagnosis import DiagnosisRecord


def load_owned_record(db: Session, record_id: int, user_id: int) -> DiagnosisRecord:
    """取记录并校验归属：不存在 4001；存在但不属于当前用户 4002（不回 404，避免枚举探测）。"""
    record = db.scalar(
        select(DiagnosisRecord).where(
            DiagnosisRecord.id == record_id,
            DiagnosisRecord.deleted_at.is_(None),
        )
    )
    if record is None:
        raise BizError(Code.RECORD_NOT_FOUND)
    if int(record.user_id) != int(user_id):
        raise BizError(Code.RECORD_FORBIDDEN)
    return record
