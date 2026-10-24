"""DeepSeek 模型配置。CrewAI 走 LiteLLM，所以模型名要带 provider 前缀。"""

from __future__ import annotations

import os
from pathlib import Path

from crewai import LLM
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_MODEL = "deepseek/deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com"


def get_llm(temperature: float = 0.3) -> LLM:
    api_key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    if not api_key:
        raise SystemExit(
            "缺少 DEEPSEEK_API_KEY。\n"
            f"请在 {PROJECT_ROOT / '.env'} 里写入：\n"
            "    DEEPSEEK_API_KEY=sk-你的key\n"
            "（可从 https://platform.deepseek.com/api_keys 获取）"
        )

    return LLM(
        model=os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL),
        api_key=api_key,
        base_url=os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL),
        temperature=temperature,
    )
