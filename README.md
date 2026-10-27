# CrewAI + DeepSeek 最小可跑项目

一个能真的跑起来的最小工程：**自研爬虫工具 → 研究员 Agent 抓取提炼 → 撰稿人 Agent 出中文报告**。

刻意做得小：2 个 Agent、2 个 Task、1 个工具、1 个 Flow，全部代码不到 400 行，没有多余抽象。你可以直接在这个骨架上长出真正的业务。

## 项目结构

```
crewai-deepseek-crawler/
├── main.py               # 命令行入口（demo / crew / flow 三个模式）
├── smoke_test.py         # 无 Key、无网络的结构自检
├── app/
│   ├── crawler.py        # 纯 Python 爬虫 + 并发抓取，不依赖 crewai，可单独测试
│   ├── tools.py          # 把爬虫包装成 CrewAI 工具 crawl_webpage
│   ├── llm.py            # DeepSeek 模型配置（含 json_object 模式）
│   ├── models.py         # 结构化输出用的 Pydantic 模型
│   ├── agents.py         # 两个角色：研究员 + 撰稿人
│   ├── tasks.py          # 两个任务：整理材料 + 成稿
│   ├── crew_def.py       # 组装 Crew，并在这里做并发预取
│   ├── trace.py          # 运行轨迹记录：抓取与 Agent 的耗时点
│   ├── observer.py       # 订阅 CrewAI 事件总线，采集 LLM/工具/Agent 步骤
│   ├── viz.py            # 把轨迹渲染成自包含 HTML 时间线
│   ├── web.py            # 本地网页界面的服务端（标准库 http.server）
│   ├── web_ui.html       # 界面本身（单文件，无框架）
│   └── flow_def.py       # 用 Flow 包一层：入口校验 → Crew → 质量闸门
├── samples/
│   └── sample_article.html   # 离线样例，用来验证爬虫不用联网
├── output/               # 报告落盘位置
├── requirements.txt
└── .env.example
```

## 快速开始

> **不想敲命令？** 跑 `python main.py web`，浏览器会打开一个界面：贴网址、点按钮，进度和结果都在里面看。

### 1. 装依赖

```bash
cd crewai-deepseek-crawler
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
```

> **国内网络建议加镜像**，否则 crewai 的依赖树（含 chromadb、onnxruntime，约 700MB）会慢到怀疑人生：
>
> ```bash
> pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
> ```
>
> 如果 `pip` 卡在解析阶段很久不动，换成 `uv` 会快一个数量级：
>
> ```bash
> pip install uv -i https://pypi.tuna.tsinghua.edu.cn/simple
> python -m uv pip install --python .venv/Scripts/python.exe -r requirements.txt --index-url https://pypi.tuna.tsinghua.edu.cn/simple
> ```

### 2. 结构自检（0 成本，不需要 Key）

```bash
python smoke_test.py
```

预期输出 6 行 `[1]`~`[6]`，覆盖爬虫解析、工具容错、Crew 构建、Flow 构建。**先跑通这一步，再花钱调模型。**

### 3. 验证爬虫（不需要 API Key，不花钱）

```bash
python main.py demo
```

默认抓本地的 `samples/sample_article.html`。你应该看到标题、字符数、正文预览，并且**导航栏、相关阅读、页脚都被剔掉了** —— 这说明正文抽取逻辑是对的。

想验真实网络：

```bash
python main.py demo --url https://example.com
```

### 4. 配 DeepSeek

去 <https://platform.deepseek.com/api_keys> 拿 key，然后：

```bash
# Windows
copy .env.example .env
# macOS / Linux
cp .env.example .env
```

编辑 `.env`：

```ini
DEEPSEEK_API_KEY=sk-你的key
```

### 5. 跑完整 Crew

```bash
python main.py crew --url https://example.com --url https://another-page.com
```

报告会写到 `output/report.md`，同时在终端打印。想换路径用 `--out`，想调温度用 `--temp`。

默认走**并发预取**：所有链接先在本地用线程池抓完（默认 4 并发），再把正文一次性交给 Agent，Agent 不再逐个调用工具。

```bash
# 关掉预取，退回「Agent 自己调工具」的老路子，用来做对比
python main.py crew --no-prefetch --url https://a.com --url https://b.com

# 调并发数与正文总预算（所有链接共享，按数量均摊）
python main.py crew --workers 6 --total-chars 20000 --url https://a.com
```

### 6. 结构化输出（可入库）

```bash
python main.py crew --structured --url https://example.com
```

产出 `output/report.json`，字段固定为 `title / summary / key_points / sections / comparison / sources`（见 `app/models.py`），已经过 Pydantic 校验，可以直接 `db.insert(obj.model_dump())`。

> ⚠️ **DeepSeek 不支持 CrewAI 的 `output_pydantic`**。它只接受 `response_format={"type":"json_object"}`，不接受 OpenAI 那种带 JSON Schema 的结构化输出，直接开 `output_pydantic` 会报
> `This response_format type is unavailable now`。
> 所以本项目改成：撰稿人用 json_object 模式输出 JSON，再由 `save_structured()` 用 Pydantic 校验并落盘。

### 7. 跑 Flow 版本

```bash
python main.py flow --url https://example.com
```

多出来的价值是**确定性骨架**：入口校验 → Crew 执行 → 按报告长度过质量闸门 → 分流到 `ok` / `too_short` 两个分支。真实项目里把闸门换成关键词校验、LLM 打分或人工审批即可。

> 一次传很多链接时，把它们写进一个 txt（每行一个，`#` 开头是注释），然后 `--urls-file urls.txt`。

## 网页界面（不用命令行）

```bash
python main.py web
```

默认在 <http://127.0.0.1:8765/> 启动并自动打开浏览器。不引入 Flask/FastAPI——用的是标准库 `http.server`，所以没有任何新依赖。

界面上能做的事：

| 区域 | 内容 |
|---|---|
| 模式切换 | **只抓正文**（免费）/ **生成报告**（走 DeepSeek） |
| 输入 | 一行一个网址，支持多行粘贴 |
| 选项 | 并发线程、输出格式（md/txt/json）、每页单独存、结构化 JSON |
| 过程面板 | 带时间戳的实时进度、成功/失败/耗时统计 |
| 结果面板 | 抓取结果卡片（标题、链接、字符数、正文预览）+ 文件下载；报告模式额外内嵌时间线 |

命令行参数：

```bash
python main.py web --port 9000      # 换端口
python main.py web --no-open        # 不自动开浏览器
python main.py web --host 0.0.0.0   # 允许局域网访问（谨慎，默认只监听本机）
```

几个实现上的取舍：

- **轮询而非 SSE**：前端每 400ms 拉一次 `/api/job/<id>`。SSE 更"实时"，但长连接在反代/休眠场景下坑更多，本地工具用轮询足够。
- **只监听 127.0.0.1**：这个服务能用你的 API Key 花钱、能抓任意 URL，不要随手 `--host 0.0.0.0` 暴露到公网。
- **文件服务做了目录穿越防护**：`/files/` 只允许读 `output/` 下的文件。
- **任务记录 1 小时后自动清理**，长期开着不会攒内存。

## 只爬内容（零成本，不调用模型）

如果你只想把网页正文抓下来存着——不做摘要、不要报告——用 `crawl` 子命令。它完全不碰 LLM，不花钱，也不需要 API Key。

```bash
# 存成一个 Markdown 文件
python main.py crawl --url https://example.com/a --url https://example.com/b

# 每个网页一个文件，方便丢进别的工具
python main.py crawl --split --out output/pages \
  --url https://example.com/a --url https://example.com/b

# 输出 JSON 数组，适合程序消费
python main.py crawl --format json --out output/pages.json --url https://example.com/a

# 不限长度（默认就是 0 = 不截断）
python main.py crawl --max-chars 0 --url https://example.com/a

# 从文件批量读链接
python main.py crawl --urls-file urls.txt --split --out output/pages
```

参数速查：

| 参数 | 说明 |
|---|---|
| `--url` | 可重复，或改用 `--urls-file` |
| `--out` | 默认 `output/pages.md`；`--split` 时当作目录 |
| `--format` | `md`（默认）/ `txt` / `json` |
| `--split` | 每页一个文件，文件名 `01-标题.md` |
| `--max-chars` | 每页字符上限，`0` 表示不截断（默认） |
| `--workers` | 并发线程数，默认 4 |

跑完会打印成功/失败清单，并额外生成 `output/crawl_timeline.html` 时间线。

> 说明：输出的是**按 DOM 文本节点逐行排列的正文**，不是排版还原。所以会看到「作者：」和「阮一峰」各占一行——这是正常的，保留原始断行对下游 LLM 处理更友好。要阅读体验更好的版本，得换 Readability 之类的正文抽取算法。

## 可视化

分两层，都不引入新依赖。

**① 终端实时进度** —— 每条抓取带时间戳，能直接看出并发有没有生效：

```
[   0.0s] [1/2] 请求 https://www.ruanyifeng.com/blog/2024/01/...
[   0.0s] [2/2] 请求 https://www.ruanyifeng.com/blog/2024/03/...
[   1.1s] [1/2] 完成 6000 字符 / 1.1s
[   1.8s] [2/2] 完成 5073 字符 / 1.8s
[prefetch] 2 个链接并发抓取完成：2 成功 / 0 失败，用时 1.8s（正文合计 11073 字符）
```

**② HTML 时间线** —— `crew` 跑完自动生成 `output/run.html`，同时落一份 `output/run.json`：

- **时间线**：每个网址一条横条，起点都对齐在 0 秒。串行模式下条形会首尾相接，并发模式下会重叠 —— 这是最直观的对照。
- **链路图**：输入 → 抓取 → 研究员 → 撰稿人 → 产物，每段带上耗时。
- **明细表**：状态、耗时、字符数、失败原因。
- 单文件、无 CDN，双击就能看，也可以直接发给别人。

**零成本试看**（不需要 API Key）：

```bash
python main.py demo \
  --url https://www.ruanyifeng.com/blog/2024/01/weekly-issue-285.html \
  --url https://www.ruanyifeng.com/blog/2024/03/weekly-issue-293.html \
  --url https://example.com
# 生成 output/demo_timeline.html
```

**改样式后重新出图**（不用重跑，省 token）：

```bash
python main.py viz --input output/run.json --out output/run.html
```

## 过程观察（Agent 每一步在干什么）

除了"抓了多久、出了什么"，还能看到 Agent 内部的三类动作：**Agent 开始/结束、每次 LLM 调用（含 token）、每次工具调用**。

```
[   5.3s] Agent 开始：网页资料研究员
[  14.5s] LLM #1 · 3,514 in / 1,562 out · 9.2s
[  14.6s] Agent 完成：网页资料研究员，输出 2,641 字符
[  14.6s] Agent 开始：中文分析报告撰稿人
[  21.4s] LLM #2 · 1,925 in / 1,309 out · 6.8s
[  21.4s] Agent 完成：中文分析报告撰稿人，输出 2,253 字符
```

同一份数据会出现在三处：

| 位置 | 形式 |
|---|---|
| 终端 | 上面这种逐行日志 |
| 网页界面 | 「过程明细」列表 + Token 统计卡片 |
| `output/run.html` | 「LLM 调用明细」表格（输入/输出/缓存/耗时）+ 顶部 Token 卡片 |

**实现原理**：订阅 CrewAI 的事件总线，而不是靠解析控制台输出。

```python
from crewai.events import crewai_event_bus
from crewai.events.types.llm_events import LLMCallCompletedEvent

@crewai_event_bus.on(LLMCallCompletedEvent)
def on_llm_done(source, event):
    usage = event.usage or {}      # {"prompt_tokens": 3514, "completion_tokens": 1562, ...}
    ...
```

监听的事件共 6 个：`LLMCallStarted/Completed`、`ToolUsageStarted/Finished`、`AgentExecutionStarted/Completed`。
观察器放在 `app/observer.py`，只在需要时 import——这样 `crawler.py` 依然不依赖 crewai。

> 注意：`cached_tokens` 取的是 provider 返回的缓存命中数。DeepSeek 自己的字段叫 `prompt_cache_hit_tokens`，
> 经 LiteLLM 转换后可能拿不到，显示为 `—` 是正常的，不影响费用估算（按输入/输出 token 算即可）。

## 关键设计说明

**为什么爬虫和工具分成两个文件？**
`crawler.py` 不 import crewai。这样 `demo` 模式在没装 crewai、没有 key、甚至断网的情况下都能跑，调试爬虫不用等 LLM 编排。这是最小项目里最值得保留的一个约束。

**为什么抓取要前置到代码里？**
爬虫是确定性的，不该让模型来调度。串行调用时，每个网址都要多一次完整 LLM 往返（把系统提示、任务、历史工具结果重发一遍），链接越多越亏。预取把这部分挪出 Agent，往返次数固定为 2 次。

实测（2 个链接、同一台机器）：并发预取 20s，逐个调工具 23s。**差距没有想象中大**，因为 LLM 延迟占了大头；真正的收益在链接数变多、或目标站点响应慢的时候才明显 —— 串行时每次下载都要等，并行时只等最慢那一个。

**为什么工具函数不抛异常？**
`crawl_webpage` 抓取失败时返回 `[抓取失败] ...` 文本，而不是 raise。Agent 看到失败原因后能自己决定换链接还是跳过；抛异常会直接打断整个 Crew 执行。

**为什么 `expected_output` 写得这么啰嗦？**
CrewAI 里最影响成稿质量的不是模型，是 `Task.description` 和 `expected_output`。把「交付什么格式、不许做什么」写死，比反复调 prompt 有效得多。

**为什么预取的正文可以安全地塞进任务描述？**
CrewAI 的 `interpolate_only` 是「先扫描模板里的 `{变量}`，再 `str.replace`」，插入的值不会被二次解析。所以正文里出现花括号（代码片段里很常见）也不会炸。前提是模板里只写 `{material}`，不要让正文自己当模板。

**为什么轨迹用模块级单例？**
爬虫有两条调用路径：并发预取走 `crawl_many`，退回工具模式走 `crawl_webpage`。两条都要落进同一条时间线，把 trace 一路当参数传会污染所有函数签名。`trace.set_active()` 在 `build_crew` 里设置一次即可。

**为什么时间线的行序不等于完成顺序？**
抓取是并发的，谁先完成谁先结束。轨迹里给每个任务带了 `index`，配对时按 index 排序，保证图和表的编号与输入顺序一致 —— 否则读者会对不上号。

**为什么不用 `memory=True`？**
CrewAI 的短期记忆默认要调 embedding 接口，会额外产生费用和失败点。这个项目的任务是一次性的，不需要记忆。要开的话记得配 embedding 模型。

## 换成别的模型

改 `.env` 里两个变量就行，代码不用动（CrewAI 底层走 LiteLLM）：

```ini
# 通义千问（OpenAI 兼容模式）
DEEPSEEK_MODEL=openai/qwen-plus
DEEPSEEK_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# 本地 Ollama
DEEPSEEK_MODEL=ollama/qwen2.5:14b
DEEPSEEK_BASE_URL=http://localhost:11434
```

注意：变量名叫 `DEEPSEEK_*` 只是历史原因，它实际就是「主模型配置」。换 provider 时 `DEEPSEEK_API_KEY` 要填对应服务商的 key（Ollama 随便填一个非空值即可）。

## 常见问题

**`ModuleNotFoundError: No module named 'crewai'`**
没激活虚拟环境。Windows 下 `.venv\Scripts\activate`，或直接用 `.venv\Scripts\python.exe main.py ...`。

**Windows 安装 crewai 报 `chroma-hnswlib` 编译错误（找不到 `float.h`）**
装 Visual Studio Build Tools，勾选「Desktop development with C++」。

**`TypeError: argument should be a str or an os.PathLike ... not 'NoneType'`（在 `crewai_core/token_manager.py`）**
这是 Git Bash / MSYS 下 `LOCALAPPDATA` 没被导出的典型症状，CrewAI 拿它拼凭证目录时会撞上 `None`。
`app/__init__.py` 里已经做了兜底（自动指向 `~/AppData/Local`），正常不需要处理。
如果在别的脚本里直接 `from crewai import ...`，请先 `export LOCALAPPDATA="$USERPROFILE/AppData/Local"`。

**终端中文乱码或报 `UnicodeEncodeError`**
`main.py` 开头已经把 stdout 强制成 UTF-8 了。如果还有问题，先执行 `chcp 65001`。

**报告内容空泛 / 大量编造**
先看研究员那一步的工具返回。如果多数链接返回 `[抓取失败]`，Agent 只能靠猜。常见原因是目标站点需要登录、正文由 JS 渲染，或者被反爬拦截。

**`--structured` 报 `This response_format type is unavailable now`**
这是 DeepSeek 不支持 OpenAI 的 json_schema 结构化输出。本项目已绕过（走 json_object + 本地校验），如果你自己写了 `output_pydantic` 就会撞上，删掉即可。

**`--structured` 报「JSON 能解析但不符合 Report 结构」**
模型偶尔会漏 `key_points` 或把 `sections` 写成字符串。直接重跑一次通常就好；反复失败的话，把 `app/tasks.py` 里 `_STRUCTURED_BRIEF` 的字段说明再写具体一点。

**想只跑爬虫、不发请求给模型**
`python main.py demo --url ...` 就是纯本地执行，零成本。

## 下一步可以加什么

- **搜索工具**：现在需要你自己给链接。接一个 Serper / Bocha / Tavily，让研究员自己找资料。
- **PDF / 公众号解析**：给爬虫加分支，遇到 `.pdf` 走 `pypdf`，遇到微信链接走专用解析。
- **失败重试**：预取失败的链接，在 `crawl_many` 里做一次指数退避重试。
- **入库**：`--structured` 已经产出 `Report` 对象，接 SQLite / Postgres 只需在 `save_structured` 后面加一行。
- **人类审批**：在 `flow_def.py` 的 `quality_gate` 里插入 `@human_feedback`，或换回 LangGraph 的 `interrupt()`（CrewAI 的 HITL 更轻，但恢复语义弱一些）。

