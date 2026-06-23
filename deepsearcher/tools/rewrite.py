"""查询改写工具

基于已有搜索结果，改写搜索查询词以提高召回率。
对应 node-DeepResearch 的 query-rewriter.ts。
"""

import json
import logging
from ..llm import get_client
from ..config import LLM_CONFIG
from ..models import RewrittenQueries
from ..utils.text_tools import extract_json
from ..tools.search import SearchResult

logger = logging.getLogger(__name__)


REWRITE_SYSTEM = """你是一个搜索查询优化器。
根据原始问题和已有搜索结果，生成改写后的搜索查询词以覆盖信息盲区。

<rules>
1. 每个查询词聚焦不同角度，避免搜索到相同内容
2. 如果已有结果覆盖充分，返回已覆盖的查询
3. 使用不同的措辞、同义词、相关术语
4. 英文查询配合英文术语，中文查询保持中文
5. 只输出 JSON，不要任何其他文字
</rules>

输出格式：
{{"queries": ["改写查询1", "改写查询2", "改写查询3"], "think": "思考过程"}}
"""


async def rewrite_queries(
    question: str,
    existing_results: list[SearchResult],
    num_queries: int = 3,
) -> list[str]:
    """基于已有结果改写查询词"""
    client = get_client()

    # 构建已有结果摘要
    existing_summary = "已有搜索结果:\n"
    for i, r in enumerate(existing_results[:10], 1):
        existing_summary += f"{i}. {r.title}: {r.snippet[:150]}\n"

    prompt = f"""(系统指令){REWRITE_SYSTEM}

(输入)原始问题: {question}

{existing_summary}

请生成 {num_queries} 个改写后的搜索查询词，覆盖信息盲区。
"""

    resp = await client.chat.completions.create(
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
