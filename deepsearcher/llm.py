"""共享 LLM 客户端与统一调用入口

所有模块从此获取 AsyncOpenAI 实例和 chat_completion 调用函数，
避免重复创建，统一 429 降级策略。
"""

from .llm_adapter import get_client, chat_completion

__all__ = ["get_client", "chat_completion"]
