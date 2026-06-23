"""Token 用量追踪器"""
import logging

logger = logging.getLogger(__name__)

class TokenTracker:
    def __init__(self, budget: int = 100000):
        self.budget = budget
        self.used = 0
        self.usage_log: list[dict] = []

    def track(self, tool: str, prompt_tokens: int, completion_tokens: int) -> None:
        total = prompt_tokens + completion_tokens
        self.used += total
        self.usage_log.append({
            "tool": tool,
            "prompt": prompt_tokens,
            "completion": completion_tokens,
            "total": total,
        })
        logger.debug(f"[TokenTracker] {tool}: +{total} tokens (total: {self.used}/{self.budget})")

    @property
    def remaining(self) -> int:
        return max(0, self.budget - self.used)

    @property
    def budget_exhausted(self) -> bool:
        return self.used >= self.budget

    @property
    def usage_pct(self) -> float:
        return self.used / self.budget * 100 if self.budget else 0
