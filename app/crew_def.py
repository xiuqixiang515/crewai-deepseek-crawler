"""把 agents + tasks 组装成一个 Crew；抓取在此处并发预取。"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from crewai import Crew, Process
from pydantic import ValidationError

from . import trace as trace_mod
from .agents import build_agents
from .crawler import (
    DEFAULT_TOTAL_CHARS,
    DEFAULT_WORKERS,
    crawl_many,
    parse_urls,
    render_material,
    summarize,
)
from .llm import get_llm
from .tasks import build_tasks
from .tools import crawl_webpage

DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "output" / "report.md"
DEFAULT_JSON = Path(__file__).resolve().parent.parent / "output" / "report.json"


def build_crew(
    urls: str,
    output_file: str | Path | None = None,
    temperature: float = 0.3,
    prefetch: bool = True,
    structured_model: type | None = None,
    workers: int = DEFAULT_WORKERS,
    total_chars: int = DEFAULT_TOTAL_CHARS,
    trace: trace_mod.RunTrace | None = None,
    verbose: bool = True,
) -> tuple[Crew, dict]:
    """返回 (crew, inputs)。

    prefetch=True 时先并发抓完所有链接，把正文作为 material 注入任务，
    Agent 不再逐个调用工具，LLM 往返从 N 次降到 2 次。
    structured_model 传入 Pydantic 模型时，撰稿人改用 json_object 模式输出。
    trace 用于收集时间线，供终端进度与 HTML 可视化使用。
    """
    tr = trace or trace_mod.RunTrace()
    trace_mod.set_active(tr)
    tr.meta.update(
        {
            "mode": "prefetch" if prefetch else "tools",
            "structured": structured_model is not None,
            "workers": workers,
            "total_chars": total_chars,
        }
    )

    structured = structured_model is not None
    out_path = Path(output_file) if output_file else (DEFAULT_JSON if structured else DEFAULT_OUTPUT)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    material = ""
    if prefetch:
        targets = parse_urls(urls)
        started = time.perf_counter()
        results = crawl_many(targets, total_chars=total_chars, workers=workers)
        elapsed = time.perf_counter() - started
        ok, failed = summarize(results)
        material = render_material(results)
        trace_mod.progress(
            f"并发抓取完成：{ok} 成功 / {failed} 失败，用时 {elapsed:.1f}s"
            f"（正文合计 {len(material)} 字符）"
        )

    llm = get_llm(temperature=temperature)
    writer_llm = get_llm(temperature=temperature, json_mode=True) if structured else None
    researcher, writer = build_agents(llm, [crawl_webpage], writer_llm=writer_llm)

    research_task, report_task = build_tasks(
        researcher,
        writer,
        None if structured else str(out_path),
        use_material=prefetch,
        structured=structured,
    )

    crew = Crew(
        agents=[researcher, writer],
        tasks=[research_task, report_task],
        process=Process.sequential,
        verbose=verbose,
        memory=False,
        task_callback=tr.task_callback,
    )
    return crew, {"urls": urls, "material": material}


def run_crew(crew: Crew, inputs: dict, trace: trace_mod.RunTrace | None = None):
    """跑 Crew，期间挂上事件观察器，把每一步写进轨迹。"""
    from .observer import CrewObserver

    tr = trace or trace_mod.get_active()
    observer = CrewObserver()
    observer.attach()
    try:
        if tr:
            tr.add("crew_start")
        result = crew.kickoff(inputs=inputs)
        if tr:
            tr.add("crew_end")
        return result
    finally:
        observer.detach()


def _extract_json(text: str) -> dict:
    """从模型输出里抠出 JSON，兼容 ```json 包裹和前后多余文字。"""
    raw = (text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end > start:
            return json.loads(raw[start : end + 1])
        raise


def save_structured(result, path: str | Path | None, model: type):
    """把 Crew 输出的 JSON 校验成模型对象并落盘。"""
    raw = getattr(result, "raw", str(result))
    try:
        data = _extract_json(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"模型没有返回合法 JSON：{exc}\n原始输出前 300 字：{raw[:300]}") from exc

    try:
        obj = model.model_validate(data)
    except ValidationError as exc:
        raise RuntimeError(
            f"JSON 能解析但不符合 {model.__name__} 结构：\n{exc}\n"
            "可以直接重跑一次；若反复失败，把 app/tasks.py 里的字段说明再写具体些。"
        ) from exc

    target = Path(path) if path else DEFAULT_JSON
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(obj.model_dump_json(indent=2), encoding="utf-8")
    return obj
