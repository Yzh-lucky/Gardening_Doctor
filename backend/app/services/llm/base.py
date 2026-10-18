"""LLM Provider 抽象层。

设计目的：业务层（recognizer）只依赖 LLMProvider 接口，换模型/换厂商时改配置即可，
不需要动业务代码。T2.3/T2.4 的 Prompt 组装与 JSON 校验都建立在这层之上。
"""
from __future__ import annotations

import base64
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Sequence


@dataclass(slots=True)
class LLMImage:
    """待送进模型的一张图片（内存字节，不落盘）。"""

    content: bytes
    mime_type: str = "image/jpeg"

    def to_data_url(self) -> str:
        b64 = base64.b64encode(self.content).decode("ascii")
        return f"data:{self.mime_type};base64,{b64}"


@dataclass(slots=True)
class LLMResponse:
    text: str
    model_name: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(slots=True)
class LLMMessage:
    role: str
    content: str


class LLMError(Exception):
    """模型调用失败（网络/超时/HTTP 错误/返回体异常）。

    上层（recognizer）据此决定：重试 1 次 → 仍失败则走知识库降级。
    """

    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = True) -> None:
        self.status_code = status_code
        self.retryable = retryable
        super().__init__(message)


class LLMProvider(ABC):
    """所有模型实现的公共接口。"""

    name: str = "base"
    model: str = ""

    @abstractmethod
    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        images: Sequence[LLMImage] | None = None,
        temperature: float = 0.2,
        json_mode: bool = True,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """发起一次多模态对话，返回模型原始文本（JSON 字符串）。"""

    def health(self) -> str:
        """返回 up / degraded，供 /health 使用。"""
        return "up" if self.model else "degraded"

    def describe(self) -> str:
        return f"{self.name}:{self.model or 'n/a'}"
