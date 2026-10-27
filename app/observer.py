"""订阅 CrewAI 事件总线，把 Agent 每一步都记进轨迹。

放在独立模块，是为了让 crawler/trace 那条链路继续保持「不 import crewai」的约束。
"""

from __future__ import annotations

import time

from crewai.events import crewai_event_bus
from crewai.events.types.agent_events import (
    AgentExecutionCompletedEvent,
    AgentExecutionStartedEvent,
)
from crewai.events.types.llm_events import LLMCallCompletedEvent, LLMCallStartedEvent
from crewai.events.types.tool_usage_events import (
    ToolUsageFinishedEvent,
    ToolUsageStartedEvent,
)

from . import trace as trace_mod


class CrewObserver:
    """把事件流翻译成人类可读的进度行 + 结构化轨迹。"""

    def __init__(self) -> None:
        self._bound: list[tuple[type, object]] = []
        self._llm_stack: list[float] = []
        self._tool_stack: list[tuple[str, float]] = []
        self._seq = 0

    # ---------- 注册 ----------
    def attach(self) -> None:
        pairs = [
            (LLMCallStartedEvent, self._on_llm_start),
            (LLMCallCompletedEvent, self._on_llm_done),
            (ToolUsageStartedEvent, self._on_tool_start),
            (ToolUsageFinishedEvent, self._on_tool_done),
            (AgentExecutionStartedEvent, self._on_agent_start),
            (AgentExecutionCompletedEvent, self._on_agent_done),
        ]
        for event_type, handler in pairs:
            try:
                crewai_event_bus.on(event_type)(handler)
                self._bound.append((event_type, handler))
            except Exception:  # 某个事件类型不存在时不影响其它监听
                continue

    def detach(self) -> None:
        for event_type, handler in self._bound:
            try:
                crewai_event_bus.off(event_type, handler)
            except Exception:
                continue
        self._bound.clear()
        self._llm_stack.clear()
        self._tool_stack.clear()

    # ---------- 内部工具 ----------
    def _record(self, kind: str, **data) -> None:
        tr = trace_mod.get_active()
        if tr:
            tr.add(kind, **data)

    def _say(self, message: str) -> None:
        trace_mod.progress(message)

    # ---------- 处理器 ----------
    def _on_llm_start(self, source, event) -> None:
        try:
            self._llm_stack.append(time.perf_counter())
        except Exception:
            pass

    def _on_llm_done(self, source, event) -> None:
        try:
            now = time.perf_counter()
            started = self._llm_stack.pop() if self._llm_stack else now
            duration = now - started
            usage = getattr(event, "usage", None) or {}
            prompt = int(usage.get("prompt_tokens") or 0)
            completion = int(usage.get("completion_tokens") or 0)
            total = int(usage.get("total_tokens") or prompt + completion)
            cached = int(
                usage.get("prompt_cache_hit_tokens")
                or (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
                or 0
            )
            self._seq += 1

            # 起止都换算成「相对本次运行开始」的秒数，便于时间线绘制
            tr = trace_mod.get_active()
            start_rel = round(started - tr.t0, 3) if tr else 0.0

            self._record(
                "llm_call",
                seq=self._seq,
                start=start_rel,
                duration=round(duration, 3),
                prompt=prompt,
                completion=completion,
                total=total,
                cached=cached,
            )
            cache_note = f"（命中缓存 {cached}）" if cached else ""
            self._say(
                f"LLM #{self._seq} · {prompt:,} in / {completion:,} out"
                f"{cache_note} · {duration:.1f}s"
            )
        except Exception:
            pass

    def _on_tool_start(self, source, event) -> None:
        try:
            name = getattr(event, "tool_name", "tool")
            self._tool_stack.append((name, time.perf_counter()))
            self._say(f"调用工具 {name}…")
        except Exception:
            pass

    def _on_tool_done(self, source, event) -> None:
        try:
            now = time.perf_counter()
            if self._tool_stack:
                name, started = self._tool_stack.pop()
            else:
                name, started = getattr(event, "tool_name", "tool"), now
            duration = now - started
            failed = getattr(event, "failure", None) is not None
            self._record("tool_call", name=name, duration=round(duration, 3), failed=failed)
            self._say(f"工具 {name} 完成 · {duration:.1f}s" + (" · 返回失败" if failed else ""))
        except Exception:
            pass

    def _on_agent_start(self, source, event) -> None:
        try:
            role = getattr(getattr(event, "agent", None), "role", "") or "Agent"
            self._record("agent_start", role=role)
            self._say(f"Agent 开始：{role}")
        except Exception:
            pass

    def _on_agent_done(self, source, event) -> None:
        try:
            role = getattr(getattr(event, "agent", None), "role", "") or "Agent"
            output = getattr(event, "output", "") or ""
            self._record("agent_done", role=role, chars=len(str(output)))
            self._say(f"Agent 完成：{role}，输出 {len(str(output)):,} 字符")
        except Exception:
            pass
