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


def get_llm(temperature: float = 0.3, json_mode: bool = False) -> LLM:
    """构造 DeepSeek LLM。

    json_mode=True 时启用 response_format={"type": "json_object"}。
    注意：DeepSeek 只支持 json_object，不支持 OpenAI 那种 json_schema /
    response_model 结构化输出（会报 "This response_format type is unavailable"），
    所以结构化报告走「模型出 JSON + 本地 Pydantic 校验」，而不是 CrewAI 的
    output_pydantic。
    """
    api_key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    if not api_key:
        raise SystemExit(
            "缺少 DEEPSEEK_API_KEY。\n"
            f"请在 {PROJECT_ROOT / '.env'} 里写入：\n"
            "    DEEPSEEK_API_KEY=sk-你的key\n"
            "（可从 https://platform.deepseek.com/api_keys 获取）"
        )

    kwargs: dict = {
        "model": os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL),
        "api_key": api_key,
        "base_url": os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL),
        "temperature": temperature,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    return LLM(**kwargs)
