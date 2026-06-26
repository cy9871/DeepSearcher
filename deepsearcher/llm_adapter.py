"""
LLM 适配器 — 四级优先级解析，统一出口为 AsyncOpenAI 客户端

优先级（高 → 低）：
  1. DEEPSEARCH_BASE_URL / DEEPSEARCH_API_KEY / DEEPSEARCH_MODEL  环境变量
  2. 项目根目录 local_config.json
  3. OPENAI_BASE_URL / OPENAI_API_KEY 标准环境变量
  4. 硬编码默认值 → https://api.openai.com/v1 , model=gpt-4o

用法:
    from .llm_adapter import get_client
    client = get_client()
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from openai import AsyncOpenAI

# ── 默认值 ──────────────────────────────────────────────────────
_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_MODEL = "gpt-4o"

# ── 单例 ────────────────────────────────────────────────────────
_client: AsyncOpenAI | None = None
_config: dict | None = None


def _resolve_config() -> dict:
    """四级优先级解析 LLM 配置，结果缓存在模块级 _config"""
    base_url = None
    api_key = None
    model = None

    # L1: DEEPSEARCH_* 环境变量（最高优先级）
    if os.environ.get("DEEPSEARCH_BASE_URL"):
        base_url = os.environ["DEEPSEARCH_BASE_URL"]
    if os.environ.get("DEEPSEARCH_API_KEY"):
        api_key = os.environ["DEEPSEARCH_API_KEY"]
    if os.environ.get("DEEPSEARCH_MODEL"):
        model = os.environ["DEEPSEARCH_MODEL"]

    # L2: 项目根目录 local_config.json
    if base_url is None or api_key is None or model is None:
        local_path = _find_local_config()
        if local_path:
            try:
                with open(local_path, "r", encoding="utf-8") as f:
                    local = json.load(f)
                if base_url is None and local.get("base_url"):
                    base_url = local["base_url"]
                if api_key is None and local.get("api_key"):
                    api_key = local["api_key"]
                if model is None and local.get("model"):
                    model = local["model"]
            except (json.JSONDecodeError, IOError):
                pass

    # L3: OpenAI 标准环境变量
    if base_url is None:
        base_url = os.environ.get("OPENAI_BASE_URL")
    if api_key is None:
        api_key = os.environ.get("OPENAI_API_KEY")

    # L4: 硬编码默认值
    if base_url is None:
        base_url = _DEFAULT_BASE_URL
    if model is None:
        model = _DEFAULT_MODEL

    return {
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
    }


def _find_local_config() -> Path | None:
    """从当前工作目录向上查找 local_config.json
    
    从 cwd 而非包目录开始查找，确保只有用户在项目根目录执行时
    才会匹配到自己的 local_config.json。
    """
    current = Path.cwd()
    for _ in range(5):
        candidate = current / "local_config.json"
        if candidate.exists():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def resolve_config() -> dict:
    """公开接口：返回解析后的 LLM 配置 dict"""
    global _config
    if _config is None:
        _config = _resolve_config()
    return _config


def get_client() -> AsyncOpenAI:
    """获取全局 AsyncOpenAI 客户端单例"""
    global _client
    if _client is None:
        cfg = resolve_config()
        _client = AsyncOpenAI(
            base_url=cfg["base_url"],
            api_key=cfg["api_key"],
        )
    return _client


def reset_client():
    """重置客户端和配置缓存（测试用）"""
    global _client, _config
    _client = None
    _config = None
