"""
Pydantic 数据模型

对应 node-DeepResearch 的 types.ts，用于结构化 LLM 输出。
"""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


# ── 搜索相关 ────────────────────────────────────────────────────

class SearchResult(BaseModel):
    """单条搜索结果"""
    title: str
    url: str
    snippet: str


class SearchResponse(BaseModel):
    """搜索响应"""
    results: list[SearchResult] = Field(default_factory=list)
    total_hits: int = 0


class BoostedSnippet(BaseModel):
    """加权后的搜索片段"""
    url: str
    title: str
    snippet: str
    weight: float = 0.0


# ── 知识管理 ────────────────────────────────────────────────────

class KnowledgeItem(BaseModel):
    """知识条目：问答对"""
    question: str
    answer: str
    references: list[str] = Field(default_factory=list)


class Snippet(BaseModel):
    """搜索结果片段"""
    url: str
    title: str
    snippet: str
    score: float = 0.0
    source: str = "duckduckgo"


# ── 动作类型 ────────────────────────────────────────────────────

ActionType = Literal["search", "visit", "reflect", "rewrite", "answer", "beast_mode"]


class Action(BaseModel):
    """Agent 动作"""
    type: ActionType
    search_queries: list[str] = Field(default_factory=list, description="search 动作的查询词")
    urls_to_visit: list[str] = Field(default_factory=list, description="visit 动作的 URL")
    gaps: list[str] = Field(default_factory=list, description="reflect 动作识别的缺口")
    answer: str = Field(default="", description="answer 动作的答案内容")
    think: str = Field(default="", description="LLM 思考过程")


class AnswerAction(BaseModel):
    """回答动作"""
    answer: str
    references: list[str] = Field(default_factory=list)
    think: str = ""


# ── 评估相关 ────────────────────────────────────────────────────

EvaluationType = Literal["definitive", "freshness", "plurality", "completeness", "strict"]


class EvaluationResponse(BaseModel):
    """单次评估结果"""
    pass_: bool = Field(alias="pass")
    think: str = ""
    type: str = ""


class QuestionEvaluation(BaseModel):
    """问题评估：需要哪些维度的检查"""
    needs_definitive: bool = Field(alias="needsDefinitive")
    needs_freshness: bool = Field(alias="needsFreshness")
    needs_plurality: bool = Field(alias="needsPlurality")
    needs_completeness: bool = Field(alias="needsCompleteness")
    think: str = ""

    @property
    def types(self) -> list[EvaluationType]:
        types: list[EvaluationType] = []
        if self.needs_definitive:
            types.append("definitive")
        if self.needs_freshness:
            types.append("freshness")
        if self.needs_plurality:
            types.append("plurality")
        if self.needs_completeness:
            types.append("completeness")
        return types


class DefinitiveResult(BaseModel):
    pass_: bool = Field(alias="pass")
    think: str = ""


class FreshnessResult(BaseModel):
    pass_: bool = Field(alias="pass")
    think: str = ""


class PluralityResult(BaseModel):
    pass_: bool = Field(alias="pass")
    think: str = ""


class CompletenessResult(BaseModel):
    pass_: bool = Field(alias="pass")
    think: str = ""


class StrictResult(BaseModel):
    pass_: bool = Field(alias="pass")
    think: str = ""
    improvement_plan: str = ""


# ── 研究规划 ────────────────────────────────────────────────────

class ResearchPlan(BaseModel):
    """问题拆解结果"""
    subproblems: list[str]
    think: str = ""


# ── 查询改写 ────────────────────────────────────────────────────

class RewrittenQueries(BaseModel):
    """改写后的查询词"""
    queries: list[str]
    think: str = ""


# ── Agent 状态 ──────────────────────────────────────────────────

class AgentState(BaseModel):
    """LangGraph Agent 的全局状态"""
    question: str = ""
    gaps: list[str] = Field(default_factory=list)
    all_knowledge: list[KnowledgeItem] = Field(default_factory=list)
    all_urls: dict[str, Snippet] = Field(default_factory=dict)
    visited_urls: list[str] = Field(default_factory=list)
    weighted_urls: list[BoostedSnippet] = Field(default_factory=list)
    diary_context: list[str] = Field(default_factory=list)
    step_count: int = 0
    total_steps: int = 0
    token_budget_used: int = 0
    token_budget_total: int = 100000
    beast_mode_used: bool = False
    final_answer: str = ""
    references: list[str] = Field(default_factory=list)
    failed_attempts: int = 0
    evaluation_types: list[str] = Field(default_factory=list)
    current_action: str = ""

    class Config:
        arbitrary_types_allowed = True
