"""科普接口验收（API接口文档 3.8）：免鉴权列表与详情。

覆盖：精简字段列表、关键字/类别筛选、分页、参数校验、完整详情、记录不存在。
运行：在 backend/ 目录执行 `python -m pytest tests -q`
"""
import pytest
from sqlalchemy import delete

from app.models.disease import Disease
from app.schemas.disease import BRIEF_SYMPTOM_LEN

_PREFIX = "pytest科普-"


@pytest.fixture()
def seed_diseases(db_session):
    """造一批科普条目，用完按前缀清干净，避免污染真实知识库。"""
    def _purge():
        db_session.execute(delete(Disease).where(Disease.name.like(f"{_PREFIX}%")))
        db_session.commit()

    _purge()
    rows = [
        Disease(
            name=f"{_PREFIX}月季白粉病",
            aliases="白粉菌,粉霉",
            category="真菌性病害",
            symptoms="x" * 100,  # 超长，用来验证列表摘要截断
            causes="通风差、湿度高",
            plan_l1={"title": "家庭零风险处置", "items": ["摘除病叶并隔离"]},
            plan_l2={"title": "低毒合规处置", "items": [{"name": "代森锰锌", "usage": "按说明书稀释，安全间隔期 7 天"}]},
            plan_l3={"title": "专业干预", "items": ["症状持续加重时联系植保站"]},
            safety_notes="药剂放好\n施药后洗手",
            confused_with="月季霜霉病",
            version=2,
        ),
        Disease(name=f"{_PREFIX}番茄早疫病", aliases="轮纹病", category="真菌性病害", symptoms="叶片同心轮纹斑"),
        Disease(name=f"{_PREFIX}蚜虫", aliases="腻虫", category="虫害", symptoms="嫩梢聚集绿色小虫"),
    ]
    for row in rows:
        db_session.add(row)
    db_session.commit()
    yield rows
    _purge()


def test_list_is_public_and_brief(client, seed_diseases):
    # 不带任何鉴权头也能访问
    resp = client.get("/api/v1/diseases", params={"keyword": _PREFIX})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0, body
    assert body["data"]["total"] == 3
    assert body["data"]["page"] == 1
    assert body["data"]["page_size"] == 20
    assert body["data"]["has_more"] is False

    brief = next(x for x in body["data"]["list"] if x["name"] == f"{_PREFIX}月季白粉病")
    # 精简字段：只有 id/name/category/symptoms；不含 plan/safety/version
    assert set(brief.keys()) == {"id", "name", "category", "symptoms"}
    assert brief["category"] == "真菌性病害"
    # 摘要被截断
    assert len(brief["symptoms"]) == BRIEF_SYMPTOM_LEN + 1
    assert brief["symptoms"].endswith("…")


def test_list_keyword_matches_alias(client, seed_diseases):
    # 别名（俗名）也要能搜到。知识库里允许存在同名的真实条目（如种子数据的"蚜虫"），
    # 所以只断言"目标条目被命中"，不把结果总数锁死。
    body = client.get("/api/v1/diseases", params={"keyword": "腻虫"}).json()
    assert body["code"] == 0
    assert f"{_PREFIX}蚜虫" in [x["name"] for x in body["data"]["list"]]


def test_list_category_filter(client, seed_diseases):
    body = client.get("/api/v1/diseases", params={"keyword": _PREFIX, "category": "虫害"}).json()
    assert body["code"] == 0
    assert body["data"]["total"] == 1
    assert body["data"]["list"][0]["name"] == f"{_PREFIX}蚜虫"


def test_list_pagination(client, seed_diseases):
    first = client.get("/api/v1/diseases", params={"keyword": _PREFIX, "page": 1, "page_size": 2}).json()
    assert len(first["data"]["list"]) == 2
    assert first["data"]["has_more"] is True
    second = client.get("/api/v1/diseases", params={"keyword": _PREFIX, "page": 2, "page_size": 2}).json()
    assert len(second["data"]["list"]) == 1
    assert second["data"]["has_more"] is False
    # 两页不重叠
    ids1 = {x["id"] for x in first["data"]["list"]}
    ids2 = {x["id"] for x in second["data"]["list"]}
    assert ids1.isdisjoint(ids2)


def test_list_invalid_page_param(client):
    # 与全局参数校验口径一致：非法入参 → 2001
    assert client.get("/api/v1/diseases", params={"page": 0}).json()["code"] == 2001
    assert client.get("/api/v1/diseases", params={"page_size": 999}).json()["code"] == 2001


def test_detail_returns_full_disease(client, seed_diseases):
    target = seed_diseases[0]
    body = client.get(f"/api/v1/diseases/{target.id}").json()
    assert body["code"] == 0, body
    data = body["data"]
    assert data["id"] == str(target.id)
    assert data["name"] == f"{_PREFIX}月季白粉病"
    assert data["aliases"] == "白粉菌,粉霉"
    assert data["symptoms"] == "x" * 100  # 详情不截断
    assert data["plan_l1"]["items"] == ["摘除病叶并隔离"]
    assert data["plan_l2"]["items"][0]["name"] == "代森锰锌"
    assert data["safety_notes"] == "药剂放好\n施药后洗手"
    assert data["confused_with"] == "月季霜霉病"
    assert data["version"] == 2


def test_detail_not_found(client):
    body = client.get("/api/v1/diseases/999999999").json()
    assert body["code"] == 4001


def test_detail_invalid_id(client):
    # 非整数路径参数 → 参数校验失败 2001
    assert client.get("/api/v1/diseases/abc").json()["code"] == 2001
