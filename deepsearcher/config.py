"""
Deep Research Agent 配置

LLM 层走 QClaw 内部网关（自动探测端口和 token，OpenAI 兼容格式）。
探测逻辑与 RAGine 完全对齐：单一 _detect_gateway() → (port, token)。
可通过环境变量覆盖。
"""

import json
import os
from pathlib import Path


def _detect_gateway() -> tuple[int, str]:
    """Auto-detect QClaw gateway port and auth token from openclaw.json.

    Returns (port, token). Falls back to (62258, "") if config file not found.
    Identical to RAGine ragine/config.py to keep both projects in sync.
    """
    config_paths = [
        Path(os.environ.get("OPENCLAW_CONFIG_PATH", "")) if os.environ.get("OPENCLAW_CONFIG_PATH") else None,
        Path.home() / ".qclaw" / "openclaw.json",
    ]
    for cp in config_paths:
        if cp and cp.exists():
            try:
                cfg = json.loads(cp.read_text())
                port = int(cfg.get("gateway", {}).get("port", 62258))
                token = cfg.get("gateway", {}).get("auth", {}).get("token", "")
                return (port, token)
            except (json.JSONDecodeError, KeyError, IOError, ValueError):
                continue
    return (62258, "")


_gw_port, _gw_token = _detect_gateway()

# ── LLM 配置（走 QClaw 内部网关）────────────────────────────────
LLM_CONFIG = {
    "base_url": os.environ.get("DEEPSEARCH_BASE_URL") or f"http://127.0.0.1:{_gw_port}/v1",
    "api_key": os.environ.get("DEEPSEARCH_API_KEY") or _gw_token or "sk-local",
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
