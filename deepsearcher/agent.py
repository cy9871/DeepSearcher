"""
Deep Research 深度研究 Agent - LangGraph 主循环

基于 node-DeepResearch 架构：
5 个动作 × 六维质量门禁 × Beast Mode 兜底
"""

from __future__ import annotations

import sys, os, site
# 自动挂载项目 venv 路径
_venv = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'venv')
if os.path.isdir(_venv):
    _sp = os.path.join(_venv, 'lib', f'python{sys.version_info.major}.{sys.version_info.minor}', 'site-packages')
    if os.path.isdir(_sp) and _sp not in sys.path:
        sys.path.insert(0, _sp)
        site.addsitedir(_sp)

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Literal

from .config import (
    LLM_CONFIG,
    MAX_TURNS,
    MAX_FAILURES,
    MAX_URLS_TO_READ,
    NUM_EVALS_REQUIRED,
    MAX_RETRIES,
    RETRY_DELAY,
    BAD_HOSTNAMES,
    ONLY_HOSTNAMES,
)
from .models import (
    AnswerAction,
    BoostedSnippet,
    KnowledgeItem,
    Snippet,
    SearchResult as SearchResultModel,
)
from .tools import search as search_tool
from .tools import read as read_tool
from .tools import evaluate as eval_tool
from .tools import planner as plan_tool
from .tools import rewrite as rewrite_tool
from .llm import chat_completion
from .utils.text_tools import (
    clean_text,
    extract_json,
    extract_references,
    format_knowledge_for_context,
    estimate_tokens,
)
from .evaluator.metrics import MetricsCollector, ActionRecord
from .evaluator.storage import MetricsStorage

from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# 动作执行函数
# ═══════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════
# 动作执行函数
# ═══════════════════════════════════════════════════════════════════


def _filter_urls(urls: dict[str, Snippet], visited: set[str], bad_hostnames: set[str]) -> dict[str, Snippet]:
    """
    门禁4: URL 过滤 — 去掉已访问的、坏域名的、白名单外的。
    对应 node-DeepResearch 的 filterURLs()。
    """
    filtered: dict[str, Snippet] = {}
    for url, snippet in urls.items():
        # 已访问 → 跳过
        if url in visited:
            continue
        # 坏域名 → 跳过
        hostname = urlparse(url).hostname or ""
        if any(bad in hostname for bad in bad_hostnames):
            logger.debug(f"  🚫 过滤坏域名: {hostname}")
            continue
        # 白名单模式
        if ONLY_HOSTNAMES and not any(allowed in hostname for allowed in ONLY_HOSTNAMES):
            logger.debug(f"  🚫 不在白名单: {hostname}")
            continue
        filtered[url] = snippet
    skipped = len(urls) - len(filtered)
    if skipped:
        logger.info(f"  URL 过滤: 跳过 {skipped} 个（已访问/坏域名/不在白名单）")
    return filtered


async def _rerank_results(question: str, query: str, urls: dict[str, Snippet]) -> dict[str, Snippet]:
    """
    LLM relevance rerank：一次调用看批量 URLs，返回相关性最高的子集。
    对应方案 A：搜索条数翻倍后，用 LLM 一次性筛出有价值的 URL。
    """
    if len(urls) <= 6:
        return urls  # 不够 6 条就不用筛

    try:
        items = []
        for i, (url, sn) in enumerate(urls.items()):
            items.append(f"[{i}] 标题: {sn.title or '无标题'[:80]}\n    摘要: {(sn.snippet or '')[:200]}\n    URL: {url}")
        items_str = "\n---\n".join(items)

        select_count = min(10, len(urls))  # 选 Top N 留给 serp_cluster 做域名摊平
        prompt = f"""你是一个搜索结果过滤器。根据原始问题，从以下搜索结果中选择最相关的 {select_count} 条。
只输出选中条目的编号列表（逗号分隔），不要任何其他文字。

原始问题: {question}
当前查询: {query}

搜索结果:
{items_str}

输出格式: [1, 3, 5, 7, 9, 11]"""

        resp = await chat_completion(
            model=LLM_CONFIG["model"],
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=200,
        )
        content = resp.choices[0].message.content or ""
        # 解析编号列表
        indices = re.findall(r"\d+", content)
        selected: set[int] = set()
        for idx_str in indices:
            try:
                idx = int(idx_str)
                if 0 <= idx < len(items):
                    selected.add(idx)
            except (ValueError, IndexError):
                continue

        if not selected:
            logger.warning("  rerank 未返回有效编号，回退全量")
            return urls

        keys = list(urls.keys())
        filtered = {keys[i]: urls[keys[i]] for i in sorted(selected)}
        logger.info(f"  rerank: {len(urls)} → {len(filtered)} 条")
        return filtered
    except Exception as e:
        logger.warning(f"  rerank 失败: {e}，回退全量")
        return urls


def _serp_cluster(urls: dict[str, Snippet], max_urls: int = 6, max_per_domain: int = 2) -> list[str]:
    """
    serpCluster: 将搜索结果按域名聚类，取各域名最有价值的 URL。
    保证待读来源多样化，不会全部指向同一个网站。
    对应 node-DeepResearch 的核心机制：搜索后自动排队，跳过则永远缺失证据。
    """
    by_domain: dict[str, list[tuple[str, Snippet]]] = {}
    for url, snippet in urls.items():
        domain = urlparse(url).netloc
        by_domain.setdefault(domain, []).append((url, snippet))

    selected: list[str] = []
    for domain, items in sorted(by_domain.items(), key=lambda x: -len(x[1])):
        items.sort(key=lambda x: -len(x[1].title or ""))
        for url, _ in items[:max_per_domain]:
            selected.append(url)
            if len(selected) >= max_urls:
                return selected
    return selected


async def _execute_search(state: dict, queries: list[str]) -> dict:
    """执行搜索，自动 serpCluster 后把高价值 URL 推入待读队列"""
    # ── 门禁1: 查询去重 ──
    all_keywords = set(state.get("all_keywords", []))
    deduped_queries = [q for q in queries if q not in all_keywords]
    skipped = len(queries) - len(deduped_queries)
    if skipped:
        logger.info(f"  查询去重: 跳过 {skipped} 个已搜过的词")
    if not deduped_queries:
        logger.warning("  所有查询词均已搜索过，跳过搜索")
        return {}
    # 记录本次搜索词
    state["all_keywords"].extend(deduped_queries)

    results_by_query = await search_tool.multi_search(deduped_queries)

    # ── 积累原始搜索结果（供 rewrite 使用）──
    all_raw = []
    for results in results_by_query.values():
        all_raw.extend(results)
    state.setdefault("raw_search_results", []).extend(all_raw)

    new_urls: dict[str, Snippet] = {}

    for query, results in results_by_query.items():
        for r in results:
            if r.url not in state["all_urls"]:
                snippet = Snippet(
                    url=r.url,
                    title=r.title,
                    snippet=r.snippet,
                    source=r.source,
                )
                new_urls[r.url] = snippet

    # ── serpCluster：按域名聚类，推入待读队列 ──
    # ── 门禁4: URL 过滤（去已访问、坏域名、不在白名单）──
    visited = set(state.get("visited_urls", []))
    bad_set = set(BAD_HOSTNAMES)
    new_urls = _filter_urls(new_urls, visited, bad_set)
    if not new_urls:
        logger.warning("  URL 过滤后无可用链接")
        return {"all_urls": state["all_urls"]}

    # ── LLM relevance rerank：从原始结果中筛出最相关的（方案 A）──
    new_urls = await _rerank_results(state["question"], deduped_queries[0], new_urls)

    clustered_urls = _serp_cluster(new_urls, max_urls=6, max_per_domain=2)
    existing_todo = set(state.get("urls_to_visit", []))
    visited = set(state.get("visited_urls", []))
    newly_queued = 0
    for url in clustered_urls:
        if url not in existing_todo and url not in visited:
            state.setdefault("urls_to_visit", []).append(url)
            newly_queued += 1

    diary = [f"[search] {len(queries)} 查询 → {len(new_urls)} 新 URL, {newly_queued} 入待读队列"]
    state["diary_context"].extend(diary)
    logger.info(f"  搜索完成: {len(new_urls)} 新 URL, {newly_queued} 入待读队列")

    return {"all_urls": {**state["all_urls"], **new_urls}}


async def _execute_visit(state: dict, urls: list[str], concurrency: int = 1) -> dict:
    """执行读取 URL 动作"""
    urls_to_read = urls[:MAX_URLS_TO_READ]
    results = await read_tool.read_urls(urls_to_read)

    # 批量提取：按 \n\n 边界切块，并行 LLM 提取
    new_knowledge = await _batch_summarize(state["question"], results, concurrency=concurrency)

    # 记录已访问 URL
    for r in results:
        state.setdefault("visited_urls", []).append(r["url"])

    # ── 从待读队列移除已访问的 URL ──
    todo = state.get("urls_to_visit", [])
    visited_set = set(state["visited_urls"])
    state["urls_to_visit"] = [u for u in todo if u not in visited_set]

    diary = [f"[visit] 读取 {len(urls_to_read)} URL → {len(new_knowledge)} 条知识"]
    state["diary_context"].extend(diary)
    logger.info(f"  读取完成: {len(new_knowledge)} 条新知识")

    # ── diary 注入"路不通"信号 ──
    visited_count = len(state.get("visited_urls", []))
    knowledge_count = len(state.get("all_knowledge", [])) + len(new_knowledge)
    remaining_todo = len(state["urls_to_visit"])
    if remaining_todo == 0 and knowledge_count < 2:
        state["diary_context"].append(
            "[⚠️] 待读队列已清空，但收集的知识不足。"
            "你无法再通过 visit 获取新信息，必须 reflect 找出信息缺口或 search 寻找新来源。"
        )
    elif visited_count >= 5 and knowledge_count < 2:
        state["diary_context"].append(
            f"[⚠️] 已读 {visited_count} 个 URL 但只提取了 {knowledge_count} 条知识。"
            "继续 visit 收益可能很低，考虑 reflect 分析缺口或 search 换方向。"
        )

    return {
        "all_knowledge": state["all_knowledge"] + new_knowledge,
        "visited_urls": state.get("visited_urls", []),
    }


_CHUNK_SIZE = 30000  # 每块字符数（按 \n\n 边界对齐，≤ 此值）

async def _batch_summarize(question: str, results: list[dict], concurrency: int = 1) -> list[KnowledgeItem]:
    """批量提取：URL 正文按 \n\n 边界切 30000 字块，每块单独 LLM 调用并行提取知识"""
    valid = []
    for r in results:
        if r["success"] and r.get("content") and len(r["content"]) >= 50:
            valid.append(r)
    if not valid:
        return []

    # ── 切块：每个 URL 按 CHUNK_SIZE 边界切 ──
    chunks: list[tuple[int, int, str, str, str]] = []  # (url_idx, chunk_idx, title, url, text)
    for url_idx, r in enumerate(valid):
        content = r["content"]
        url = r["url"]
        title = r.get("title", "")
        if len(content) <= _CHUNK_SIZE:
            chunks.append((url_idx, 0, title, url, content))
        else:
            offset = 0
            chunk_idx = 0
            while offset < len(content):
                end = offset + _CHUNK_SIZE
                if end >= len(content):
                    chunks.append((url_idx, chunk_idx, title, url, content[offset:]))
                    break
                # 找最近的 \n\n 边界（最多回退 2000 字符）
                boundary = content.rfind("\n\n", end - 2000, end)
                if boundary > offset:
                    end = boundary
                chunks.append((url_idx, chunk_idx, title, url, content[offset:end]))
                offset = end
                chunk_idx += 1

    # ── 并行提取 ──
    sem = asyncio.Semaphore(concurrency)

    async def _extract_one(url_idx, chunk_idx, title, url, text):
        async with sem:
            label = f"[{url_idx}]" if chunk_idx == 0 else f"[{url_idx}](续{chunk_idx})"
            prompt = (
                f"(系统指令)你是一个信息提取器。从以下页面片段中，"
                f"提取与问题相关的关键事实。\n\n"
                f"只输出 JSON，不要任何其他文字：\n"
                f'{{"knowledge": [{{"fact": "..."}}, ...]}}\n'
                f'或 {{"knowledge": ["NO_MATCH"]}}\n\n'
                f"(输入)问题: {question}\n\n"
                f"{label} 标题: {title[:100]}\n"
                f"    正文:\n{text}"
            )
            try:
                resp = await chat_completion(
                    model=LLM_CONFIG["model"],
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                    max_tokens=2000,
                )
                content = resp.choices[0].message.content or "{}"
                data = extract_json(content)
                return (url_idx, url, data.get("knowledge", []) if data else [])
            except Exception as e:
                logger.warning(f"  提取 chunk [{url_idx}][{chunk_idx}] 失败: {e}")
                return (url_idx, url, [])

    tasks = [_extract_one(*c) for c in chunks]
    all_results = await asyncio.gather(*tasks)

    # ── 汇总 ──
    new_knowledge: list[KnowledgeItem] = []
    for url_idx, url, facts in all_results:
        for fact in facts:
            if isinstance(fact, str):
                if fact != "NO_MATCH" and fact.strip():
                    new_knowledge.append(KnowledgeItem(
                        question=question,
                        answer=clean_text(fact),
                        references=[url],
                    ))
            elif isinstance(fact, dict) and fact.get("fact"):
                f = fact["fact"]
                if f != "NO_MATCH" and f.strip():
                    new_knowledge.append(KnowledgeItem(
                        question=question,
                        answer=clean_text(f),
                        references=[url],
                    ))

    logger.info(f"  batch_summarize: {len(valid)} URL → {len(chunks)} chunks → {len(new_knowledge)} 条知识 ({concurrency} 并发)")
    return new_knowledge


async def _execute_reflect(state: dict) -> dict:
    """执行反思动作：分析知识缺口，生成子问题"""
    knowledge_text = format_knowledge_for_context(state["all_knowledge"][-5:])

    try:
        resp = await chat_completion(
            model=LLM_CONFIG["model"],
            messages=[
                {
                    "role": "user",
                    "content": f"(系统指令)你是一个研究员。分析已有知识，找出信息缺口，生成 2-3 个待解决的子问题。"
                    f"只输出 JSON 格式，不要任何其他文字：\n"
                    f"{{\"gaps\": [\"子问题1\", \"子问题2\"], \"think\": \"分析\"}}\n\n"
                    f"(输入)原始问题: {state['question']}\n\n已有知识:\n{knowledge_text}\n\n请找出信息缺口。",
                },
            ],
            temperature=0.2,
            max_tokens=1000,
        )
        content = resp.choices[0].message.content or "{}"
        data = extract_json(content)
        new_gaps = data.get("gaps", [])

        new_gaps_count = len(new_gaps)
        diary = [f"[reflect] 发现 {new_gaps_count} 个缺口: {', '.join(new_gaps[:3])}"]
        if new_gaps_count == 0:
            diary.append(
                "[⚠️] reflect 未发现新缺口，说明当前搜索方向可能已枯竭。"
                "必须换一个完全不同角度重新搜索。"
            )
        state["diary_context"].extend(diary)
        logger.info(f"  反思: {new_gaps_count} 个新缺口")

        return {"gaps": new_gaps}
    except Exception as e:
        logger.warning(f"反思失败: {e}")
        return {"gaps": []}


async def _execute_rewrite(state: dict) -> dict:
    """执行改写动作：基于已有搜索结果改写查询词，返回改写后的查询词供下一轮 search 使用"""
    raw_results = state.get("raw_search_results", [])
    if not raw_results:
        logger.warning("  无搜索结果可改写，下一轮将使用 gaps 搜索")
        return {"rewritten_queries": state.get("gaps", [])[:3]}

    try:
        all_knowledge = state.get("all_knowledge", [])
        covered_topics = [k.question for k in all_knowledge[-10:]] if all_knowledge else []

        new_queries = await rewrite_tool.rewrite_queries(
            question=state["question"],
            existing_results=raw_results,
            gaps=state.get("gaps", []),
            covered_topics=covered_topics,
            num_queries=3,
        )
        diary = [f"[rewrite] 改写查询: {', '.join(new_queries[:3])}"]
        state["diary_context"].extend(diary)
        logger.info(f"  改写查询: {new_queries}")
        return {"rewritten_queries": new_queries}
    except Exception as e:
        logger.warning(f"改写失败: {e}")
        diary = [f"[rewrite] 改写失败, 下一轮回退到 gaps: {state.get('gaps', [])[:3]}"]
        state["diary_context"].extend(diary)
        return {"rewritten_queries": state.get("gaps", [])[:3]}


async def _execute_answer(state: dict) -> dict:
    """生成最终答案（含引用标记）"""
    knowledge_text = format_knowledge_for_context(state["all_knowledge"])

    # 上次评估的改进建议
    improvement_context = ""
    last_plan = state.get("last_improvement_plan", "")
    if last_plan:
        improvement_context = f"\n\n<改善指示>\n上次评估发现的问题（请务必修复）:\n{last_plan}\n</改善指示>"

    try:
        resp = await chat_completion(
            model=LLM_CONFIG["model"],
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"(系统指令)你是一个深度研究分析员。基于已收集的信息，给出全面、有据的回答。\n\n"
                        f"<rules>\n"
                        f"1. 只使用下面提供的已有知识，不要编造\n"
                        f"2. 每条知识都标注了来源URL（[来源: xxx]）。你必须在对应内容后面标注引用编号 [1] [2] [3]\n"
                        f"3. 结构清晰，分点论述\n"
                        f"4. 如果信息不足，诚实说明缺失了什么\n"
                        f"5. 用中文回答\n"
                        f"6. 在回答末尾，用【参考资料】标题列出所有引用来源，格式：\n"
                        f"   [1] https://...\n"
                        f"   [2] https://...\n"
                        f"</rules>\n\n"
                        f"(输入)问题: {state['question']}\n\n已有知识:\n{knowledge_text}\n\n{improvement_context}"
                    ),
                },
            ],
            temperature=0.0,
            max_tokens=3000,
        )
        answer = resp.choices[0].message.content or ""
        refs_from_answer = extract_references(answer)
        refs_from_knowledge = []
        for k in state.get("all_knowledge", []):
            for r in getattr(k, "references", []):
                if r not in refs_from_knowledge:
                    refs_from_knowledge.append(r)
        references = refs_from_answer + [r for r in refs_from_knowledge if r not in refs_from_answer]

        diary = [f"[answer] 生成答案: {len(answer)} 字符, {len(references)} 引用"]
        state["diary_context"].extend(diary)
        logger.info(f"  生成答案: {len(answer)} 字符")

        return {
            "final_answer": answer,
            "references": references,
        }
    except Exception as e:
        logger.error(f"生成答案失败: {e}")
        return {"final_answer": f"生成答案时出错: {e}", "references": []}


# ═══════════════════════════════════════════════════════════════════
# Beast Mode 兜底
# ═══════════════════════════════════════════════════════════════════

async def _execute_beast_mode(state: dict) -> dict:
    """Beast Mode：预算耗尽或多次失败后，强制生成答案。任何答案优于无答案。"""
    logger.warning("⚠️ 触发 Beast Mode — 强制生成答案")

    knowledge_text = format_knowledge_for_context(state["all_knowledge"])
    try:
        resp = await chat_completion(
            model=LLM_CONFIG["model"],
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"(系统指令)你必须在信息有限的情况下给出最佳答案。"
                        f"基于现有知识诚实回答，说明局限性。"
                        f"任何答案优于无答案。用中文。\n\n"
                        f"<引用规则>\n"
                        f"每条知识都标注了来源URL（[来源: xxx]）。你必须在对应内容后面标注引用编号 [1] [2]\n"
                        f"回答末尾用【参考资料】标题列出所有引用来源。\n"
                        f"</引用规则>\n\n"
                        f"(输入)问题: {state['question']}\n\n已有知识:\n{knowledge_text}\n\n请给出最终答案。"
                    ),
                },
            ],
            temperature=0.0,
            max_tokens=2000,
        )
        answer = resp.choices[0].message.content or ""
        # 从答案抓取 URL + 知识项引用
        refs_from_answer = extract_references(answer)
        refs_from_knowledge = []
        for k in state.get("all_knowledge", []):
            for r in getattr(k, "references", []):
                if r not in refs_from_knowledge:
                    refs_from_knowledge.append(r)
        references = refs_from_answer + [r for r in refs_from_knowledge if r not in refs_from_answer]
        state["diary_context"].append("[beast_mode] 强制生成答案")
        return {"final_answer": answer, "references": references, "beast_mode_used": True}
    except Exception as e:
        return {
            "final_answer": f"深度研究未能完成。已收集 {len(state['all_knowledge'])} 条信息，但无法生成综合答案。错误: {e}",
            "references": [],
            "beast_mode_used": True,
        }


# ═══════════════════════════════════════════════════════════════════
# 主函数：Deep Research Agent
# ═══════════════════════════════════════════════════════════════════

async def deep_research(
    question: str,
    max_turns: int = MAX_TURNS,
    concurrency: int = 1,
    event_callback=None,
    task_id: str = "",
) -> dict:
    """
    深度研究 Agent 主入口。

    Args:
        question: 用户问题
        max_turns: 最大循环轮次
        concurrency: LLM 并发数（知识提取阶段并行调用数）
        event_callback: 可选异步回调(state: dict)，每完成一步后调用

    Returns:
        {"answer": str, "references": list[str], "diary": list[str], "knowledge_count": int}
    """
    async def _emit():
        if event_callback:
            await event_callback(dict(state))
    logger.info(f"🔍 Deep Research 启动: {question[:60]}...")
    logger.info(f"   max_turns={max_turns}")

    # ── 指标采集器 ────────────────────────────────────────────
    if not task_id:
        task_id = uuid.uuid4().hex[:12]
    metrics_collector = MetricsCollector(
        task_id=task_id,
        question=question,
        max_turns=max_turns,
    )

    # 初始化状态
    state = {
        "question": question,
        "gaps": [],
        "all_knowledge": [],
        "all_urls": {},
        "visited_urls": [],
        "urls_to_visit": [],  # serpCluster 自动生成的待读队列
        "weighted_urls": [],
        "diary_context": [],
        "raw_search_results": [],
        "all_keywords": [],       # 已搜索过的所有查询词（去重用）
        "last_improvement_plan": "",
        "step_count": 0,
        "beast_mode_used": False,
        "final_answer": "",
        "references": [],
        "failed_attempts": 0,
    }

    # ── 第零步：拆解问题 ────────────────────────────────────────
    try:
        subproblems = await plan_tool.plan_research(question)
        state["gaps"] = subproblems
        state["diary_context"].append(f"[plan] 拆解为 {len(subproblems)} 个子问题: {', '.join(subproblems[:3])}...")
        logger.info(f"  研究规划: {len(subproblems)} 个子问题")
    except Exception as e:
        logger.warning(f"研究规划失败: {e}，直接使用原始问题")
        state["gaps"] = [question]

    # 初始化评估类型
    try:
        q_eval = await eval_tool.evaluate_question(question)
        state["evaluation_types"] = q_eval.types
        state["diary_context"].append(f"[evaluate_question] 需要检查: {q_eval.types}")
        logger.info(f"  问题评估维度: {q_eval.types}")
        if "freshness" in q_eval.types:
            state["diary_context"].append(
                "[⏰ freshness] 该问题对时效性敏感，将优先收集最新信息"
            )
            logger.info("  ⏰ 时效性问题，将优先收集最新信息")
    except Exception as e:
        logger.warning(f"问题评估失败: {e}")
        state["evaluation_types"] = ["definitive"]

    await _emit()

    # ── 主循环：每轮 = 1 次完整 search → visit → reflect → rewrite ──
    while state["step_count"] < max_turns:
        # 一轮开始：step_count 是目标轮数序号
        state["step_count"] += 1
        logger.info(f"\n═══ 轮次 {state['step_count']}/{max_turns} ═══")
        state["diary_context"].append(f"")
        state["diary_context"].append(f"═══ 轮次 {state['step_count']}/{max_turns} ═══")
        state["diary_context"].append(f"")

        # ═══════════════════════════════════════════
        # 阶段 1/4: search
        # ═══════════════════════════════════════════
        # 优先用 rewrite 改写的查询词，没有则用 gaps，再没有用原始问题
        rewritten_queries = state.pop("rewritten_queries", None)
        if rewritten_queries:
            search_queries = rewritten_queries[:3]
        else:
            search_queries = state.get("gaps", [])[:3]
        if not search_queries:
            search_queries = [state["question"]]
        logger.info(f"  ① search: {search_queries}")
        t0 = time.monotonic()
        try:
            updates = await _execute_search(state, search_queries)
            state.update(updates)
        except Exception as e:
            logger.warning(f"  search 失败: {e}")
        dt_ms = (time.monotonic() - t0) * 1000
        metrics_collector.record_action(ActionRecord(
            action_type="search", step=state["step_count"],
            success=True, elapsed_ms=dt_ms, llm_calls=0,
            extra={"queries": len(search_queries)},
        ))
        await _emit()

        # ═══════════════════════════════════════════
        # 阶段 2/4: visit（把待读队列尽量读空）
        # ═══════════════════════════════════════════
        # 如果本轮有 2 次 visit 空间，尽量多读
        visit_remaining = 2  # 每轮最多读 2 批

        while visit_remaining > 0:
            todo = state.get("urls_to_visit", [])
            visited_set = set(state.get("visited_urls", []))
            unvisited = [u for u in todo if u not in visited_set]
            if not unvisited:
                break  # 待读空了就跳到 reflect

            target_urls = unvisited[:MAX_URLS_TO_READ]
            logger.info(f"  ② visit({3-visit_remaining}): {len(target_urls)} 个 URL")
            t0 = time.monotonic()
            try:
                updates = await _execute_visit(state, target_urls, concurrency=concurrency)
                state.update(updates)
            except Exception as e:
                logger.warning(f"  visit 失败: {e}")
            dt_ms = (time.monotonic() - t0) * 1000
            metrics_collector.record_action(ActionRecord(
                action_type="visit", step=state["step_count"],
                success=True, elapsed_ms=dt_ms, llm_calls=1,
                extra={"urls_read": len(target_urls)},
            ))
            await _emit()
            visit_remaining -= 1

        # visit 后注入"路不通"信号
        visited_count = len(state.get("visited_urls", []))
        knowledge_count = len(state.get("all_knowledge", []))
        if visited_count >= 5 and knowledge_count < 2:
            state["diary_context"].append(
                f"[⚠️] 已读 {visited_count} 个 URL 但只提取了 {knowledge_count} 条知识，继续 visit 收益可能很低"
            )

        # ═══════════════════════════════════════════
        # 阶段 3/4: reflect
        # ═══════════════════════════════════════════
        if knowledge_count >= 2:
            logger.info(f"  ③ reflect")
            t0 = time.monotonic()
            try:
                updates = await _execute_reflect(state)
                state.update(updates)
            except Exception as e:
                logger.warning(f"  reflect 失败: {e}")
            dt_ms = (time.monotonic() - t0) * 1000
            gaps_found = len(updates.get("gaps", [])) if isinstance(updates, dict) else 0
            metrics_collector.record_action(ActionRecord(
                action_type="reflect", step=state["step_count"],
                success=gaps_found > 0, elapsed_ms=dt_ms, llm_calls=1,
                extra={"gaps_found": gaps_found},
            ))
            await _emit()
        else:
            logger.info(f"  ③ reflect: 跳过（知识不足 {knowledge_count}<2）")

        # ═══════════════════════════════════════════
        # 阶段 4/4: rewrite（用反思结果改写搜索词）
        # ═══════════════════════════════════════════
        if state.get("gaps"):
            logger.info(f"  ④ rewrite")
            t0 = time.monotonic()
            try:
                updates = await _execute_rewrite(state)
                state.update(updates)
            except Exception as e:
                logger.warning(f"  rewrite 失败: {e}")
            dt_ms = (time.monotonic() - t0) * 1000
            metrics_collector.record_action(ActionRecord(
                action_type="rewrite", step=state["step_count"],
                success=True, elapsed_ms=dt_ms, llm_calls=1,
                extra={"queries_generated": 3},
            ))
            await _emit()
        else:
            logger.info(f"  ④ rewrite: 跳过（无 gaps）")

        # ── 轮次快照 ──
        p = len([u for u in state.get("urls_to_visit", []) if u not in set(state.get("visited_urls", []))])
        v = len(state.get("visited_urls", []))
        k = len(state.get("all_knowledge", []))
        state["diary_context"].append(f"  ├ 知识:{k} | 已读:{v} | 待读:{p}")

        # ── 轮次结束：answer 判定 ──
        # 退出条件（满足任一即答）：
        #   1. 达到最大轮次上限
        #   2. 失败次数超限
        #   3. 无 gaps 且无 rewritten_queries → 反思和改写都没产出新搜索方向，提前退出
        should_answer = (
            state["step_count"] >= max_turns
            or state.get("failed_attempts", 0) >= MAX_FAILURES
            or (not state.get("gaps") and not state.get("rewritten_queries"))
        )

        if should_answer:
            t_as = time.monotonic()
            ans_state = await _execute_answer(state)
            dt_as = (time.monotonic() - t_as) * 1000
            state.update(ans_state)

            if state.get("final_answer"):
                # 评估答案
                eval_passed = False
                eval_total = 0
                for ea in range(NUM_EVALS_REQUIRED):
                    eval_passed, improvement_plan = await eval_tool.evaluate_answer(
                        question=question,
                        answer=state["final_answer"],
                        answer_action={"answer": state["final_answer"]},
                        evaluation_types=state.get("evaluation_types", ["definitive"]),
                        all_knowledge=state["all_knowledge"],
                    )
                    eval_total += 1
                    if eval_passed:
                        break
                    logger.info(f"  评估未通过 {ea+2}/{NUM_EVALS_REQUIRED+1}")
                    if improvement_plan:
                        state["last_improvement_plan"] = improvement_plan
                    metrics_collector.mark_eval_failure()
                    ans_updates = await _execute_answer(state)
                    state.update(ans_updates)

                metrics_collector.record_action(ActionRecord(
                    action_type="answer", step=state["step_count"],
                    success=eval_passed, elapsed_ms=dt_as,
                    llm_calls=1 + eval_total,
                    extra={"eval_passed": eval_passed, "eval_attempts": eval_total},
                ))
                if eval_passed:
                    break
                else:
                    state["failed_attempts"] = state.get("failed_attempts", 0) + 1
                    state["diary_context"].append("[evaluate] 答案未通过，继续")
                    if state["failed_attempts"] >= MAX_FAILURES:
                        t_bm = time.monotonic()
                        bm_updates = await _execute_beast_mode(state)
                        dt_bm = (time.monotonic() - t_bm) * 1000
                        metrics_collector.mark_beast_mode(reason="max_failures")
                        metrics_collector.record_action(ActionRecord(
                            action_type="beast_mode", step=state["step_count"],
                            success=True, elapsed_ms=dt_bm, llm_calls=1,
                            extra={"trigger_reason": "max_failures"},
                        ))
                        state.update(bm_updates)
                        break
            else:
                state["failed_attempts"] = state.get("failed_attempts", 0) + 1
                state["diary_context"].append("[answer] 无法生成答案")
                if state["failed_attempts"] >= MAX_FAILURES:
                    t_bm = time.monotonic()
                    bm_updates = await _execute_beast_mode(state)
                    dt_bm = (time.monotonic() - t_bm) * 1000
                    metrics_collector.mark_beast_mode(reason="max_failures")
                    metrics_collector.record_action(ActionRecord(
                        action_type="beast_mode", step=state["step_count"],
                        success=True, elapsed_ms=dt_bm, llm_calls=1,
                        extra={"trigger_reason": "max_failures"},
                    ))
                    state.update(bm_updates)
                    break

    await _emit()

    # ── 循环结束 ──────────────────────────────────────────────────
    # 如果还没答案，Beast Mode
    if not state.get("final_answer"):
        logger.warning("循环结束但无答案，触发 Beast Mode")
        t_bm = time.monotonic()
        updates = await _execute_beast_mode(state)
        dt_bm = (time.monotonic() - t_bm) * 1000
        metrics_collector.mark_beast_mode(reason="loop_exhausted")
        metrics_collector.record_action(ActionRecord(
            action_type="beast_mode",
            step=state["step_count"],
            success=bool(state.get("final_answer", "")),
            elapsed_ms=dt_bm,
            llm_calls=1,
            extra={"trigger_reason": "loop_exhausted"},
        ))
        state.update(updates)

    logger.info(f"✅ Deep Research 完成: {len(state['final_answer'])} 字符, "
                f"{len(state['references'])} 引用, {state['step_count']} 步骤")

    await _emit()

    result = {
        "answer": state["final_answer"],
        "references": state["references"],
        "diary": state["diary_context"],
        "knowledge_count": len(state["all_knowledge"]),
        "steps": state["step_count"],
        "beast_mode_used": state["beast_mode_used"],
    }

    # ── 持久化指标 ────────────────────────────────────────────
    try:
        task_metrics = metrics_collector.finalize()
        # 用结果中的 task_id（如果有的话）
        storage = MetricsStorage()
        storage.save_task_metrics(task_metrics)
        logger.info(f"[Metrics] 已保存任务指标: {task_metrics.task_id or '(id pending)'}")
    except Exception as e:
        logger.warning(f"[Metrics] 保存指标失败: {e}")

    return result
