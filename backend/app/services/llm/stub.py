"""Stub Provider：本地无 API Key 时的假模型。

返回一份符合 DiseaseResult 契约的固定 JSON，好处是：
- W1/W2 期间没有 Key 也能把"上传 → 识别 → 结果页渲染"整条链路跑通
- 单测/联调不依赖外部服务，不会消耗额度也不会超时
"""
from __future__ import annotations

import json
import time
from typing import Sequence

from .base import LLMImage, LLMProvider, LLMResponse

# 一份"看起来真实"的识别结果，字段与 API接口文档 2.3 完全一致
_STUB_RESULT: dict = {
    "disease_name": "番茄早疫病",
    "aliases": ["轮纹病"],
    "category": "真菌性病害",
    "confidence": 0.86,
    "severity": "moderate",
    "symptom_summary": "叶片出现深褐色同心轮纹斑，边缘黄化，下部老叶先发病。",
    "confirm_points": [
        "病斑有同心轮纹（靶心状）",
        "从下部老叶向上发展",
        "高湿环境下病斑边缘有浅色霉层",
    ],
    "confused_with": [
        {"name": "番茄晚疫病", "key_difference": "晚疫病斑边缘不清晰、水渍状，扩展极快"}
    ],
    "plan_l1_safe": {
        "title": "家庭零风险处置（有儿童/宠物首选）",
        "items": [
            "立即摘除病叶病果，装袋密封丢弃，不要丢进堆肥",
            "增加通风，避免叶面长时间挂水",
            "基部浇水，不要从叶面淋水",
        ],
    },
    "plan_l2_low_toxicity": {
        "title": "低毒合规处置（按说明书使用，注意安全间隔期）",
        "items": [
            {"name": "枯草芽孢杆菌", "usage": "1000 倍液叶面喷雾，7 天一次，连用 2–3 次"},
            {"name": "代森锰锌", "usage": "按登记剂量使用，采收前 15 天停止"},
        ],
        "note": "家庭阳台建议优先 L1，L2 仅在病情发展较快时使用",
    },
    "plan_l3_professional": {
        "title": "专业干预（家庭场景不建议自行操作）",
        "items": ["病情大面积爆发或反复发作时，联系当地植保站/专业园艺服务"],
        "risk_note": "涉及中高毒药剂与专业施药设备，家庭环境存在安全风险",
    },
    "safety_notes": [
        "所有药剂置于儿童与宠物接触不到处",
        "施药后洗手，当天避免宠物舔舐叶片",
        "食用部位采收前务必遵守安全间隔期",
    ],
    "need_more_info": False,
    "followup_questions": [],
}


class StubProvider(LLMProvider):
    name = "stub"
    model = "stub-vision-v0"

    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        images: Sequence[LLMImage] | None = None,
        temperature: float = 0.2,
        json_mode: bool = True,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        started = time.perf_counter()
        # 模拟一点"思考耗时"，让前端的 loading 态有东西可看
        await _fake_delay()
        latency_ms = int((time.perf_counter() - started) * 1000)
        return LLMResponse(
            text=json.dumps(_STUB_RESULT, ensure_ascii=False),
            model_name=self.model,
            prompt_tokens=1200 + 300 * len(images or []),
            completion_tokens=520,
            latency_ms=latency_ms,
        )


async def _fake_delay() -> None:
    import asyncio

    await asyncio.sleep(0.3)
