"""共享 LLM 客户端

所有模块从此获取 AsyncOpenAI 实例，避免重复创建。
"""

from __future__ import annotations

from openai import AsyncOpenAI

from .config import LLM_CONFIG

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url=LLM_CONFIG["base_url"],
            api_key=LLM_CONFIG["api_key"],
        )
    return _client
