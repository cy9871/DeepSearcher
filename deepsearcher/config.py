"""
Deep Research Agent 配置

LLM 配置由 llm_adapter 统一管理（四级优先级）：
  1. DEEPSEARCH_* 环境变量
  2. 项目根目录 local_config.json
  3. OPENAI_BASE_URL / OPENAI_API_KEY 标准环境变量
  4. 默认值 → https://api.openai.com/v1, model=gpt-4o
"""

import os

from .llm_adapter import resolve_config

# ── LLM 配置（通过适配器延迟解析）────────────────────────────────
def _build_llm_config() -> dict:
    cfg = resolve_config()
    return {
        "base_url": cfg["base_url"],
        "api_key": cfg["api_key"],
        "model": cfg["model"],
        "temperature": 0.1,
        "max_tokens": 4096,
    }

LLM_CONFIG = _build_llm_config()

# ── 搜索配置 ────────────────────────────────────────────────────
# DuckDuckGo（免费，默认）
DUCKDUCKGO_ENABLED = True
# Jina Search API（可选，需 API Key）
JINA_SEARCH_API_KEY = os.environ.get("JINA_API_KEY", "")
JINA_SEARCH_ENABLED = bool(JINA_SEARCH_API_KEY)

# ── Agent 配置 ──────────────────────────────────────────────────
MAX_TURNS = 20               # 最大循环轮次
MAX_FAILURES = 3             # 最大失败次数
MAX_SEARCH_RESULTS = 10       # 每次搜索保留结果数（提高后由 LLM rerank 过滤）
MAX_URLS_TO_READ = 3         # 每轮最多读取 URL 数
TEAM_SIZE = 3                # 问题拆解的子问题数
NUM_EVALS_REQUIRED = 1       # 答案评估重复轮次

# ── 重试 ────────────────────────────────────────────────────────
MAX_RETRIES = 3
RETRY_DELAY = 1.0            # 秒

# ── URL 过滤 ────────────────────────────────────────────────────
# 已知垃圾站/短链接/广告域名，搜索结果直接跳过
BAD_HOSTNAMES = [
    # 广告/低质量内容农场
    "adclick", "doubleclick", "adsense", "adservice",
    # 短链接服务（无法判断内容质量）
    "t.co", "bit.ly", "ow.ly", "tinyurl.com", "short.url",
    # 搜索引擎自身
    "google.com/search", "bing.com/search",
]
# 仅允许这些域名（白名单模式，为空则不限制）
ONLY_HOSTNAMES: list[str] = []

# ── 日志 ────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"
