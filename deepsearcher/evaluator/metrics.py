"""
Agent 效果评估 — 核心指标采集器

设计原则：
  - 无侵入：作为观察者挂载到 agent 循环，不影响现有决策逻辑
  - 每次任务一个 MetricsCollector 实例，任务结束 → 输出 TaskMetrics
  - 所有时间戳用 time.monotonic() 避免墙钟偏移
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)

ActionType = Literal["search", "visit", "reflect", "rewrite", "answer", "beast_mode"]


@dataclass
class ActionRecord:
    """单次动作执行记录"""
    action_type: ActionType
    step: int
    success: bool
    elapsed_ms: float
    llm_calls: int = 0                # 本次动作中的 LLM 调用次数
    llm_tokens_used: int = 0          # 本次动作消耗的 token（估算）
    extra: dict = field(default_factory=dict)  # 动作类型特定的附加数据

    # extra 可能的 key:
    #   search: { "queries": int, "results_found": int, "urls_queued": int }
    #   visit:  { "urls_read": int, "knowledge_extracted": int, "read_failures": int }
    #   answer: { "eval_passed": bool, "eval_attempts": int, "char_count": int }
    #   reflect: { "gaps_found": int }
    #   rewrite: { "queries_generated": int }
    #   beast_mode: { "trigger_reason": str }


@dataclass
class TaskMetrics:
    """单次深度研究任务的完整指标"""
    task_id: str = ""
    question: str = ""

    # ── 1. 任务完成率 ──
    completed: bool = False           # 是否产出最终答案
    answer_generated: bool = False    # answer 动作是否成功执行
    beast_mode_triggered: bool = False  # 是否触发 Beast Mode 兜底
    eval_passed: bool = False         # 质量门禁是否通过
    eval_attempts: int = 0            # 评估尝试次数

    # ── 2. 工具调用准确率 ──
    action_records: list[ActionRecord] = field(default_factory=list)
    total_actions: int = 0
    successful_actions: int = 0

    # ── 3. 路径长度 ──
    steps_taken: int = 0              # 实际步骤数
    max_steps_allowed: int = 20       # 配置允许的最大步骤
    actions_by_type: dict[str, int] = field(default_factory=dict)

    # ── 4. 平均耗时 ──
    total_elapsed_ms: float = 0       # 总耗时（墙钟）
    per_step_avg_ms: float = 0        # 每步平均耗时
    llm_total_calls: int = 0          # LLM 总调用次数
    llm_total_tokens: int = 0         # LLM 总 token 消耗（估算）
    action_timing: dict[str, list[float]] = field(default_factory=dict)  # 按时序记录

    # ── 5. 异常率 ──
    failed_actions: int = 0
    empty_searches: int = 0           # 搜索返回 0 结果的次数
    empty_visits: int = 0             # 阅读未产生知识的次数
    evaluation_failures: int = 0      # 评估不通过的次数
    hard_intercepts: int = 0          # 硬拦截次数（待读URL>0时禁止answer）
    llm_errors: int = 0               # LLM 调用失败次数

    # ── 元信息 ──
    created_at: float = 0
    difficulty_label: str = ""        # 问题难度标签（简单/中等/复杂）


class MetricsCollector:
    """指标采集器 — 每个任务创建一个实例"""

    def __init__(self, task_id: str, question: str, max_turns: int, token_budget: int):
        self.task_id = task_id
        self.question = question
        self.max_turns = max_turns
        self.token_budget = token_budget

        # 内部状态
        self._start_time = time.monotonic()
        self._step_start_times: dict[int, float] = {}  # step → monotonic
        self._records: list[ActionRecord] = []
        self._action_timing: dict[str, list[float]] = {
            "search": [], "visit": [], "reflect": [],
            "rewrite": [], "answer": [], "beast_mode": [],
        }

        # 异常计数
        self._empty_searches = 0
        self._empty_visits = 0
        self._eval_failures = 0
        self._hard_intercepts = 0
        self._llm_errors = 0

        # answer 追踪
        self._answer_generated = False
        self._eval_passed = False
        self._eval_attempts = 0
        self._beast_mode = False
        self._beast_reason = ""

        logger.info(f"[MetricsCollector] 初始化 task_id={task_id} question={question[:40]}")

    # ── 公共钩子方法 ──────────────────────────────────────────

    def mark_step_start(self, step: int):
        """标记步骤开始"""
        self._step_start_times[step] = time.monotonic()

    def mark_step_end(self, step: int):
        """标记步骤结束（可选，用于细粒度计时）"""
        pass  # action 级别已记录

    def record_action(self, record: ActionRecord):
        """记录一次动作执行"""
        self._records.append(record)
        # 记录耗时分布
        if record.action_type in self._action_timing:
            self._action_timing[record.action_type].append(record.elapsed_ms)

        if not record.success:
            if record.action_type == "search":
                if record.extra.get("results_found", 0) == 0:
                    self._empty_searches += 1
            elif record.action_type == "visit":
                if record.extra.get("knowledge_extracted", 0) == 0:
                    self._empty_visits += 1

        if record.action_type == "answer":
            self._answer_generated = True
            self._eval_attempts = record.extra.get("eval_attempts", 0)
            self._eval_passed = record.extra.get("eval_passed", False)
            if record.extra.get("eval_failed", False):
                self._eval_failures += 1

        if record.extra.get("llm_error", False):
            self._llm_errors += 1

    def mark_hard_intercept(self):
        """标记硬拦截（待读 URL > 0 时禁止 answer）"""
        self._hard_intercepts += 1

    def mark_beast_mode(self, reason: str = ""):
        """标记 Beast Mode 触发"""
        self._beast_mode = True
        self._beast_reason = reason

    def mark_eval_failure(self):
        """标记一次评估不通过"""
        self._eval_failures += 1

    # ── 输出指标 ──────────────────────────────────────────────

    def finalize(self) -> TaskMetrics:
        """结束采集，输出结构化指标"""
        total_elapsed_ms = (time.monotonic() - self._start_time) * 1000

        successful = sum(1 for r in self._records if r.success)
        failed = sum(1 for r in self._records if not r.success)

        actions_by_type: dict[str, int] = {}
        for r in self._records:
            actions_by_type[r.action_type] = actions_by_type.get(r.action_type, 0) + 1

        total_llm_calls = sum(r.llm_calls for r in self._records)
        total_llm_tokens = sum(r.llm_tokens_used for r in self._records)
        steps = len(self._records)

        per_step_avg = total_elapsed_ms / steps if steps > 0 else 0

        # 难度标签：基于步骤数 + Beast Mode + 评估失败
        if self._beast_mode or self._eval_failures >= 2:
            difficulty = "复杂"
        elif steps > 5:
            difficulty = "中等"
        else:
            difficulty = "简单"

        return TaskMetrics(
            task_id=self.task_id,
            question=self.question,
            completed=self._answer_generated,
            answer_generated=self._answer_generated,
            beast_mode_triggered=self._beast_mode,
            eval_passed=self._eval_passed,
            eval_attempts=self._eval_attempts,
            action_records=self._records,
            total_actions=len(self._records),
            successful_actions=successful,
            steps_taken=steps,
            max_steps_allowed=self.max_turns,
            actions_by_type=actions_by_type,
            total_elapsed_ms=total_elapsed_ms,
            per_step_avg_ms=per_step_avg,
            llm_total_calls=total_llm_calls,
            llm_total_tokens=total_llm_tokens,
            action_timing=self._action_timing,
            failed_actions=failed,
            empty_searches=self._empty_searches,
            empty_visits=self._empty_visits,
            evaluation_failures=self._eval_failures,
            hard_intercepts=self._hard_intercepts,
            llm_errors=self._llm_errors,
            created_at=time.time(),
            difficulty_label=difficulty,
        )


# ── 聚合分析类型 ───────────────────────────────────────────────

@dataclass
class ToolAccuracy:
    """工具调用准确率聚合"""
    action_type: str
    total: int
    successful: int
    success_rate: float  # 0-1
    avg_elapsed_ms: float
    total_elapsed_ms: float


@dataclass
class TaskCompletion:
    """任务完成率聚合"""
    total_tasks: int
    completed: int
    completion_rate: float
    beast_mode_rate: float
    eval_pass_rate: float
    avg_answer_length: int = 0


@dataclass
class PathAnalysis:
    """路径长度分析"""
    min_steps: int
    max_steps: int
    mean_steps: float
    median_steps: float
    action_distribution: dict[str, float] = field(default_factory=dict)
    difficulty_distribution: dict[str, int] = field(default_factory=dict)


@dataclass
class TimingProfile:
    """耗时画像"""
    avg_total_ms: float
    avg_per_step_ms: float
    p50_total_ms: float
    p95_total_ms: float
    avg_llm_calls: float
    avg_llm_tokens: float
    slowest_action_type: str = ""
    action_avg_timing: dict[str, float] = field(default_factory=dict)


@dataclass
class AnomalyReport:
    """异常率报告"""
    empty_search_rate: float
    empty_visit_rate: float
    eval_failure_rate: float
    hard_intercept_rate: float
    llm_error_rate: float
    beast_mode_rate: float
    action_failure_rate: float
    top_failure_types: list[str] = field(default_factory=list)


@dataclass
class MetricsSummary:
    """完整聚合指标摘要"""
    task_completion: TaskCompletion
    tool_accuracy: list[ToolAccuracy]
    path_analysis: PathAnalysis
    timing_profile: TimingProfile
    anomaly_report: AnomalyReport
    total_tasks: int = 0
    generated_at: float = 0
