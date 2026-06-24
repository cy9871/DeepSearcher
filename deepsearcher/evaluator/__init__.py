"""
DeepSearcher Agent 效果评估体系

维度：
  1. 任务完成率 — 是否产出答案 + 质量门禁通过率
  2. 工具调用准确率 — 各动作的成功/有效率
  3. 路径长度 — 步骤数分布 + 动作类型分布
  4. 平均耗时 — 总耗时 + 每步耗时 + LLM 调用次数
  5. 异常率 — 失败动作 / Beast Mode / 评估不通过 / 空搜索 / 空阅读

所有指标自动持久化到 results/metrics/ 目录，
与现有 results/index.json 互补，不冲突。
"""

from .metrics import (
    MetricsCollector,
    ActionRecord,
    TaskMetrics,
    ActionType,
    ToolAccuracy,
    TaskCompletion,
    PathAnalysis,
    TimingProfile,
    AnomalyReport,
    MetricsSummary,
)
from .storage import MetricsStorage
from .reporter import MetricsReporter

__all__ = [
    "MetricsCollector",
    "ActionRecord",
    "TaskMetrics",
    "ActionType",
    "ToolAccuracy",
    "TaskCompletion",
    "PathAnalysis",
    "TimingProfile",
    "AnomalyReport",
    "MetricsSummary",
    "MetricsStorage",
    "MetricsReporter",
]
