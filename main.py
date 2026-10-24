"""命令行入口。

用法:
    python main.py demo                      # 不需要 API Key，只测爬虫（默认抓本地样例）
    python main.py demo --url https://...    # 抓真实网页，验证网络与解析
    python main.py crew --url https://a --url https://b
    python main.py flow --url https://a --url https://b
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Windows 控制台默认 GBK，CrewAI 会打印大量符号，先强制 UTF-8 免得中途崩
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "samples" / "sample_article.html"
DEFAULT_OUT = ROOT / "output" / "report.md"


def _collect_urls(args) -> list[str]:
    urls: list[str] = list(args.url or [])
    if getattr(args, "urls_file", None):
        content = Path(args.urls_file).read_text(encoding="utf-8")
        urls += [ln.strip() for ln in content.splitlines() if ln.strip() and not ln.startswith("#")]
    return urls


def _to_input(urls: list[str]) -> str:
    return "\n".join(f"- {u}" for u in urls)


def cmd_demo(args) -> int:
    from app.crawler import crawl

    targets = args.url or [str(SAMPLE)]
    for target in targets:
        print("=" * 68)
        print(f"抓取: {target}")
        try:
            page = crawl(target, max_chars=args.max_chars)
        except Exception as exc:
            print(f"[失败] {type(exc).__name__}: {exc}")
            continue

        flag = " (已截断)" if page.truncated else ""
        print(f"标题: {page.title or '(无标题)'}")
        print(f"来源: {page.url}")
        print(f"正文: {page.chars} 字符{flag}")
        print("-" * 68)
        print(page.text[: args.preview])
        if len(page.text) > args.preview:
            print("...")
    print("=" * 68)
    print("爬虫自检完成。下一步：填好 .env 后运行 python main.py crew --url <链接>")
    return 0


def cmd_crew(args) -> int:
    from app.crew_def import build_crew

    urls = _collect_urls(args)
    if not urls:
        print("[错误] 至少给一个 --url，或用 --urls-file 指定列表文件")
        return 2

    out = Path(args.out) if args.out else DEFAULT_OUT
    crew, inputs = build_crew(_to_input(urls), out, temperature=args.temp)

    print(f"模型: {args.model_hint}")
    print(f"目标链接 {len(urls)} 个，报告将写入 {out}\n")
    result = crew.kickoff(inputs=inputs)

    print("\n" + "=" * 68)
    print(getattr(result, "raw", str(result)))
    print("=" * 68)
    print(f"报告文件: {out}")
    return 0


def cmd_flow(args) -> int:
    from app.flow_def import run_flow

    urls = _collect_urls(args)
    if not urls:
        print("[错误] 至少给一个 --url，或用 --urls-file 指定列表文件")
        return 2

    out = Path(args.out) if args.out else DEFAULT_OUT
    final_path = run_flow(_to_input(urls), out)

    print("\n" + "=" * 68)
    print(f"Flow 执行完毕，报告文件: {final_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crewai-deepseek-crawler",
        description="CrewAI + DeepSeek 最小项目：爬网页 -> 出中文报告",
    )
    sub = parser.add_subparsers(dest="cmd")

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--url", action="append", help="要处理的网址，可重复多次")
        p.add_argument("--urls-file", help="网址列表文件，每行一个，# 开头为注释")
        p.add_argument("--out", help="报告输出路径，默认 output/report.md")

    p_demo = sub.add_parser("demo", help="只测爬虫，不需要 API Key")
    p_demo.add_argument("--url", action="append", help="要抓的网址，默认用本地样例")
    p_demo.add_argument("--max-chars", type=int, default=8000, help="正文字符上限")
    p_demo.add_argument("--preview", type=int, default=800, help="终端预览字符数")
    p_demo.set_defaults(func=cmd_demo)

    p_crew = sub.add_parser("crew", help="跑完整 Crew（需要 DEEPSEEK_API_KEY）")
    add_common(p_crew)
    p_crew.add_argument("--temp", type=float, default=0.3, help="采样温度，默认 0.3")
    p_crew.set_defaults(func=cmd_crew, model_hint="deepseek/deepseek-chat（可用 DEEPSEEK_MODEL 覆盖）")

    p_flow = sub.add_parser("flow", help="跑 Flow 包裹的 Crew（需要 DEEPSEEK_API_KEY）")
    add_common(p_flow)
    p_flow.set_defaults(func=cmd_flow)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "cmd", None):
        # 不带参数时给一个零成本的自检
        args = parser.parse_args(["demo"])

    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
