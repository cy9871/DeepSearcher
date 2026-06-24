"""
指标持久化存储

存储位置：deepsearcher/results/metrics/
  - {task_id}.json          → 单个任务的 TaskMetrics
  - summary.json             → 全量聚合 MetricsSummary
  - index.json               → 指标任务索引

与现有 results/index.json（结果索引）互补，不冲突。
"""

from __future__ import annotations

import json
import logging
import os
import statistics
import time
from pathlib import Path

from .metrics import (
    TaskMetrics,
    ActionRecord,
    ToolAccuracy,
    TaskCompletion,
    PathAnalysis,
    TimingProfile,
    AnomalyReport,
    MetricsSummary,
)

logger = logging.getLogger(__name__)


def _get_metrics_dir(package_dir: str | None = None) -> str:
    """获取 metrics 目录路径"""
    if package_dir:
        return os.path.join(package_dir, "results", "metrics")
    # 默认：从 evaluator 模块位置推导项目根
    evaluator_dir = os.path.dirname(os.path.abspath(__file__))
    deepsearcher_dir = os.path.dirname(evaluator_dir)
    return os.path.join(deepsearcher_dir, "results", "metrics")


class MetricsStorage:
    """指标持久化"""

    def __init__(self, package_dir: str | None = None):
        self._metrics_dir = _get_metrics_dir(package_dir)
        os.makedirs(self._metrics_dir, exist_ok=True)

    # ── 单任务存储 ────────────────────────────────────────────

    def save_task_metrics(self, metrics: TaskMetrics) -> str:
        """保存单任务指标为 JSON"""
        filepath = os.path.join(self._metrics_dir, f"{metrics.task_id}.json")

        # 序列化 ActionRecord（dataclass → dict）
        data = {
            "task_id": metrics.task_id,
            "question": metrics.question,
            "completed": metrics.completed,
            "answer_generated": metrics.answer_generated,
            "beast_mode_triggered": metrics.beast_mode_triggered,
            "eval_passed": metrics.eval_passed,
            "eval_attempts": metrics.eval_attempts,
            "total_actions": metrics.total_actions,
            "successful_actions": metrics.successful_actions,
            "steps_taken": metrics.steps_taken,
            "max_steps_allowed": metrics.max_steps_allowed,
            "actions_by_type": metrics.actions_by_type,
            "total_elapsed_ms": metrics.total_elapsed_ms,
            "per_step_avg_ms": metrics.per_step_avg_ms,
            "llm_total_calls": metrics.llm_total_calls,
            "llm_total_tokens": metrics.llm_total_tokens,
            "action_timing": {k: v for k, v in metrics.action_timing.items()},
            "failed_actions": metrics.failed_actions,
            "empty_searches": metrics.empty_searches,
            "empty_visits": metrics.empty_visits,
            "evaluation_failures": metrics.evaluation_failures,
            "hard_intercepts": metrics.hard_intercepts,
            "llm_errors": metrics.llm_errors,
            "created_at": metrics.created_at,
            "difficulty_label": metrics.difficulty_label,
            "action_records": [
                {
                    "type": r.action_type,
                    "step": r.step,
                    "success": r.success,
                    "elapsed_ms": r.elapsed_ms,
                    "llm_calls": r.llm_calls,
                    "llm_tokens_used": r.llm_tokens_used,
                    "extra": r.extra,
                }
                for r in metrics.action_records
            ],
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"[MetricsStorage] 已保存: {filepath}")
        self._update_index(metrics)
        return filepath

    # ── 任务索引 ──────────────────────────────────────────────

    def _update_index(self, metrics: TaskMetrics):
        """更新 metrics 索引"""
        index_path = os.path.join(self._metrics_dir, "index.json")
        if os.path.exists(index_path):
            with open(index_path, "r", encoding="utf-8") as f:
                index = json.load(f)
        else:
            index = []

        # 去重
        index = [e for e in index if e.get("task_id") != metrics.task_id]
        index.append({
            "task_id": metrics.task_id,
            "question": metrics.question[:60],
            "created_at": metrics.created_at,
            "steps_taken": metrics.steps_taken,
            "completed": metrics.completed,
            "eval_passed": metrics.eval_passed,
            "total_elapsed_ms": metrics.total_elapsed_ms,
            "difficulty_label": metrics.difficulty_label,
            "beast_mode_triggered": metrics.beast_mode_triggered,
        })
        index.sort(key=lambda x: x["created_at"], reverse=True)

        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    # ── 加载 ──────────────────────────────────────────────────

    def load_task_metrics(self, task_id: str) -> TaskMetrics | None:
        """加载单个任务指标"""
        filepath = os.path.join(self._metrics_dir, f"{task_id}.json")
        if not os.path.exists(filepath):
            return None
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        records = [
            ActionRecord(
                action_type=r["type"],
                step=r["step"],
                success=r["success"],
                elapsed_ms=r["elapsed_ms"],
                llm_calls=r.get("llm_calls", 0),
                llm_tokens_used=r.get("llm_tokens_used", 0),
                extra=r.get("extra", {}),
            )
            for r in data.get("action_records", [])
        ]

        return TaskMetrics(
            task_id=data["task_id"],
            question=data["question"],
            completed=data["completed"],
            answer_generated=data.get("answer_generated", data["completed"]),
            beast_mode_triggered=data.get("beast_mode_triggered", False),
            eval_passed=data.get("eval_passed", False),
            eval_attempts=data.get("eval_attempts", 0),
            action_records=records,
            total_actions=data["total_actions"],
            successful_actions=data["successful_actions"],
            steps_taken=data["steps_taken"],
            max_steps_allowed=data.get("max_steps_allowed", 20),
            actions_by_type=data.get("actions_by_type", {}),
            total_elapsed_ms=data["total_elapsed_ms"],
            per_step_avg_ms=data.get("per_step_avg_ms", 0),
            llm_total_calls=data.get("llm_total_calls", 0),
            llm_total_tokens=data.get("llm_total_tokens", 0),
            action_timing=data.get("action_timing", {}),
            failed_actions=data["failed_actions"],
            empty_searches=data.get("empty_searches", 0),
            empty_visits=data.get("empty_visits", 0),
            evaluation_failures=data.get("evaluation_failures", 0),
            hard_intercepts=data.get("hard_intercepts", 0),
            llm_errors=data.get("llm_errors", 0),
            created_at=data["created_at"],
            difficulty_label=data.get("difficulty_label", ""),
        )

    def load_all_metrics(self) -> list[TaskMetrics]:
        """加载所有任务指标"""
        index_path = os.path.join(self._metrics_dir, "index.json")
        if not os.path.exists(index_path):
            return []

        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)

        metrics_list = []
        for entry in index:
            m = self.load_task_metrics(entry["task_id"])
            if m:
                metrics_list.append(m)
        return metrics_list

    def get_metrics_index(self) -> list[dict]:
        """获取指标索引"""
        index_path = os.path.join(self._metrics_dir, "index.json")
        if os.path.exists(index_path):
            with open(index_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def get_all_task_ids(self) -> list[str]:
        """获取所有有指标的任务 ID"""
        index = self.get_metrics_index()
        return [e["task_id"] for e in index]

    def task_count(self) -> int:
        """已记录的任务数"""
        return len(self.get_metrics_index())


# ── 聚合分析 ───────────────────────────────────────────────────

def _percentile(values: list[float], p: float) -> float:
    """计算百分位数"""
    if not values:
        return 0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * p / 100
    f = int(k)
    c = k - f
    if f + 1 < len(sorted_vals):
        return sorted_vals[f] + c * (sorted_vals[f + 1] - sorted_vals[f])
    return sorted_vals[f]


def compute_summary(
    storage_or_metrics: MetricsStorage | list[TaskMetrics],
) -> MetricsSummary:
    """从存储或指标列表计算全量聚合摘要"""
    if isinstance(storage_or_metrics, MetricsStorage):
        all_metrics = storage_or_metrics.load_all_metrics()
    else:
        all_metrics = storage_or_metrics

    if not all_metrics:
        return MetricsSummary(
            task_completion=TaskCompletion(0, 0, 0, 0, 0),
            tool_accuracy=[],
            path_analysis=PathAnalysis(0, 0, 0, 0),
            timing_profile=TimingProfile(0, 0, 0, 0, 0, 0),
            anomaly_report=AnomalyReport(0, 0, 0, 0, 0, 0, 0),
            generated_at=time.time(),
        )

    n = len(all_metrics)

    # ── 1. 任务完成率 ──
    completed = sum(1 for m in all_metrics if m.completed)
    beast_modes = sum(1 for m in all_metrics if m.beast_mode_triggered)
    eval_passed = sum(1 for m in all_metrics if m.eval_passed)
    completion = TaskCompletion(
        total_tasks=n,
        completed=completed,
        completion_rate=completed / n if n else 0,
        beast_mode_rate=beast_modes / n if n else 0,
        eval_pass_rate=eval_passed / n if n else 0,
    )

    # ── 2. 工具调用准确率（按动作类型聚合）──
    tool_stats: dict[str, dict] = {}
    for m in all_metrics:
        for r in m.action_records:
            t = r.action_type
            if t not in tool_stats:
                tool_stats[t] = {"total": 0, "successful": 0, "elapsed_list": []}
            tool_stats[t]["total"] += 1
            if r.success:
                tool_stats[t]["successful"] += 1
            tool_stats[t]["elapsed_list"].append(r.elapsed_ms)

    tool_accuracy = []
    for action_type, stats in sorted(tool_stats.items()):
        total = stats["total"]
        successful = stats["successful"]
        elapsed = stats["elapsed_list"]
        tool_accuracy.append(ToolAccuracy(
            action_type=action_type,
            total=total,
            successful=successful,
            success_rate=successful / total if total else 0,
            avg_elapsed_ms=sum(elapsed) / len(elapsed) if elapsed else 0,
            total_elapsed_ms=sum(elapsed),
        ))

    # ── 3. 路径长度 ──
    steps_list = [m.steps_taken for m in all_metrics]
    steps_median = statistics.median(steps_list) if steps_list else 0

    # 动作分布
    total_actions = sum(len(m.action_records) for m in all_metrics)
    action_dist: dict[str, float] = {}
    for ta in tool_accuracy:
        action_dist[ta.action_type] = ta.total / total_actions if total_actions else 0

    # 难度分布
    difficulty_dist: dict[str, int] = {}
    for m in all_metrics:
        d = m.difficulty_label or "未知"
        difficulty_dist[d] = difficulty_dist.get(d, 0) + 1

    path = PathAnalysis(
        min_steps=min(steps_list) if steps_list else 0,
        max_steps=max(steps_list) if steps_list else 0,
        mean_steps=sum(steps_list) / len(steps_list) if steps_list else 0,
        median_steps=steps_median,
        action_distribution=action_dist,
        difficulty_distribution=difficulty_dist,
    )

    # ── 4. 耗时 ──
    elapsed_list = [m.total_elapsed_ms for m in all_metrics]
    avg_total = sum(elapsed_list) / len(elapsed_list) if elapsed_list else 0
    p50 = _percentile(elapsed_list, 50)
    p95 = _percentile(elapsed_list, 95)
    avg_llm = sum(m.llm_total_calls for m in all_metrics) / n if n else 0
    avg_tokens = sum(m.llm_total_tokens for m in all_metrics) / n if n else 0

    # 按动作类型的平均耗时聚合
    action_avg_timing: dict[str, float] = {}
    for ta in tool_accuracy:
        action_avg_timing[ta.action_type] = ta.avg_elapsed_ms

    slowest = max(tool_accuracy, key=lambda t: t.avg_elapsed_ms).action_type if tool_accuracy else ""

    timing = TimingProfile(
        avg_total_ms=avg_total,
        avg_per_step_ms=sum(m.per_step_avg_ms for m in all_metrics) / n if n else 0,
        p50_total_ms=p50,
        p95_total_ms=p95,
        avg_llm_calls=avg_llm,
        avg_llm_tokens=avg_tokens,
        slowest_action_type=slowest,
        action_avg_timing=action_avg_timing,
    )

    # ── 5. 异常率 ──
    total_searches = sum(m.actions_by_type.get("search", 0) for m in all_metrics)
    total_visits = sum(m.actions_by_type.get("visit", 0) for m in all_metrics)
    total_eval = sum(m.eval_attempts for m in all_metrics)
    total_actions_all = sum(m.total_actions for m in all_metrics)
    total_hard = sum(m.hard_intercepts for m in all_metrics)
    total_llm_err = sum(m.llm_errors for m in all_metrics)
    total_failed = sum(m.failed_actions for m in all_metrics)

    empty_s = sum(m.empty_searches for m in all_metrics)
    empty_v = sum(m.empty_visits for m in all_metrics)
    eval_f = sum(m.evaluation_failures for m in all_metrics)

    # 识别高频失败类型
    failure_counts: dict[str, int] = {}
    for m in all_metrics:
        for r in m.action_records:
            if not r.success:
                failure_counts[r.action_type] = failure_counts.get(r.action_type, 0) + 1
    top_failures = sorted(failure_counts, key=failure_counts.get, reverse=True)[:3]

    anomaly = AnomalyReport(
        empty_search_rate=empty_s / total_searches if total_searches else 0,
        empty_visit_rate=empty_v / total_visits if total_visits else 0,
        eval_failure_rate=eval_f / total_eval if total_eval else 0,
        hard_intercept_rate=total_hard / total_actions_all if total_actions_all else 0,
        llm_error_rate=total_llm_err / total_actions_all if total_actions_all else 0,
        beast_mode_rate=beast_modes / n if n else 0,
        action_failure_rate=total_failed / total_actions_all if total_actions_all else 0,
        top_failure_types=top_failures,
    )

    return MetricsSummary(
        task_completion=completion,
        tool_accuracy=tool_accuracy,
        path_analysis=path,
        timing_profile=timing,
        anomaly_report=anomaly,
        total_tasks=n,
        generated_at=time.time(),
    )
