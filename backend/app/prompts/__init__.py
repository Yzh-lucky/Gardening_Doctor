"""Prompt 模板加载：模板按版本号存文件，落库时把版本号写进 prompt_version，便于回滚与 A/B。

改 Prompt 的铁律：**不要原地改老版本**，新建 prompt_v2.md 并更新 CURRENT_VERSION。
这样历史记录里的 prompt_version 才能对应到当时的真实 Prompt。
"""
from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent

# 当前生效版本；写入 diagnosis_records.prompt_version
CURRENT_VERSION = "v1"


@lru_cache(maxsize=8)
def load_prompt(version: str = CURRENT_VERSION) -> str:
    """读取 prompt_vN.md 全文作为 system prompt；读不到直接报错，不带默认值兜底（避免静默用错版本）。"""
    path = PROMPT_DIR / f"prompt_{version}.md"
    return path.read_text(encoding="utf-8")
