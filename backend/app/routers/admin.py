"""后台管理接口（API接口文档 3.10）。

后台 token 与用户 token 分离（typ=admin，12 小时），由 CurrentAdminId 依赖校验，
非管理员 token 一律 1003（HTTP 403）。除 /admin/login 外全部要求管理员身份。
"""
import math
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Query
from sqlalchemy import case, func, or_, select

from app.core.config import settings
from app.core.deps import CurrentAdminId, DbSession, PageParams
from app.core.logging import get_logger
from app.core.response import ApiResponse, BizError, Code, PageData, ok
from app.core.security import create_admin_token, verify_password
from app.models.admin import Admin
from app.models.diagnosis import DiagnosisRecord
from app.models.disease import Disease
from app.models.feedback import Feedback
from app.models.user import User
from app.schemas.admin import (
    AdminLoginData,
    AdminLoginRequest,
    AdminRecordItem,
    DayStat,
    DiseaseAdminItem,
    DiseaseCreateRequest,
    DiseaseUpdateRequest,
    DiseaseWriteData,
    StatsData,
    StatsSummary,
    admin_record_out,
    disease_admin_out,
)
from app.schemas.feedback import FeedbackItem, feedback_item_out
from app.utils.timeutil import today_cn

router = APIRouter(prefix="/admin", tags=["admin"])
logger = get_logger("app.admin")


@router.post("/login", response_model=ApiResponse[AdminLoginData], summary="后台登录")
async def admin_login(payload: AdminLoginRequest, db: DbSession) -> ApiResponse[AdminLoginData]:
    admin = db.scalar(select(Admin).where(Admin.username == payload.username))
    # 账号不存在与密码错误返回同一个业务码，避免被用来枚举后台账号
    if admin is None or not verify_password(payload.password, admin.password_hash):
        logger.warning("admin_login_failed", extra={"username": payload.username})
        raise BizError(Code.ADMIN_LOGIN_FAILED)

    token, expires_in = create_admin_token(admin.id)
    logger.info("admin_login", extra={"admin_id": admin.id, "username": admin.username})
    return ok(AdminLoginData(token=token, expires_in=expires_in))


@router.get("/feedbacks", response_model=ApiResponse[PageData[FeedbackItem]], summary="反馈查询")
async def list_feedbacks(
    admin_id: CurrentAdminId,
    db: DbSession,
    page_params: PageParams,
    record_id: int | None = Query(default=None, description="按诊断记录过滤"),
    user_id: int | None = Query(default=None, description="按用户过滤"),
    type: str | None = Query(default=None, description="like / dislike / wrong"),
) -> ApiResponse[PageData[FeedbackItem]]:
    page, page_size = page_params
    conditions = []
    if record_id is not None:
        conditions.append(Feedback.record_id == record_id)
    if user_id is not None:
        conditions.append(Feedback.user_id == user_id)
    if type:
        conditions.append(Feedback.type == type)

    total = int(db.scalar(select(func.count()).select_from(Feedback).where(*conditions)) or 0)
    rows = db.scalars(
        select(Feedback)
        .where(*conditions)
        .order_by(Feedback.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return ok(
        PageData[FeedbackItem](
            list=[feedback_item_out(r) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
            has_more=page * page_size < total,
        )
    )


# ---------- 知识库 CRUD（T3.5） ----------


def _plan_dump(value) -> dict | None:
    """把 PlanL1/L2/L3 落成普通 dict 存 JSON 列；没传就保持 None。"""
    return value.model_dump(mode="json") if value is not None else None


def _assert_name_available(db: DbSession, name: str, exclude_id: int | None = None) -> None:
    stmt = select(Disease.id).where(Disease.name == name)
    if exclude_id is not None:
        stmt = stmt.where(Disease.id != exclude_id)
    if db.scalar(stmt) is not None:
        raise BizError(Code.DISEASE_NAME_EXISTS)


def _load_disease(db: DbSession, disease_id: int) -> Disease:
    disease = db.get(Disease, disease_id)
    if disease is None:
        raise BizError(Code.RECORD_NOT_FOUND, "病害不存在")
    return disease


@router.get("/diseases", response_model=ApiResponse[PageData[DiseaseAdminItem]], summary="知识库列表")
async def list_diseases(
    admin_id: CurrentAdminId,
    db: DbSession,
    page_params: PageParams,
    keyword: str | None = Query(default=None, description="按病名/别名/症状模糊搜索"),
    category: str | None = Query(default=None, description="按类别过滤"),
) -> ApiResponse[PageData[DiseaseAdminItem]]:
    page, page_size = page_params
    conditions = []
    if keyword and keyword.strip():
        pattern = f"%{keyword.strip()}%"
        conditions.append(
            or_(Disease.name.like(pattern), Disease.aliases.like(pattern), Disease.symptoms.like(pattern))
        )
    if category and category.strip():
        conditions.append(Disease.category == category.strip())

    total = int(db.scalar(select(func.count()).select_from(Disease).where(*conditions)) or 0)
    rows = db.scalars(
        select(Disease)
        .where(*conditions)
        .order_by(Disease.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return ok(
        PageData[DiseaseAdminItem](
            list=[disease_admin_out(r) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
            has_more=page * page_size < total,
        )
    )


@router.post("/diseases", response_model=ApiResponse[DiseaseWriteData], summary="新增病害")
async def create_disease(
    payload: DiseaseCreateRequest,
    admin_id: CurrentAdminId,
    db: DbSession,
) -> ApiResponse[DiseaseWriteData]:
    _assert_name_available(db, payload.name)
    disease = Disease(
        name=payload.name,
        aliases=payload.aliases,
        category=payload.category,
        symptoms=payload.symptoms,
        causes=payload.causes,
        plan_l1=_plan_dump(payload.plan_l1),
        plan_l2=_plan_dump(payload.plan_l2),
        plan_l3=_plan_dump(payload.plan_l3),
        safety_notes=payload.safety_notes,
        confused_with=payload.confused_with,
        version=1,
    )
    db.add(disease)
    db.commit()
    db.refresh(disease)
    logger.info("admin_disease_create", extra={"admin_id": admin_id, "disease_id": disease.id})
    return ok(DiseaseWriteData(id=str(disease.id), version=int(disease.version)))


@router.put("/diseases/{disease_id}", response_model=ApiResponse[DiseaseWriteData], summary="修改病害")
async def update_disease(
    disease_id: int,
    payload: DiseaseUpdateRequest,
    admin_id: CurrentAdminId,
    db: DbSession,
) -> ApiResponse[DiseaseWriteData]:
    disease = _load_disease(db, disease_id)
    updates = payload.model_dump(exclude_unset=True)

    # plan_* 传进来是嵌套模型，需要转成可入库的 dict；显式传 null 表示清空该字段
    for field in ("plan_l1", "plan_l2", "plan_l3"):
        if field in updates:
            value = getattr(payload, field)
            updates[field] = _plan_dump(value)

    if "name" in updates and updates["name"] != disease.name:
        _assert_name_available(db, updates["name"], exclude_id=disease.id)

    for field, value in updates.items():
        setattr(disease, field, value)
    disease.version = int(disease.version or 1) + 1  # 版本自增，历史 Prompt/方案变更可追溯
    db.commit()
    db.refresh(disease)
    logger.info("admin_disease_update", extra={"admin_id": admin_id, "disease_id": disease.id, "fields": list(updates)})
    return ok(DiseaseWriteData(id=str(disease.id), version=int(disease.version)))


@router.delete("/diseases/{disease_id}", response_model=ApiResponse[None], summary="删除病害")
async def delete_disease(disease_id: int, admin_id: CurrentAdminId, db: DbSession) -> ApiResponse[None]:
    disease = _load_disease(db, disease_id)
    db.delete(disease)
    db.commit()
    logger.info("admin_disease_delete", extra={"admin_id": admin_id, "disease_id": disease_id})
    return ok(None)


# ---------- 诊断记录查询（T3.5） ----------


def _parse_date(value: str | None, field: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise BizError(Code.PARAM_INVALID, f"{field} 需为 YYYY-MM-DD") from exc


@router.get("/records", response_model=ApiResponse[PageData[AdminRecordItem]], summary="诊断记录查询")
async def list_records(
    admin_id: CurrentAdminId,
    db: DbSession,
    page_params: PageParams,
    user_id: int | None = Query(default=None, description="按用户过滤"),
    status: str | None = Query(default=None, description="按状态过滤"),
    start_date: str | None = Query(default=None, description="起始日期 YYYY-MM-DD，含当天"),
    end_date: str | None = Query(default=None, description="结束日期 YYYY-MM-DD，含当天"),
) -> ApiResponse[PageData[AdminRecordItem]]:
    page, page_size = page_params
    conditions = [DiagnosisRecord.deleted_at.is_(None)]
    if user_id is not None:
        conditions.append(DiagnosisRecord.user_id == user_id)
    if status:
        conditions.append(DiagnosisRecord.status == status)

    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date")
    if start is not None:
        conditions.append(DiagnosisRecord.created_at >= datetime.combine(start, datetime.min.time()))
    if end is not None:
        # 结束日期含当天：用次日 0 点做开区间上界
        conditions.append(DiagnosisRecord.created_at < datetime.combine(end + timedelta(days=1), datetime.min.time()))

    total = int(db.scalar(select(func.count()).select_from(DiagnosisRecord).where(*conditions)) or 0)
    rows = db.scalars(
        select(DiagnosisRecord)
        .where(*conditions)
        .order_by(DiagnosisRecord.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return ok(
        PageData[AdminRecordItem](
            list=[admin_record_out(r) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
            has_more=page * page_size < total,
        )
    )


# ---------- 数据看板（T3.7） ----------


def _p95(values: list[int]) -> int:
    """最近秩法取 95 分位：排序后取 ceil(0.95*n) 位。MySQL 无现成分位函数，MVP 在应用层算。"""
    if not values:
        return 0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)
    return int(ordered[idx])


def _rate(part: int, total: int) -> float:
    return round(part / total, 3) if total else 0.0


@router.get("/stats", response_model=ApiResponse[StatsData], summary="运营数据看板")
async def stats(
    admin_id: CurrentAdminId,
    db: DbSession,
    date_from: str | None = Query(default=None, alias="from", description="起始日期 YYYY-MM-DD，默认 7 天前"),
    date_to: str | None = Query(default=None, alias="to", description="结束日期 YYYY-MM-DD，默认今天"),
) -> ApiResponse[StatsData]:
    start = _parse_date(date_from, "from") or (today_cn() - timedelta(days=6))
    end = _parse_date(date_to, "to") or today_cn()
    if end < start:
        raise BizError(Code.PARAM_INVALID, "结束日期不能早于起始日期")

    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end + timedelta(days=1), datetime.min.time())
    day_expr = func.date(DiagnosisRecord.created_at)
    record_filter = (
        DiagnosisRecord.deleted_at.is_(None),
        DiagnosisRecord.created_at >= start_dt,
        DiagnosisRecord.created_at < end_dt,
    )

    # ① 按日聚合计数 / 成本 / 平均耗时
    success_statuses = ("success", "corrected")  # 被纠错的记录仍算产出了成功结果
    agg_rows = db.execute(
        select(
            day_expr.label("day"),
            func.count().label("total"),
            func.sum(case((DiagnosisRecord.status.in_(success_statuses), 1), else_=0)).label("success"),
            func.sum(case((DiagnosisRecord.status == "degraded", 1), else_=0)).label("degraded"),
            func.sum(case((DiagnosisRecord.status == "failed", 1), else_=0)).label("failed"),
            func.coalesce(func.sum(DiagnosisRecord.cost_tokens), 0).label("tokens"),
            func.coalesce(func.avg(DiagnosisRecord.latency_ms), 0).label("avg_latency"),
        )
        .where(*record_filter)
        .group_by(day_expr)
    ).all()

    # ② 明细耗时用来算 p95（一次查回来在应用层分位，MVP 数据量下最省事）
    latency_rows = db.execute(
        select(day_expr.label("day"), DiagnosisRecord.latency_ms).where(*record_filter)
    ).all()

    # ③ 每日新增用户
    user_day_expr = func.date(User.created_at)
    user_rows = db.execute(
        select(user_day_expr.label("day"), func.count().label("cnt"))
        .where(User.created_at >= start_dt, User.created_at < end_dt)
        .group_by(user_day_expr)
    ).all()

    by_day: dict[str, dict] = {}
    for row in agg_rows:
        by_day[str(row.day)] = {
            "total": int(row.total or 0),
            "success": int(row.success or 0),
            "degraded": int(row.degraded or 0),
            "failed": int(row.failed or 0),
            "tokens": int(row.tokens or 0),
            "avg_latency": int(row.avg_latency or 0),
        }
    latencies: dict[str, list[int]] = {}
    for row in latency_rows:
        latencies.setdefault(str(row.day), []).append(int(row.latency_ms or 0))
    new_users = {str(row.day): int(row.cnt or 0) for row in user_rows}

    days: list[DayStat] = []
    cursor = start
    while cursor <= end:
        key = cursor.isoformat()
        bucket = by_day.get(key)
        if bucket:
            tokens = bucket["tokens"]
            days.append(
                DayStat(
                    stat_date=key,
                    total_calls=bucket["total"],
                    success_calls=bucket["success"],
                    degraded_calls=bucket["degraded"],
                    failed_calls=bucket["failed"],
                    success_rate=_rate(bucket["success"], bucket["total"]),
                    avg_latency_ms=bucket["avg_latency"],
                    p95_latency_ms=_p95(latencies.get(key, [])),
                    total_cost_cny=round(tokens / 1000.0 * settings.LLM_PRICE_PER_1K_TOKENS, 4),
                    new_users=new_users.get(key, 0),
                )
            )
        else:
            # 区间内没有数据的日子也要出现（补零），看板断档比缺行更直观
            days.append(DayStat(stat_date=key, new_users=new_users.get(key, 0)))
        cursor += timedelta(days=1)

    total_calls = sum(d.total_calls for d in days)
    total_success = sum(d.success_calls for d in days)
    total_cost = round(sum(d.total_cost_cny for d in days), 4)
    return ok(
        StatsData(
            days=days,
            summary=StatsSummary(
                total_calls=total_calls,
                success_rate=_rate(total_success, total_calls),
                total_cost_cny=total_cost,
            ),
        )
    )
