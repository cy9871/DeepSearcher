"""DeepSearcher CLI"""

import argparse
import asyncio
import logging
import re
import sys
from datetime import datetime

from .agent import deep_research
from .config import LOG_LEVEL, MAX_TURNS, TOKEN_BUDGET


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
        "--budget", "-b",
        type=int,
        default=TOKEN_BUDGET,
        help=f"Total token budget (default: {TOKEN_BUDGET})",
    )
    parser.add_argument(
        "--log-level", "-l",
        default=LOG_LEVEL,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
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

    question = args.question
    if not question:
        question = sys.stdin.read().strip()

    if not question:
        print("Usage: python -m deepsearcher \"your question\"")
        sys.exit(1)

    budget_tokens = count_tokens(question)
    if budget_tokens > args.budget * 0.8:
        print(f"Question too long ({budget_tokens:.0f} tokens, max {args.budget * 0.8:.0f})")
        sys.exit(1)

    t0 = datetime.now()
    print(f"\n{'='*60}")
    print(f"  DeepSearcher")
    print(f"  Question: {question[:80]}{'...' if len(question) > 80 else ''}")
    print(f"  Max turns: {args.max_turns} | Budget: {args.budget}")
    print(f"{'='*60}\n")

    result = asyncio.run(
        deep_research(
            question=question,
            max_turns=args.max_turns,
            token_budget=args.budget,
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


if __name__ == "__main__":
    main()
