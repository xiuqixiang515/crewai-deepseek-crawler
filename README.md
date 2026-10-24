# CrewAI + DeepSeek 最小可跑项目

一个能真的跑起来的最小工程：**自研爬虫工具 → 研究员 Agent 抓取提炼 → 撰稿人 Agent 出中文报告**。

刻意做得小：2 个 Agent、2 个 Task、1 个工具、1 个 Flow，全部代码不到 400 行，没有多余抽象。你可以直接在这个骨架上长出真正的业务。

## 项目结构

```
crewai-deepseek-crawler/
├── main.py               # 命令行入口（demo / crew / flow 三个模式）
├── smoke_test.py         # 无 Key、无网络的结构自检
├── app/
│   ├── crawler.py        # 纯 Python 爬虫，不依赖 crewai，可单独测试
│   ├── tools.py          # 把爬虫包装成 CrewAI 工具 crawl_webpage
│   ├── llm.py            # DeepSeek 模型配置
│   ├── agents.py         # 两个角色：研究员 + 撰稿人
│   ├── tasks.py          # 两个任务：抓取笔记 + 成稿
│   ├── crew_def.py       # 组装 Crew
│   └── flow_def.py       # 用 Flow 包一层：入口校验 → Crew → 质量闸门
├── samples/
│   └── sample_article.html   # 离线样例，用来验证爬虫不用联网
├── output/               # 报告落盘位置
├── requirements.txt
└── .env.example
```

## 快速开始

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

### 6. 跑 Flow 版本

```bash
python main.py flow --url https://example.com
```

多出来的价值是**确定性骨架**：入口校验 → Crew 执行 → 按报告长度过质量闸门 → 分流到 `ok` / `too_short` 两个分支。真实项目里把闸门换成关键词校验、LLM 打分或人工审批即可。

> 一次传很多链接时，把它们写进一个 txt（每行一个，`#` 开头是注释），然后 `--urls-file urls.txt`。

## 关键设计说明

**为什么爬虫和工具分成两个文件？**
`crawler.py` 不 import crewai。这样 `demo` 模式在没装 crewai、没有 key、甚至断网的情况下都能跑，调试爬虫不用等 LLM 编排。这是最小项目里最值得保留的一个约束。

**为什么工具函数不抛异常？**
`crawl_webpage` 抓取失败时返回 `[抓取失败] ...` 文本，而不是 raise。Agent 看到失败原因后能自己决定换链接还是跳过；抛异常会直接打断整个 Crew 执行。

**为什么 `expected_output` 写得这么啰嗦？**
CrewAI 里最影响成稿质量的不是模型，是 `Task.description` 和 `expected_output`。把「交付什么格式、不许做什么」写死，比反复调 prompt 有效得多。

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

**想只跑爬虫、不发请求给模型**
`python main.py demo --url ...` 就是纯本地执行，零成本。

## 下一步可以加什么

- **搜索工具**：现在需要你自己给链接。接一个 Serper / Bocha / Tavily，让研究员自己找资料。
- **并发抓取**：`crawler.py` 里用 `concurrent.futures.ThreadPoolExecutor` 一次抓多个。
- **PDF 解析**：给工具加一个分支，遇到 `.pdf` 走 `pypdf`。
- **结构化输出**：把报告 Task 改成 `output_pydantic=ReportModel`，直接拿到 Python 对象入库。
- **人类审批**：在 `flow_def.py` 的 `quality_gate` 里插入 `@human_feedback`，或换回 LangGraph 的 `interrupt()`（CrewAI 的 HITL 更轻，但恢复语义弱一些）。
