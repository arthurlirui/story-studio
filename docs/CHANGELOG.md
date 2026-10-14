# 变更日志 (CHANGELOG)

> 所有版本变更记录，按版本倒序排列。版本号遵循 [语义化版本规范](VERSIONING.md)。

---

## v2.0.0 — 2026-10-13

> 本次版本建立了完整的文档体系，将项目从"有 README 的代码仓库"升级为"有专业文档维护方案的软件工程项目"。

### Added
- **文档体系**：新增 `docs/INDEX.md`（文档中心导航）、`docs/architecture.md`（系统架构设计）、`docs/VERSIONING.md`（版本管理策略）、`docs/CONTRIBUTING.md`（贡献指南）、`docs/CHANGELOG.md`（本文件）
- **模块手册**：新增 `docs/modules/` 目录，包含 8 个模块文档，覆盖全部代码模块和文件的详细功能说明
- **版本号系统**：引入语义化版本号，在 `pyproject.toml`、文档头部同步维护

### Changed
- `pyproject.toml` 版本号从 `1.0.0` 升级到 `2.0.0`
- 文档从散落的 README/ARCHITECTURE 整合为结构化文档体系

---

## v1.9.0 — 2026-09-09

### Added
- 去AI化引擎配置 UI：设置页新增去AI化引擎参数面板（激进度/字数比/审计阈值/重试上限/提示词版本）
- 热词路由：时代热词按章节 era 查表注入场景写作
- 设置页修复：四 Tab 分区（连接与模型 / 生成流水线 / 调研与润色 / 智能体路由）
- 14 个智能体的 per-agent 模型路由可在设置页配置
- 多模型润色配置 UI

### Fixed
- 设置页敏感字段脱敏只读、只读字段拒绝写入、可写字段白名单校验

---

## v1.8.0 — 2026-08-22

### Added
- Milkdown 富文本编辑器集成到章节页（`/novels/{id}/chapters/{n}`）
- 章节自动保存：1.5s debounce，状态指示器（保存中/已保存/保存失败），`beforeunload` 守卫
- 前端主题视觉升级：双主题切换、配色重写、阅读排版与布局统一
- 前端各功能页面截图 9 张

### Changed
- 流式生成期间禁用编辑

### Fixed
- 删除临时截图脚本 `screenshot_outline.py`

---

## v1.7.0 — 2026-08-10

### Added
- 全局配置读写 API（`GET/PUT /config`），白名单校验，写回后热重载
- `GET /config/paths` 端点

### Fixed
- deai 润色新增字数合规重试与截断保护
- 短篇章节标题格式统一为「第N章」并修正章号错乱

---

## v1.6.0 — 2026-08-08

### Added
- CLI 新增 `short` / `bench` 命令
- Job 重跑支持（`ss jobs retry`）
- 桌面端 GUI（DearPyGUI）

### Changed
- CLI 重构公共初始化逻辑，提取辅助函数
- GUI 重构日志渲染与控制器事件分发机制
- 优化启动开销，统一客户端构造逻辑

### Fixed
- 核心编排与 LLM 客户端缺陷修复
- 短篇端到端生成测试

---

## v1.5.0 — 2026-08-04

### Added
- Next.js + shadcn/ui 前端
- SSE 流式端点（token 流 / job 进度 / 智能体活动）
- API 路由包化（`api/` 包替代单文件 `api.py`）

### Changed
- 移除单文件 `api.py`，重构为路由包

---

## v1.4.0 — 2026-08-03

### Added
- 基于 Typer 的统一命令行接口 `ss`
- Rich 集成的格式化输出（table / panel / tree）
- 全局选项（`-v` / `--config` / `--no-interaction`）

---

## v1.3.0 — 2026-07-30

### Added
- **角色心理学家** (CharacterPsychologist) Agent：MBTI + 荣格认知栈 + 九型人格 + 大五人格 + 依恋类型 + 防御机制

---

## v1.2.0 — 2026-07-29

### Added
- 去AI化润色提示词 v2/v3/v4 版本化
- AI 文本检测器集成（腾讯云优先 + HuggingFace 本地回退）
- 短篇统一 CLI `run_short.py` + 批量 20 篇 `run_zhihu20.py`
- 短篇 `_phase_deai` 去 AI 感润色阶段

### Changed
- 重构工具脚本，提取公共 LLM 调用模块

---

## v1.1.0 — 2026-07-27

### Added
- 统一任务入口 `run_all.py`
- deai 去 AI 感润色模块（24 类 AI 痕迹检测）
- 强化去 AI 感检查规则，新增语言指纹与 8 维度检测体系
- 短篇生成引擎 `short_story/`（14 类型 skill 配置 + batch50 生成器）
- 哥伦布计划 20 部完整大纲

### Changed
- 重构工具脚本，提取公共 LLM 调用模块并清理代码

---

## v1.0.1 — 2026-07-26

### Added
- deai 模块：24 类 AI 痕迹检测与重写引擎（基于 Humanizer-zh）
- 网文方法论注入全部 11 个 Agent 的 system prompt

---

## v1.0.0 — 2026-07-21

### Added
- **多 Agent 协作创作系统**正式发布
- 11 位创作 Agent（Showrunner / WorldArchitect / CharacterDesigner / SceneWriter / Editor / LiteraryAdvisor / ContinuityKeeper / TitleDesigner / Hooker / ClimaxDesigner）
- 6 Phase 编排引擎（策划→建立→大纲→写作→完稿）
- 自动修订质量门（scene→edit→continuity→review，max_rounds=3）
- RunState 持久化与崩溃恢复
- Per-agent 模型路由（main / light 两档）
- RunCost 按 model 分桶聚合 token 用量
- 章节摘要与上下文压缩（≤200 字/章，bisect 预算裁剪）
- KnowledgeStore 双层级知识库（series + variant）
- WorkLog JSONL 审计日志
- BatchCoordinator 批次并行写作 + merge gate
- JobRunner 多 Job 并发（Semaphore 限流）
- TaskPlanner 7 任务清单与断点恢复
- FastAPI REST API（27 端点）
- 交互式 REPL（`/new` / `/next` / `/write` / `/review` / `/chat` / `/debate` 等命令）
- 联网搜索（豆包 / 博查 / Mock 三 provider）
- 选题研究员 + 创新顾问 Agent
- 时代热词研究员 Agent
- ComfyUI 封面生成工具链
- 11 个可复用技能包（skills/）
- 10 个系列工程项目（series/）
- 525+ pytest 测试用例

### Fixed
- 并发安全、连接池泄漏及错误哨兵污染等关键问题

---

## v0.9.0 — 2026-07-19

### Changed
- 全部 Agent 切换到 DeepSeek-V4-Pro + reasoning/streaming 支持
- `volcengine_client.py` 重命名为 `llm_client.py`，`VolcengineClient` → `LLMClient`
- 完成 LLM API 迁移（config / daily_novels / 所有引用）

---

## v0.5.0 — 2026-06-25

### Added
- TitleDesigner / Hooker / ClimaxDesigner Agent
- chapter-hooks / title-design / climax-design 技能包
- VolcEngine 客户端、skills 系统、series 模板、tools 工具

---

## v0.1.0 — 2026-06-06

### Added
- 🎭 Story Studio v1.0 初始版本 — 小说剧本创作智能体团队
- 基础 Agent 框架（Showrunner / WorldArchitect / CharacterDesigner / SceneWriter / Editor / LiteraryAdvisor / ContinuityKeeper）
- 编排器与知识库原型

---

*变更日志维护者：Story Studio Team · 遵循 [Keep a Changelog](https://keepachangelog.com/) 格式*
