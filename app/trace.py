"""运行轨迹记录：把抓取和 Agent 的耗时点收集起来，供终端进度与 HTML 可视化使用。

刻意用模块级单例：爬虫可能被 crawl_many 或 CrewAI 工具两条路径调用，
两条路径都要落进同一条时间线，传参会很啰嗦。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

_active: "RunTrace | None" = None
_sink = None


class RunTrace:
    def __init__(self, meta: dict | None = None) -> None:
        self.t0 = time.perf_counter()
        self.events: list[dict] = []
        self.meta = meta or {}

    def add(self, kind: str, **data) -> None:
        event = {"kind": kind, "t": round(time.perf_counter() - self.t0, 3)}
        event.update(data)
        self.events.append(event)

    def task_callback(self, output) -> None:
        """传给 Crew(task_callback=...)，每个 Task 结束时被调用。"""
        raw = getattr(output, "raw", "") or ""
        self.add(
            "task_end",
            name=getattr(output, "name", "") or "",
            agent=getattr(output, "agent", "") or "",
            chars=len(str(raw)),
        )

    @property
    def total(self) -> float:
        return round(time.perf_counter() - self.t0, 3)

    def summary(self) -> dict:
        crawls = self._pair_crawls()
        tasks = [e for e in self.events if e["kind"] == "task_end"]
        llm = [e for e in self.events if e["kind"] == "llm_call"]
        tools = [e for e in self.events if e["kind"] == "tool_call"]
        wall = max((c["end"] for c in crawls), default=0.0) - min(
            (c["start"] for c in crawls), default=0.0
        )
        return {
            "links": len(crawls),
            "ok": sum(1 for c in crawls if c["ok"]),
            "failed": sum(1 for c in crawls if not c["ok"]),
            "chars": sum(c["chars"] for c in crawls),
            "crawl_seconds": round(sum(c["duration"] for c in crawls), 2),
            "crawl_wall": round(max(wall, 0.0), 2),
            "task_seconds": round(tasks[-1]["t"] - self._crew_start(), 2) if tasks else 0.0,
            "total_seconds": self.total,
            "llm_calls": len(llm),
            "tool_calls": len(tools),
            "prompt_tokens": sum(int(e.get("prompt") or 0) for e in llm),
            "completion_tokens": sum(int(e.get("completion") or 0) for e in llm),
            "total_tokens": sum(int(e.get("total") or 0) for e in llm),
            "cached_tokens": sum(int(e.get("cached") or 0) for e in llm),
        }

    def _crew_start(self) -> float:
        for e in self.events:
            if e["kind"] == "crew_start":
                return e["t"]
        return self.events[0]["t"] if self.events else 0.0

    def _pair_crawls(self) -> list[dict]:
        # 用 index 配对而不是 url：同一个链接可能被抓两次，url 做键会互相覆盖
        pending: dict[object, float] = {}
        out: list[dict] = []
        for e in self.events:
            if e["kind"] == "crawl_start":
                pending[e.get("index", e["url"])] = e["t"]
            elif e["kind"] == "crawl_end":
                key = e.get("index", e["url"])
                start = pending.pop(key, e["t"])
                out.append(
                    {
                        "index": e.get("index", len(out) + 1),
                        "url": e["url"],
                        "start": start,
                        "end": e["t"],
                        "duration": e.get("duration", round(e["t"] - start, 3)),
                        "ok": e.get("ok", False),
                        "chars": e.get("chars", 0),
                        "error": e.get("error", ""),
                    }
                )
        out.sort(key=lambda c: c["index"])
        return out

    def to_dict(self) -> dict:
        return {
            "meta": self.meta,
            "total": self.total,
            "summary": self.summary(),
            "events": self.events,
            "crawls": self._pair_crawls(),
            "tasks": [e for e in self.events if e["kind"] == "task_end"],
            "llm_calls": [e for e in self.events if e["kind"] == "llm_call"],
            "tool_calls": [e for e in self.events if e["kind"] == "tool_call"],
            "agents": [e for e in self.events if e["kind"] in ("agent_start", "agent_done")],
            "crew_start": self._crew_start(),
        }

    def export(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return target


def set_active(trace: RunTrace | None) -> None:
    global _active
    _active = trace


def get_active() -> RunTrace | None:
    return _active


def set_sink(fn) -> None:
    """注册一个进度订阅者（如网页端的日志面板）。传 None 取消。"""
    global _sink
    _sink = fn


def progress(message: str) -> None:
    """终端里打一行紧凑进度，形如 [  1.2s] 文本；同时推给订阅者。"""
    trace = get_active()
    elapsed = trace.total if trace else 0.0
    print(f"[{elapsed:>6.1f}s] {message}")
    if _sink is not None:
        try:
            _sink(message, elapsed)
        except Exception:  # 订阅者出错不能影响主流程
            pass
