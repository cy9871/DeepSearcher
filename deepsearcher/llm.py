"""共享 LLM 客户端

所有模块从此获取 AsyncOpenAI 实例，避免重复创建。
"""

from .llm_adapter import get_client

__all__ = ["get_client"]
