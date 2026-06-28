"""查询改写工具

基于搜索结果（soundbites）从 7 个认知人格角度生成多样化搜索词。
对应 node-DeepResearch 的 query-rewriter.ts。
"""

import json
import logging
from datetime import datetime
from ..llm import chat_completion
from ..config import LLM_CONFIG
from ..models import RewrittenQueries
from ..utils.text_tools import extract_json

logger = logging.getLogger(__name__)


REWRITE_SYSTEM = f"""你是一个搜索查询优化器，从 4 个认知视角生成多样化的搜索词。

<cognitive-personas>
从以下 4 个认知视角各生成 1 条搜索词：

1. Contrarian（唱反调）：找局限、反证、被高估、证据不足、不适用场景。
   例："X 局限性 失败案例"、"X 被高估 证据不足"

2. Deep Diver（细节狂）：挖技术细节、精确参数、规格数据、实现原理。
   例："X 架构 MoE 参数"、"X 训练方法 数据策略"

3. Evolution Tracker（进化学家）：跟踪版本演变、历史脉络、新旧迭代差异。
   例："X V3 V4 演进 迭代"、"X 发展历史 路线图"

4. Comparatist（对比者）：探索竞品、替代方案、权衡优劣势。
   例："X vs Y 对比"、"X 替代方案 选择指南"
</cognitive-personas>

<search-tips>
- 关键词 2-5 个，简短精准
- 英文主题配合英文术语（技术类用英文搜更权威）
- 需要时效性时可加入当前年份 {datetime.now().year}
</search-tips>

<rules>
1. 每条查询聚焦一个特定视角，视角之间不重复
2. 基于已有知识的盲区生成搜索词，已有信息已充分覆盖的方向不要重复搜索
3. 只输出 JSON，不要任何其他文字
</rules>

输出格式：
{{"queries": ["搜索词1", "搜索词2", "搜索词3", "搜索词4"], "think": "思考过程"}}
"""


async def rewrite_queries(
    question: str,
    knowledge: str = "",
    num_queries: int = 4,
) -> list[str]:
    """基于已有知识，从 4 个认知人格生成多样化搜索词

    Args:
        question: 原始问题
        knowledge: 已有知识摘要文本（all_knowledge 中的事实片段）
        num_queries: 生成查询词数量（默认 4，对应 4 个人格）

    Returns:
        改写后的搜索词列表
    """

    knowledge_section = ""
    if knowledge:
        knowledge_section = f"\n<已有知识>\n以下是从已读页面中提取的事实片段：\n{knowledge[:2000]}\n</已有知识>"

    prompt = f"""(系统指令){REWRITE_SYSTEM}

(输入)原始问题: {question}
{knowledge_section}

请从 4 个认知视角生成 {num_queries} 条搜索词，每条聚焦已有知识中尚未充分覆盖的方向。
"""

    try:
        resp = await chat_completion(
            model=LLM_CONFIG["model"],
            messages=[
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=1000,
        )

        content = resp.choices[0].message.content or "{}"
        data = extract_json(content)
        if not data:
            logger.warning(f"查询改写解析失败")
            return [question]
        try:
            rewritten = RewrittenQueries(**data)
            logger.info(f"查询改写({len(rewritten.queries)}条): {rewritten.queries[:3]}...")
            return rewritten.queries
        except Exception as e:
            logger.warning(f"查询改写解析失败: {e}")
            return [question]
    except Exception as e:
        logger.warning(f"查询改写失败: {e}")
        return [question]
