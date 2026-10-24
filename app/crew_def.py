"""把 agents + tasks 组装成一个 Crew。"""

from __future__ import annotations

from pathlib import Path

from crewai import Crew, Process

from .agents import build_agents
from .llm import get_llm
from .tasks import build_tasks
from .tools import crawl_webpage

DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "output" / "report.md"


def build_crew(urls: str, output_file: str | Path | None = None, temperature: float = 0.3) -> tuple[Crew, dict]:
    """返回 (crew, inputs)。urls 是多行字符串，每行一个链接。"""
    out_path = Path(output_file) if output_file else DEFAULT_OUTPUT
    out_path.parent.mkdir(parents=True, exist_ok=True)

    llm = get_llm(temperature=temperature)
    researcher, writer = build_agents(llm, [crawl_webpage])
    research_task, report_task = build_tasks(researcher, writer, str(out_path))

    crew = Crew(
        agents=[researcher, writer],
        tasks=[research_task, report_task],
        process=Process.sequential,
        verbose=True,
        memory=False,
    )
    return crew, {"urls": urls}
