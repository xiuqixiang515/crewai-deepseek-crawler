"""把爬虫包装成 CrewAI 工具。这个模块会 import crewai，所以 demo 模式不要去碰它。"""

from __future__ import annotations

from crewai.tools import tool

from .crawler import DEFAULT_MAX_CHARS, crawl


@tool("crawl_webpage")
def crawl_webpage(url: str) -> str:
    """抓取一个网页的正文并转成纯文本（已剔除导航、脚本、广告等噪音）。

    当需要阅读某个网页的具体内容、核对事实或提取数据时，调用本工具。

    Args:
        url: 完整网页地址，必须是以 http:// 或 https:// 开头的 URL。

    Returns:
        包含标题、来源链接和正文的文本块；抓取失败时返回以 [抓取失败] 开头的说明。
    """
    target = (url or "").strip().strip("<>\"'")
    if not target:
        return "[抓取失败] url 为空，请传入完整的 http(s) 链接。"

    try:
        page = crawl(target, max_chars=DEFAULT_MAX_CHARS)
    except Exception as exc:  # 工具里不要抛异常，返回文本让 LLM 自己决策
        return (
            f"[抓取失败] {target}\n"
            f"原因: {type(exc).__name__}: {exc}\n"
            "建议: 检查链接是否可公开访问；若页面需要登录或由 JS 渲染，请换一个来源。"
        )

    return page.to_prompt()
