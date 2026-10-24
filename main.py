"""命令行入口。

用法:
    python main.py demo                      # 不需要 API Key，只测爬虫（默认抓本地样例）
    python main.py demo --url https://...    # 抓真实网页，验证网络与解析
    python main.py crawl --url https://a --url https://b    # 只抓正文存档，零成本
    python main.py crew --url https://a --url https://b
    python main.py crew --url https://a --structured        # 输出结构化 JSON
    python main.py flow --url https://a --url https://b
"""

from __future__ import annotations

import argparse
import json
import re
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
DEFAULT_JSON = ROOT / "output" / "report.json"


def _collect_urls(args) -> list[str]:
    urls: list[str] = list(args.url or [])
    if getattr(args, "urls_file", None):
        content = Path(args.urls_file).read_text(encoding="utf-8")
        urls += [ln.strip() for ln in content.splitlines() if ln.strip() and not ln.startswith("#")]
    return urls


def _to_input(urls: list[str]) -> str:
    return "\n".join(f"- {u}" for u in urls)


def _slug(text: str, fallback: str) -> str:
    """给文件名用的安全 slug，只保留字母数字与中文。"""
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text or "").strip("-")
    return (cleaned[:40] or fallback).strip("-")


def cmd_crawl(args) -> int:
    """只抓正文并存档，不调用任何模型，零成本。"""
    from app.crawler import CrawlFailure, Page, crawl_many, parse_urls

    urls = _collect_urls(args)
    if not urls:
        print("[错误] 至少给一个 --url，或用 --urls-file 指定列表文件")
        return 2
    urls = parse_urls("\n".join(urls))

    # max_chars=0 表示不截断；否则所有链接共享预算
    if args.max_chars > 0:
        total_chars = args.max_chars * len(urls)
    else:
        total_chars = 10**9

    from app.trace import RunTrace, set_active

    tr = RunTrace(meta={"mode": "demo", "workers": args.workers})
    set_active(tr)
    results = crawl_many(urls, total_chars=total_chars, workers=args.workers)

    pages = [r for r in results if isinstance(r, Page)]
    failures = [r for r in results if isinstance(r, CrawlFailure)]

    out = Path(args.out)
    if args.split:
        out.mkdir(parents=True, exist_ok=True)
        saved: list[tuple[Page, Path]] = []
        for i, page in enumerate(pages, 1):
            name = f"{i:02d}-{_slug(page.title, 'page')}.{args.format}"
            target = out / name
            target.write_text(_render_page(page, args.format), encoding="utf-8")
            saved.append((page, target))
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        if args.format == "json":
            payload = [
                {
                    "title": p.title,
                    "url": p.url,
                    "chars": p.chars,
                    "truncated": p.truncated,
                    "text": p.text,
                }
                for p in pages
            ]
            out.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        else:
            out.write_text(
                "\n\n".join(_render_page(p, args.format) for p in pages), encoding="utf-8"
            )
        saved = [(p, out) for p in pages]

    print("\n" + "=" * 68)
    for i, page in enumerate(pages, 1):
        flag = " 已截断" if page.truncated else ""
        print(f"  [{i}] {page.chars:>6} 字符{flag}  {page.title[:40] or '(无标题)'}")
    for i, fail in enumerate(failures, 1):
        print(f"  [失败{i}] {fail.url}\n          {fail.reason[:70]}")
    print("=" * 68)
    print(f"成功 {len(pages)} / 失败 {len(failures)}，总耗时 {tr.total:.1f}s")
    print(f"已保存: {out}{'（每页一个文件）' if args.split else ''}")

    if pages and tr.total > 0:
        try:
            from app.viz import render_html

            page = render_html(tr.to_dict(), ROOT / "output" / "crawl_timeline.html")
            print(f"时间线: {page}")
        except Exception:
            pass

    set_active(None)
    return 0


def _render_page(page, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(
            {
                "title": page.title,
                "url": page.url,
                "chars": page.chars,
                "truncated": page.truncated,
                "text": page.text,
            },
            ensure_ascii=False,
            indent=2,
        )
    if fmt == "txt":
        return f"{page.title}\n{page.url}\n\n{page.text}\n"
    # md（默认）
    return f"# {page.title or '(无标题)'}\n\n> 来源：{page.url}\n\n{page.text}\n"


def cmd_demo(args) -> int:
    from app.crawler import CrawlFailure, Page, crawl_many, crawl_safe
    from app.trace import RunTrace, set_active
    from app.viz import render_html

    targets = args.url or [str(SAMPLE)]
    tr = RunTrace(meta={"mode": "demo", "structured": False, "workers": args.workers})
    set_active(tr)

    if len(targets) > 1:
        results = crawl_many(
            targets,
            total_chars=max(3000, args.max_chars * len(targets)),
            workers=args.workers,
        )
    else:
        results = [crawl_safe(targets[0], args.max_chars)]

    for target, result in zip(targets, results):
        print("=" * 68)
        print(f"抓取: {target}")
        if isinstance(result, CrawlFailure):
            print(f"[失败] {result.reason}")
            continue
        assert isinstance(result, Page)
        flag = " (已截断)" if result.truncated else ""
        print(f"标题: {result.title or '(无标题)'}")
        print(f"来源: {result.url}")
        print(f"正文: {result.chars} 字符{flag}")
        print("-" * 68)
        print(result.text[: args.preview])
        if len(result.text) > args.preview:
            print("...")

    print("=" * 68)
    ok = sum(1 for r in results if isinstance(r, Page))
    print(f"抓取 {len(results)} 个目标：{ok} 成功 / {len(results) - ok} 失败，总耗时 {tr.total:.1f}s")

    if len(targets) > 1:
        page = render_html(tr.to_dict(), ROOT / "output" / "demo_timeline.html")
        print(f"时间线可视化: {page}（用浏览器打开）")

    set_active(None)
    print("下一步：填好 .env 后运行 python main.py crew --url <链接>")
    return 0


def cmd_crew(args) -> int:
    from app.crew_def import build_crew, save_structured
    from app.models import Report
    from app.trace import RunTrace, set_active
    from app.viz import render_html

    urls = _collect_urls(args)
    if not urls:
        print("[错误] 至少给一个 --url，或用 --urls-file 指定列表文件")
        return 2

    structured_model = Report if args.structured else None

    default_out = DEFAULT_JSON if args.structured else DEFAULT_OUT
    out = Path(args.out) if args.out else default_out

    tr = RunTrace(meta={"structured": bool(args.structured), "output": str(out)})
    crew, inputs = build_crew(
        _to_input(urls),
        out,
        temperature=args.temp,
        prefetch=not args.no_prefetch,
        structured_model=structured_model,
        workers=args.workers,
        total_chars=args.total_chars,
        trace=tr,
    )

    mode = "结构化 JSON" if args.structured else "Markdown"
    print("模型: deepseek/deepseek-chat（DEEPSEEK_MODEL 可覆盖）")
    print(f"抓取方式: {'并发预取' if not args.no_prefetch else 'Agent 逐个调用工具'}")
    print(f"输出形态: {mode} | 目标链接 {len(urls)} 个 | 写入 {out}\n")

    tr.add("crew_start")
    result = crew.kickoff(inputs=inputs)
    tr.add("crew_end")

    print("\n" + "=" * 68)
    if args.structured:
        report = save_structured(result, out, Report)
        print(f"标题: {report.title}")
        print(f"摘要: {report.summary}")
        print(f"要点: {len(report.key_points)} 条 | 小节: {len(report.sections)} 段 | 来源: {len(report.sources)} 个")
        print(f"对比: {report.comparison[:120]}")
    else:
        print(getattr(result, "raw", str(result)))
    print("=" * 68)
    print(f"输出文件: {out}")

    if not args.no_viz:
        tr.export(ROOT / "output" / "run.json")
        page = render_html(tr.to_dict(), ROOT / "output" / "run.html")
        summary = tr.summary()
        print(
            f"时间线: {page}\n"
            f"       总耗时 {summary['total_seconds']:.1f}s"
            f"（抓取 {summary['crawl_seconds']:.1f}s / Agent {summary['task_seconds']:.1f}s）"
        )

    set_active(None)
    return 0


def cmd_viz(args) -> int:
    from app.viz import render_from_json

    page = render_from_json(args.input, args.out)
    print(f"已渲染: {page}")
    return 0


def cmd_flow(args) -> int:
    from app.flow_def import run_flow

    urls = _collect_urls(args)
    if not urls:
        print("[错误] 至少给一个 --url，或用 --urls-file 指定列表文件")
        return 2

    out = Path(args.out) if args.out else DEFAULT_OUT
    final_path = run_flow(_to_input(urls), out, prefetch=not args.no_prefetch)

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
        p.add_argument("--out", help="输出路径，默认 output/report.md（结构化模式为 report.json）")
        p.add_argument("--workers", type=int, default=4, help="并发抓取的线程数，默认 4")
        p.add_argument("--total-chars", type=int, default=12000, help="所有链接共享的正文总预算，默认 12000")
        p.add_argument("--no-prefetch", action="store_true", help="关闭并发预取，退回 Agent 逐个调用工具")

    p_demo = sub.add_parser("demo", help="只测爬虫，不需要 API Key")
    p_demo.add_argument("--url", action="append", help="要抓的网址，默认用本地样例；多个时并发抓取并生成时间线")
    p_demo.add_argument("--max-chars", type=int, default=8000, help="正文字符上限")
    p_demo.add_argument("--preview", type=int, default=800, help="终端预览字符数")
    p_demo.add_argument("--workers", type=int, default=4, help="并发线程数，默认 4")
    p_demo.set_defaults(func=cmd_demo)

    p_crawl = sub.add_parser("crawl", help="只抓正文存档，不调用模型（零成本）")
    p_crawl.add_argument("--url", action="append", help="要抓的网址，可重复多次")
    p_crawl.add_argument("--urls-file", help="网址列表文件，每行一个，# 开头为注释")
    p_crawl.add_argument("--out", default=str(ROOT / "output" / "pages.md"), help="保存路径；--split 时视为目录")
    p_crawl.add_argument("--format", choices=["md", "txt", "json"], default="md", help="保存格式，默认 md")
    p_crawl.add_argument("--split", action="store_true", help="每个网页保存为独立文件")
    p_crawl.add_argument("--max-chars", type=int, default=0, help="每页字符上限，0 表示不截断")
    p_crawl.add_argument("--workers", type=int, default=4, help="并发线程数，默认 4")
    p_crawl.set_defaults(func=cmd_crawl)

    p_crew = sub.add_parser("crew", help="跑完整 Crew（需要 DEEPSEEK_API_KEY）")
    add_common(p_crew)
    p_crew.add_argument("--temp", type=float, default=0.3, help="采样温度，默认 0.3")
    p_crew.add_argument("--structured", action="store_true", help="改用 Pydantic 结构化输出，写入 JSON")
    p_crew.add_argument("--no-viz", action="store_true", help="不生成 run.html 时间线")
    p_crew.set_defaults(func=cmd_crew)

    p_flow = sub.add_parser("flow", help="跑 Flow 包裹的 Crew（需要 DEEPSEEK_API_KEY）")
    add_common(p_flow)
    p_flow.set_defaults(func=cmd_flow)

    p_viz = sub.add_parser("viz", help="从 run.json 重新渲染时间线 HTML")
    p_viz.add_argument("--input", default=str(ROOT / "output" / "run.json"), help="轨迹 JSON 路径")
    p_viz.add_argument("--out", default=str(ROOT / "output" / "run.html"), help="HTML 输出路径")
    p_viz.set_defaults(func=cmd_viz)

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
