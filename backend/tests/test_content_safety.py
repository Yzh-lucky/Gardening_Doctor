"""T3.4 验收：内容安全（图片 + 文本）在识别主链路上的接线。

三条分支都要覆盖：
- 未配置微信凭证 → 跳过并放行（本地开发不能因缺凭证卡住识别）
- 配置了且命中违规码 → 2004，不落库、不扣额度
- 安全接口不可用（抛异常）→ fail-open 放行，不拖垮主链路

运行：在 backend/ 目录执行 `python -m pytest tests -q`
"""
import pytest
from conftest import PNG_BYTES
from sqlalchemy import func, select
from test_diagnosis import FakeProvider, _use_provider

from app.core.config import settings
from app.models.diagnosis import DiagnosisRecord
from app.models.quota import QuotaUsage
from app.services import content_safety


@pytest.fixture()
def wechat_configured(monkeypatch):
    """临时把微信凭证"配好"，触发真正的内容检测分支（不发起网络请求）。"""
    monkeypatch.setattr(settings, "WECHAT_APPID", "wx_test_appid")
    monkeypatch.setattr(settings, "WECHAT_SECRET", "wx_test_secret")


@pytest.fixture()
def wechat_missing(monkeypatch):
    monkeypatch.setattr(settings, "WECHAT_APPID", "")
    monkeypatch.setattr(settings, "WECHAT_SECRET", "")


def _patch(monkeypatch, *, token=None, img=None, msg=None):
    async def _tok():
        return "fake-token"

    monkeypatch.setattr(content_safety, "_get_access_token", token or _tok)
    if img is not None:
        monkeypatch.setattr(content_safety, "_img_sec_check", img)
    if msg is not None:
        monkeypatch.setattr(content_safety, "_msg_sec_check", msg)


def _assert_nothing_charged(auth, db_session):
    db_session.rollback()  # 先结束旧快照，才能看到 client 那边刚提交的数据
    user_id = auth["user_id"]
    records = db_session.scalar(
        select(func.count()).select_from(DiagnosisRecord).where(DiagnosisRecord.user_id == user_id)
    )
    assert records == 0, "被内容安全拦下的请求不该落库"
    quota = db_session.scalar(select(QuotaUsage).where(QuotaUsage.user_id == user_id))
    assert quota is None or int(quota.used_count) == 0, "被拦下的请求不该扣额度"


def test_image_violation_blocked(auth, monkeypatch, wechat_configured, db_session):
    _use_provider(monkeypatch, FakeProvider())

    async def _img(token, image):
        return content_safety.UNSAFE_ERRCODE

    _patch(monkeypatch, img=_img)

    resp = auth["client"].post(
        "/api/v1/diagnosis",
        files={"images": ("leaf.png", PNG_BYTES, "image/png")},
        headers=auth["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 2004
    _assert_nothing_charged(auth, db_session)


def test_text_violation_blocked(auth, monkeypatch, wechat_configured, db_session):
    _use_provider(monkeypatch, FakeProvider())

    async def _msg(token, text):
        return content_safety.UNSAFE_ERRCODE

    _patch(monkeypatch, msg=_msg)

    resp = auth["client"].post(
        "/api/v1/diagnosis",
        files={"images": ("leaf.png", PNG_BYTES, "image/png")},
        data={"plant_hint": "违规文本"},
        headers=auth["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 2004
    _assert_nothing_charged(auth, db_session)


def test_safety_api_failure_fails_open(auth, monkeypatch, wechat_configured):
    provider = FakeProvider()
    _use_provider(monkeypatch, provider)

    async def _boom(token, image):
        raise RuntimeError("security api down")

    async def _msg_boom(token, text):
        raise RuntimeError("security api down")

    _patch(monkeypatch, img=_boom, msg=_msg_boom)

    body = auth["client"].post(
        "/api/v1/diagnosis",
        files={"images": ("leaf.png", PNG_BYTES, "image/png")},
        data={"plant_hint": "番茄"},
        headers=auth["headers"],
    ).json()
    # 安全接口挂了不能连累识别：正常出结果
    assert body["code"] == 0, body
    assert body["data"]["status"] == "success"


def test_skipped_when_not_configured(auth, monkeypatch, wechat_missing):
    _use_provider(monkeypatch, FakeProvider())

    async def _must_not_be_called():
        raise AssertionError("未配置微信凭证时不应请求 access_token")

    _patch(monkeypatch, token=_must_not_be_called)

    body = auth["client"].post(
        "/api/v1/diagnosis",
        files={"images": ("leaf.png", PNG_BYTES, "image/png")},
        data={"plant_hint": "番茄"},
        headers=auth["headers"],
    ).json()
    assert body["code"] == 0, body
