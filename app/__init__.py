"""CrewAI + DeepSeek 最小可跑项目。"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _ensure_windows_env() -> None:
    """在 Git Bash / MSYS 等环境下，LOCALAPPDATA 可能没有被导出。

    crewai_core.token_manager 在 win32 下直接用 os.environ["LOCALAPPDATA"]
    拼凭证目录，取不到 None 就会在 import 阶段抛 TypeError。
    这里在包初始化时补一个默认值，保证在任何终端里都能跑。
    """
    if sys.platform != "win32" or os.environ.get("LOCALAPPDATA"):
        return
    fallback = Path(os.environ.get("USERPROFILE") or Path.home()) / "AppData" / "Local"
    try:
        fallback.mkdir(parents=True, exist_ok=True)
        os.environ["LOCALAPPDATA"] = str(fallback)
    except OSError:
        pass


def _ensure_utf8_stdout() -> None:
    """Windows 控制台默认 GBK，CrewAI 会打印大量符号和 emoji，先强制 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:
            pass


_ensure_windows_env()
_ensure_utf8_stdout()

__all__ = ["crawler"]
