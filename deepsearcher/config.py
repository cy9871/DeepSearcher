"""
Deep Research Agent 配置

LLM 层走 QClaw 内部网关（localhost:57036，OpenAI 兼容格式）。
自动读取网关 token，也可通过环境变量覆盖。
"""

import json
import os


def _get_gateway_token() -> str:
    """从 OpenClaw 配置文件自动读取 gateway token"""
    env_token = os.environ.get("DEEPSEARCH_API_KEY", "")
    if env_token:
        return env_token
    try:
        config_path = os.path.expanduser("~/.qclaw/openclaw.json")
        with open(config_path) as f:
            return json.load(f)["gateway"]["auth"]["token"]
    except Exception:
        return ""


# ── LLM 配置（走 QClaw 内部网关）────────────────────────────────
LLM_CONFIG = {
    "base_url": os.environ.get("DEEPSEARCH_BASE_URL", "http://localhost:57036/v1"),
    "api_key": _get_gateway_token(),
    "model": os.environ.get("DEEPSEARCH_MODEL", "openclaw"),
    "temperature": 0.1,
    "max_tokens": 4096,
}

# ── 搜索配置 ────────────────────────────────────────────────────
# DuckDuckGo（免费，默认）
DUCKDUCKGO_ENABLED = True
# Jina Search API（可选，需 API Key）
JINA_SEARCH_API_KEY = os.environ.get("JINA_API_KEY", "")
JINA_SEARCH_ENABLED = bool(JINA_SEARCH_API_KEY)

# ── Agent 配置 ──────────────────────────────────────────────────
MAX_TURNS = 20               # 最大循环轮次
TOKEN_BUDGET = 100000        # 总 Token 预算
BEAST_MODE_RATIO = 0.15      # Beast Mode 兜底预算占比
MAX_FAILURES = 3             # 最大失败次数
MAX_SEARCH_RESULTS = 5       # 每次搜索保留结果数
MAX_URLS_TO_READ = 3         # 每轮最多读取 URL 数
TEAM_SIZE = 3                # 问题拆解的子问题数
NUM_EVALS_REQUIRED = 1       # 答案评估重复轮次

# ── 重试 ────────────────────────────────────────────────────────
MAX_RETRIES = 3
RETRY_DELAY = 1.0            # 秒

# ── 日志 ────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"
