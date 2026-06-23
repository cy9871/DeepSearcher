"""URL 内容读取工具

使用 trafilatura 提取网页正文。
优先 httpx（可设 User-Agent 防反爬），回退 trafilatura 自带下载。
"""

import asyncio
import logging
from ..utils.url_tools import is_valid_url

logger = logging.getLogger(__name__)

# 已确认不可读的域名（跳过重试）
_BLOCKED_DOMAINS: set[str] = {
    "zhihu.com",          # 知乎需 Cookie，未配置
    "www.zhihu.com",
    "zhuanlan.zhihu.com",
    "sciengine.com",       # 学术论文反爬
    "www.sciengine.com",
}

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}

# 特定站点头部增强
_SPECIAL_HEADERS = {
    "zhihu.com": {
        **_DEFAULT_HEADERS,
        "Referer": "https://www.zhihu.com/",
        "Cookie": "",  # 无 Cookie 也能读取部分公开文章
    },
}


async def read_url(url: str, max_chars: int = 8000) -> dict:
    """读取 URL 正文内容（带 30s 超时）

    Returns:
        {"url": str, "title": str, "content": str, "success": bool, "error": str}
    """
    if not url.strip():
        return {"url": url, "title": "", "content": "", "success": False, "error": "URL 为空"}

    if not is_valid_url(url):
        return {"url": url, "title": "", "content": "", "success": False, "error": f"无效 URL: {url}"}

    # 跳过已知反爬域名
    from urllib.parse import urlparse
    domain = urlparse(url).hostname or ""
    if domain in _BLOCKED_DOMAINS:
        logger.debug(f"跳过已知反爬域名: {domain}")
        return {"url": url, "title": "", "content": "", "success": False, "error": f"已知反爬域名: {domain}"}

    try:
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, _fetch_trafilatura, url, max_chars),
            timeout=30.0,
        )
        return result
    except asyncio.TimeoutError:
        logger.warning(f"读取 URL 超时 (30s): {url}")
        from urllib.parse import urlparse
        domain = urlparse(url).hostname or ""
        _BLOCKED_DOMAINS.add(domain)
        return {"url": url, "title": "", "content": "", "success": False, "error": "超时"}
    except Exception as e:
        logger.warning(f"读取 URL 失败 {url}: {e}")
        return {"url": url, "title": "", "content": "", "success": False, "error": str(e)}


def _fetch_trafilatura(url: str, max_chars: int) -> dict:
    """同步获取并提取正文（含反爬对策）"""
    import trafilatura
    from trafilatura.metadata import extract_metadata

    # 跳过非 HTML 文件（PDF/图片/视频等）
    _SKIP_EXTENSIONS = (".pdf", ".zip", ".png", ".jpg", ".jpeg", ".gif", ".mp4", ".mp3", ".doc", ".docx", ".xls", ".xlsx")
    if url.lower().rstrip("?").split("?")[0].endswith(_SKIP_EXTENSIONS):
        logger.info(f"跳过非 HTML 文件: {url}")
        return {"url": url, "title": "", "content": "", "success": False, "error": "不支持的文件格式"}

    # ── 策略1：httpx + 自定义 User-Agent ──
    html = _fetch_via_httpx(url)
    if not html:
        # ── 策略2：trafilatura 自带下载 ──
        html = trafilatura.fetch_url(url)

    if not html:
        from urllib.parse import urlparse
        domain = urlparse(url).hostname or ""
        _BLOCKED_DOMAINS.add(domain)
        return {"url": url, "title": "", "content": "", "success": False, "error": "无法下载页面"}

    # ── 正文提取 ──
    result = trafilatura.extract(
        html,
        include_links=True,
        include_tables=False,
        include_images=False,
        output_format="markdown",
    )
    if not result:
        result = trafilatura.extract(html, output_format="text")

    if not result:
        return {"url": url, "title": "", "content": "", "success": False, "error": "无法提取正文"}

    # ── 提取标题 ──
    title = ""
    try:
        metadata = extract_metadata(html)
        if metadata:
            title = metadata.title or ""
    except Exception:
        pass

    if len(result) > max_chars:
        result = result[:max_chars] + "\n\n[... 内容已截断]"

    logger.info(f"读取 URL: {url} → {len(result)} 字符")
    return {"url": url, "title": title or url, "content": result, "success": True, "error": ""}


def _fetch_via_httpx(url: str) -> str | None:
    """用 httpx 下载页面（带站点自适应 User-Agent）"""
    try:
        import httpx
        # 选站点专用头或默认头
        headers = _DEFAULT_HEADERS
        for domain, h in _SPECIAL_HEADERS.items():
            if domain in url:
                headers = h
                break
        resp = httpx.get(url, headers=headers, timeout=20, follow_redirects=True)
        if resp.status_code != 200:
            logger.warning(f"httpx 返回 {resp.status_code} for {url}")
            return None
        ct = resp.headers.get("content-type", "").lower()
        # 非 HTML/XML/文本内容（如 PDF/图片）直接跳过
        if not any(t in ct for t in ["html", "text", "xml", "json"]):
            logger.info(f"跳过非文本内容: {url} ({ct})")
            return None
        return resp.text
    except Exception as e:
        logger.debug(f"httpx 下载失败 {url}: {e}")
        return None


async def read_urls(urls: list[str], max_per_url: int = 8000) -> list[dict]:
    """批量读取多个 URL"""
    import asyncio

    tasks = [read_url(u, max_per_url) for u in urls]
    return await asyncio.gather(*tasks)
