"""T3.6 验收：降级兜底的知识库多关键词评分检索。

直接测 app.services.degrade.degrade_result（不经过 HTTP 层），
验证 name / aliases / symptoms 三类命中与"匹配不到就通用兜底"的保守取向。

运行：在 backend/ 目录执行 `python -m pytest tests -q`
"""
import pytest
from sqlalchemy import delete

from app.models.disease import Disease
from app.services.degrade import degrade_result

# 测试专用病名，避免与真实知识库数据撞唯一键
_NAMES = ["月季白粉病-测试", "月季白粉病-测试-严重型", "茄科测试病"]


def _add(db, **kwargs):
    name = kwargs["name"]
    db.execute(delete(Disease).where(Disease.name == name))
    db.add(Disease(**kwargs))
    db.commit()


@pytest.fixture()
def clean_diseases(db_session):
    """保证测试病名在库里干净，用完删掉。"""
    def _purge():
        db_session.execute(delete(Disease).where(Disease.name.in_(_NAMES)))
        db_session.commit()

    _purge()
    yield
    _purge()


def test_match_by_name_keyword(clean_diseases, db_session):
    """提示按空格切成多个关键词，任一命中病名即可匹配。"""
    _add(
        db_session,
        name="月季白粉病-测试",
        category="真菌性病害",
        plan_l1={"title": "家庭处置", "items": ["摘除病叶"]},
    )
    result = degrade_result(db_session, "月季 白粉病")
    assert result.disease_name == "月季白粉病-测试"
    assert result.confidence == pytest.approx(0.6)


def test_whole_name_in_hint_preferred(clean_diseases, db_session):
    """提示里出现完整病名时，更具体的（名字更长的）那条胜出，而不是被短名前缀截胡。"""
    _add(db_session, name="月季白粉病-测试", category="真菌性病害")
    _add(db_session, name="月季白粉病-测试-严重型", category="真菌性病害")
    result = degrade_result(db_session, "月季白粉病-测试-严重型")
    assert result.disease_name == "月季白粉病-测试-严重型"


def test_match_by_alias(clean_diseases, db_session):
    """别名命中（用户说的俗名）也要能检索到。

    用测试专用别名：真实知识库里"月季白粉病"也带"白粉菌"别名，
    复用同一个词会让两条打平、结果受库里数据影响，这里换成库里不会出现的写法。
    """
    _add(
        db_session,
        name="茄科测试病",
        aliases="测试粉霉别称,粉霉",
        category="真菌性病害",
        plan_l1={"title": "家庭处置", "items": ["通风降湿"]},
    )
    result = degrade_result(db_session, "测试粉霉别称")
    assert result.disease_name == "茄科测试病"
    assert "测试粉霉别称" in result.aliases


def test_symptom_hit_combines_with_name(clean_diseases, db_session):
    """症状字段参与打分：和病名关键词叠加后仍能定位到同一条。

    病名换成库里没有的"茄科测试病"：真实数据的"月季黑斑病"别名里带"月季"，
    用"月季"作关键词会被它抢先命中，测的就不是症状叠加这条规则了。
    """
    _add(
        db_session,
        name="茄科测试病",
        category="真菌性病害",
        symptoms="叶片出现同心轮纹斑，边缘褐色。",
    )
    result = degrade_result(db_session, "茄科 同心轮纹斑")
    assert result.disease_name == "茄科测试病"


def test_symptom_only_is_conservative(clean_diseases, db_session):
    """只有症状命中（没有病名/别名）时不给结论，走通用兜底——宁可少说也不编。"""
    _add(db_session, name="茄科测试病", symptoms="叶片出现同心轮纹斑，边缘褐色。")
    result = degrade_result(db_session, "同心轮纹斑")
    assert result.disease_name == "无法识别"
    assert result.need_more_info is True


def test_no_match_returns_generic(clean_diseases, db_session):
    """完全不相关的提示直接通用兜底，绝不瞎猜病名。"""
    result = degrade_result(db_session, "今天天气不错")
    assert result.disease_name == "无法识别"
    assert result.plan_l1_safe.items, "兜底也必须给 L1 方案"
    assert result.followup_questions


def test_empty_hint_returns_generic(clean_diseases, db_session):
    assert degrade_result(db_session, None).disease_name == "无法识别"
    assert degrade_result(db_session, "   ").disease_name == "无法识别"
