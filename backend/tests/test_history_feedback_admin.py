"""T3.1 历史分页 + T3.2 反馈闭环 + T3.5 后台知识库/记录查询 的验收用例。

运行：在 backend/ 目录执行 `python -m pytest tests -q`
"""
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import delete

from app.core.security import hash_password
from app.models.admin import Admin
from app.models.diagnosis import DiagnosisRecord
from app.models.disease import Disease
from app.models.feedback import Feedback
from app.services.llm.stub import _STUB_RESULT
from app.utils.timeutil import now_cn


def _make_record(
    db, user_id, *, status="success", name="番茄早疫病", confidence=0.86, minutes_ago=0, latency_ms=1200, cost_tokens=100
):
    """直接造一条诊断记录：比跑一次完整识别快，且能精确控制状态/时间。"""
    record = DiagnosisRecord(
        user_id=user_id,
        image_urls=["/static/2026/10/pytest.png"],
        image_hash=uuid.uuid4().hex,
        status=status,
        prompt_version="v1",
        model_name="pytest-model",
        disease_name=name,
        confidence=confidence,
        result_json=dict(_STUB_RESULT),
        cost_tokens=cost_tokens,
        latency_ms=latency_ms,
        created_at=now_cn() - timedelta(minutes=minutes_ago),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@pytest.fixture()
def admin_ctx(db_session):
    """造一个临时管理员并登录，拿到后台 token。"""
    username = "adm_" + uuid.uuid4().hex[:8]
    password = "pytest-pass-123"
    admin = Admin(username=username, password_hash=hash_password(password))
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)

    yield {"id": admin.id, "username": username, "password": password}

    db_session.execute(delete(Admin).where(Admin.id == admin.id))
    db_session.commit()


# ---------- T3.1 历史列表 ----------


def test_history_paging_and_detail_consistency(auth, db_session):
    user_id = auth["user_id"]
    r1 = _make_record(db_session, user_id, name="番茄早疫病", minutes_ago=30)
    r2 = _make_record(db_session, user_id, name="蚜虫", status="degraded", minutes_ago=20)
    r3 = _make_record(db_session, user_id, name="白粉病", minutes_ago=10)

    page1 = auth["client"].get("/api/v1/diagnosis?page=1&page_size=2", headers=auth["headers"]).json()
    assert page1["code"] == 0
    data = page1["data"]
    assert data["total"] == 3
    assert data["page"] == 1 and data["page_size"] == 2
    assert data["has_more"] is True
    assert len(data["list"]) == 2
    # 按 id 倒序（最新在前）
    assert [x["id"] for x in data["list"]] == [str(r3.id), str(r2.id)]
    # 列表只给摘要：不带完整 result，但要有缩略图
    assert "result" not in data["list"][0]
    assert data["list"][0]["thumbnail"] == "/static/2026/10/pytest.png"
    assert data["list"][0]["confidence"] == pytest.approx(0.86)
    assert data["list"][0]["created_at"].endswith("+08:00")

    page2 = auth["client"].get("/api/v1/diagnosis?page=2&page_size=2", headers=auth["headers"]).json()
    assert [x["id"] for x in page2["data"]["list"]] == [str(r1.id)]
    assert page2["data"]["has_more"] is False

    # 状态过滤（页面按 success 只看成功记录）
    filtered = auth["client"].get("/api/v1/diagnosis?status=degraded", headers=auth["headers"]).json()
    assert filtered["data"]["total"] == 1
    assert filtered["data"]["list"][0]["id"] == str(r2.id)

    # 详情回看：结果必须与库里那份一致（历史详情复用结果页渲染的数据源）
    detail = auth["client"].get(f"/api/v1/diagnosis/{r3.id}", headers=auth["headers"]).json()
    assert detail["code"] == 0
    assert detail["data"]["result"]["disease_name"] == _STUB_RESULT["disease_name"]
    assert detail["data"]["disease_name"] == "白粉病"
    assert detail["data"]["image_urls"] == ["/static/2026/10/pytest.png"]


# ---------- T3.2 反馈 ----------


def test_feedback_wrong_closes_the_loop(auth, db_session):
    record = _make_record(db_session, auth["user_id"])

    resp = auth["client"].post(
        "/api/v1/feedback",
        json={
            "record_id": record.id,
            "type": "wrong",
            "correct_name": "番茄晚疫病",
            "comment": "病斑没有同心轮纹，边缘是水渍状",
        },
        headers=auth["headers"],
    )
    body = resp.json()
    assert body["code"] == 0, body
    assert body["data"]["record_status"] == "corrected"

    # 这里用独立的 Session 直连库校验，必须先把事务结束掉：
    # MySQL 默认 RR 隔离级别下，沿用旧快照读不到 client 那边刚提交的数据
    db_session.rollback()

    # 落库
    row = db_session.get(Feedback, int(body["data"]["feedback_id"]))
    assert row is not None
    assert row.type == "wrong"
    assert row.correct_name == "番茄晚疫病"
    assert row.user_id == auth["user_id"]

    # 纠错闭环：记录状态变成 corrected，历史列表能看到
    db_session.refresh(record)
    assert record.status == "corrected"
    listing = auth["client"].get("/api/v1/diagnosis", headers=auth["headers"]).json()
    assert listing["data"]["list"][0]["status"] == "corrected"


def test_feedback_like_does_not_change_status(auth, db_session):
    record = _make_record(db_session, auth["user_id"])

    body = auth["client"].post(
        "/api/v1/feedback",
        json={"record_id": record.id, "type": "like"},
        headers=auth["headers"],
    ).json()
    assert body["code"] == 0, body
    # "结果有帮助"≠"被纠正过"，不该把记录标成 corrected 污染准确率统计
    assert body["data"]["record_status"] == "success"
    db_session.rollback()  # 结束旧快照后再读，避免读到自己之前的缓存状态
    db_session.refresh(record)
    assert record.status == "success"


def test_feedback_rejects_other_users_record(auth, db_session):
    other = _make_record(db_session, auth["user_id"] + 999_999)
    try:
        body = auth["client"].post(
            "/api/v1/feedback",
            json={"record_id": other.id, "type": "dislike"},
            headers=auth["headers"],
        ).json()
        assert body["code"] == 4002
    finally:
        db_session.execute(delete(DiagnosisRecord).where(DiagnosisRecord.id == other.id))
        db_session.commit()


def test_feedback_param_invalid(auth, db_session):
    record = _make_record(db_session, auth["user_id"])

    # comment 超 200 字
    resp = auth["client"].post(
        "/api/v1/feedback",
        json={"record_id": record.id, "type": "wrong", "comment": "字" * 201},
        headers=auth["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 2001

    # type 不在枚举内
    assert (
        auth["client"].post(
            "/api/v1/feedback", json={"record_id": record.id, "type": "whatever"}, headers=auth["headers"]
        ).json()["code"]
        == 2001
    )

    # record_id 不是数字
    assert (
        auth["client"].post(
            "/api/v1/feedback", json={"record_id": "abc", "type": "like"}, headers=auth["headers"]
        ).json()["code"]
        == 2001
    )

    # 记录不存在
    assert (
        auth["client"].post(
            "/api/v1/feedback", json={"record_id": 999_999_999, "type": "like"}, headers=auth["headers"]
        ).json()["code"]
        == 4001
    )


# ---------- 后台 ----------


def test_admin_login_and_feedback_query(auth, db_session, admin_ctx):
    record = _make_record(db_session, auth["user_id"])
    auth["client"].post(
        "/api/v1/feedback",
        json={"record_id": record.id, "type": "wrong", "correct_name": "霜霉病"},
        headers=auth["headers"],
    )

    # 密码错误 → 6001
    assert (
        auth["client"].post(
            "/api/v1/admin/login", json={"username": admin_ctx["username"], "password": "wrong-pass"}
        ).json()["code"]
        == 6001
    )

    login = auth["client"].post(
        "/api/v1/admin/login",
        json={"username": admin_ctx["username"], "password": admin_ctx["password"]},
    ).json()
    assert login["code"] == 0, login
    assert login["data"]["expires_in"] == 12 * 3600
    admin_headers = {"Authorization": f"Bearer {login['data']['token']}"}

    listing = auth["client"].get(
        f"/api/v1/admin/feedbacks?record_id={record.id}", headers=admin_headers
    ).json()
    assert listing["code"] == 0
    assert listing["data"]["total"] == 1
    item = listing["data"]["list"][0]
    assert item["type"] == "wrong"
    assert item["correct_name"] == "霜霉病"
    assert item["record_id"] == str(record.id)


def test_admin_requires_admin_token(auth, client):
    # 用普通用户 token 摸后台 → 1003 / 403
    resp = client.get("/api/v1/admin/feedbacks", headers=auth["headers"])
    assert resp.status_code == 403
    assert resp.json()["code"] == 1003

    # 不带头 → 1001
    assert client.get("/api/v1/admin/feedbacks").json()["code"] == 1001


# ---------- T3.5 知识库 CRUD + 记录查询 ----------


def _admin_headers(client, admin_ctx):
    login = client.post(
        "/api/v1/admin/login",
        json={"username": admin_ctx["username"], "password": admin_ctx["password"]},
    ).json()
    assert login["code"] == 0, login
    return {"Authorization": f"Bearer {login['data']['token']}"}


@pytest.fixture()
def admin_headers(client, admin_ctx):
    return _admin_headers(client, admin_ctx)


@pytest.fixture()
def clean_disease_name(db_session):
    """生成一个唯一病名并保证用完删干净，避免污染真实知识库。"""
    name = "pytest病害-" + uuid.uuid4().hex[:6]

    def _purge():
        db_session.execute(delete(Disease).where(Disease.name.like("pytest病害-%")))
        db_session.commit()

    _purge()
    yield name
    _purge()


def test_admin_disease_crud(client, db_session, admin_headers, clean_disease_name):
    name = clean_disease_name
    payload = {
        "name": name,
        "aliases": "测试别名",
        "category": "真菌性病害",
        "symptoms": "叶片出现褐色斑点。",
        "plan_l1": {"title": "家庭零风险处置", "items": ["摘除病叶"]},
        "plan_l2": {"title": "低毒合规处置", "items": [{"name": "代森锰锌", "usage": "按说明书稀释，安全间隔期 7 天"}]},
        "safety_notes": "药剂放好\n施药后洗手",
        "confused_with": "番茄晚疫病",
    }

    created = client.post("/api/v1/admin/diseases", json=payload, headers=admin_headers).json()
    assert created["code"] == 0, created
    disease_id = created["data"]["id"]
    assert created["data"]["version"] == 1

    # 重名 → 6002
    dup = client.post("/api/v1/admin/diseases", json={"name": name}, headers=admin_headers).json()
    assert dup["code"] == 6002

    # 列表按关键字能搜到，且带 version / 完整方案
    listing = client.get(f"/api/v1/admin/diseases?keyword={name}", headers=admin_headers).json()
    assert listing["code"] == 0
    assert listing["data"]["total"] >= 1
    hit = next(x for x in listing["data"]["list"] if x["id"] == disease_id)
    assert hit["name"] == name
    assert hit["plan_l1"]["items"] == ["摘除病叶"]
    assert hit["plan_l2"]["items"][0]["name"] == "代森锰锌"
    assert hit["safety_notes"] == "药剂放好\n施药后洗手"

    # 部分更新：只改症状，version 自增
    updated = client.put(
        f"/api/v1/admin/diseases/{disease_id}", json={"symptoms": "叶片褐色斑点扩大。"}, headers=admin_headers
    ).json()
    assert updated["code"] == 0, updated
    assert updated["data"]["version"] == 2

    # 改名到已存在的病名 → 6002（另造一条来撞）
    other_name = name + "-B"
    assert (
        client.post("/api/v1/admin/diseases", json={"name": other_name}, headers=admin_headers).json()["code"] == 0
    )
    conflict = client.put(
        f"/api/v1/admin/diseases/{disease_id}", json={"name": other_name}, headers=admin_headers
    ).json()
    assert conflict["code"] == 6002

    # 改自身名字（不变）不该报重名
    same = client.put(f"/api/v1/admin/diseases/{disease_id}", json={"name": name}, headers=admin_headers).json()
    assert same["code"] == 0

    # 删除后列表搜不到，再删一次 4001
    assert client.delete(f"/api/v1/admin/diseases/{disease_id}", headers=admin_headers).json()["code"] == 0
    after = client.get(f"/api/v1/admin/diseases?keyword={name}", headers=admin_headers).json()
    assert all(x["id"] != disease_id for x in after["data"]["list"])
    assert client.delete(f"/api/v1/admin/diseases/{disease_id}", headers=admin_headers).json()["code"] == 4001


def test_admin_disease_update_missing(client, admin_headers):
    assert (
        client.put("/api/v1/admin/diseases/999999999", json={"symptoms": "x"}, headers=admin_headers).json()["code"]
        == 4001
    )
    assert client.delete("/api/v1/admin/diseases/999999999", headers=admin_headers).json()["code"] == 4001


def test_admin_records_filters(auth, client, db_session, admin_headers):
    user_id = auth["user_id"]
    _make_record(db_session, user_id, name="番茄早疫病", minutes_ago=5)
    _make_record(db_session, user_id, name="蚜虫", status="degraded", minutes_ago=4)

    by_user = client.get(f"/api/v1/admin/records?user_id={user_id}", headers=admin_headers).json()
    assert by_user["code"] == 0
    assert by_user["data"]["total"] == 2
    item = by_user["data"]["list"][0]
    assert item["user_id"] == str(user_id)
    assert item["created_at"].endswith("+08:00")

    by_status = client.get(
        f"/api/v1/admin/records?user_id={user_id}&status=degraded", headers=admin_headers
    ).json()
    assert [x["disease_name"] for x in by_status["data"]["list"]] == ["蚜虫"]

    today = now_cn().date().isoformat()
    in_range = client.get(
        f"/api/v1/admin/records?user_id={user_id}&start_date={today}&end_date={today}", headers=admin_headers
    ).json()
    assert in_range["data"]["total"] == 2

    # 非法日期 → 2001
    assert (
        client.get("/api/v1/admin/records?start_date=2026/10/01", headers=admin_headers).json()["code"] == 2001
    )


# ---------- T3.7 数据看板 ----------


def test_admin_stats_daily_aggregation(auth, client, db_session, admin_headers):
    user_id = auth["user_id"]
    _make_record(db_session, user_id, status="success", latency_ms=1000, cost_tokens=100)
    _make_record(db_session, user_id, status="degraded", latency_ms=2000, cost_tokens=100)
    _make_record(db_session, user_id, status="corrected", latency_ms=3000, cost_tokens=100)
    _make_record(db_session, user_id, status="failed", latency_ms=4000, cost_tokens=100)

    today = now_cn().date().isoformat()
    body = client.get(f"/api/v1/admin/stats?from={today}&to={today}", headers=admin_headers).json()
    assert body["code"] == 0, body
    assert len(body["data"]["days"]) == 1
    day = body["data"]["days"][0]
    assert day["stat_date"] == today
    assert day["total_calls"] == 4
    assert day["success_calls"] == 2  # success + corrected
    assert day["degraded_calls"] == 1
    assert day["failed_calls"] == 1
    assert day["success_rate"] == pytest.approx(0.5)
    assert day["avg_latency_ms"] == 2500
    assert day["p95_latency_ms"] == 4000
    assert day["total_cost_cny"] == pytest.approx(0.008)  # 400 tokens / 1000 * 0.02
    assert day["new_users"] >= 1

    summary = body["data"]["summary"]
    assert summary["total_calls"] == 4
    assert summary["success_rate"] == pytest.approx(0.5)
    assert summary["total_cost_cny"] == pytest.approx(0.008)

    # 默认区间（近 7 天）应补齐无数据的日子，不能缺行
    default_body = client.get("/api/v1/admin/stats", headers=admin_headers).json()
    assert len(default_body["data"]["days"]) == 7

    # 起止倒挂 → 2001
    assert (
        client.get("/api/v1/admin/stats?from=2026-10-10&to=2026-10-01", headers=admin_headers).json()["code"]
        == 2001
    )
