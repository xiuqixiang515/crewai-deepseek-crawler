"""结构化输出模型。

刻意做得浅：报告本质是长文本，字段一多、嵌套一深，
模型漏字段和 JSON 截断的概率会明显上升。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReportSection(BaseModel):
    heading: str = Field(description="小节标题，通常用来源页面的标题")
    url: str = Field(default="", description="该小节对应的来源链接，没有则留空")
    body: str = Field(description="该小节正文，可以用 Markdown 段落")


class Report(BaseModel):
    """一份调研报告的结构化形态，可直接入库。"""

    title: str = Field(description="报告标题")
    summary: str = Field(description="一句话摘要，不超过 80 字")
    key_points: list[str] = Field(description="3 到 5 条核心要点，每条不超过 60 字")
    sections: list[ReportSection] = Field(description="按来源分组的详解小节")
    comparison: str = Field(
        description="跨来源的对比或差异；信息不足时写「资料不足」，不要编造"
    )
    sources: list[str] = Field(description="实际用到的来源链接；抓取失败的单独标注")
