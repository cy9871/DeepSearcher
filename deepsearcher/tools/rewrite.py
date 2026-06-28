"""查询改写工具

基于已有搜索结果 + 反思缺口 + 已覆盖方向，改写搜索查询词以提高召回率。
对应 node-DeepResearch 的 query-rewriter.ts。
"""

import json
import logging
from ..llm import chat_completion
from ..config import LLM_CONFIG
from ..models import RewrittenQueries
from ..utils.text_tools import extract_json
from ..tools.search import SearchResult

logger = logging.getLogger(__name__)


REWRITE_SYSTEM = """你是一个搜索查询优化器。
根据原始问题、已有搜索结果、已覆盖方向和知识缺口，生成改写后的搜索查询词。

<rules>
1. 每个查询词聚焦不同角度，避免搜索到相同内容
2. 如果已有结果覆盖充分，返回已覆盖的查询
3. 使用不同的措辞、同义词、相关术语
4. 英文查询配合英文术语，中文查询保持中文
5. 不要改写已覆盖方向的查询词 —— 那些方向不用再搜
6. 重点围绕知识缺口设计查询词
7. 只输出 JSON，不要任何其他文字
</rules>

输出格式：
{{"queries": ["改写查询1", "改写查询2", "改写查询3"], "think": "思考过程"}}
"""


async def rewrite_queries(
    question: str,
    existing_results: list[SearchResult],
    gaps: list[str] | None = None,
    covered_topics: list[str] | None = None,
    num_queries: int = 3,
) -> list[str]:
    """基于已有结果 + 反思缺口 + 已覆盖方向改写查询词

    Args:
        question: 原始问题
        existing_results: 前几轮搜索的原始结果（标题+snippet），只取前10条
        gaps: reflect 阶段发现的知识缺口
        covered_topics: 已经收集充分的方向/子问题（仅标题，不传正文）
        num_queries: 生成查询词数量
    """

    # 构建已有结果摘要
    existing_summary = "已有搜索结果:\n"
    for i, r in enumerate(existing_results[:10], 1):
        existing_summary += f"{i}. {r.title}: {r.snippet[:150]}\n"

    # 已覆盖方向（避免重复改写）
    covered_section = ""
    if covered_topics:
        covered_section = "\n以下方向已收集充分，不要再改写这些方向的查询词:\n"
        for i, t in enumerate(covered_topics[:5], 1):
            covered_section += f"{i}. {t}\n"

    # 构建缺口信息（来自反思阶段）
    gaps_section = ""
    if gaps:
        gaps_section = "\nreflect 发现的知识缺口，请围绕这些方向改写查询词:\n"
        for i, g in enumerate(gaps[:3], 1):
            gaps_section += f"{i}. {g}\n"

    prompt = f"""(系统指令){REWRITE_SYSTEM}

(输入)原始问题: {question}

{existing_summary}{covered_section}{gaps_section}
请生成 {num_queries} 个改写后的搜索查询词，覆盖信息盲区。
"""

    resp = await chat_completion(
        model=LLM_CONFIG["model"],
        messages=[
            {{"role": "user", "content": prompt}},
        ],
        temperature=0.3,
        max_tokens=1000,
    )

    content = resp.choices[0].message.content or "{}"
    data = extract_json(content)
    if not data:
        logger.warning(f"查询改写解析失败")
        return [question]
    try:
        rewritten = RewrittenQueries(**data)
        logger.info(f"查询改写: {rewritten.queries}")
        return rewritten.queries
    except Exception as e:
        logger.warning(f"查询改写解析失败: {e}")
        return [question]  # 回退到原始问题
