"""
Deep Research 深度研究 Agent - LangGraph 主循环

基于 node-DeepResearch 架构：
5 个动作 × 六维质量门禁 × Token Budget 控制 × Beast Mode 兜底
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
from typing import Literal

from .config import (
    LLM_CONFIG,
    MAX_TURNS,
    TOKEN_BUDGET,
    BEAST_MODE_RATIO,
    MAX_FAILURES,
    MAX_URLS_TO_READ,
    NUM_EVALS_REQUIRED,
    MAX_RETRIES,
    RETRY_DELAY,
)
from .models import (
    Action,
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
from .llm import get_client
from .utils.token_tracker import TokenTracker
from .utils.text_tools import (
    clean_text,
    extract_json,
    extract_references,
    format_knowledge_for_context,
    estimate_tokens,
)

from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# 决策 Prompt（选择下一个动作）
# ═══════════════════════════════════════════════════════════════════

DECIDE_SYSTEM = """你是研究 Agent 的决策器。

== 可用动作 ==
1. visit — 读取待读队列中的 URL，获取正文事实。优先做这个。
2. search — 用子问题搜索新信息。
3. reflect — 分析已有知识的缺口。
4. rewrite — 基于已有搜索结果改写查询词并重新搜索，覆盖信息盲区。
5. answer — 输出最终答案。

== 硬约束 ==
- 待读 URL > 1 时，只能 visit，严禁 answer
- 步骤 < 3 时，只能 visit 或 search，严禁 answer
- 已有搜索结果但知识不足时，优先用 rewrite 改进搜索词

== 输出规则 ==
只输出以下 JSON，不输出任何其他文字、解释、思考过程：
{"type":"search","search_queries":["q1"],"think":""}
{"type":"visit","urls_to_visit":["url"],"think":""}
{"type":"reflect","gaps":["gap1"],"think":""}
{"type":"rewrite","think":""}
{"type":"answer","answer":"最终答案","think":""}
"""


async def _decide_action(state: dict) -> Action:
    """LLM 决策：选择下一步动作"""
    client = get_client()

    context = _build_decision_context(state)

    system = DECIDE_SYSTEM

    for attempt in range(MAX_RETRIES):
        try:
            resp = await client.chat.completions.create(
                model=LLM_CONFIG["model"],
                messages=[
                    {"role": "user", "content": f"(决策指令)\n{system}\n\n(当前状态)\n{context}"},
                ],
                temperature=0.0,
                max_tokens=350,
            )
            content = resp.choices[0].message.content or "{}"
            data = extract_json(content)
            if not data:
                raise ValueError(f"无有效 JSON: {content[:200]}")
            action = Action(**data)
            if not action.type or action.type not in ("search", "visit", "reflect", "rewrite", "answer"):
                raise ValueError(f"无效动作类型: {action.type}")
            logger.info(f"决策 → {action.type}: {str(action.think)[:50]}")
            return action
        except Exception as e:
            logger.warning(f"决策 LLM 调用失败 (attempt {attempt+1}): {e}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)
            else:
                # 最终回退：尝试回答
                return Action(type="answer", answer="无法做出决策，请重试。", think="fallback")

    return Action(type="answer", answer="无法做出决策，请重试。", think="fallback")


def _build_decision_context(state: dict) -> str:
    """构建决策上下文"""
    parts = [f"## 原始问题\n{state['question']}"]

    # 待读队列（serpCluster 自动生成）
    todo = state.get("urls_to_visit", [])
    visited = set(state.get("visited_urls", []))
    pending = [u for u in todo if u not in visited]
    if pending:
        parts.append(f"\n## 待读 URL 队列 ({len(pending)} 个，必须 visit 后才能 answer)")
        for url in pending[:5]:
            snippet = state["all_urls"].get(url)
            title = snippet.title if snippet else ""
            parts.append(f"- [{title or url}]({url})")
        if len(pending) > 5:
            parts.append(f"  ...及其他 {len(pending)-5} 个")

    # 当前知识缺口（来自上次反思）
    gaps = state.get("gaps", [])
    if gaps:
        parts.append(f"\n## 当前知识缺口 ({len(gaps)} 个)")
        for i, gap in enumerate(gaps, 1):
            parts.append(f"{i}. {gap}")

    # 已有知识（来自 visit 的正文提取）
    if state["all_knowledge"]:
        parts.append(f"\n## 已读取的知识 ({len(state['all_knowledge'])} 条)")
        for i, k in enumerate(state["all_knowledge"][-5:], 1):
            parts.append(f"{i}. Q: {k.question[:100]}\n   A: {k.answer[:200]}")

    # 已发现的 URL（全部）
    if state["all_urls"]:
        urls = list(state["all_urls"].values())
        unvisited = [u for u in urls if u.url not in visited]
        still_new = [u for u in unvisited if u.url not in todo]
        if still_new:
            parts.append(f"\n## 其他未发现的 URL ({len(still_new)} 个，待 search 发现后入队)")

    # 已访问的 URL
    if visited:
        parts.append(f"\n## 已访问 ({len(visited)} 个)")
        for u in list(visited)[-3:]:
            parts.append(f"- {u}")

    # 操作日记
    if state.get("diary_context"):
        parts.append(f"\n## 操作记录\n" + "\n".join(state["diary_context"][-8:]))

    # 步骤信息
    parts.append(f"\n## 进度\n当前步骤: {state.get('step_count', 0)}/{MAX_TURNS}")

    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════
# 动作执行函数
# ═══════════════════════════════════════════════════════════════════

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
    results_by_query = await search_tool.multi_search(queries)

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


async def _execute_visit(state: dict, urls: list[str]) -> dict:
    """执行读取 URL 动作"""
    urls_to_read = urls[:MAX_URLS_TO_READ]
    results = await read_tool.read_urls(urls_to_read)

    new_knowledge: list[KnowledgeItem] = []
    for r in results:
        if r["success"]:
            # 用 LLM 从正文中提取关键信息
            summary = await _summarize_content(state["question"], r["title"], r["content"])
            if summary:
                new_knowledge.append(
                    KnowledgeItem(
                        question=state["question"],
                        answer=summary,
                        references=[r["url"]],
                    )
                )
        state.setdefault("visited_urls", []).append(r["url"])

    # ── 从待读队列移除已访问的 URL ──
    todo = state.get("urls_to_visit", [])
    visited_set = set(state["visited_urls"])
    state["urls_to_visit"] = [u for u in todo if u not in visited_set]

    diary = [f"[visit] 读取 {len(urls_to_read)} URL → {len(new_knowledge)} 条知识"]
    state["diary_context"].extend(diary)

    logger.info(f"  读取完成: {len(new_knowledge)} 条新知识")
    return {
        "all_knowledge": state["all_knowledge"] + new_knowledge,
        "visited_urls": state.get("visited_urls", []),
    }


async def _summarize_content(question: str, title: str, content: str) -> str:
    """用 LLM 从页面正文中提取与问题相关的关键信息"""
    if not content or len(content) < 50:
        return ""
    try:
        client = get_client()
        resp = await client.chat.completions.create(
            model=LLM_CONFIG["model"],
            messages=[
                {
                    "role": "user",
                    "content": f"(系统指令)你是一个信息提取器。从页面正文中提取与问题相关的关键事实。"
                    f"只输出事实，不要评价。如果页面与问题无关，输出 NO_MATCH。\n\n"
                    f"(输入)问题: {question}\n\n页面标题: {title}\n\n页面正文:\n{content[:4000]}",
                },
            ],
            temperature=0.0,
            max_tokens=800,
        )
        result = resp.choices[0].message.content or ""
        if "NO_MATCH" in result:
            return ""
        return clean_text(result)
    except Exception:
        return ""


async def _execute_reflect(state: dict) -> dict:
    """执行反思动作：分析知识缺口，生成子问题"""
    knowledge_text = format_knowledge_for_context(state["all_knowledge"][-5:])

    try:
        client = get_client()
        resp = await client.chat.completions.create(
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

        diary = [f"[reflect] 发现 {len(new_gaps)} 个缺口: {', '.join(new_gaps[:3])}"]
        state["diary_context"].extend(diary)
        logger.info(f"  反思: {len(new_gaps)} 个新缺口")

        return {"gaps": new_gaps}
    except Exception as e:
        logger.warning(f"反思失败: {e}")
        return {"gaps": []}


async def _execute_rewrite(state: dict) -> dict:
    """执行改写动作：基于已有搜索结果改写查询词并重新搜索"""
    # 取积累的原始搜索结果（最近优先）
    raw_results = state.get("raw_search_results", [])
    if not raw_results:
        logger.warning("  无搜索结果可改写，回退到 search")
        return await _execute_search(state, state["gaps"][:2])

    try:
        new_queries = await rewrite_tool.rewrite_queries(
            question=state["question"],
            existing_results=raw_results,
            num_queries=3,
        )
        diary = [f"[rewrite] 改写查询: {', '.join(new_queries[:3])}"]
        state["diary_context"].extend(diary)
        logger.info(f"  改写查询: {new_queries}")

        # 用改写后的查询执行搜索
        return await _execute_search(state, new_queries)
    except Exception as e:
        logger.warning(f"改写失败: {e}")
        return await _execute_search(state, state["gaps"][:2])


async def _execute_answer(state: dict) -> dict:
    """生成最终答案（含引用标记）"""
    knowledge_text = format_knowledge_for_context(state["all_knowledge"])

    # 上次评估的改进建议
    improvement_context = ""
    last_plan = state.get("last_improvement_plan", "")
    if last_plan:
        improvement_context = f"\n\n<改善指示>\n上次评估发现的问题（请务必修复）:\n{last_plan}\n</改善指示>"

    try:
        client = get_client()
        resp = await client.chat.completions.create(
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
        client = get_client()
        resp = await client.chat.completions.create(
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
    token_budget: int = TOKEN_BUDGET,
    event_callback=None,
) -> dict:
    """
    深度研究 Agent 主入口。

    Args:
        question: 用户问题
        max_turns: 最大循环轮次
        token_budget: 总 Token 预算
        event_callback: 可选异步回调(state: dict)，每完成一步后调用

    Returns:
        {"answer": str, "references": list[str], "diary": list[str], "knowledge_count": int}
    """
    async def _emit():
        if event_callback:
            await event_callback(dict(state))
    logger.info(f"🔍 Deep Research 启动: {question[:60]}...")
    logger.info(f"   budget={token_budget}, max_turns={max_turns}")

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
        "last_improvement_plan": "",
        "step_count": 0,
        "token_budget": token_budget,
        "tokens_used": 0,        "beast_mode_used": False,
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
    except Exception as e:
        logger.warning(f"问题评估失败: {e}")
        state["evaluation_types"] = ["definitive"]

    await _emit()

    # ── 主循环 ──────────────────────────────────────────────────
    while state["step_count"] < max_turns:
        state["step_count"] += 1
        logger.info(f"\n─── 步骤 {state['step_count']}/{max_turns} ───")
        state["diary_context"].append(f"")
        state["diary_context"].append(f"═══ 步骤 {state['step_count']}/{max_turns} ═══")
        state["diary_context"].append(f"")
        state["_step_todo_before"] = len([u for u in state.get("urls_to_visit", []) if u not in set(state.get("visited_urls", []))])
        state["_step_knowledge_before"] = len(state.get("all_knowledge", []))

        # 第一轮固定 search（跳过 LLM 决策，直接搜子问题）
        if state["step_count"] == 1:
            queries = state["gaps"][:3]
            logger.info(f"  首轮 → search: {queries}")
            updates = await _execute_search(state, queries)
            state.update(updates)
            state["diary_context"].append(f"[step 1] 首轮搜索 {len(queries)} 个查询")
            p = len([u for u in state.get("urls_to_visit", []) if u not in set(state.get("visited_urls", []))])
            v = len(state.get("visited_urls", []))
            k = len(state.get("all_knowledge", []))
            state["diary_context"].append(f"  ├ 知识:{k} | 已读:{v} | 待读:{p}")
            await _emit()
            continue

        # 第二轮及之后用 LLM 决策
        # 检查 budget
        if estimate_tokens(str(state)) > token_budget * (1 - BEAST_MODE_RATIO):
            logger.warning(f"Token 预算紧张 ({state['tokens_used']}/{token_budget})")

        # 决策
        action = await _decide_action(state)
        state["current_action"] = action.type

        # ── 硬拦截：待读 URL > 0 且步骤 < 最大步数时，禁止 answer ──
        todo = state.get("urls_to_visit", [])
        visited = set(state.get("visited_urls", []))
        unvisited_count = len([u for u in todo if u not in visited])
        if action.type == "answer" and unvisited_count > 1 and state["step_count"] < max_turns - 1:
            logger.info(f"  ⛔ 硬拦截：{unvisited_count} 个 URL 未读，强制 visit")
            action.type = "visit"
            state["diary_context"].append(f"[⛔ 硬拦截] 待读队列还有 {unvisited_count} 个 URL，禁止提前 answer")

        # 执行动作
        try:
            if action.type == "search":
                updates = await _execute_search(state, action.search_queries or state["gaps"][:2])
            elif action.type == "visit":
                # 从待读队列取 URL
                todo = state.get("urls_to_visit", [])
                visited_set = set(state.get("visited_urls", []))
                if action.urls_to_visit:
                    target_urls = [u for u in action.urls_to_visit if u not in visited_set]
                else:
                    target_urls = [u for u in todo if u not in visited_set]
                if not target_urls:
                    logger.warning("  待读队列为空，回退到公海 URL")
                    target_urls = [
                        u.url for u in state["all_urls"].values()
                        if u.url not in visited_set
                    ][:MAX_URLS_TO_READ]
                updates = await _execute_visit(state, target_urls[:MAX_URLS_TO_READ])
            elif action.type == "reflect":
                updates = await _execute_reflect(state)
            elif action.type == "rewrite":
                updates = await _execute_rewrite(state)
            elif action.type == "answer":
                # 生成答案 → 评估 → 决定是否继续
                answer_state = await _execute_answer(state)
                state.update(answer_state)

                if not state.get("final_answer"):
                    state["failed_attempts"] += 1
                    continue

                # 评估答案
                eval_passed = False
                for eval_attempt in range(NUM_EVALS_REQUIRED):
                    answer_action = {"answer": state["final_answer"]}
                    eval_passed, improvement_plan = await eval_tool.evaluate_answer(
                        question=question,
                        answer=state["final_answer"],
                        answer_action=answer_action,
                        evaluation_types=state.get("evaluation_types", ["definitive"]),
                        all_knowledge=state["all_knowledge"],
                    )
                    if eval_passed:
                        break
                    logger.info(f"  评估未通过，尝试 {eval_attempt+2}/{NUM_EVALS_REQUIRED+1}")
                    # 将改进方案存入 state，下一轮 answer 会使用
                    if improvement_plan:
                        state["last_improvement_plan"] = improvement_plan
                    # 重新生成答案
                    updates = await _execute_answer(state)
                    state.update(updates)

                if eval_passed:
                    break  # 通过评估，退出循环
                else:
                    state["failed_attempts"] += 1
                    state["diary_context"].append("[evaluate] 答案未通过评估，继续研究")
                    if state["failed_attempts"] >= MAX_FAILURES:
                        logger.warning(f"达到最大失败次数 {MAX_FAILURES}，触发 Beast Mode")
                        updates = await _execute_beast_mode(state)
                        state.update(updates)
                        break
                    continue
            else:
                logger.warning(f"未知动作类型: {action.type}")
                continue

            state.update(updates)
            await _emit()

            # 步骤快照
            p = len([u for u in state.get("urls_to_visit", []) if u not in set(state.get("visited_urls", []))])
            v = len(state.get("visited_urls", []))
            k = len(state.get("all_knowledge", []))
            state["diary_context"].append(f"  ├ 知识:{k} | 已读:{v} | 待读:{p}")

        except Exception as e:
            logger.error(f"动作 {action.type} 执行失败: {e}")
            state["failed_attempts"] += 1
            state["diary_context"].append(f"[error] {action.type} 失败: {e}")
            if state["failed_attempts"] >= MAX_FAILURES:
                updates = await _execute_beast_mode(state)
                state.update(updates)
                break

    await _emit()

    # ── 循环结束 ──────────────────────────────────────────────────
    # 如果还没答案，Beast Mode
    if not state.get("final_answer"):
        logger.warning("循环结束但无答案，触发 Beast Mode")
        updates = await _execute_beast_mode(state)
        state.update(updates)

    logger.info(f"✅ Deep Research 完成: {len(state['final_answer'])} 字符, "
                f"{len(state['references'])} 引用, {state['step_count']} 步骤")

    await _emit()

    return {
        "answer": state["final_answer"],
        "references": state["references"],
        "diary": state["diary_context"],
        "knowledge_count": len(state["all_knowledge"]),
        "steps": state["step_count"],
        "beast_mode_used": state["beast_mode_used"],
    }
