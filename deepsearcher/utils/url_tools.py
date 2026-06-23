"""URL 处理工具"""

from urllib.parse import urlparse


def is_valid_url(url: str) -> bool:
    """检查 URL 是否合法"""
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def normalize_url(url: str) -> str:
    """标准化 URL：去尾部斜杠、去片段"""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"


def extract_domain(url: str) -> str:
    """提取域名"""
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""
