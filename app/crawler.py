"""纯 Python 爬虫，不依赖 CrewAI —— 方便单独测试和离线调试。"""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from . import trace

DEFAULT_MAX_CHARS = 8000
DEFAULT_TIMEOUT = 20
DEFAULT_WORKERS = 4
DEFAULT_TOTAL_CHARS = 12000
MIN_PER_PAGE_CHARS = 1500

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# 这些标签里的内容基本是噪音，先整块删掉再取正文
NOISE_TAGS = (
    "script",
    "style",
    "noscript",
    "iframe",
    "svg",
    "canvas",
    "form",
    "nav",
    "footer",
    "header",
    "aside",
    "button",
)


@dataclass
class Page:
    url: str
    title: str
    text: str
    chars: int
    truncated: bool

    def to_prompt(self) -> str:
        note = "（正文较长，已截断）" if self.truncated else ""
        return (
            f"标题: {self.title or '(无标题)'}\n"
            f"来源: {self.url}\n"
            f"抓取字符数: {self.chars}{note}\n"
            f"---- 正文开始 ----\n{self.text}\n---- 正文结束 ----"
        )


@dataclass
class CrawlFailure:
    """抓取失败的结果，和 Page 一起组成 crawl_many 的返回值。"""

    url: str
    reason: str


def _read_html(target: str) -> tuple[str, str]:
    """返回 (html 源码, 最终 url)。支持 http(s) 链接和本地 html 文件。"""
    parsed = urlparse(target)
    if parsed.scheme in ("http", "https"):
        resp = requests.get(
            target,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml",
            },
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=True,
        )
        resp.raise_for_status()

        ctype = resp.headers.get("Content-Type", "")
        if ctype and "html" not in ctype.lower() and "text" not in ctype.lower():
            raise ValueError(f"目标不是网页内容（Content-Type: {ctype}）")

        # 很多中文站点不声明 charset，requests 会退回 ISO-8859-1 导致乱码
        if not resp.encoding or resp.encoding.lower() in {"iso-8859-1", "ascii"}:
            resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text, resp.url

    path = Path(target)
    if not path.exists():
        raise FileNotFoundError(f"既不是 http(s) 链接，也不是本地文件：{target}")
    return path.read_text(encoding="utf-8", errors="ignore"), path.resolve().as_uri()


def _html_to_text(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all(NOISE_TAGS):
        tag.decompose()

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(" ", strip=True)

    # 优先取语义化正文容器，退化到 body
    root = soup.find("article") or soup.find("main") or soup.body or soup
    raw = root.get_text("\n", strip=True)

    lines = [ln.strip() for ln in raw.splitlines()]
    lines = [ln for ln in lines if ln]
    text = "\n".join(lines)
    text = re.sub(r"[ \t\u3000]{2,}", " ", text)
    return title, text


def crawl(target: str, max_chars: int = DEFAULT_MAX_CHARS) -> Page:
    """抓取一个页面并返回结构化结果。失败时抛异常，由调用方决定怎么兜底。"""
    html, final_url = _read_html(target)
    title, text = _html_to_text(html)

    if not text:
        raise ValueError("页面里没抽到正文，可能是纯前端渲染（JS）或需要登录")

    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]

    return Page(
        url=final_url,
        title=title,
        text=text,
        chars=len(text),
        truncated=truncated,
    )


def parse_urls(text: str) -> list[str]:
    """把多行文本（可带 - / * 前缀）解析成去重后的网址列表。"""
    urls: list[str] = []
    for line in (text or "").splitlines():
        item = line.strip().lstrip("-*").strip()
        if not item or item.startswith("#"):
            continue
        if item not in urls:
            urls.append(item)
    return urls


def crawl_safe(target: str, max_chars: int, index: int = 0) -> Page | CrawlFailure:
    """抓取并把结果/耗时写进当前轨迹，失败收敛成 CrawlFailure 不抛异常。

    index 只用于可视化里的排序与编号，保持与输入顺序一致。
    """
    tr = trace.get_active()
    started = time.perf_counter()
    if tr:
        tr.add("crawl_start", url=target, index=index)
    try:
        page = crawl(target, max_chars=max_chars)
        if tr:
            tr.add(
                "crawl_end",
                url=target,
                index=index,
                ok=True,
                chars=page.chars,
                duration=round(time.perf_counter() - started, 3),
            )
        return page
    except Exception as exc:  # 并发场景下统一收敛成结果对象，不让异常穿透线程池
        if tr:
            tr.add(
                "crawl_end",
                url=target,
                index=index,
                ok=False,
                chars=0,
                duration=round(time.perf_counter() - started, 3),
                error=f"{type(exc).__name__}: {exc}"[:120],
            )
        return CrawlFailure(url=target, reason=f"{type(exc).__name__}: {exc}")


def crawl_many(
    targets: list[str],
    total_chars: int = DEFAULT_TOTAL_CHARS,
    workers: int = DEFAULT_WORKERS,
) -> list[Page | CrawlFailure]:
    """并发抓取多个网址，结果顺序与输入一致。

    total_chars 是所有页面共享的正文预算，按链接数均摊，
    避免 10 个链接一口气塞进 8 万字符把上下文撑爆。
    """
    urls = [u for u in targets if u and u.strip()]
    if not urls:
        return []

    per_page = max(MIN_PER_PAGE_CHARS, total_chars // len(urls))
    workers = max(1, min(workers, len(urls)))
    total = len(urls)

    def _job(item: tuple[int, str]) -> Page | CrawlFailure:
        idx, url = item
        short = url if len(url) <= 58 else url[:55] + "..."
        trace.progress(f"[{idx}/{total}] 请求 {short}")
        started = time.perf_counter()
        result = crawl_safe(url, per_page, index=idx)
        elapsed = time.perf_counter() - started
        if isinstance(result, Page):
            trace.progress(f"[{idx}/{total}] 完成 {result.chars} 字符 / {elapsed:.1f}s")
        else:
            trace.progress(f"[{idx}/{total}] 失败 {elapsed:.1f}s -> {result.reason[:50]}")
        return result

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_job, enumerate(urls, 1)))


def render_material(results: list[Page | CrawlFailure]) -> str:
    """把并发抓取结果拼成给 Agent 阅读的材料块。"""
    blocks: list[str] = []
    for idx, item in enumerate(results, 1):
        if isinstance(item, CrawlFailure):
            blocks.append(
                f"【来源 {idx}】抓取失败\n链接: {item.url}\n原因: {item.reason}"
            )
            continue
        note = "（正文已截断）" if item.truncated else ""
        blocks.append(
            f"【来源 {idx}】{item.title or '(无标题)'}\n"
            f"链接: {item.url}\n"
            f"正文（{item.chars} 字符{note}）:\n{item.text}"
        )
    return "\n\n".join(blocks)


def summarize(results: list[Page | CrawlFailure]) -> tuple[int, int]:
    """返回 (成功数, 失败数)。"""
    ok = sum(1 for r in results if isinstance(r, Page))
    return ok, len(results) - ok
