"""把一次运行的轨迹渲染成自包含的 HTML 可视化报告。

不依赖任何 CDN 或前端框架，单文件双击即可打开。
"""

from __future__ import annotations

import html
import json
from pathlib import Path


_MODE_LABEL = {"prefetch": "并发预取", "tools": "Agent 调工具", "demo": "仅抓取（demo）"}


def _label(url: str) -> str:
    """优先用路径末段做标签 —— 同一站点的多篇文章，光看域名区分不出来。"""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        tail = (parsed.path or "").rstrip("/").split("/")[-1]
        if tail and len(tail) >= 4:
            return tail[:22]
        return (parsed.netloc or url).replace("www.", "")[:22]
    except Exception:
        return url[:22]


def _ticks(total: float) -> tuple[float, list[float]]:
    for step in (0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300):
        if total / step <= 7:
            values = []
            t = 0.0
            while t <= total + 1e-9:
                values.append(round(t, 3))
                t += step
            return step, values
    return 300, [0.0]


def _timeline_svg(data: dict) -> str:
    total = max(float(data.get("total", 0)) or 0.1, 0.1)
    crawls = data.get("crawls", [])
    tasks = data.get("tasks", [])
    crew_start = float(data.get("crew_start", 0))

    x0, x1 = 158, 884
    scale = (x1 - x0) / total

    rows: list[str] = []
    y = 34

    def bar(y: int, start: float, end: float, color: str, label: str, note: str) -> None:
        bx = x0 + start * scale
        bw = max(3.0, (end - start) * scale)
        tip = f"{start:.1f}s → {end:.1f}s｜{note}"
        rows.append(
            f'<text x="{x0 - 10}" y="{y + 13}" text-anchor="end" class="rlabel">{html.escape(label)}</text>'
        )
        rows.append(
            f'<rect x="{bx:.1f}" y="{y + 2}" width="{bw:.1f}" height="18" rx="4" '
            f'fill="{color}" opacity="0.9"><title>{html.escape(tip)}</title></rect>'
        )
        # 标注默认放条形右侧；若会超出画布，就挪到条形内部右端（白字）
        estimated = len(note) * 6.4
        if bx + bw + 6 + estimated > 896:
            rows.append(
                f'<text x="{bx + bw - 6:.1f}" y="{y + 13}" text-anchor="end" '
                f'class="rnote inbar">{html.escape(note)}</text>'
            )
        else:
            rows.append(
                f'<text x="{bx + bw + 6:.1f}" y="{y + 13}" class="rnote">{html.escape(note)}</text>'
            )

    for c in crawls:
        bar(
            y,
            c["start"],
            c["end"],
            "#185FA5" if c.get("ok") else "#A32D2D",
            f"#{c.get('index', 0)} {_label(c['url'])}",
            f"{c['duration']:.1f}s",
        )
        y += 30

    if crawls and tasks:
        y += 10

    prev = crew_start
    for t in tasks:
        end = float(t["t"])
        name = (t.get("agent") or t.get("name") or "task")[:6]
        bar(y, prev, end, "#534AB7", name, f"{end - prev:.1f}s")
        prev = end
        y += 30

    height = y + 42

    step, values = _ticks(total)
    grid = []
    for v in values:
        gx = x0 + v * scale
        grid.append(
            f'<path d="M{gx:.1f} 24 L{gx:.1f} {height - 28}" stroke="#E5E3DC" stroke-width="0.5" stroke-dasharray="3 3" fill="none"/>'
        )
        grid.append(
            f'<text x="{gx:.1f}" y="{height - 12}" text-anchor="middle" class="axis">{v:g}s</text>'
        )

    legend = (
        f'<g><rect x="{x0}" y="6" width="10" height="10" rx="2" fill="#185FA5"/>'
        f'<text x="{x0 + 15}" y="15" class="axis">抓取成功</text></g>'
        f'<g><rect x="{x0 + 82}" y="6" width="10" height="10" rx="2" fill="#A32D2D"/>'
        f'<text x="{x0 + 97}" y="15" class="axis">抓取失败</text></g>'
        f'<g><rect x="{x0 + 164}" y="6" width="10" height="10" rx="2" fill="#534AB7"/>'
        f'<text x="{x0 + 179}" y="15" class="axis">Agent 阶段</text></g>'
        f'<text x="{x1}" y="15" text-anchor="end" class="axis">横轴：从启动起算的秒数</text>'
    )

    return (
        f'<svg viewBox="0 0 900 {height}" width="100%" role="img" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f"<title>一次运行的时间线</title>"
        f"{legend}{''.join(grid)}{''.join(rows)}</svg>"
    )


def _cards(summary: dict) -> str:
    items = [
        ("链接数", f"{summary.get('links', 0)}", "并发抓取的目标数量"),
        (
            "成功 / 失败",
            f"{summary.get('ok', 0)} / {summary.get('failed', 0)}",
            "失败不会中断流程",
        ),
        ("提取正文", f"{summary.get('chars', 0):,}", "字符数，已剔除噪音"),
        ("总耗时", f"{summary.get('total_seconds', 0):.1f}s", "含抓取与模型调用"),
    ]
    return "".join(
        f'<div class="card"><div class="k">{k}</div><div class="v">{v}</div>'
        f'<div class="d">{d}</div></div>'
        for k, v, d in items
    )


def _pipeline(summary: dict, meta: dict) -> str:
    mode = _MODE_LABEL.get(meta.get("mode", ""), "并发预取")
    parallel = meta.get("mode") in ("prefetch", "demo")
    crawl_value = (
        f"{summary.get('crawl_wall', 0):.1f}s"
        if parallel
        else f"累计 {summary.get('crawl_seconds', 0):.1f}s"
    )
    boxes = [
        ("输入链接", f"{summary.get('links', 0)} 个"),
        ("并发抓取" if parallel else "逐条抓取", crawl_value),
        ("研究员", "提炼要点"),
        ("撰稿人", "结构化" if meta.get("structured") else "Markdown"),
        ("产物", "report"),
    ]
    parts = []
    for i, (title, sub) in enumerate(boxes):
        parts.append(
            f'<div class="node"><div class="nt">{title}</div><div class="ns">{sub}</div></div>'
        )
        if i < len(boxes) - 1:
            parts.append('<div class="arrow">→</div>')
    head = f'<div class="pipehead">抓取方式：{mode}</div>'
    return head + '<div class="pipe">' + "".join(parts) + "</div>"


def _rows(data: dict) -> str:
    out = []
    for i, c in enumerate(data.get("crawls", []), 1):
        status = (
            '<span class="chip ok">成功</span>'
            if c.get("ok")
            else '<span class="chip bad">失败</span>'
        )
        note = html.escape(c.get("error", "") or "—")
        url = html.escape(c["url"])
        out.append(
            f"<tr><td>{c.get('index', i)}</td><td class='url'>{url}</td><td>{status}</td>"
            f"<td class='num'>{c['duration']:.2f}s</td>"
            f"<td class='num'>{c.get('chars', 0):,}</td><td class='note'>{note}</td></tr>"
        )
    if not out:
        out.append("<tr><td colspan='6' class='note'>本次没有抓取记录</td></tr>")
    return "".join(out)


_CSS = """
*{box-sizing:border-box}
body{margin:0;background:#F4F2EC;color:#2C2C2A;
 font-family:system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;line-height:1.6}
.wrap{max-width:980px;margin:0 auto;padding:36px 24px 56px}
h1{font-size:22px;font-weight:600;margin:0 0 6px}
h2{font-size:14px;font-weight:600;margin:0 0 14px;color:#2C2C2A}
.sub{color:#5F5E5A;font-size:13px;margin-bottom:18px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:24px}
.chip{font-size:12px;padding:3px 10px;border-radius:999px;background:#fff;
 border:1px solid #E5E3DC;color:#5F5E5A}
.chip.ok{background:#EAF3DE;border-color:#C0DD97;color:#3B6D11}
.chip.bad{background:#FCEBEB;border-color:#F7C1C1;color:#A32D2D}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:22px}
.card{background:#fff;border:1px solid #E5E3DC;border-radius:12px;padding:14px 16px}
.card .k{font-size:12px;color:#888780}
.card .v{font-size:24px;font-weight:600;margin:2px 0 2px}
.card .d{font-size:11px;color:#B4B2A9}
.panel{background:#fff;border:1px solid #E5E3DC;border-radius:12px;
 padding:18px 20px;margin-bottom:18px}
.rlabel{font-size:11px;fill:#5F5E5A}
.rnote{font-size:11px;fill:#888780}
.rnote.inbar{fill:#FFFFFF}
.axis{font-size:10px;fill:#B4B2A9}
.pipehead{font-size:12px;color:#888780;margin-bottom:10px}
.pipe{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.node{flex:1;min-width:96px;background:#F7F6F1;border:1px solid #E5E3DC;
 border-radius:8px;padding:8px 10px;text-align:center}
.node .nt{font-size:12px;font-weight:600}
.node .ns{font-size:11px;color:#888780}
.arrow{color:#B4B2A9;font-size:14px}
table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:left;font-weight:500;color:#888780;font-size:11px;
 padding:6px 8px;border-bottom:1px solid #E5E3DC}
td{padding:8px;border-bottom:1px solid #F1EFE8;vertical-align:top}
td.url{max-width:320px;word-break:break-all;color:#185FA5}
td.num{text-align:right;font-variant-numeric:tabular-nums}
td.note{color:#888780;max-width:200px}
"""

_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>运行可视化 · crewai-deepseek-crawler</title>
<style>__CSS__</style>
</head>
<body>
<div class="wrap">
  <h1>一次运行的全过程</h1>
  <div class="sub">上半部分是按秒排列的时间线，能直观看出哪些抓取是并行的；下半部分是链路与逐条明细。</div>
  <div class="chips">__CHIPS__</div>
  <section class="cards">__CARDS__</section>
  <section class="panel">
    <h2>时间线</h2>
    __SVG__
  </section>
  <section class="panel">
    <h2>处理链路</h2>
    __PIPE__
  </section>
  <section class="panel">
    <h2>抓取明细</h2>
    <table>
      <thead><tr><th>#</th><th>地址</th><th>状态</th><th>耗时</th><th>字符</th><th>备注</th></tr></thead>
      <tbody>__ROWS__</tbody>
    </table>
  </section>
</div>
</body>
</html>
"""


def render_html(data: dict, out_path: str | Path) -> Path:
    meta = data.get("meta", {})
    summary = data.get("summary", {})

    chips = [("抓取方式", _MODE_LABEL.get(meta.get("mode", ""), "并发预取"))]
    if meta.get("mode") != "demo":
        chips.append(("输出形态", "结构化 JSON" if meta.get("structured") else "Markdown"))
    chips.append(("并发线程", str(meta.get("workers") or "—")))
    if meta.get("mode") != "demo":
        chips.append(("正文预算", f"{meta.get('total_chars', 0):,} 字符"))
    chip_html = "".join(
        f'<span class="chip">{html.escape(k)}：{html.escape(v)}</span>' for k, v in chips
    )

    page = (
        _TEMPLATE.replace("__CSS__", _CSS)
        .replace("__CHIPS__", chip_html)
        .replace("__CARDS__", _cards(summary))
        .replace("__SVG__", _timeline_svg(data))
        .replace("__PIPE__", _pipeline(summary, meta))
        .replace("__ROWS__", _rows(data))
    )

    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page, encoding="utf-8")
    return target


def render_from_json(json_path: str | Path, out_path: str | Path) -> Path:
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    return render_html(data, out_path)
