"""两个任务：先整理材料成笔记，再扩写成报告（Markdown 或 JSON）。"""

from __future__ import annotations

from crewai import Agent, Task

# 预取模式下，正文通过 inputs 的 {material} 注入。
# CrewAI 的 interpolate_only 是先扫描模板再 str.replace，
# 所以正文里出现花括号不会被二次解析，安全。
_MATERIAL_HEADER = (
    "以下网页正文已经在本地并发抓取完成，按来源编号排列：\n\n"
    "{material}\n\n"
    "处理规则：\n"
    "1. 只使用上述材料里确实写了的信息，不得补充外部知识。\n"
    "2. 标记为「抓取失败」的来源，如实记入失败清单，不要臆测其内容。\n"
    "3. 仅当某条材料明显被截断、且缺失关键信息时，才调用 crawl_webpage 补抓该链接。\n"
    "4. 不要重复抓取已经完整返回的来源。"
)

_FETCH_HEADER = (
    "需要调研的网址列表：\n"
    "{urls}\n\n"
    "对列表中的每一个网址调用 crawl_webpage 工具抓取正文。"
    "如果某个地址抓取失败（返回以 [抓取失败] 开头的说明），"
    "记录失败原因后继续处理下一个，不要中断整个流程。"
)

_NOTE_FORMAT = (
    "按网址分组的 Markdown 笔记。每一组必须包含：\n"
    "- 页面标题\n"
    "- 原始链接\n"
    "- 3 到 6 条要点，每条不超过 60 字，且必须是原文里确实写了的\n"
    "- 关键数据或日期（如果原文有）\n\n"
    "若某个网址抓取失败，单列一节“抓取失败清单”，写明链接和失败原因。"
)

_MARKDOWN_BRIEF = (
    "把研究员提供的笔记整合成一份中文 Markdown 报告，严格按以下结构：\n\n"
    "## 一句话摘要\n"
    "## 核心要点\n"
    "（3 到 5 条，带序号）\n"
    "## 分来源详解\n"
    "（每个成功抓取的网址一小节，用三级标题）\n"
    "## 横向对比 / 值得注意的差异\n"
    "（资料不足就写“资料不足”，不要猜测）\n"
    "## 来源清单\n"
    "（列出所有实际用到的链接；失败的链接单独标注）\n\n"
    "硬性要求：只使用笔记中的事实，不得引入外部知识；"
    "保持客观陈述，不要写营销腔；不要用代码块包裹整篇文档。"
)

# DeepSeek 不支持 OpenAI 的 json_schema 结构化输出，
# 所以这里把目标结构写进 prompt，配合 response_format=json_object，
# 再由 app/crew_def.py 用 Pydantic 校验。
_STRUCTURED_BRIEF = (
    "把研究员提供的笔记整合成一个 JSON 对象，严格只输出这个 JSON，"
    "不要输出 Markdown 代码块、不要任何解释文字。\n\n"
    "JSON 结构必须完全符合以下形状：\n"
    "{\n"
    '  "title": "报告标题（字符串）",\n'
    '  "summary": "一句话摘要，不超过 80 字",\n'
    '  "key_points": ["3 到 5 条核心要点，每条不超过 60 字"],\n'
    '  "sections": [\n'
    '    {"heading": "来源页面标题", "url": "来源链接", "body": "该来源的详解正文，可含 Markdown 段落"}\n'
    "  ],\n"
    '  "comparison": "跨来源对比；信息不足时写「资料不足」，不要编造",\n'
    '  "sources": ["实际用到的链接，抓取失败的要在字符串中注明"]\n'
    "}\n\n"
    "硬性要求：只使用笔记中的事实；宁可写「资料不足」，也不要填空式编造；"
    "所有字段都必须出现，即使内容为空也要保留字段。"
)


def build_tasks(
    researcher: Agent,
    writer: Agent,
    output_file: str | None,
    use_material: bool = False,
    structured: bool = False,
) -> tuple[Task, Task]:
    """构造两个任务。

    use_material: 正文已由代码并发预取，通过 inputs["material"] 注入
    structured:   撰稿人输出 JSON 字符串，由调用方校验成 Pydantic 对象
    """
    research_task = Task(
        description=_MATERIAL_HEADER if use_material else _FETCH_HEADER,
        expected_output=_NOTE_FORMAT,
        agent=researcher,
    )

    report_kwargs: dict = {
        "description": _STRUCTURED_BRIEF if structured else _MARKDOWN_BRIEF,
        "expected_output": (
            "一个合法的 JSON 对象，字段与给定结构一致，不含任何额外文字。"
            if structured
            else "一份完整的 Markdown 报告，含标题层级、分节内容和来源链接。"
        ),
        "agent": writer,
        "context": [research_task],
    }

    if not structured and output_file:
        report_kwargs["output_file"] = output_file

    return research_task, Task(**report_kwargs)
