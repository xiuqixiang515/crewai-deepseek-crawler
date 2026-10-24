"""用 Flow 给 Crew 套一层确定性骨架：入口校验 -> 跑 Crew -> 质量闸门分流。"""

from __future__ import annotations

from pathlib import Path

from crewai.flow.flow import Flow, listen, router, start
from pydantic import BaseModel

from .crew_def import build_crew


class ReportState(BaseModel):
    urls: str = ""
    output_file: str = ""
    report_chars: int = 0
    prefetch: bool = True


class ReportFlow(Flow[ReportState]):
    @start()
    def prepare(self) -> str:
        urls = (self.state.urls or "").strip()
        if not urls:
            raise ValueError("urls 为空：至少给一个网址（--url）")

        if not self.state.output_file:
            self.state.output_file = str(
                Path(__file__).resolve().parent.parent / "output" / "report.md"
            )
        Path(self.state.output_file).parent.mkdir(parents=True, exist_ok=True)

        print(f"[flow] 待抓取网址数: {len(urls.splitlines())}")
        print(f"[flow] 报告输出路径: {self.state.output_file}")
        return urls

    @listen(prepare)
    def run_crew(self, urls: str) -> str:
        print("[flow] 进入 Crew：研究员抓取 -> 撰稿人成稿")
        crew, inputs = build_crew(urls, self.state.output_file, prefetch=self.state.prefetch)
        result = crew.kickoff(inputs=inputs)
        text = getattr(result, "raw", str(result))
        self.state.report_chars = len(text or "")
        print(f"[flow] Crew 完成，正文 {self.state.report_chars} 字符")
        return text

    @router(run_crew)
    def quality_gate(self) -> str:
        # 这里只看长度做演示；真实项目可以换成关键词校验、LLM 打分或人工审批
        return "ok" if self.state.report_chars >= 400 else "too_short"

    @listen("ok")
    def on_ok(self) -> str:
        print(f"[flow] 通过质量闸门，报告已写入: {self.state.output_file}")
        return self.state.output_file

    @listen("too_short")
    def on_too_short(self) -> str:
        print(
            "[flow] 报告偏短（<400 字符），可能多数链接抓取失败。\n"
            f"       仍已写入: {self.state.output_file}，请人工确认。"
        )
        return self.state.output_file


def run_flow(urls: str, output_file: str | Path | None = None, prefetch: bool = True) -> str:
    flow = ReportFlow()
    flow.kickoff(
        inputs={
            "urls": urls,
            "output_file": str(output_file) if output_file else "",
            "prefetch": prefetch,
        }
    )
    return flow.state.output_file
