# CLI 层 (Typer Command Line Interface)

> `ss` 统一命令行接口，基于 Typer + Rich 构建，懒加载架构

---

## 文件清单

| 文件 | 职责 | 关键类/函数 |
|------|------|------------|
| `cli/__init__.py` | 包标记（故意不导入 app，避免 runpy 警告） | — |
| `cli/main.py` | 根 Typer app + 全局选项 + 子命令注册 | `app`, `cli_state`, `run()` |
| `cli/run.py` | `ss run` 子命令组（pipeline/short/stage/polish/batch/revise/style/multi-polish） | — |
| `cli/jobs.py` | `ss jobs` 子命令组（list/show/cancel/retry/tasks） | — |
| `cli/short.py` | `ss short` 子命令组（generate/trends/genres） | — |
| `cli/short_core.py` | 短篇流水线异步 API（plan→write→deai） | `run_short_task()`, `run_short_batch()` |
| `cli/pipeline_core.py` | 长篇流水线异步 API（summaries→polish_outline→write_chapters→deai→export） | `run_pipeline()` |
| `cli/novels.py` | `ss list` 子命令组（series/novels/chapters） | `_resolve_novel()` |
| `cli/export.py` | `ss export` 子命令组（final/covers） | — |
| `cli/config_cmd.py` | `ss config` 子命令组（get/set/show/path） | — |
| `cli/agents.py` | `ss agents` 子命令组（list/inspect） | `_load_agent_configs()` |
| `cli/status.py` | `ss status` — 项目状态 | — |
| `cli/repl.py` | `ss repl` — 交互式 REPL | — |
| `cli/health.py` | `ss health` — 系统诊断 | — |
| `cli/show.py` | `ss show` 子命令组（outline/world/characters/chapter/cost/quality/research） | — |
| `cli/bench.py` | `ss bench` — LLM 性能基准测试 | — |
| `cli/_common.py` | 共享工具（Console、表格渲染、统一访问器） | `load_cfg()`, `get_runner()`, `build_orch()` |

---

## 核心设计

### 命令树

```
ss
├── run                         运行生成管线
│   ├── pipeline <task>         长篇系列管线
│   ├── short <task>            短篇管线
│   ├── stage <phase>           单 phase 执行
│   ├── polish <chapter>        单章去AI化
│   ├── batch                   批次并行写作
│   ├── revise <chapter>        重写章节
│   ├── style                   风格润色（LoRA）
│   └── multi-polish            多模型润色对比
├── submit <brief>              提交后台 Job
├── status                      系统/项目状态
├── jobs                        管理后台 Job
│   ├── list / show / cancel / retry
│   └── tasks (run / run-all / resume)
├── list                        列出内容
│   ├── novels / series / chapters
├── export                      导出成品
│   ├── final / covers
├── config                      配置管理
│   ├── get / set / show / path
├── agents                      智能体团队
│   ├── list / inspect
├── show                        知识库查看
│   ├── outline / world / characters / chapter / cost / quality / research
├── health                      系统诊断
├── bench                       LLM 性能基准
└── repl                        交互式 REPL
```

### 全局选项

| 选项 | 说明 |
|------|------|
| `-v, --verbose` | 详细输出（`-v` INFO, `-vv` DEBUG, `-vvv` 全量） |
| `--config <path>` | 指定 settings.yaml 路径（默认 config/settings.yaml） |
| `-n, --no-interaction` | 非交互模式（CI 友好，不弹确认） |

### 懒加载架构

`cli/main.py` 的 `app` 在注册子命令时只 import 模块本身，不 import orchestrator（93KB）。重模块在命令函数体内部导入，使 `ss --help` 秒级响应。

### 共享访问器 (`cli/_common.py`)

统一替代各子命令重复的初始化逻辑：

| 函数 | 说明 |
|------|------|
| `load_cfg(create_dirs=True)` | 加载配置，尊重 `--config` 全局选项 |
| `get_runner()` | 获取 JobRunner 单例（base_dir="jobs"） |
| `create_llm_client(cfg)` | 工厂函数构造 LLMClient（消除 7+ 处重复构造） |
| `build_orch()` | cfg + LLMClient + StoryOrchestrator 一站式 |
| `resolve_novel_kd(novel)` | 解析小说路径到 knowledge_dir |
| `build_knowledge_store(novel)` | 构建只读 KnowledgeStore |

### 输出格式

- **table**（默认）：Rich 格式化表格/面板/树，带颜色和图标
- **json**：`--format json` 输出纯 JSON，供脚本/CI 消费

### 流水线阶段 (`cli/pipeline_core.py`)

长篇管线 5 阶段，支持 checkpoint resume：

```
STAGE_ORDER = ["summaries", "polish_outline", "write_chapters", "deai", "export"]
```

| 阶段 | 说明 |
|------|------|
| `summaries` | 逐章摘要生成 |
| `polish_outline` | 4 顾问 agent → Showrunner 综合打磨大纲 |
| `write_chapters` | 批次并行写作，单章失败回退串行重试 |
| `deai` | 规则清洗 + LLM 润色（3 次重试 + 429 退避） |
| `export` | 合并润色/原始章节为 final.md/txt |

`TaskProgress` 类管理 `.task_progress.json` checkpoint，原子写入。

### 短篇管线 (`cli/short_core.py`)

```
STAGE_ORDER = ["plan", "write", "deai"]
```

支持从 JSON 重建 `StoryPlan` / `StoryResult` 数据类以恢复中断的流水线。

---

## 设计决策

1. **懒加载**：`ss --help` 不触发 orchestrator import，秒级响应
2. **`pretty_exceptions_show_locals=False`**：防止 traceback 泄露 API key
3. **`cli_state` 用 dict 而非 dataclass**：避免循环导入
4. **config_cmd 模块名避开 config 冲突**：`cli/config_cmd.py` 而非 `cli/config.py`
5. **只读命令 `create_dirs=False`**：`ss config show` / `ss agents list` 不创建目录
6. **脱敏**：`config show` / `config get llm_api_key` 自动脱敏，拒绝 `config set` 写入敏感字段

---

## 依赖关系

```
cli/main.py ──▶ cli/run.py, cli/jobs.py, cli/novels.py, cli/export.py,
                 cli/config_cmd.py, cli/agents.py, cli/status.py,
                 cli/repl.py, cli/health.py, cli/show.py, cli/bench.py,
                 cli/short.py

cli/run.py ──▶ cli/pipeline_core.py, cli/short_core.py, cli/_common.py
cli/jobs.py ──▶ cli/_common.py, jobs.py, planner.py
cli/repl.py ──▶ main.py (main_interactive), orchestrator.py
cli/_common.py ──▶ config/, jobs.py, orchestrator.py, agents/
```

---

*模块文档版本：v2.0.0 · 对应代码版本：v2.0.0*
