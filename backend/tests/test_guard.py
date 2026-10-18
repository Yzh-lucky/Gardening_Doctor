"""T3.3 验收：双维度限流 + 成本熔断（护栏都必须"不扣额度"）。

运行：在 backend/ 目录执行 `python -m pytest tests -q`
"""
import hashlib
import json
import uuid
from datetime import timedelta

import pytest
from conftest import PNG_BYTES
from sqlalchemy import select

from app.core.config import settings
from app.models.diagnosis import DiagnosisRecord
from app.models.quota import QuotaUsage
from app.services.guard import reset_rate_limiter, today_cost_cny
from app.services.llm.base import LLMResponse
from app.services.llm.stub import StubProvider, _STUB_RESULT
from app.utils.timeutil import now_cn


class FakeProvider:
    """假的模型：只记录"被调了几次"，用来验证熔断时模型根本没被调用。"""

    name = "fake"

    def __init__(self):
        self.model = f"fake-{uuid.uuid4().hex[:8]}"
        self.calls = 0

    async def chat(self, system_prompt, user_prompt, images=None, temperature=0.2, json_mode=True, max_tokens=2048):
        self.calls += 1
        return LLMResponse(
            text=json.dumps(_STUB_RESULT, ensure_ascii=False),
            model_name=self.model,
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=5,
        )

    def health(self):
        return "up"


@pytest.fixture(autouse=True)
def _isolate_limiter():
    """每个用例前后清空计数窗口，避免用例之间互相踩限流阈值。"""
    reset_rate_limiter()
    yield
    reset_rate_limiter()


def _use_provider(monkeypatch, provider):
    monkeypatch.setattr("app.services.recognizer.get_llm_provider", lambda: provider)


def _diagnose(ctx):
    return ctx["client"].post(
        "/api/v1/diagnosis",
        files={"images": ("leaf.png", PNG_BYTES, "image/png")},
        data={"plant_hint": "番茄"},
        headers=ctx["headers"],
    )


def _seed_record(db, user_id, *, cost_tokens=100, image_hash=None, model_name="seed-model", status="success"):
    record = DiagnosisRecord(
        user_id=user_id,
        image_urls=["/static/2026/10/seed.png"],
        image_hash=image_hash or uuid.uuid4().hex,
        status=status,
        prompt_version="v1",
        model_name=model_name,
        disease_name="番茄早疫病",
        confidence=0.8,
        result_json=dict(_STUB_RESULT),
        cost_tokens=cost_tokens,
        latency_ms=900,
        created_at=now_cn(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _count_records(db, user_id):
    return len(db.scalars(select(DiagnosisRecord).where(DiagnosisRecord.user_id == user_id)).all())


# ---------- 维度一：每用户每分钟 ----------


def test_user_rate_limit_blocks_and_does_not_charge(auth, db_session, monkeypatch):
    _use_provider(monkeypatch, FakeProvider())
    monkeypatch.setattr(settings, "RATE_LIMIT_USER_PER_MINUTE", 1)
    monkeypatch.setattr(settings, "RATE_LIMIT_GLOBAL_QPS", 50)

    first = _diagnose(auth)
    assert first.status_code == 200
    assert first.json()["code"] == 0

    second = _diagnose(auth)
    assert second.status_code == 429
    assert second.json()["code"] == 3002

    db_session.rollback()
    # 被限流的那次不落库、不扣额度
    assert _count_records(db_session, auth["user_id"]) == 1
    quota = db_session.scalar(select(QuotaUsage).where(QuotaUsage.user_id == auth["user_id"]))
    assert quota.used_count == 1


# ---------- 维度二：全局 QPS ----------


def test_global_qps_limit_blocks(auth, monkeypatch):
    _use_provider(monkeypatch, FakeProvider())
    monkeypatch.setattr(settings, "RATE_LIMIT_USER_PER_MINUTE", 50)
    monkeypatch.setattr(settings, "RATE_LIMIT_GLOBAL_QPS", 1)

    assert _diagnose(auth).json()["code"] == 0

    # 同一秒内的第二次请求触发全局 QPS 上限（与用户维度无关）
    second = _diagnose(auth)
    assert second.status_code == 429
    assert second.json()["code"] == 3002


# ---------- 成本熔断 ----------


def test_cost_circuit_blocks_llm_before_calling(auth, db_session, monkeypatch):
    provider = FakeProvider()
    _use_provider(monkeypatch, provider)
    # 1 元 / 千 token，上限 1 元；先造一条今天已经烧掉 2000 token 的记录 → 已超限
    monkeypatch.setattr(settings, "LLM_PRICE_PER_1K_TOKENS", 1.0)
    monkeypatch.setattr(settings, "DAILY_COST_LIMIT_CNY", 1.0)
    _seed_record(db_session, auth["user_id"], cost_tokens=2000)

    today_cost = today_cost_cny(db_session)
    assert today_cost >= 1.0

    resp = _diagnose(auth)
    assert resp.status_code == 429
    assert resp.json()["code"] == 3002
    assert resp.json()["data"] is None

    # 熔断生效：模型一次都没调，也没扣额度
    assert provider.calls == 0
    db_session.rollback()
    assert _count_records(db_session, auth["user_id"]) == 1  # 只有那条种子记录
    quota = db_session.scalar(select(QuotaUsage).where(QuotaUsage.user_id == auth["user_id"]))
    assert quota is None or quota.used_count == 0


def test_cost_circuit_does_not_block_cache_hit(auth, db_session, monkeypatch):
    """熔断拦的是"要真调模型"的请求；命中缓存的请求不烧 Token，照常返回。"""
    provider = StubProvider()
    _use_provider(monkeypatch, provider)
    monkeypatch.setattr(settings, "LLM_PRICE_PER_1K_TOKENS", 1.0)
    monkeypatch.setattr(settings, "DAILY_COST_LIMIT_CNY", 1.0)

    # 同一天 + 同一张图 + 同 Prompt 版本 + 同模型 → 命中 recognizer 缓存
    source = _seed_record(
        db_session,
        auth["user_id"],
        cost_tokens=2_000_000,  # 折算 2000 元，远超上限
        image_hash=hashlib.sha256(PNG_BYTES).hexdigest(),
        model_name=provider.model,
    )
    assert today_cost_cny(db_session) >= 1.0

    resp = _diagnose(auth)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0, body
    assert body["data"]["record_id"] != str(source.id)
    # 复用缓存不重复计费：额度没动
    assert body["data"]["remaining_quota"] == settings.DAILY_FREE_QUOTA

    db_session.rollback()
    fresh = db_session.get(DiagnosisRecord, int(body["data"]["record_id"]))
    assert fresh.cost_tokens == 0
    assert fresh.image_hash == source.image_hash
