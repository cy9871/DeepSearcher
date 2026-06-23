"""文本处理工具"""

import re
from ..models import KnowledgeItem


def clean_text(text: str) -> str:
    """清洗文本：去多余空白、控制字符"""
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()


def truncate_text(text: str, max_chars: int = 8000) -> str:
    """截断文本"""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n[... truncated, {len(text) - max_chars} more chars]"


def extract_search_keywords(text: str, max_len: int = 50) -> str:
    """从问题中提取搜索关键词"""
    cleaned = text.strip().strip("?？。.")
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[:max_len].rsplit(" ", 1)[0]


def format_knowledge_for_context(items: list[KnowledgeItem]) -> str:
    """将知识条目格式化为 LLM 上下文（含来源URL）"""
    if not items:
        return "（尚无已有知识）"
    parts = []
    for i, item in enumerate(items, 1):
        url_str = f"\n**来源**: {', '.join(item.references)}" if item.references else ""
        parts.append(f"### 已知知识 {i}\n**问题**: {item.question}\n**回答**: {item.answer}{url_str}")
    return "\n\n".join(parts)


def extract_references(answer: str) -> list[str]:
    """从答案中提取引用 URL"""
    urls = re.findall(r'https?://[^\s<>"\')\]]+', answer)
    return list(set(urls))


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数（中文按 1.5 字符/token，英文按 4 字符/token）"""
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    other_chars = len(text) - chinese_chars
    return int(chinese_chars * 0.7 + other_chars / 4)


def extract_json(content: str) -> dict:
    """从 LLM 响应中提取 JSON。支持：
    - 纯 JSON
    - markdown 代码块包裹
    - 自然语言前导 + JSON（扫描所有可能的 { … } 组合）
    """
    if not content or not content.strip():
        return {}
    import json

    # 1. 纯 JSON
    try:
        return json.loads(content.strip())
    except json.JSONDecodeError:
        pass

    # 2. markdown 代码块
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. 找到所有 { … } 区域，从最后往前尝试解析（最有可能的是最后一个 JSON）
    #    这样即使自然语言部分有 { 也不影响
    brace_starts = [m.start() for m in re.finditer(r'{', content)]
    brace_ends = [m.start() for m in re.finditer(r'}', content)]

    for start in reversed(brace_starts):
        for end in brace_ends:
            if end <= start:
                continue
            try:
                candidate = content[start:end + 1]
                obj = json.loads(candidate)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue

    return {}
