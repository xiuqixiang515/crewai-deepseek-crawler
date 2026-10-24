"""无 API Key、无网络的冒烟测试：验证爬虫、并发预取、工具、Crew/Flow 结构。"""

import os

os.environ.setdefault("DEEPSEEK_API_KEY", "sk-smoke-test-not-real")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

from app.crawler import crawl, crawl_many, parse_urls, render_material, summarize
from app.crew_def import build_crew
from app.flow_def import ReportFlow
from app.models import Report
from app.tools import crawl_webpage

SAMPLE = "samples/sample_article.html"

print("[1] 爬虫：", end=" ")
page = crawl(SAMPLE, max_chars=300)
print(f"标题={page.title[:18]}... 字符={page.chars} 截断={page.truncated}")
assert page.title and page.chars > 0

print("[2] 工具封装：", end=" ")
out = crawl_webpage.run(SAMPLE)
assert "标题" in out and "正文开始" in out
print(f"返回 {len(out)} 字符，含标题与正文标记")

print("[3] 工具容错：", end=" ")
bad = crawl_webpage.run("https://this-domain-should-not-exist-xyz.invalid/a")
assert bad.startswith("[抓取失败]")
print("非法地址返回友好错误，未抛异常")

print("[4] 并发抓取：", end=" ")
targets = [SAMPLE, "https://invalid-host-xyz.invalid/a", SAMPLE]
results = crawl_many(targets, total_chars=3000, workers=3)
assert isinstance(results[0], type(page)) and results[1].reason and isinstance(results[2], type(page))
ok, failed = summarize(results)
print(f"{len(targets)} 个目标 -> {ok} 成功 / {failed} 失败，顺序保持一致")

print("[5] 材料渲染：", end=" ")
material = render_material(results)
assert "【来源 1】" in material and "抓取失败" in material
print(f"{len(material)} 字符，成功与失败分别成块")

print("[6] URL 解析：", end=" ")
parsed = parse_urls("- https://a.com/1\n* https://b.com/2\n# 注释\n\nhttps://a.com/1")
assert parsed == ["https://a.com/1", "https://b.com/2"]
print(f"解析并去重 -> {len(parsed)} 条")

print("[7] Crew 构建（工具模式）：", end=" ")
crew_tool, _ = build_crew(f"- {SAMPLE}", "output/_smoke.md", prefetch=False)
assert len(crew_tool.agents) == 2 and len(crew_tool.tasks) == 2
print(f"agents={len(crew_tool.agents)} tasks={len(crew_tool.tasks)}")

print("[8] Crew 构建（预取 + 结构化）：", end=" ")
crew_struct, inputs = build_crew(
    f"- {SAMPLE}", None, prefetch=True, structured_model=Report
)
assert "JSON" in crew_struct.tasks[1].description
assert crew_struct.agents[1].llm is not crew_struct.agents[0].llm
assert inputs["material"].startswith("【来源 1】")
print(f"撰稿人改用 json_object LLM，material {len(inputs['material'])} 字符")

print("[9] Flow 控制流离线跑通：", end=" ")
import app.flow_def as fd


class _FakeResult:
    raw = "# 离线报告\n" + "这是一段用于验证路由分支的占位内容。" * 40


class _FakeCrew:
    def kickoff(self, inputs=None):
        return _FakeResult()


fd.build_crew = lambda urls, out=None, **kw: (_FakeCrew(), {"urls": urls})
final_path = fd.run_flow(f"- {SAMPLE}", "output/_flow_smoke.md")
assert final_path
print("start -> crew -> router -> ok 分支，引擎接线无误")

print("[10] JSON 抽取容错：", end=" ")
from app.crew_def import _extract_json

cases = [
    '{"title": "a"}',
    '```json\n{"title": "b"}\n```',
    '好的，结果如下：\n{"title": "c"}\n以上。',
]
assert [_extract_json(c)["title"] for c in cases] == ["a", "b", "c"]
print("裸 JSON / 代码块 / 带前后文 三种都能解析")

print("\n全部通过：项目结构可用，缺的只是真实 API Key。")
