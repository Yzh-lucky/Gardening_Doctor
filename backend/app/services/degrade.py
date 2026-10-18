"""降级兜底（准备文档 3.4.3 / T3.6）：大模型超时或输出不可解析时，不让用户看到失败，
而是用知识库关键词检索给出一个"保守可用"的结果，status=degraded。

设计取向：宁可少说，也不能编。知识库匹配不到就返回通用的"无法识别 + 补拍建议"，
而不是瞎猜一个病名。

检索思路（T3.6 升级）：把 plant_hint 切成多个关键词，对每条知识在
name / aliases / symptoms / category 四个字段上分别打分，取最高分那条；
分数低于阈值就当作"没有可信匹配"，走通用兜底。中文没有天然分词，
字段匹配采用双向包含（关键词在字段里、或整个字段是关键词的一部分），
这样"月季 白粉"这类空格分隔的输入和"我的月季得了白粉病"这类整句都能命中。
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.disease import Disease
from app.schemas.diagnosis import (
    ConfusedItem,
    DiseaseResult,
    PlanL1,
    PlanL2,
    PlanL3,
)

# 兜底结果的通用建议：不依赖具体病名，任何情况都能用
_FOLLOWUP = [
    "建议补拍病斑特写（正对光源，别用闪光灯）",
    "建议补拍叶片背面，很多虫害与霉层在背面",
    "建议补拍整株与盆土，便于判断是局部还是全株问题",
]

_SAFETY = [
    "隔离可疑病株，避免接触儿童与宠物",
    "处理病叶后洗手，工具用后清洁",
]

# 匹配不到知识库时的通用兜底（"无法识别"，明确让用户补拍）
_GENERIC_L1_ITEMS = [
    "先把可疑叶片单独摘除装袋丢弃，不要丢进堆肥",
    "增加通风、避免叶面长时间挂水",
    "拍照时正对病斑，补拍背面与整株，再重新识别一次",
]

# 关键词切分：中英文标点、空白、连字符都算分隔符
_SPLIT_RE = re.compile(r"[\s,，;；、/|·:：\-—]+")

# 字段权重：病名最能代表一条知识，别名次之，症状/分类只作辅助
_W_NAME = 10
_W_ALIAS = 6
_W_SYMPTOM = 3
_W_CATEGORY = 2
# 整段提示直接命中病名/别名（用户张口就是病名）额外加分，确保压过零散的字段命中
_W_WHOLE_NAME = 30
_W_WHOLE_ALIAS = 12
# 低于该分数视作"没有可信匹配"，宁可不猜（单字命中等泛匹配至少需要两个字段叠加）
_MIN_SCORE = 6


def _keywords(hint: str) -> list[str]:
    """把提示切成关键词；去重，并丢掉单字（单字命中太泛，容易误判）。"""
    seen: list[str] = []
    for piece in _SPLIT_RE.split(hint):
        piece = piece.strip()
        if len(piece) >= 2 and piece not in seen:
            seen.append(piece)
    return seen


def _hit(field: str, keyword: str, weight: int) -> int:
    """字段与关键词双向包含都算命中，覆盖中文整句输入的情况。"""
    if not field or not keyword:
        return 0
    if keyword in field or field in keyword:
        return weight
    return 0


def _score(disease: Disease, keywords: list[str], hint: str) -> int:
    name = (disease.name or "").strip()
    aliases = disease.aliases or ""
    symptoms = disease.symptoms or ""
    category = disease.category or ""

    score = 0
    # 整段提示命中最直接：用户直接把病名说出来了。加上病名长度作细分，
    # 保证"番茄早疫病-降级测试"这种更长的名字压过它自己作为子串的短名
    if name and (hint == name or name in hint):
        score += _W_NAME + _W_WHOLE_NAME + len(name)
    if hint and hint in aliases:
        score += _W_ALIAS + _W_WHOLE_ALIAS

    for keyword in keywords:
        score += _hit(name, keyword, _W_NAME)
        score += _hit(aliases, keyword, _W_ALIAS)
        score += _hit(symptoms, keyword, _W_SYMPTOM)
        score += _hit(category, keyword, _W_CATEGORY)
    return score


def _generic_result() -> DiseaseResult:
    return DiseaseResult(
        disease_name="无法识别",
        aliases=[],
        category="生理性病害",
        confidence=0.3,
        severity="mild",
        symptom_summary="识别服务当前不稳定，暂时无法给出确定判断，请按提示补拍后重试。",
        confirm_points=[],
        confused_with=[],
        plan_l1_safe=PlanL1(title="家庭零风险处置（有儿童/宠物首选）", items=_GENERIC_L1_ITEMS),
        plan_l2_low_toxicity=PlanL2(
            title="低毒合规处置（按说明书使用，注意安全间隔期）",
            items=[],
            note="未确认病因前不建议用药，先补拍重试",
        ),
        plan_l3_professional=PlanL3(
            title="专业干预（家庭场景不建议自行操作）",
            items=["若症状持续加重，可携样本咨询当地植保站或专业园艺服务"],
            risk_note="未明确病因前使用中高毒药剂存在安全与药害风险",
        ),
        safety_notes=_SAFETY,
        need_more_info=True,
        followup_questions=_FOLLOWUP,
    )


def _from_knowledge(disease: Disease) -> DiseaseResult:
    """用知识库条目拼一个 DiseaseResult；结构缺失的地方补保守默认值，保证 schema 一定通过。"""
    plan_l1 = disease.plan_l1 if isinstance(disease.plan_l1, dict) else {}
    plan_l2 = disease.plan_l2 if isinstance(disease.plan_l2, dict) else {}
    plan_l3 = disease.plan_l3 if isinstance(disease.plan_l3, dict) else {}

    safety = [s.strip() for s in (disease.safety_notes or "").split("\n") if s.strip()] or _SAFETY
    confused = [
        ConfusedItem(name=name.strip(), key_difference="参考知识库同类条目，注意区分发病部位与病斑形态")
        for name in (disease.confused_with or "").split(",")
        if name.strip()
    ]
    aliases = [a.strip() for a in (disease.aliases or "").split(",") if a.strip()]

    return DiseaseResult(
        disease_name=disease.name,
        aliases=aliases,
        category=disease.category or "生理性病害",
        # 降级结果置信度不高于 0.6：它是"知识库匹配"而非"模型看图判断"，要让用户知道不确定
        confidence=0.6,
        severity="moderate",
        symptom_summary=disease.symptoms or "识别服务暂不可用，以下方案来自知识库匹配，仅供参考。",
        confirm_points=[],
        confused_with=confused,
        plan_l1_safe=PlanL1(**{**{"title": "家庭零风险处置（有儿童/宠物首选）", "items": _GENERIC_L1_ITEMS}, **plan_l1}),
        plan_l2_low_toxicity=PlanL2(**{**{"title": "低毒合规处置（按说明书使用，注意安全间隔期）", "items": []}, **plan_l2}),
        plan_l3_professional=PlanL3(**{**{"title": "专业干预（家庭场景不建议自行操作）", "items": []}, **plan_l3}),
        safety_notes=safety,
        need_more_info=True,
        followup_questions=_FOLLOWUP,
    )


def degrade_result(db: Session, plant_hint: str | None = None) -> DiseaseResult:
    """多关键词评分检索知识库，取最高分条目；没有可信匹配则走通用兜底。

    知识库在 MVP 阶段很小（几十条），这里直接全表打分，清晰且无需额外索引；
    条目上千后应改为倒排索引/向量检索，届时再换实现。
    """
    hint = (plant_hint or "").strip()
    if hint:
        keywords = _keywords(hint)
        best: Disease | None = None
        best_key = (0, 0, 0)
        for disease in db.scalars(select(Disease).order_by(Disease.version.desc())):
            score = _score(disease, keywords, hint)
            if score < _MIN_SCORE:
                continue
            # 同分时优先"名字更长（更具体）"、再优先版本更高；外层已按 version 降序，严格大于可保住先遇到的
            key = (score, len(disease.name or ""), int(disease.version or 1))
            if key > best_key:
                best, best_key = disease, key
        if best is not None:
            return _from_knowledge(best)
    return _generic_result()
