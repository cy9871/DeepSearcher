"""
指标报告生成器

支持三种输出格式：
  1. text  — 终端友好的彩色文本报告
  2. json  — 机器可读的完整数据
  3. markdown — 文档友好的报告
"""

from __future__ import annotations

import json
import time
from datetime import datetime

from .metrics import (
    TaskMetrics,
    MetricsSummary,
    ToolAccuracy,
    TaskCompletion,
    PathAnalysis,
    TimingProfile,
    AnomalyReport,
)
from .storage import MetricsStorage, compute_summary


class MetricsReporter:
    """指标报告生成器"""

    def __init__(self, storage: MetricsStorage | None = None):
        self.storage = storage or MetricsStorage()

    # ── 文本报告（终端 / CLI）────────────────────────────────

    @staticmethod
    def format_text(summary: MetricsSummary) -> str:
        """生成终端友好的文本报告"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = []
        sep = "━" * 56

        lines.append(f"\n{sep}")
        lines.append(f"  📊 Agent 效果评估报告")
        lines.append(f"  生成时间: {now}  |  任务总数: {summary.total_tasks}")
        lines.append(sep)

        # ── 1. 任务完成率 ──
        tc = summary.task_completion
        lines.append(f"\n  1️⃣  任务完成率")
        lines.append(f"  ├─ 完成任务: {tc.completed}/{tc.total_tasks} ({tc.completion_rate:.0%})")
        lines.append(f"  ├─ Beast Mode: {tc.beast_mode_rate:.0%}")
        lines.append(f"  └─ 质量门禁通过: {tc.eval_pass_rate:.0%}")

        # ── 2. 工具调用准确率 ──
        lines.append(f"\n  2️⃣  工具调用准确率")
        for ta in summary.tool_accuracy:
            bar = _mini_bar(ta.success_rate, 12)
            lines.append(f"  ├─ {ta.action_type:10s} {bar} {ta.success_rate:.0%}  "
                         f"({ta.successful}/{ta.total}, 均{ta.avg_elapsed_ms:.0f}ms)")

        # ── 3. 路径长度 ──
        pa = summary.path_analysis
        lines.append(f"\n  3️⃣  路径长度")
        lines.append(f"  ├─ 步骤: min={pa.min_steps}  max={pa.max_steps}  "
                     f"均值={pa.mean_steps:.1f}  中位数={pa.median_steps:.1f}")
        # 动作分布
        dist_parts = []
        for atype, ratio in sorted(pa.action_distribution.items(), key=lambda x: -x[1]):
            if ratio > 0:
                dist_parts.append(f"{atype}:{ratio:.0%}")
        lines.append(f"  └─ 动作分布: {'  '.join(dist_parts)}")

        # 难度分布
        if pa.difficulty_distribution:
            diff_parts = [f"{d}:{c}" for d, c in sorted(pa.difficulty_distribution.items())]
            lines.append(f"     难度分布: {'  '.join(diff_parts)}")

        # ── 4. 平均耗时 ──
        tp = summary.timing_profile
        lines.append(f"\n  4️⃣  平均耗时")
        lines.append(f"  ├─ 平均总耗时: {_format_ms(tp.avg_total_ms)}")
        lines.append(f"  ├─ 平均每步耗时: {_format_ms(tp.avg_per_step_ms)}")
        lines.append(f"  ├─ 耗时中位数: {_format_ms(tp.p50_total_ms)} (P95: {_format_ms(tp.p95_total_ms)})")
        lines.append(f"  ├─ 平均 LLM 调用: {tp.avg_llm_calls:.1f} 次 / 任务")
        lines.append(f"  ├─ 平均 Token: {tp.avg_llm_tokens:.0f} / 任务")
        lines.append(f"  └─ 最慢动作: {tp.slowest_action_type}")

        # ── 5. 异常率 ──
        ar = summary.anomaly_report
        lines.append(f"\n  5️⃣  异常率")
        lines.append(f"  ├─ 空搜索率: {ar.empty_search_rate:.1%}  (搜索返回0结果)")
        lines.append(f"  ├─ 空阅读率: {ar.empty_visit_rate:.1%}  (阅读未产生知识)")
        lines.append(f"  ├─ 评估失败率: {ar.eval_failure_rate:.1%}  (质量门禁不通过)")
        lines.append(f"  ├─ 硬拦截率: {ar.hard_intercept_rate:.1%}  (待读URL>0禁止answer)")
        lines.append(f"  ├─ LLM 错误率: {ar.llm_error_rate:.1%}")
        lines.append(f"  ├─ Beast Mode 率: {ar.beast_mode_rate:.1%}")
        lines.append(f"  ├─ 动作失败率: {ar.action_failure_rate:.1%}")
        if ar.top_failure_types:
            lines.append(f"  └─ 高频失败类型: {', '.join(ar.top_failure_types)}")

        lines.append(f"\n{sep}\n")
        return "\n".join(lines)

    @staticmethod
    def format_task_text(metrics: TaskMetrics) -> str:
        """单任务终端文本报告"""
        lines = []
        lines.append(f"\n{'─'*52}")
        lines.append(f"  📋 任务指标: {metrics.task_id}")
        lines.append(f"  问题: {metrics.question[:60]}")
        lines.append(f"{'─'*52}")
        lines.append(f"  完成: {'✅' if metrics.completed else '❌'}  "
                     f"|  步骤: {metrics.steps_taken}/{metrics.max_steps_allowed}  "
                     f"|  难度: {metrics.difficulty_label}")
        lines.append(f"  耗时: {_format_ms(metrics.total_elapsed_ms)}  "
                     f"|  每步均: {_format_ms(metrics.per_step_avg_ms)}")
        lines.append(f"  成功动作: {metrics.successful_actions}/{metrics.total_actions}  "
                     f"|  LLM 调用: {metrics.llm_total_calls}  "
                     f"|  Token: ~{metrics.llm_total_tokens}")
        lines.append(f"  质量门禁: {'✅' if metrics.eval_passed else '❌'}  "
                     f"|  Beast Mode: {'⚠️' if metrics.beast_mode_triggered else '—'}  "
                     f"|  评估重试: {metrics.eval_attempts}")

        # 动作明细表
        if metrics.action_records:
            lines.append(f"\n  动作明细:")
            for r in metrics.action_records:
                icon = "✅" if r.success else "❌"
                detail = ""
                if r.action_type == "search":
                    detail = f"结果:{r.extra.get('results_found','?')} 入队:{r.extra.get('urls_queued','?')}"
                elif r.action_type == "visit":
                    detail = f"知识:{r.extra.get('knowledge_extracted','?')} 失败:{r.extra.get('read_failures','?')}"
                elif r.action_type == "answer":
                    detail = f"字数:{r.extra.get('char_count','?')} 评估:{r.extra.get('eval_passed','?')}"
                lines.append(f"    {icon} step{r.step} {r.action_type:8s} {_format_ms(r.elapsed_ms):>8s}  {detail}")

        # 异常摘要
        anomalies = []
        if metrics.empty_searches:
            anomalies.append(f"空搜索×{metrics.empty_searches}")
        if metrics.empty_visits:
            anomalies.append(f"空阅读×{metrics.empty_visits}")
        if metrics.evaluation_failures:
            anomalies.append(f"评估失败×{metrics.evaluation_failures}")
        if metrics.hard_intercepts:
            anomalies.append(f"硬拦截×{metrics.hard_intercepts}")
        if metrics.llm_errors:
            anomalies.append(f"LLM错误×{metrics.llm_errors}")
        if anomalies:
            lines.append(f"\n  异常: {'  '.join(anomalies)}")

        lines.append("")
        return "\n".join(lines)

    # ── JSON 报告 ─────────────────────────────────────────────

    @staticmethod
    def format_json(summary: MetricsSummary) -> str:
        """导出完整 JSON 报告"""
        data = {
            "generated_at": summary.generated_at,
            "total_tasks": summary.total_tasks,
            "task_completion": {
                "total": summary.task_completion.total_tasks,
                "completed": summary.task_completion.completed,
                "completion_rate": summary.task_completion.completion_rate,
                "beast_mode_rate": summary.task_completion.beast_mode_rate,
                "eval_pass_rate": summary.task_completion.eval_pass_rate,
            },
            "tool_accuracy": [
                {
                    "action_type": ta.action_type,
                    "total": ta.total,
                    "successful": ta.successful,
                    "success_rate": ta.success_rate,
                    "avg_elapsed_ms": ta.avg_elapsed_ms,
                }
                for ta in summary.tool_accuracy
            ],
            "path_analysis": {
                "min_steps": summary.path_analysis.min_steps,
                "max_steps": summary.path_analysis.max_steps,
                "mean_steps": summary.path_analysis.mean_steps,
                "median_steps": summary.path_analysis.median_steps,
                "action_distribution": summary.path_analysis.action_distribution,
                "difficulty_distribution": summary.path_analysis.difficulty_distribution,
            },
            "timing_profile": {
                "avg_total_ms": summary.timing_profile.avg_total_ms,
                "avg_per_step_ms": summary.timing_profile.avg_per_step_ms,
                "p50_total_ms": summary.timing_profile.p50_total_ms,
                "p95_total_ms": summary.timing_profile.p95_total_ms,
                "avg_llm_calls": summary.timing_profile.avg_llm_calls,
                "avg_llm_tokens": summary.timing_profile.avg_llm_tokens,
                "slowest_action_type": summary.timing_profile.slowest_action_type,
                "action_avg_timing": summary.timing_profile.action_avg_timing,
            },
            "anomaly_report": {
                "empty_search_rate": summary.anomaly_report.empty_search_rate,
                "empty_visit_rate": summary.anomaly_report.empty_visit_rate,
                "eval_failure_rate": summary.anomaly_report.eval_failure_rate,
                "hard_intercept_rate": summary.anomaly_report.hard_intercept_rate,
                "llm_error_rate": summary.anomaly_report.llm_error_rate,
                "beast_mode_rate": summary.anomaly_report.beast_mode_rate,
                "action_failure_rate": summary.anomaly_report.action_failure_rate,
                "top_failure_types": summary.anomaly_report.top_failure_types,
            },
        }
        return json.dumps(data, ensure_ascii=False, indent=2)

    # ── 便捷方法 ──────────────────────────────────────────────

    def build_summary(self) -> MetricsSummary:
        """从存储构建聚合摘要"""
        return compute_summary(self.storage)

    def print_summary(self):
        """打印文本摘要到终端"""
        summary = self.build_summary()
        print(self.format_text(summary))

    def export_json(self, filepath: str | None = None) -> str:
        """导出 JSON 报告"""
        summary = self.build_summary()
        json_str = self.format_json(summary)
        if filepath:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(json_str)
        return json_str


# ── 辅助 ──────────────────────────────────────────────────────

def _mini_bar(ratio: float, width: int = 10) -> str:
    """微型进度条"""
    filled = int(ratio * width)
    if filled == 0 and ratio > 0:
        filled = 1
    return "█" * filled + "░" * (width - filled)


def _format_ms(ms: float) -> str:
    """格式化毫秒"""
    if ms < 1000:
        return f"{ms:.0f}ms"
    elif ms < 60000:
        return f"{ms/1000:.1f}s"
    else:
        m = ms / 60000
        s = (ms % 60000) / 1000
        return f"{m:.0f}m{s:.0f}s"
