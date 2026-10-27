"""本地 Web 界面：不用记命令，点按钮就能抓取或生成报告。

只用标准库 http.server，不引入 Flask/FastAPI 之类的依赖。
前端通过轮询 /api/job/<id> 拿进度，比 SSE 简单且不易踩连接坑。
"""

from __future__ import annotations

import json
import mimetypes
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import trace as trace_mod

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"

_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()


def _new_job(mode: str) -> dict:
    job = {
        "id": uuid.uuid4().hex[:12],
        "mode": mode,
        "status": "running",
        "started": time.time(),
        "events": [],
        "result": None,
        "error": "",
    }
    with _LOCK:
        # 顺手清掉一小时前的旧任务，避免长时间开着把内存撑大
        cutoff = job["started"] - 3600
        for jid, old in list(_JOBS.items()):
            if old["started"] < cutoff:
                _JOBS.pop(jid, None)
        _JOBS[job["id"]] = job
    return job


def _log(job: dict, message: str, kind: str = "info") -> None:
    with _LOCK:
        job["events"].append(
            {"t": round(time.time() - job["started"], 2), "msg": message, "kind": kind}
        )


def _file_entry(path: Path) -> dict:
    rel = path.relative_to(OUTPUT).as_posix()
    return {"name": path.name, "url": f"/files/{rel}"}


def _run_crawl(job: dict, urls: list[str], workers: int, fmt: str, split: bool) -> None:
    from .crawler import CrawlFailure, Page, crawl_many

    try:
        trace_mod.set_sink(lambda msg, t: _log(job, msg, "crawl"))
        results = crawl_many(urls, total_chars=10**9, workers=workers)

        pages = [r for r in results if isinstance(r, Page)]
        failures = [r for r in results if isinstance(r, CrawlFailure)]

        files: list[dict] = []
        if split:
            target_dir = OUTPUT / "pages"
            target_dir.mkdir(parents=True, exist_ok=True)
            for i, page in enumerate(pages, 1):
                name = f"{i:02d}-{_slug(page.title, 'page')}.{fmt}"
                path = target_dir / name
                path.write_text(_render_page(page, fmt), encoding="utf-8")
                files.append(_file_entry(path))
        else:
            path = OUTPUT / f"pages.{fmt}"
            if fmt == "json":
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
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            else:
                path.write_text(
                    "\n\n".join(_render_page(p, fmt) for p in pages), encoding="utf-8"
                )
            files.append(_file_entry(path))

        job["result"] = {
            "pages": [
                {
                    "title": p.title,
                    "url": p.url,
                    "chars": p.chars,
                    "truncated": p.truncated,
                    "preview": p.text[:400],
                }
                for p in pages
            ],
            "failed": [{"url": f.url, "reason": f.reason} for f in failures],
            "files": files,
            "seconds": round(time.time() - job["started"], 1),
        }
        _log(job, f"完成：{len(pages)} 成功 / {len(failures)} 失败", "done")
    except Exception as exc:
        job["error"] = f"{type(exc).__name__}: {exc}"
        _log(job, f"出错：{job['error']}", "error")
    finally:
        trace_mod.set_sink(None)
        job["status"] = "done"


def _run_crew(job: dict, urls: list[str], structured: bool, workers: int) -> None:
    from .crew_def import build_crew, save_structured
    from .models import Report

    try:
        trace_mod.set_sink(lambda msg, t: _log(job, msg, "crawl"))
        tr = trace_mod.RunTrace(meta={"mode": "prefetch", "structured": structured, "workers": workers})
        trace_mod.set_active(tr)

        model = Report if structured else None
        out = OUTPUT / ("report.json" if structured else "report.md")
        _log(job, "准备模型与任务…", "info")

        crew, inputs = build_crew(
            "\n".join(f"- {u}" for u in urls),
            out,
            prefetch=True,
            structured_model=model,
            workers=workers,
            trace=tr,
            verbose=False,
        )
        _log(job, "进入 Crew：研究员整理 → 撰稿人成稿", "info")
        tr.add("crew_start")
        result = crew.kickoff(inputs=inputs)
        tr.add("crew_end")

        files = [_file_entry(out)]
        entry: dict = {"files": files, "seconds": tr.total, "structured": structured}

        if structured:
            report = save_structured(result, out, Report)
            entry["report"] = {
                "title": report.title,
                "summary": report.summary,
                "key_points": report.key_points,
                "comparison": report.comparison,
                "sections": [
                    {"heading": s.heading, "body": s.body[:600]} for s in report.sections
                ],
                "sources": report.sources,
            }
        else:
            entry["report_text"] = str(getattr(result, "raw", result))

        tr.export(OUTPUT / "run.json")
        from .viz import render_html

        run_html = render_html(tr.to_dict(), OUTPUT / "run.html")
        files.append(_file_entry(run_html))
        entry["timeline"] = _file_entry(run_html)["url"]

        job["result"] = entry
        _log(job, f"Crew 完成，用时 {tr.total:.1f}s", "done")
    except SystemExit as exc:  # 缺 API Key 时 llm.py 会 SystemExit
        job["error"] = str(exc)
        _log(job, f"未配置密钥：{exc}", "error")
    except Exception as exc:
        job["error"] = f"{type(exc).__name__}: {exc}"
        _log(job, f"出错：{job['error']}", "error")
    finally:
        trace_mod.set_sink(None)
        trace_mod.set_active(None)
        job["status"] = "done"


def _slug(text: str, fallback: str) -> str:
    import re

    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text or "").strip("-")
    return (cleaned[:40] or fallback).strip("-")


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
    return f"# {page.title or '(无标题)'}\n\n> 来源：{page.url}\n\n{page.text}\n"


class Handler(BaseHTTPRequestHandler):
    server_version = "CrewCrawlerUI/1.0"

    def log_message(self, fmt: str, *args) -> None:  # 静音默认访问日志
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, code: int, data: dict) -> None:
        self._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path

        if path in ("/", "/index.html"):
            self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return

        if path.startswith("/api/job/"):
            job_id = path.rsplit("/", 1)[-1]
            job = _JOBS.get(job_id)
            if not job:
                self._json(404, {"error": "job not found"})
                return
            with _LOCK:
                payload = {
                    "id": job["id"],
                    "mode": job["mode"],
                    "status": job["status"],
                    "events": list(job["events"]),
                    "result": job["result"],
                    "error": job["error"],
                }
            self._json(200, payload)
            return

        if path.startswith("/files/"):
            rel = unquote(path[len("/files/") :])
            target = (OUTPUT / rel).resolve()
            try:
                target.relative_to(OUTPUT.resolve())
            except ValueError:
                self._json(403, {"error": "forbidden"})
                return
            if not target.is_file():
                self._json(404, {"error": "not found"})
                return
            ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/json",):
                ctype += "; charset=utf-8"
            self._send(200, target.read_bytes(), ctype)
            return

        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/run":
            self._json(404, {"error": "not found"})
            return

        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "invalid json"})
            return

        mode = payload.get("mode", "crawl")
        urls = [u.strip() for u in (payload.get("urls") or []) if u.strip()]
        if not urls:
            self._json(400, {"error": "请至少填一个网址"})
            return

        workers = max(1, min(int(payload.get("workers") or 4), 8))
        job = _new_job(mode)

        if mode == "crew":
            target = _run_crew
            args = (job, urls, bool(payload.get("structured")), workers)
        else:
            fmt = payload.get("format") or "md"
            target = _run_crawl
            args = (job, urls, workers, fmt, bool(payload.get("split")))

        threading.Thread(target=target, args=args, daemon=True).start()
        self._json(200, {"job": job["id"]})


INDEX_HTML = (Path(__file__).resolve().parent / "web_ui.html").read_text(encoding="utf-8")


def serve(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}/"
    print(f"界面已启动：{url}")
    print("按 Ctrl+C 停止")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        httpd.server_close()
