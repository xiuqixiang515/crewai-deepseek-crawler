# Changelog

本项目的所有重要变更都记录在此文件。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 计划中
- 接入搜索工具（Serper / Bocha / Tavily），让研究员自主发现链接，而非依赖用户提供
- 预取失败的链接支持指数退避重试
- PDF 与微信公众号文章解析

## [1.1.0] - 2026-10-25

抓取方式与产出形态双双升级：抓取从 Agent 手里挪回代码，报告可选结构化输出。

### 新增
- **并发预取**（`app/crawler.py`）：`crawl_many()` 用 `ThreadPoolExecutor` 并发抓取，
  默认 4 线程；`total_chars` 作为所有链接共享的正文预算按数量均摊，
  单页下限 1500 字符，避免多链接把上下文撑爆。
- **材料渲染**：`render_material()` 把抓取结果拼成带来源编号的文本块，
  `parse_urls()` 支持 `-` / `*` 前缀与去重。
- **结构化输出**（`app/models.py`）：`Report` / `ReportSection` 两级模型，
  `--structured` 时撰稿人改用 `response_format={"type":"json_object"}`，
  由 `save_structured()` 做 Pydantic 校验后写入 `output/report.json`。
- **命令行动作**：`--workers`、`--total-chars`、`--no-prefetch`、`--structured`。

### 变更
- 研究员职责从「逐个调用爬虫工具」改为「基于预取材料提炼要点」；
  工具仍然保留，仅在材料明显截断时用于补抓。
- `build_agents()` 支持为撰稿人注入独立 LLM（结构化模式下的 json_object 实例）。
- `build_tasks()` 新增 `use_material` 与 `structured` 参数；`output_pydantic`
  因 DeepSeek 不支持而不再使用。

### 修复
- `.gitignore` 未忽略 `output/report.json`，导致结构化产物会被误提交。

### 文档
- README 补充并发预取的原理与实测数据（2 链接：20s vs 23s），
  以及 DeepSeek 不支持 json_schema 的说明与绕行方案。

## [1.0.0] - 2026-10-25

首个可用版本：以网页链接为输入，输出中文 Markdown 调研报告。

### 新增
- **爬虫模块**（`app/crawler.py`）：基于 requests + BeautifulSoup 的正文抽取，剔除
  `script/style/nav/footer/aside` 等噪音；优先取 `article` / `main` 容器；自动纠正
  中文站点缺失 charset 导致的乱码；支持本地 HTML 文件，便于离线调试。
- **CrewAI 工具封装**（`app/tools.py`）：`crawl_webpage` 工具，抓取失败时返回结构化
  错误文本而非抛异常，避免中断整个 Crew 执行。
- **DeepSeek 接入**（`app/llm.py`）：通过 LiteLLM 使用 `deepseek/deepseek-chat`，
  支持 `DEEPSEEK_MODEL` / `DEEPSEEK_BASE_URL` 覆盖，可无缝切换到其他 OpenAI 兼容服务。
- **双角色协作**（`app/agents.py`、`app/tasks.py`、`app/crew_def.py`）：研究员负责抓取
  与提炼可核查事实，撰稿人负责按固定结构成稿，产出写入 `output/report.md`。
- **Flow 编排**（`app/flow_def.py`）：入口校验 → Crew 执行 → 按报告长度过质量闸门，
  分流到 `ok` / `too_short` 两个分支。
- **命令行入口**（`main.py`）：`demo`（纯爬虫自检，零成本）、`crew`（完整 Crew）、
  `flow`（Flow 包裹版）三个子命令，支持 `--url` / `--urls-file` / `--out` / `--temp`。
- **零成本自检**（`smoke_test.py`）：7 项检查覆盖爬虫解析、工具容错、Crew 构建、
  Flow 控制流，无需 API Key 即可验证工程结构。

### 修复
- **Windows 下 `LOCALAPPDATA` 缺失导致导入失败**（`app/__init__.py`）：在 Git Bash / MSYS
  环境中该变量未被导出，`crewai_core.token_manager` 拼路径时会拿到 `None` 并抛
  `TypeError`。包初始化时补默认值指向 `~/AppData/Local`。
- **Windows 控制台 GBK 编码导致中途崩溃**：统一将 stdout/stderr 重配置为 UTF-8，
  兼容 CrewAI 输出中的 emoji 与制表符号。

### 文档
- 补充国内镜像安装方式、`uv` 加速方案，以及 `chroma-hnswlib` 编译失败的排错说明。
