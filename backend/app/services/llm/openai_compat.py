"""OpenAI 兼容协议实现：通义千问 VL、豆包 Vision、智谱等国内模型都提供兼容端点，
差异只在 base_url 与 model，因此一套实现覆盖多家，切换只改 .env。
"""
from __future__ import annotations

import time
from typing import Any, Sequence

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from .base import LLMError, LLMImage, LLMProvider, LLMResponse

logger = get_logger("app.llm")

# 厂商默认端点（.env 里的 LLM_BASE_URL 优先级更高）
PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-vl-max",
    },
    "doubao": {
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "model": "",  # 火山方舟需要填推理接入点 ID（ep-xxxx）
    },
}


class OpenAICompatProvider(LLMProvider):
    def __init__(
        self,
        provider: str,
        api_key: str,
        model: str = "",
        base_url: str = "",
        timeout: float = 15.0,
    ) -> None:
        self.name = provider
        defaults = PROVIDER_DEFAULTS.get(provider, {})
        self.api_key = api_key
        self.model = model or defaults.get("model", "")
        self.base_url = (base_url or defaults.get("base_url", "")).rstrip("/")
        self.timeout = timeout

    def health(self) -> str:
        return "up" if (self.api_key and self.base_url and self.model) else "degraded"

    def _build_messages(self, system_prompt: str, user_prompt: str, images: Sequence[LLMImage] | None) -> list[dict]:
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if images:
            # 多模态：文本 + 若干 image_url（data url 形式，免去图片公网可达的要求）
            content: list[dict[str, Any]] = [{"type": "text", "text": user_prompt}]
            content.extend(
                {"type": "image_url", "image_url": {"url": img.to_data_url()}} for img in images
            )
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": user_prompt})
        return messages

    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        images: Sequence[LLMImage] | None = None,
        temperature: float = 0.2,
        json_mode: bool = True,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        if not self.health() == "up":
            raise LLMError(f"{self.name} 未正确配置（api_key/base_url/model）", retryable=False)

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._build_messages(system_prompt, user_prompt, images),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if json_mode:
            # 强约束 JSON 输出，少一层解析失败的风险
            payload["response_format"] = {"type": "json_object"}

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise LLMError(f"{self.name} 调用超时（>{self.timeout}s）", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"{self.name} 网络异常：{exc}", retryable=True) from exc

        latency_ms = int((time.perf_counter() - started) * 1000)

        if resp.status_code >= 400:
            body = resp.text[:500]
            # 401/403 属于配置问题，重试没意义
            retryable = resp.status_code not in (401, 403)
            raise LLMError(
                f"{self.name} 返回 {resp.status_code}：{body}", status_code=resp.status_code, retryable=retryable
            )

        try:
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"{self.name} 返回体结构异常：{resp.text[:300]}", retryable=True) from exc

        usage = data.get("usage") or {}
        result = LLMResponse(
            text=text or "",
            model_name=data.get("model") or self.model,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            latency_ms=latency_ms,
        )
        logger.info(
            "llm_call",
            extra={
                "provider": self.name,
                "model": result.model_name,
                "latency_ms": latency_ms,
                "total_tokens": result.total_tokens,
            },
        )
        return result


def build_provider_from_settings() -> OpenAICompatProvider:
    return OpenAICompatProvider(
        provider=settings.LLM_PROVIDER,
        api_key=settings.LLM_API_KEY,
        model=settings.LLM_MODEL,
        base_url=settings.LLM_BASE_URL,
        timeout=float(settings.LLM_TIMEOUT),
    )
