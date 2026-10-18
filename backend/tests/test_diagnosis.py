"""T2.4 验收：识别编排三条支路（成功 / 重试 / 降级）+ T2.1 上传校验与越权。

运行：在 backend/ 目录执行 `python -m pytest tests -q`
"""
import json
import uuid

import pytest
from conftest import PNG_BASE64, PNG_BYTES

from app.services.llm.base import LLMError, LLMResponse
from app.services.llm.stub import _STUB_RESULT


class FakeProvider:
    """可控的假模型：按脚本依次吐文本或抛错，方便断言"重试了几次、温度是多少"。"""

    name = "fake"

    def __init__(self, texts=None, errors=None, model=None):
        # model 每次都不同，避免跨用例命中 recognizer 的 sha256 缓存
        self.model = model or f"fake-{uuid.uuid4().hex[:8]}"
        self.texts = list(texts or [])
        self.errors = list(errors or [])
        self.calls = []  # 记录每次调用的 temperature

    async def chat(self, system_prompt, user_prompt, images=None, temperature=0.2, json_mode=True, max_tokens=2048):
        self.calls.append(temperature)
        if self.errors:
            raise self.errors.pop(0)
        text = self.texts.pop(0) if self.texts else json.dumps(_STUB_RESULT, ensure_ascii=False)
        return LLMResponse(text=text, model_name=self.model, prompt_tokens=100, completion_tokens=50, latency_ms=7)

    def health(self):
        return "up"


def _use_provider(monkeypatch, provider):
    # recognizer 内部是从 app.services.llm 导入的 get_llm_provider，patch 它的名字即可
    monkeypatch.setattr("app.services.recognizer.get_llm_provider", lambda: provider)


def _text_error(msg="boom"):
    return LLMError(msg, retryable=True)


# ---------- 成功支路 ----------


def test_success_branch_and_detail_list_delete(auth, monkeypatch):
    provider = FakeProvider()
    _use_provider(monkeypatch, provider)

    resp = auth["client"].post(
        "/api/v1/diagnosis",
        files={"images": ("leaf.png", PNG_BYTES, "image/png")},
        data={"plant_hint": "番茄", "client_ts": "1760000000000"},
        headers=auth["headers"],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0, body
    data = body["data"]
    assert data["status"] == "success"
    assert data["degraded"] is False
    assert data["result"]["disease_name"] == "番茄早疫病"
    assert data["result"]["plan_l1_safe"]["items"], "L1 方案必须非空"
    assert data["remaining_quota"] == 9  # 成功扣一次
    assert provider.calls == [0.2]

    record_id = data["record_id"]

    # 查详情：图片 URL 应指向后端静态目录，且真的能取到文件（T2.1 存储抽象验收）
    detail = auth["client"].get(f"/api/v1/diagnosis/{record_id}", headers=auth["headers"]).json()
    assert detail["code"] == 0
    urls = detail["data"]["image_urls"]
    assert urls and urls[0].startswith("/static/")
    assert auth["client"].get(urls[0]).status_code == 200
    assert detail["data"]["confidence"] == pytest.approx(0.86)

    # 列表
    listing = auth["client"].get("/api/v1/diagnosis", headers=auth["headers"]).json()
    assert listing["code"] == 0
    assert listing["data"]["total"] == 1
    assert listing["data"]["list"][0]["id"] == record_id

    # 删除（软删除）后列表为空，详情 4001
    assert auth["client"].delete(f"/api/v1/diagnosis/{record_id}", headers=auth["headers"]).json()["code"] == 0
    assert auth["client"].get("/api/v1/diagnosis", headers=auth["headers"]).json()["data"]["total"] == 0
    assert auth["client"].get(f"/api/v1/diagnosis/{record_id}", headers=auth["headers"]).json()["code"] == 4001


def test_json_base64_multi_image(auth, monkeypatch):
    """小程序多图走 JSON + base64 的备用路径也要通。"""
    provider = FakeProvider()
    _use_provider(monkeypatch, provider)

    resp = auth["client"].post(
        "/api/v1/diagnosis",
        json={"images": [f"data:image/png;base64,{PNG_BASE64}", PNG_BASE64], "plant_hint": "番茄"},
        headers=auth["headers"],
    )
    body = resp.json()
    assert body["code"] == 0, body
    detail = auth["client"].get(f"/api/v1/diagnosis/{body['data']['record_id']}", headers=auth["headers"]).json()
    assert len(detail["data"]["image_urls"]) == 2  # 两张图都落盘了


# ---------- 重试支路 ----------


def test_retry_then_success(auth, monkeypatch):
    """首次输出畸形 → 降温度重试一次 → 成功。"""
    provider = FakeProvider(texts=["这不是 JSON", json.dumps(_STUB_RESULT, ensure_ascii=False)])
    _use_provider(monkeypatch, provider)

    body = auth["client"].post(
        "/api/v1/diagnosis",
        files={"images": ("leaf.png", PNG_BYTES, "image/png")},
        headers=auth["headers"],
    ).json()
    assert body["code"] == 0, body
    assert body["data"]["status"] == "success"
    assert provider.calls == [0.2, 0.0], "重试必须降低 temperature"


# ---------- 降级支路 ----------


def test_degrade_branch(auth, monkeypatch):
    """模型连续两次失败 → 知识库兜底，返回 degraded（业务码 5001），仍计一次额度。"""
    provider = FakeProvider(errors=[_text_error("超时1"), _text_error("超时2")])
    _use_provider(monkeypatch, provider)

    resp = auth["client"].post(
        "/api/v1/diagnosis",
        files={"images": ("leaf.png", PNG_BYTES, "image/png")},
        headers=auth["headers"],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 5001, body
    assert body["data"]["status"] == "degraded"
    assert body["data"]["degraded"] is True
    assert body["data"]["result"]["need_more_info"] is True
    assert body["data"]["result"]["plan_l1_safe"]["items"], "降级结果也必须给 L1"
    assert body["data"]["remaining_quota"] == 9  # 降级按成功计一次
    assert len(provider.calls) == 2


def test_degrade_falls_back_to_knowledge_base(auth, monkeypatch, db_session):
    """知识库里有匹配条目时，降级结果应来自知识库而不是通用兜底。"""
    from sqlalchemy import delete

    from app.models.disease import Disease

    # 名称带后缀：既能被 plant_hint 的 LIKE 匹配到，又避免与已有数据的唯一键冲突
    name = "番茄早疫病-降级测试"
    db_session.execute(delete(Disease).where(Disease.name == name))
    db_session.add(
        Disease(
            name=name,
            aliases="轮纹病",
            category="真菌性病害",
            symptoms="叶片出现深褐色同心轮纹斑。",
            plan_l1={"title": "家庭零风险处置", "items": ["摘除病叶"]},
            plan_l2={"title": "低毒合规处置", "items": [], "note": "发展快时再用"},
            plan_l3={"title": "专业干预", "items": ["联系植保站"], "risk_note": "有风险"},
            safety_notes="药剂放好\n施药后洗手",
            confused_with="番茄晚疫病",
            version=1,
        )
    )
    db_session.commit()

    try:
        provider = FakeProvider(errors=[_text_error("挂1"), _text_error("挂2")])
        _use_provider(monkeypatch, provider)
        body = auth["client"].post(
            "/api/v1/diagnosis",
            files={"images": ("leaf.png", PNG_BYTES, "image/png")},
            data={"plant_hint": name},
            headers=auth["headers"],
        ).json()
        result = body["data"]["result"]
        assert result["disease_name"] == name
        assert result["confidence"] == pytest.approx(0.6)
        assert result["aliases"] == ["轮纹病"]
        assert result["safety_notes"] == ["药剂放好", "施药后洗手"]
    finally:
        db_session.execute(delete(Disease).where(Disease.name == name))
        db_session.commit()


# ---------- T2.1 上传校验 ----------


def test_reject_unsupported_format(auth, monkeypatch):
    _use_provider(monkeypatch, FakeProvider())
    resp = auth["client"].post(
        "/api/v1/diagnosis",
        files={"images": ("note.txt", b"this is not an image", "text/plain")},
        headers=auth["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 2002


def test_reject_oversize(auth, monkeypatch):
    _use_provider(monkeypatch, FakeProvider())
    big = PNG_BYTES + b"\x00" * (3 * 1024 * 1024)  # 魔数合法但体积超过 2MB
    resp = auth["client"].post(
        "/api/v1/diagnosis",
        files={"images": ("big.png", big, "image/png")},
        headers=auth["headers"],
    )
    assert resp.status_code == 413
    assert resp.json()["code"] == 2003


def test_reject_too_many_images(auth, monkeypatch):
    _use_provider(monkeypatch, FakeProvider())
    files = [("images", (f"l{i}.png", PNG_BYTES, "image/png")) for i in range(4)]
    resp = auth["client"].post("/api/v1/diagnosis", files=files, headers=auth["headers"])
    assert resp.status_code == 413
    assert resp.json()["code"] == 2003


def test_reject_missing_images(auth, monkeypatch):
    _use_provider(monkeypatch, FakeProvider())
    resp = auth["client"].post("/api/v1/diagnosis", data={"plant_hint": "番茄"}, headers=auth["headers"])
    assert resp.json()["code"] == 2001


def test_requires_auth(client):
    resp = client.post("/api/v1/diagnosis", json={"images": [PNG_BASE64]})
    assert resp.status_code == 401
    assert resp.json()["code"] == 1001


# ---------- 越权 / 找不存在 ----------


def test_cross_user_forbidden(auth, client, monkeypatch):
    _use_provider(monkeypatch, FakeProvider())
    record_id = auth["client"].post(
        "/api/v1/diagnosis",
        files={"images": ("leaf.png", PNG_BYTES, "image/png")},
        headers=auth["headers"],
    ).json()["data"]["record_id"]

    # 另一个用户来查 → 4002（不回 404，避免枚举探测）
    other = client.post("/api/v1/auth/login", json={"code": "mock_pytest_" + uuid.uuid4().hex[:12]}).json()
    other_headers = {"Authorization": f"Bearer {other['data']['token']}"}
    try:
        assert client.get(f"/api/v1/diagnosis/{record_id}", headers=other_headers).json()["code"] == 4002
    finally:
        from sqlalchemy import delete

        from app.core.database import SessionLocal
        from app.models.quota import QuotaUsage
        from app.models.user import User

        db = SessionLocal()
        uid = int(other["data"]["user"]["id"])
        db.execute(delete(QuotaUsage).where(QuotaUsage.user_id == uid))
        db.execute(delete(User).where(User.id == uid))
        db.commit()
        db.close()


def test_record_not_found(auth):
    assert auth["client"].get("/api/v1/diagnosis/999999", headers=auth["headers"]).json()["code"] == 4001


# ---------- 额度 ----------


def test_quota_exhausted(auth, monkeypatch):
    _use_provider(monkeypatch, FakeProvider())
    from app.core.database import SessionLocal
    from app.services.quota import get_or_create_quota

    db = SessionLocal()
    quota = get_or_create_quota(db, auth["user_id"])
    quota.used_count = quota.limit_count  # 直接顶到上限，省去跑 10 次
    db.commit()
    db.close()

    resp = auth["client"].post(
        "/api/v1/diagnosis",
        files={"images": ("leaf.png", PNG_BYTES, "image/png")},
        headers=auth["headers"],
    )
    assert resp.status_code == 429
    assert resp.json()["code"] == 3001
