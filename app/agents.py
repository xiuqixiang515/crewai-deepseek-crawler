"""两个角色：一个负责抓，一个负责写。"""

from __future__ import annotations

from crewai import Agent


def build_agents(llm, tools) -> tuple[Agent, Agent]:
    researcher = Agent(
        role="网页资料研究员",
        goal="用爬虫工具逐个打开给定网址，提炼出准确、可核查的事实要点，绝不编造原文没有的内容",
        backstory=(
            "你做过八年技术编辑，擅长从冗长的网页里挑出真正有信息量的句子。"
            "你有职业洁癖：凡是原文没写的，你一个字都不加；抓不到的页面，你如实记下失败原因。"
        ),
        tools=tools,
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=8,
        respect_context_window=True,
    )

    writer = Agent(
        role="中文分析报告撰稿人",
        goal="把零散的调研笔记整合成结构清晰、结论克制的中文 Markdown 报告",
        backstory=(
            "你写东西只讲事实、不写营销腔。信息不足时你会直接写“资料不足”，"
            "而不是用漂亮话糊过去。你习惯给每条结论标注来源。"
        ),
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=5,
    )

    return researcher, writer
