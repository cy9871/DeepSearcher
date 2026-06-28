"""DeepSearcher CLI"""

import argparse
import asyncio
import logging
import re
import sys
from datetime import datetime

from .agent import deep_research
from .config import LOG_LEVEL, MAX_TURNS


def setup_logging(level: str = LOG_LEVEL) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DeepSearcher — A multi-turn research agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "question",
        nargs="?",
        help="Research question (read from stdin if omitted)",
    )
    parser.add_argument(
        "--max-turns", "-t",
        type=int,
        default=MAX_TURNS,
        help=f"Max research loop turns (default: {MAX_TURNS})",
    )
    parser.add_argument(
        "--log-level", "-l",
        default=LOG_LEVEL,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    parser.add_argument(
        "--metrics", "-m",
        action="store_true",
        help="Print agent evaluation metrics after research completes",
    )
    parser.add_argument(
        "--metrics-only",
        action="store_true",
        help="Only print evaluation summary (no research)",
    )
    parser.add_argument(
        "--metrics-task",
        type=str,
        default="",
        help="Show metrics for a specific task ID (no research)",
    )
    return parser.parse_args()


def count_tokens(text: str) -> int:
    """Rough token count for Chinese + English."""
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    english_words = len(re.findall(r"[a-zA-Z]+", text))
    return chinese_chars * 2 + english_words * 1.3


def main() -> None:
    args = parse_args()
    setup_logging(args.log_level)

    # ── 纯指标模式 ────────────────────────────────────────────
    if args.metrics_only:
        from .evaluator.storage import MetricsStorage, compute_summary
        from .evaluator.reporter import MetricsReporter
        storage = MetricsStorage()
        if storage.task_count() == 0:
            print("暂无评估数据。先运行一次研究任务。")
            sys.exit(0)
        reporter = MetricsReporter(storage)
        reporter.print_summary()
        return

    if args.metrics_task:
        from .evaluator.storage import MetricsStorage
        from .evaluator.reporter import MetricsReporter
        storage = MetricsStorage()
        metrics = storage.load_task_metrics(args.metrics_task)
        if not metrics:
            print(f"任务 {args.metrics_task} 的指标数据不存在")
            # 尝试模糊匹配
            tasks = storage.get_metrics_index()
            if tasks:
                print(f"可用的任务 ID:")
                for t in tasks[:10]:
                    print(f"  {t['task_id']} — {t.get('question', '?')[:50]}")
            sys.exit(1)
        reporter = MetricsReporter(storage)
        print(reporter.format_task_text(metrics))
        return

    # ── 研究模式 ──────────────────────────────────────────────
    question = args.question
    if not question:
        question = sys.stdin.read().strip()

    if not question:
        print("Usage: python -m deepsearcher \"your question\"")
        sys.exit(1)

    t0 = datetime.now()
    print(f"\n{'='*60}")
    print(f"  DeepSearcher")
    print(f"  Question: {question[:80]}{'...' if len(question) > 80 else ''}")
    print(f"  Max turns: {args.max_turns}")
    print(f"{'='*60}\n")

    result = asyncio.run(
        deep_research(
            question=question,
            max_turns=args.max_turns,
        )
    )

    elapsed = (datetime.now() - t0).total_seconds()

    print(f"\n{'='*60}")
    print(f"  Research Complete ({elapsed:.1f}s)")
    print(f"{'='*60}\n")
    print(result.get("answer", "No answer generated."))
    print()

    if result.get("follow_up_questions"):
        print("\nFollow-up questions:")
        for i, q in enumerate(result["follow_up_questions"], 1):
            print(f"  {i}. {q}")
        print()

    # ── 指标输出 ──────────────────────────────────────────────
    if args.metrics:
        from .evaluator.storage import MetricsStorage
        from .evaluator.reporter import MetricsReporter
        storage = MetricsStorage()
        reporter = MetricsReporter(storage)
        # 最近的task指标
        tasks = storage.get_metrics_index()
        if tasks:
            latest = storage.load_task_metrics(tasks[0]["task_id"])
            if latest:
                print(reporter.format_task_text(latest))
        # 全量摘要
        if storage.task_count() > 1:
            reporter.print_summary()


if __name__ == "__main__":
    main()
