"""无 API Key、无网络的冒烟测试：验证代码结构、工具、Crew/Flow 能正确构建。"""

import os

os.environ.setdefault("DEEPSEEK_API_KEY", "sk-smoke-test-not-real")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

from app.crawler import crawl
from app.crew_def import build_crew
from app.flow_def import ReportFlow
from app.tools import crawl_webpage

print("[1] 爬虫：", end=" ")
page = crawl("samples/sample_article.html", max_chars=300)
print(f"标题={page.title[:20]}... 字符={page.chars} 截断={page.truncated}")
assert page.title and page.chars > 0

print("[2] 工具：", end=" ")
out = crawl_webpage.run("samples/sample_article.html")
assert "标题" in out and "正文开始" in out
print(f"返回 {len(out)} 字符，含标题与正文标记")

print("[3] 工具容错：", end=" ")
bad = crawl_webpage.run("https://this-domain-should-not-exist-xyz.invalid/a")
assert bad.startswith("[抓取失败]")
print("非法地址返回友好错误，未抛异常")

print("[4] Crew 构建：", end=" ")
crew, inputs = build_crew("- https://example.com", "output/_smoke.md")
print(f"agents={len(crew.agents)} tasks={len(crew.tasks)} process={crew.process}")
assert len(crew.agents) == 2 and len(crew.tasks) == 2

print("[5] Task 配置：", end=" ")
t = crew.tasks[1]
print(f"output_file={t.output_file} 依赖上下文={bool(t.context)}")
assert t.context

print("[6] Flow 构建：", end=" ")
flow = ReportFlow()
print(f"state 初始 urls={flow.state.urls!r}")
assert flow.state.urls == ""

print("[7] Flow 控制流离线跑通：", end=" ")
import app.flow_def as fd


class _FakeResult:
    raw = "# 离线报告\n" + "这是一段用于验证路由分支的占位内容。" * 40


class _FakeCrew:
    def kickoff(self, inputs=None):
        return _FakeResult()


fd.build_crew = lambda urls, out=None, **kw: (_FakeCrew(), {"urls": urls})
final_path = fd.run_flow("- https://example.com", "output/_flow_smoke.md")
assert final_path
print("start -> crew -> router -> ok 分支，引擎接线无误")

print("\n全部通过：项目结构可用，缺的只是真实 API Key。")
