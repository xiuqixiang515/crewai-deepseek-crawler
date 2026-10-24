"""两个任务：先抓取整理成笔记，再扩写成报告。"""

from __future__ import annotations

from crewai import Agent, Task


def build_tasks(researcher: Agent, writer: Agent, output_file: str) -> tuple[Task, Task]:
    research_task = Task(
        description=(
            "需要调研的网址列表：\n"
            "{urls}\n\n"
            "对列表中的每一个网址调用 crawl_webpage 工具抓取正文。"
            "如果某个地址抓取失败（返回以 [抓取失败] 开头的说明），"
            "记录失败原因后继续处理下一个，不要中断整个流程。"
        ),
        expected_output=(
            "按网址分组的 Markdown 笔记。每一组必须包含：\n"
            "- 页面标题\n"
            "- 原始链接\n"
            "- 3 到 6 条要点，每条不超过 60 字，且必须是原文里确实写了的\n"
            "- 关键数据或日期（如果原文有）\n\n"
            "若某个网址抓取失败，单列一节“抓取失败清单”，写明链接和失败原因。"
        ),
        agent=researcher,
    )

    report_task = Task(
        description=(
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
        ),
        expected_output="一份完整的 Markdown 报告，含标题层级、分节内容和来源链接。",
        agent=writer,
        context=[research_task],
        output_file=output_file,
    )

    return research_task, report_task
