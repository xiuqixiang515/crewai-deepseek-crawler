# Changelog

本项目的所有重要变更都记录在此文件。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 计划中
- 接入搜索工具（Serper / Bocha / Tavily），让研究员自主发现链接，而非依赖用户提供
- 并发抓取，缩短多链接场景的总耗时
- 报告 Task 改为 `output_pydantic` 结构化输出，便于入库

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
