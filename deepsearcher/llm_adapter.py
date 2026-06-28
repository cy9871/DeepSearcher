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
    """查找 local_config.json
    
    优先级:
    1. 从当前工作目录向上查找（一级优先，用户在项目根目录执行时命中）
    2. 包自身所在的项目根目录（兜底，无论从哪启动都能找到）
    """
    # L1: 从 CWD 向上查找
    current = Path.cwd()
    for _ in range(5):
        candidate = current / "local_config.json"
        if candidate.exists():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent

    # L2: 包自身所在的项目根目录（deepsearcher/..  = 项目根）
    pkg_root = Path(__file__).resolve().parent.parent
    candidate = pkg_root / "local_config.json"
    if candidate.exists():
        return candidate

    return None


def resolve_config() -> dict:
    """公开接口：返回解析后的 LLM 配置 dict"""
    global _config
    if _config is None:
        _config = _resolve_config()
    return _config


def get_client() -> AsyncOpenAI:
    """获取全局 AsyncOpenAI 客户端单例（关闭内置重试，由 chat_completion 统一控制）"""
    global _client
    if _client is None:
        cfg = resolve_config()
        _client = AsyncOpenAI(
            base_url=cfg["base_url"],
            api_key=cfg["api_key"],
            max_retries=0,
        )
    return _client


async def chat_completion(**kwargs) -> object:
    """统一的 LLM 调用入口，自带 429 限速降级。
    
    NVIDIA 免费 API 分钟级配额用完后返回 429。
    等 30 秒重试，最多重试 3 次再放弃。
    30 秒约等于等分钟窗口滑动，大概率能续上。
    """
    import asyncio
    import logging
    from openai import APIStatusError

    logger = logging.getLogger(__name__)
    client = get_client()
    max_retries = 3

    for attempt in range(max_retries):
        try:
            return await client.chat.completions.create(**kwargs)
        except APIStatusError as e:
            if e.status_code == 429 and attempt < max_retries - 1:
                logger.warning(f"LLM 429 限速，等待 30s 后重试 (第 {attempt+1}/{max_retries} 次)")
                await asyncio.sleep(30)
                continue
            raise
    raise RuntimeError("unreachable")


def reset_client():
    """重置客户端和配置缓存（测试用）"""
    global _client, _config
    _client = None
    _config = None
