"""研究规划工具

将复杂问题拆解为互不重叠的子问题。
对应 node-DeepResearch 的 research-planner.ts。
"""

import json
import logging
from ..config import LLM_CONFIG, TEAM_SIZE
from ..llm import chat_completion
from ..models import ResearchPlan
from ..utils.text_tools import extract_json

logger = logging.getLogger(__name__)


RESEARCH_PLANNER_SYSTEM = f"""你是一个研究主管，带领 {TEAM_SIZE} 名研究员进行深度研究。
将复杂问题拆解为 {TEAM_SIZE} 个独立、不重叠的子问题。

要求：
1. 每个子问题覆盖完全不同方面，重叠不超过 20%
2. 移除任何一个子问题都会导致重要理解缺失
3. 深入表面之下，探索机制和影响
4. 既包含"是什么"也包含"为什么"和"怎么做"
5. 只输出 JSON，不要任何其他文字

输出格式：
{{ "subproblems": ["子问题1", "子问题2", "子问题3"], "think": "思考过程" }}
"""


async def plan_research(question: str, team_size: int = TEAM_SIZE) -> list[str]:
    """拆解研究问题为子问题列表"""
    resp = await chat_completion(
        model=LLM_CONFIG["model"],
        messages=[
            {
                "role": "user",
                "content": f"(系统指令){RESEARCH_PLANNER_SYSTEM}\n\n(输入)问题：{question}\n\n请拆解为 {team_size} 个子问题。",
            },
        ],
        temperature=0.2,
        max_tokens=2000,
    )

    content = resp.choices[0].message.content or "{}"
    data = extract_json(content)
    if not data:
        logger.warning(f"研究规划解析失败: 无法提取 JSON")
        return [question]
    try:
        plan = ResearchPlan(**data)
        logger.info(f"研究规划: {question[:50]}... → {len(plan.subproblems)} 个子问题")
        return plan.subproblems
    except Exception as e:
        logger.warning(f"研究规划解析失败: {e}，回退到原始问题")
        return [question]
