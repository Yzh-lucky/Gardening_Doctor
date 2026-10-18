"""pytest 公共夹具：复用真实 MySQL（本地开发库），每个用例用独立 mock 用户，用完清理。

之所以不接内存库：W2 要验证的就是"落库 + 额度扣减 + 静态图可访问"这些真实行为，
用 SQLite 会掩盖 MySQL 特有差异（JSON 列、Unsigned BIGINT、Numeric 精度）。
"""
import base64
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.database import SessionLocal
from app.main import app
from app.models.diagnosis import DiagnosisRecord
from app.models.feedback import Feedback
from app.models.quota import QuotaUsage
from app.models.user import User

# 1×1 的合法 PNG，用来通过魔数校验；体积远小于 2MB 上限
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
PNG_BASE64 = base64.b64encode(PNG_BYTES).decode()


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db_session():
    """给需要直接造数据的用例一个 Session；用例自己负责提交与清理。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def auth(client):
    """用唯一的 mock code 登录拿到 token，顺带产出该用户的清理钩子。"""
    code = "mock_pytest_" + uuid.uuid4().hex[:12]
    body = client.post("/api/v1/auth/login", json={"code": code, "nickname": "pytest"}).json()
    assert body["code"] == 0, body
    user_id = int(body["data"]["user"]["id"])
    token = body["data"]["token"]

    ctx = {
        "client": client,
        "user_id": user_id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }
    yield ctx

    db = SessionLocal()
    try:
        db.execute(delete(Feedback).where(Feedback.user_id == user_id))
        db.execute(delete(DiagnosisRecord).where(DiagnosisRecord.user_id == user_id))
        db.execute(delete(QuotaUsage).where(QuotaUsage.user_id == user_id))
        db.execute(delete(User).where(User.id == user_id))
        db.commit()
    finally:
        db.close()
