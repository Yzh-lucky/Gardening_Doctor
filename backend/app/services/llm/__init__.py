"""Provider 工厂：按 .env 的 LLM_PROVIDER 选择实现，业务层只认 LLMProvider 接口。

支持值：
- `stub`   假模型，无需 Key，本地开发默认
- `qwen`   通义千问 VL（阿里云百炼，OpenAI 兼容端点）
- `doubao` 豆包 Vision（火山方舟，需填推理接入点 ID 作为 model）
"""
from functools import lru_cache

from app.core.config import settings
from app.core.logging import get_logger
from .base import LLMError, LLMImage, LLMProvider, LLMResponse
from .openai_compat import OpenAICompatProvider, build_provider_from_settings
from .stub import StubProvider

logger = get_logger("app.llm")


@lru_cache(maxsize=1)
def get_llm_provider() -> LLMProvider:
    provider = (settings.LLM_PROVIDER or "stub").strip().lower()
    if provider == "stub":
        return StubProvider()
    if provider in ("qwen", "doubao") or settings.LLM_BASE_URL:
        return build_provider_from_settings()
    logger.warning("llm_provider_unknown_fallback_stub", extra={"provider": provider})
    return StubProvider()


def reset_llm_provider() -> None:
    """清缓存，便于改了配置后热切换（测试/脚本里用）。"""
    get_llm_provider.cache_clear()


__all__ = [
    "LLMError",
    "LLMImage",
    "LLMProvider",
    "LLMResponse",
    "OpenAICompatProvider",
    "StubProvider",
    "get_llm_provider",
    "reset_llm_provider",
]
