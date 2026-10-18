"""识别编排（准备文档 3.3 流水线）。

流程：额度校验 → 首图 sha256 缓存命中 → 调大模型 → JSON 解析+Schema 校验（失败降温度重试 1 次）
→ 仍失败走知识库降级 → 落库 + 扣额度（成功/dengraded 各计一次）。

失败不扣额度的场景在路由层就拦掉了（格式/大小/额度），到这里要么产出一个结果，
要么产出降级结果，所以本函数**一定**会有 record 落库并计费一次。
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.response import BizError, Code
from app.models.diagnosis import DiagnosisRecord
from app.prompts import CURRENT_VERSION, load_prompt
from app.schemas.diagnosis import DiseaseResult
from app.services.degrade import degrade_result
from app.services.guard import check_cost_circuit, check_rate_limit
from app.services.llm import LLMError, LLMImage, get_llm_provider
from app.services.quota import get_or_create_quota
from app.services.storage import UploadedImage
from app.utils.timeutil import today_cn

logger = get_logger("app.recognizer")

# 只有这两个状态算"有效结果"，缓存复用与之对齐
_VALID_STATUS = ("success", "degraded")

# 模型偶尔会把 JSON 包在 ```json ... ``` 里，解析前先剥壳
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


class RecognizerOutcome:
    """编排结果：给路由层拼响应、给单测断言。"""

    __slots__ = ("record", "status", "degraded", "remaining_quota", "latency_ms")

    def __init__(
        self,
        record: DiagnosisRecord,
        status: str,
        remaining_quota: int,
        latency_ms: int,
    ) -> None:
        self.record = record
        self.status = status
        self.degraded = status == "degraded"
        self.remaining_quota = remaining_quota
        self.latency_ms = latency_ms


def build_user_prompt(plant_hint: str | None, image_count: int) -> str:
    parts = [f"请诊断这组植物照片（共 {image_count} 张，按顺序为多角度/多部位）。"]
    if plant_hint:
        parts.append(f"用户提供的作物提示：{plant_hint}。")
    parts.append("严格按约定的 JSON 结构输出，不要输出任何多余文字。")
    return "".join(parts)


def parse_result(text: str) -> DiseaseResult:
    """把模型返回的文本解析成 DiseaseResult；任何一步不对都抛 ValidationError/JSONDecodeError。"""
    cleaned = _FENCE_RE.sub("", (text or "").strip())
    data = json.loads(cleaned)
    return DiseaseResult.model_validate(data)


def find_cache(db: Session, image_hash: str, prompt_version: str, model_name: str) -> DiagnosisRecord | None:
    """同日 + 同 prompt 版本 + 同模型的同图结果，直接复用（不重复烧 Token，也不重复扣额度）。"""
    since = datetime.combine(today_cn(), datetime.min.time())
    return db.scalar(
        select(DiagnosisRecord)
        .where(
            DiagnosisRecord.image_hash == image_hash,
            DiagnosisRecord.prompt_version == prompt_version,
            DiagnosisRecord.model_name == model_name,
            DiagnosisRecord.status.in_(_VALID_STATUS),
            DiagnosisRecord.created_at >= since,
            DiagnosisRecord.deleted_at.is_(None),
            DiagnosisRecord.result_json.isnot(None),
        )
        .order_by(DiagnosisRecord.id.desc())
        .limit(1)
    )


def _new_record(
    user_id: int,
    image_urls: list[str],
    image_hash: str,
    status: str,
    result: DiseaseResult,
    model_name: str,
    cost_tokens: int,
    latency_ms: int,
) -> DiagnosisRecord:
    return DiagnosisRecord(
        user_id=user_id,
        image_urls=image_urls,
        image_hash=image_hash,
        status=status,
        prompt_version=CURRENT_VERSION,
        model_name=model_name,
        disease_name=result.disease_name,
        confidence=result.confidence,
        result_json=result.model_dump(mode="json"),
        cost_tokens=cost_tokens,
        latency_ms=latency_ms,
    )


async def recognize(
    db: Session,
    user_id: int,
    images: list[UploadedImage],
    plant_hint: str | None = None,
    client_ts: int | None = None,
) -> RecognizerOutcome:
    started = time.perf_counter()

    # ① 限流：每用户每分钟 + 全局 QPS，超限 3002/429，不消耗任何额度
    check_rate_limit(user_id)

    # ② 额度校验：超限直接 429，不落库不扣费
    quota = get_or_create_quota(db, user_id)
    if int(quota.used_count) >= int(quota.limit_count):
        raise BizError(Code.QUOTA_EXHAUSTED)

    provider = get_llm_provider()
    image_urls = [img.url for img in images]
    primary_hash = images[0].sha256

    # ③ 缓存命中：复用已有结果，新建一条归属当前用户的记录，但**不再扣额度**
    cached = find_cache(db, primary_hash, CURRENT_VERSION, provider.model)
    if cached is not None:
        result = DiseaseResult.model_validate(cached.result_json)
        record = _new_record(
            user_id=user_id,
            image_urls=image_urls,
            image_hash=primary_hash,
            status=cached.status,
            result=result,
            model_name=provider.model,
            cost_tokens=0,
            latency_ms=0,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        logger.info("diagnosis_cache_hit", extra={"record_id": record.id, "source_id": cached.id})
        elapsed = int((time.perf_counter() - started) * 1000)
        remaining = max(int(quota.limit_count) - int(quota.used_count), 0)
        return RecognizerOutcome(record, cached.status, remaining, elapsed)

    # ④ 成本熔断：放在缓存之后、真调模型之前——命中缓存的请求不烧 Token，没必要拦
    today_cost = check_cost_circuit(db)

    # ⑤ 调大模型：先正常温度，失败降温度重试一次
    system_prompt = load_prompt()
    user_prompt = build_user_prompt(plant_hint, len(images))
    llm_images = [LLMImage(content=img.content, mime_type=img.mime) for img in images]

    result: DiseaseResult | None = None
    cost_tokens = 0
    llm_ms = 0
    last_error = ""

    for attempt, temperature in enumerate((0.2, 0.0), start=1):
        try:
            resp = await provider.chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                images=llm_images,
                temperature=temperature,
            )
            llm_ms += resp.latency_ms
            cost_tokens += resp.total_tokens
            result = parse_result(resp.text)
            logger.info(
                "llm_parse_ok",
                extra={"attempt": attempt, "model": resp.model_name, "llm_ms": resp.latency_ms},
            )
            break
        except LLMError as exc:
            last_error = f"LLMError: {exc}"
            logger.warning("llm_call_failed", extra={"attempt": attempt, "retryable": exc.retryable, "detail": str(exc)})
            if not exc.retryable:
                break
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            # 畸形输出是最常见的失败：降温度重试一次，仍不行就降级
            logger.warning("llm_parse_failed", extra={"attempt": attempt, "detail": str(exc)[:300]})

    # ⑥ 成功 / 降级分支
    if result is not None:
        status = "success"
    else:
        status = "degraded"
        result = degrade_result(db, plant_hint)
        logger.warning("diagnosis_degraded", extra={"reason": last_error[:300]})

    latency_ms = int((time.perf_counter() - started) * 1000)
    record = _new_record(
        user_id=user_id,
        image_urls=image_urls,
        image_hash=primary_hash,
        status=status,
        result=result,
        model_name=provider.model,
        cost_tokens=cost_tokens,
        latency_ms=latency_ms,
    )
    db.add(record)

    # ⑦ 扣额度：成功与降级都计一次（降级也算产出了结果，见 API接口文档 3.4 说明）
    quota.used_count = int(quota.used_count) + 1
    db.commit()
    db.refresh(record)

    remaining = max(int(quota.limit_count) - int(quota.used_count), 0)
    logger.info(
        "diagnosis_done",
        extra={
            "record_id": record.id,
            "status": status,
            "latency_ms": latency_ms,
            "llm_ms": llm_ms,
            "cost_tokens": cost_tokens,
            "today_cost_cny": round(today_cost, 4),
            "client_ts": client_ts,
        },
    )
    return RecognizerOutcome(record, status, remaining, latency_ms)
