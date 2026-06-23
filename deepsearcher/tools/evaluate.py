"""质量评估工具

六维门禁：definitive → freshness → plurality → completeness → strict
逐项检查，一票否决。对应 node-DeepResearch 的 evaluator.ts。
"""

import json
import logging
from ..llm import get_client
from ..config import LLM_CONFIG
from ..models import (
    QuestionEvaluation,
    DefinitiveResult,
    FreshnessResult,
    PluralityResult,
    CompletenessResult,
    StrictResult,
    EvaluationType,
    KnowledgeItem,
)
from ..utils.text_tools import format_knowledge_for_context, extract_json

logger = logging.getLogger(__name__)


async def _llm_structured_call(system: str, prompt: str, response_model: type, example: str = "") -> dict:
    """调用 LLM 并返回结构化输出"""
    client = get_client()

    # 用字段描述 + 示例替代原始 JSON Schema（避免 LLM 混淆）
    fields_desc = []
    for field_name, field_info in response_model.model_fields.items():
        alias = field_info.alias or field_name
        desc = field_info.description or ""
        fields_desc.append(f"  {alias}: ({field_info.annotation.__name__ if hasattr(field_info.annotation, '__name__') else str(field_info.annotation)}) {desc}")

    example_block = f"\n示例输出：\n{example}" if example else ""

    full_prompt = f"""(系统指令){system}

输出格式要求：
{chr(10).join(fields_desc)}

请只输出 JSON 对象，key 使用 camelCase 命名，value 为对应类型的值。不要包含 JSON Schema 定义，不要包含 markdown 代码块，直接输出 JSON 对象本身。{example_block}

(输入){prompt}
"""

    resp = await client.chat.completions.create(
        model=LLM_CONFIG["model"],
        messages=[
            {"role": "user", "content": full_prompt},
        ],
        temperature=0.1,
        max_tokens=2000,
    )

    content = resp.choices[0].message.content or "{}"
    return extract_json(content)


# ── 问题评估（确定需要哪些维度的检查）─────────────────────────

QUESTION_EVAL_SYSTEM = """你是一个评估问题类型的专家。
分析用户问题，判断需要哪些维度的质量检查。

<evaluation_types>
definitive - 问题是否需要确定性答案（几乎所有问题都需要，只有不可回答的悖论除外）
freshness - 问题是否对时效性敏感（涉及"当前""最新""现在"等）
plurality - 问题是否要求多个项目/示例/计数（"列出5个""有哪些方法"）
completeness - 问题是否明确提到多个需要逐一覆盖的方面
</evaluation_types>

<rules>
1. definitive: 默认 true。仅当问题是根本无法回答的悖论时才为 false。
2. freshness: 问题涉及当前状态、近期事件、价格、版本、职位等时 true。
3. plurality: 当 completeness=true 时，plurality 必须为 false（completeness 优先）。
4. completeness: 问题明确列出多个命名元素（"A、B 和 C""X 与 Y 的区别"）时 true。
</rules>"""


async def evaluate_question(question: str) -> QuestionEvaluation:
    """评估问题需要哪些质量检查维度"""
    prompt = f"""请分析以下问题：

{question}

判断需要哪几项质量检查。"""
    data = await _llm_structured_call(
        QUESTION_EVAL_SYSTEM, prompt, QuestionEvaluation,
        example='{"needsDefinitive": true, "needsFreshness": true, "needsPlurality": false, "needsCompleteness": false, "think": "该问题涉及当前版本状态，需要确定性和时效性检查"}'
    )
    result = QuestionEvaluation(**data) if data else QuestionEvaluation(
        needs_definitive=True, needs_freshness=False, needs_plurality=False, needs_completeness=False, think="fallback"
    )
    logger.info(f"问题评估: {question[:50]}... → {result.types}")
    return result


# ── 各维度评估 prompt ──────────────────────────────────────────

async def _evaluate_definitive(question: str, answer: str) -> bool:
    system = """你是一个答案确定性评估器。
判断答案是否给出了明确、自信的回复。

非确定性的表现（不通过）:
1. 表达个人不确定："我不知道""不确定""可能""大概"
2. 表示缺乏信息："不存在""找不到""缺少信息"
3. 表示无能为力："我无法提供""我不能""无法"
4. 被拒绝后给出的替代建议而非回答原问题

确定性可以接受的表现:
- 即使承认问题复杂，仍提供了实质性信息
- 呈现多方观点同时给出清晰论述"""
    prompt = f"问题: {question}\n\n回答: {answer}"
    data = await _llm_structured_call(system, prompt, DefinitiveResult)
    return DefinitiveResult(**data).pass_ if data else True


async def _evaluate_freshness(question: str, answer: str, answer_action: dict) -> bool:
    from datetime import datetime
    current_time = datetime.now().isoformat()

    system = f"""你是一个答案时效性评估器。
根据问题类型判断答案内容是否已过时。

当前系统时间: {current_time}

各类问题最大允许天数:
- 金融数据(实时): 0.1天
- 突发新闻: 1天
- 天气: 1天
- 体育比分: 1天
- 安全公告: 1天
- 科技新闻: 7天
- 政治动态: 7天
- 市场分析: 14天
- 行业报告: 30天
- 经济预测: 30天
- 科学研究: 60天
- 教程: 180天
- 事实知识: 不限制"""
    prompt = f"问题: {question}\n\n回答: {json.dumps(answer_action, ensure_ascii=False)}"
    data = await _llm_structured_call(system, prompt, FreshnessResult)
    return FreshnessResult(**data).pass_ if data else True


async def _evaluate_plurality(question: str, answer: str) -> bool:
    system = """你是一个答案数量充分性评估器。
检查答案是否提供了问题所要求的足够数量的项目。

规则:
- 明确数量（"5个"）→ 必须提供恰好5个不重复的项目
- "几个" → 2-4个
- "多个" → 3-7个
- "许多" → 7+
- "最重要的" → 3-5个
- "优缺点" → 每类至少2个
- "步骤" → 包含所有关键步骤
- 未指定 → 3-5个要点"""
    prompt = f"问题: {question}\n\n回答: {answer}"
    data = await _llm_structured_call(system, prompt, PluralityResult)
    return PluralityResult(**data).pass_ if data else True


async def _evaluate_completeness(question: str, answer: str) -> bool:
    system = """你是一个答案完整性评估器。
检查回答是否覆盖了问题中明确提到的所有方面。

识别问题中明确命名（用逗号、"和"、"与"分隔）的各个方面，
逐一检查回答是否涉及。缺任一即不通过。"""
    prompt = f"问题: {question}\n\n回答: {answer}"
    data = await _llm_structured_call(system, prompt, CompletenessResult)
    return CompletenessResult(**data).pass_ if data else True


async def _evaluate_strict(question: str, answer: str, all_knowledge: list[KnowledgeItem]) -> StrictResult:
    system = f"""你是一个吹毛求疵的答案评审者。
找出答案中所有不足、缺失细节、逻辑漏洞。

参考知识:
{format_knowledge_for_context(all_knowledge)}"""

    prompt = f"""请严格评审以下问答对：

<question>
{question}
</question>

<answer>
{answer}
</answer>

找出所有问题并给出改进方案。"""
    data = await _llm_structured_call(system, prompt, StrictResult)
    if data:
        return StrictResult(**data)
    return StrictResult(pass_=True, think="LLM 评估失败，放行")


# ── 主评估入口 ─────────────────────────────────────────────────

async def evaluate_answer(
    question: str,
    answer: str,
    answer_action: dict,
    evaluation_types: list[EvaluationType],
    all_knowledge: list[KnowledgeItem],
) -> tuple[bool, str]:
    """主评估入口：逐项检查，一票否决

    Returns:
        (passed, improvement_plan) — improvement_plan 为 strict 评估的改进建议
    """
    improvement_plan = ""
    for eval_type in evaluation_types:
        logger.info(f"  → 评估维度: {eval_type}")

        try:
            if eval_type == "definitive":
                passed = await _evaluate_definitive(question, answer)
            elif eval_type == "freshness":
                passed = await _evaluate_freshness(question, answer, answer_action)
            elif eval_type == "plurality":
                passed = await _evaluate_plurality(question, answer)
            elif eval_type == "completeness":
                passed = await _evaluate_completeness(question, answer)
            elif eval_type == "strict":
                result = await _evaluate_strict(question, answer, all_knowledge)
                passed = result.pass_
                if not passed:
                    improvement_plan = result.improvement_plan or ""
                    logger.info(f"  → Strict 未通过: {result.think[:100]}")
                    logger.info(f"  → 改进方案: {improvement_plan[:200]}")
            else:
                logger.warning(f"未知评估类型: {eval_type}")
                continue

            if not passed:
                logger.warning(f"  ❌ {eval_type} 未通过，答案被否决")
                return False, improvement_plan
            else:
                logger.info(f"  ✅ {eval_type} 通过")

        except Exception as e:
            logger.error(f"评估 {eval_type} 出错: {e}，放行")
            continue

    logger.info("  ✅ 所有门禁通过")
    return True, ""
