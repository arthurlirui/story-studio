# 基础设施 (Infrastructure)

> 配置系统、封面生成工具、模板、技能包、系列工程、日常批量管线、测试套件

---

## 文件清单

### 配置系统 (`config/`)

已在 [API 层文档](api.md) 详细说明。核心：`StudioConfig` 数据类 + `load_config()` 加载器 + `config/io.py` 共享读写层。

### 封面生成工具 (`tools/`)

| 文件 | 职责 | 关键类/函数 |
|------|------|------------|
| `tools/book_cover_comfy.py` | ComfyUI 封面生成主程序 | `CoverBrief`, `safe_filename()`, `extract_title_from_text()` |
| `tools/llm_utils.py` | 共享异步 LLM 调用 helper | `call_llm()` |
| `tools/bench_llm_perf.py` | LLM 性能基准（TTFT/TPS/并发） | `run_for_model()` |
| `tools/scripts/` | 一次性运维脚本（修复章节/生成/润色） | — |
| `tools/test_short_story.py` | 短篇封面/LLM 路径测试 | — |

**封面生成流程**：novel/brief → LLM 生成视觉 prompt → ComfyUI workflow（FLUX.2 Klein + BookCover LoRA）→ Pillow 中文文字叠加 → PNG。标题/作者不放入 diffusion prompt，用 `BookCoverTextOverlay` 节点渲染真实文字。

### 封面模板 (`templates/`)

| 文件 | 说明 |
|------|------|
| `cover_brief_template.json` | 封面 brief JSON schema（标题/副标题/作者/类型/情绪/核心视觉/构图/调色板/positive_prompt/尺寸/字体布局） |
| `cover_designer_prompt.md` | Cover Designer agent 提示词模板（`{{title}}`/`{{author}}`/`{{story_context}}` 占位符） |
| `templates/comfy/` | ComfyUI workflow API JSON（FLUX.2 Klein + LoRA + Qwen 文字编码 + VAE + BookCoverTextOverlay） |

### 技能包 (`skills/`)

11 个可复用创作方法论包，每个含 `SKILL.md`（从番茄小说官方课程和文学分析提炼）：

| 技能包 | 说明 |
|--------|------|
| `ancient-social-drama/` | 古风世情（宫斗宅斗/嫡庶矛盾/重生复仇） |
| `ancient-tragic-romance/` | 古文虐恋（重生追妻火葬场/替身婚姻） |
| `blurb-and-cover-design/` | 封面+简介设计（番茄官方课程） |
| `book-cover-generation/` | ComfyUI 封面生成技能 |
| `chapter-hooks/` | 12 种钩子类型 + 类型匹配 |
| `climax-design/` | 8 种爽点原型 + 情绪曲线 |
| `mind-bending-shorts/` | 脑洞类短篇（番茄第 29 期） |
| `moyan-style/` | 莫言风格（幻觉现实主义/高密乡土/怪诞美学），含 `references/` |
| `murakami-style/` | 村上春树风格（洁净散文/记忆叙事/隐喻），含 `references/` |
| `title-design/` | 标题公式 + 类型模式 + A/B 测试 |
| `webnovel-foundations/` | 网文零到一基础（金番作者京祺） |

附两部参考语料：`挪威的森林.txt`（652KB）、`莫言中短篇小说散文选.txt`（870KB）。

### 系列工程 (`series/`)

10 个长篇系列项目目录：

| 系列 | 说明 |
|------|------|
| 千行百业 | 现代职业百态，10 部职业题材长篇 |
| 哥伦布计划 | 西方热门题材短篇，20 个变体 |
| 哥伦布计划美联储 | 金融史诗子系列 |
| 重生穿越 | 现代失败者穿越古代逆袭，11 部关联长篇 |
| 破镜之后 | 女频长篇（伤害后重逢） |
| 不被定义她的主场 | 女本位觉醒叙事 |
| 轮回怪谈 | 轮回题材 |
| 重生之动物变身 | 动物变身题材 |
| 知乎短篇 | 知乎平台短篇 |
| 抖音全民写作大赛 | 70 篇历史人物图文 |

**系列目录结构**（以 `不被定义她的主场` 为例）：
```
不被定义她的主场/
├── README.md
├── WORKFLOW.md              # Agent 分工指令
├── tools/new_variant.py     # 变体脚手架 CLI
├── templates/               # 章节/角色/封面/种子/卷大纲模板
└── variants/<name>/
    ├── outline.md
    ├── characters.md
    ├── continuity_log.md
    ├── cover_brief.json
    ├── seed.json
    └── chapters/
```

### 日常批量管线 (`daily_novels/`)

| 文件 | 职责 |
|------|------|
| `daily_novels/pipeline.py` | 定时任务入口：搜索热点 → 选方向 → 写小说 → 输出 TXT |

流程：
1. `search_hot_topics()` — Bocha 搜索当月热点（≤15 条）
2. `select_direction()` — 15 个方向加权随机（社会众生相/职业百态/关爱群体/亲情羁绊…）
3. `generate_novel()` — 单次 LLM 调用（5 次重试 + 429 退避 + 600s 超时），目标 1-3 万字
4. `save_novel()` — 清洗 markdown，提取标题，输出 `.txt` + `.meta.json`
5. `maybe_generate_cover()` — 可选 ComfyUI 封面（`GENERATE_COVER=1` 环境门控）

### 测试套件 (`tests/`)

39 个测试文件，525+ 用例，覆盖全栈：

| 测试文件 | 覆盖范围 |
|----------|----------|
| `test_deai_engine.py` | 去AI化引擎（参数化/提示词外置/LLM 重写锚点/策略分派/真实计数） |
| `test_outline_format.py` | 大纲解析容错/渲染往返/下游解析器兼容性契约 |
| `test_api.py` / `test_api_outline.py` | REST API 端点 + 大纲编辑 |
| `test_auto_revise.py` | 自动修订循环 |
| `test_phase_*.py` | 各 Phase 测试（research/writing_batch/complete_gate/complete_delivery/inference/outlining_title） |
| `test_planner.py` | 任务计划器 |
| `test_run_state.py` / `test_recovery.py` | RunState 持久化 + 崩溃恢复 |
| `test_batch_coordinator.py` | 批次协调器 |
| `test_llm_client.py` | LLM 客户端（重试/超时/流式） |
| `test_model_routing.py` / `test_light_model_routing.py` | 模型路由 |
| `test_job_runner.py` / `test_jobs_batch.py` | JobRunner 并发 |
| `test_knowledge_store.py` / `test_knowledge_research.py` | 知识库 |
| `test_cli.py` / `test_cli_resume.py` | CLI 命令 |
| `test_config.py` | 配置读写 |
| `test_multi_polisher.py` | 多模型润色 |
| `test_text_cleaner.py` | 文本清洗 |
| `test_web_search.py` | 联网搜索 |
| `test_worklog.py` | 工作日志 |
| `test_bugfix_regressions.py` | Bug 修复回归测试 |
| `test_cn_number.py` | 中文数字转换 |
| `test_chapter_summary.py` | 章节摘要 |
| `test_genre_knowledge.py` | 类型知识注入 |
| `test_gui_controller.py` | GUI 控制器 |
| `test_repl_robustness.py` | REPL 健壮性 |
| `test_round_checkpoint.py` | Round 检查点 |
| `test_run_cost.py` | 成本核算 |
| `test_topic_researcher.py` | 选题研究员 |
| `test_jobs_run_job_planner.py` | Job+Planner 集成 |
| `test_phase_research_innovate.py` | 调研+创新 Phase |

### 其他根级文件

| 文件 | 说明 |
|------|------|
| `pyproject.toml` | 项目元数据（name=story-studio, version=2.0.0, Python≥3.11, 依赖, console scripts, pytest 配置, 显式包声明） |
| `main.py` | 兼容入口（委托 `cli.main:app`），详见 [core.md](core.md) |
| `export_final.py` | 遗留一次性导出脚本（已被 `phase_complete` 取代） |
| `.env.example` | 环境变量示例（`WEB_SEARCH_API_KEY`） |
| `config/settings.example.yaml` | 配置文件示例 |
| `Modelfile.moyan` | 莫言风格 LoRA Modelfile |
| `fonts/` | 4 款中文字体（楷书/隶书/毛笔） |
| `characters/` | 角色档案示例（高欢/韦孝宽/斛律金/老卒） |
| `example/` | 联网搜索 API 示例 + Postman curl |

---

## 设计决策

1. **显式包声明**：`pyproject.toml` 的 `packages` 列表显式枚举，避免 setuptools flat-layout 自动发现在 `series/` / `skills/` 等数据目录上报 "Multiple top-level packages" 错误
2. **技能包数据驱动**：领域知识外化到 `SKILL.md` 和 JSON 配置，不改代码即可新增
3. **封面标题不进 diffusion prompt**：中文文字用 Pillow/ComfyUI 节点后处理叠加，避免 AI 生成的乱码文字
4. **日常管线独立**：`daily_novels/` 不依赖主编排器，用单次 LLM 调用快速产出
5. **测试覆盖广**：39 文件 525+ 用例覆盖从 LLM 客户端到 API 端点到去AI化引擎的全栈

---

*模块文档版本：v2.0.0 · 对应代码版本：v2.0.0*
