"""识别相关接口（API接口文档 3.4–3.6）：发起识别、查结果、历史列表、删除。

POST /diagnosis 同时支持两种请求体：
- `multipart/form-data`：契约主路径（curl / Swagger / 真机单图上传），字段 `images`（1–3 个文件）、`plant_hint`、`client_ts`
- `application/json`：小程序多图上传用的备用路径（小程序没法一次带多个文件，只能把图片转 base64 塞进 JSON），
  形如 `{"images": ["data:image/jpeg;base64,...", ...], "plant_hint": "番茄"}`

两条路径收敛到同一个 services/recognizer，错误语义与额度规则完全一致。
"""
from __future__ import annotations

import base64
import re

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from app.core.deps import CurrentUserId, DbSession, PageParams
from app.core.response import (
    ApiResponse,
    BizError,
    Code,
    PageData,
    message_of,
    ok,
)
from app.models.diagnosis import DiagnosisRecord
from app.schemas.diagnosis import (
    DiagnosisData,
    DiagnosisDetail,
    DiagnosisListItem,
    DiseaseResult,
    detail_out,
    list_item_out,
)
from app.services.content_safety import scan_images, scan_text
from app.services.recognizer import recognize
from app.services.records import load_owned_record
from app.services.storage import process_images
from app.utils.timeutil import now_cn

router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])

_WS_RE = re.compile(r"\s+")

# 这个路由直接读 Request（要同时兼容 multipart 与 JSON），所以 Swagger 不会自动生成请求体，
# 手动补一份 schema，保证 /docs 仍然可用可读
_DIAGNOSIS_BODY_SCHEMA = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["images"],
                    "properties": {
                        "images": {
                            "type": "array",
                            "items": {"type": "string", "format": "binary"},
                            "description": "1–3 张图片，单张 ≤ 2MB，支持 jpg/jpeg/png/webp",
                        },
                        "plant_hint": {"type": "string", "description": "作物提示，如 番茄"},
                        "client_ts": {"type": "integer", "description": "客户端毫秒时间戳"},
                    },
                }
            },
            "application/json": {
                "schema": {
                    "type": "object",
                    "required": ["images"],
                    "properties": {
                        "images": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "base64 或 data URL 数组（小程序多图上传用）",
                        },
                        "plant_hint": {"type": "string"},
                        "client_ts": {"type": "integer"},
                    },
                }
            },
        },
    }
}


def _as_int(value) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _as_str(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _decode_base64_image(value) -> tuple[str, bytes]:
    """把 JSON 里的 base64 / data URL / {data, filename} 统一解码成字节。"""
    if isinstance(value, str):
        raw = value
        filename = ""
    elif isinstance(value, dict):
        raw = value.get("data") or value.get("base64") or ""
        filename = str(value.get("filename") or "")
    else:
        raise BizError(Code.PARAM_INVALID, "images 元素必须是 base64 字符串或对象")

    if not raw:
        raise BizError(Code.PARAM_INVALID, "图片 data 不能为空")
    if raw.startswith("data:"):
        raw = raw.partition(",")[2]  # 去掉 data:image/jpeg;base64, 前缀
    try:
        content = base64.b64decode(_WS_RE.sub("", raw))
    except (ValueError, TypeError) as exc:
        raise BizError(Code.IMAGE_FORMAT_UNSUPPORTED, "图片 base64 解码失败") from exc
    return filename, content


async def _extract_request(request: Request) -> tuple[list[tuple[str, bytes]], str | None, int | None]:
    """从请求里取出 [(文件名, 字节)]、plant_hint、client_ts，兼容 multipart 与 JSON 两种体。"""
    content_type = (request.headers.get("content-type") or "").lower()

    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        items: list[tuple[str, bytes]] = []
        for part in form.getlist("images"):
            if hasattr(part, "read"):  # 文件字段
                content = await part.read()
                items.append((getattr(part, "filename", "") or "", content))
        return items, _as_str(form.get("plant_hint")), _as_int(form.get("client_ts"))

    if content_type.startswith("application/json"):
        try:
            body = await request.json()
        except ValueError as exc:
            raise BizError(Code.PARAM_INVALID, "请求体不是合法 JSON") from exc
        if not isinstance(body, dict):
            raise BizError(Code.PARAM_INVALID, "请求体必须是 JSON 对象")
        raw_images = body.get("images") or []
        if not isinstance(raw_images, list):
            raise BizError(Code.PARAM_INVALID, "images 必须是数组")
        items = [_decode_base64_image(x) for x in raw_images]
        return items, _as_str(body.get("plant_hint")), _as_int(body.get("client_ts"))

    raise BizError(Code.PARAM_INVALID, "Content-Type 必须是 multipart/form-data 或 application/json")


@router.post(
    "",
    response_model=ApiResponse[DiagnosisData],
    summary="上传图片并发起识别",
    openapi_extra=_DIAGNOSIS_BODY_SCHEMA,
)
async def create_diagnosis(request: Request, user_id: CurrentUserId, db: DbSession) -> ApiResponse[DiagnosisData]:
    items, plant_hint, client_ts = await _extract_request(request)
    images = process_images(items)  # 张数/大小/格式校验（不合法在落库前就抛出去，不扣额度）

    # T3.4 内容安全：图片 + 文本，违规直接 2004，且发生在扣额度之前
    await scan_images(images)
    await scan_text(plant_hint)

    outcome = await recognize(db, user_id, images, plant_hint=plant_hint, client_ts=client_ts)
    data = DiagnosisData(
        record_id=str(outcome.record.id),
        status=outcome.status,
        degraded=outcome.degraded,
        latency_ms=outcome.latency_ms,
        remaining_quota=outcome.remaining_quota,
        result=DiseaseResult.model_validate(outcome.record.result_json),
    )
    if outcome.degraded:
        # 降级仍返回完整结果（前端正常渲染 + "降级"标识），业务码用 5001，HTTP 200（API接口文档 3.4 错误码表）
        return ApiResponse(code=Code.DEGRADED, message=message_of(Code.DEGRADED), data=data)
    return ok(data)


@router.get("/{record_id}", response_model=ApiResponse[DiagnosisDetail], summary="查询单条识别结果")
async def get_diagnosis(record_id: int, user_id: CurrentUserId, db: DbSession) -> ApiResponse[DiagnosisDetail]:
    record = load_owned_record(db, record_id, user_id)
    return ok(detail_out(record))


@router.get("", response_model=ApiResponse[PageData[DiagnosisListItem]], summary="诊断历史（分页）")
async def list_diagnosis(
    user_id: CurrentUserId,
    db: DbSession,
    page_params: PageParams,
    status: str | None = Query(default=None, description="按状态过滤，如 success"),
) -> ApiResponse[PageData[DiagnosisListItem]]:
    page, page_size = page_params
    conditions = [
        DiagnosisRecord.user_id == user_id,
        DiagnosisRecord.deleted_at.is_(None),
    ]
    if status:
        conditions.append(DiagnosisRecord.status == status)

    total = int(db.scalar(select(func.count()).select_from(DiagnosisRecord).where(*conditions)) or 0)
    rows = db.scalars(
        select(DiagnosisRecord)
        .where(*conditions)
        .order_by(DiagnosisRecord.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return ok(
        PageData[DiagnosisListItem](
            list=[list_item_out(r) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
            has_more=page * page_size < total,
        )
    )


@router.delete("/{record_id}", response_model=ApiResponse[None], summary="删除记录（软删除）")
async def delete_diagnosis(record_id: int, user_id: CurrentUserId, db: DbSession) -> ApiResponse[None]:
    record = load_owned_record(db, record_id, user_id)
    record.deleted_at = now_cn()
    db.commit()
    return ok(None)
