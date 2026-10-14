# Story Studio 文档中心

> **当前版本：v2.0.0** · 更新日期：2026-10-13 · [完整变更日志](CHANGELOG.md)

Story Studio 是一个由 14 位 AI Agent 协作驱动的小说剧本创作平台，集成去AI化引擎、联网搜索、时代热词注入、自动修订质量门、REST API 与 Milkdown 富文本编辑器。

---

## 📖 文档导航

| 文档 | 说明 | 适用读者 |
|------|------|----------|
| [**架构设计**](architecture.md) | 系统架构、模块依赖、数据流、核心设计决策 | 开发者 / 架构师 |
| [**模块手册**](modules/) | 每个代码模块和文件的详细功能说明 | 开发者 / 维护者 |
| [**CLI 命令手册**](CLI.md) | `ss` 统一命令行接口完整文档 | 使用者 / 运维 |
| [**REST API 手册**](API.md) | FastAPI 后端 27 端点 + SSE 流式接口 | 前端开发 / 集成方 |
| [**版本管理策略**](VERSIONING.md) | 语义化版本号规则与发布流程 | 维护者 |
| [**变更日志**](CHANGELOG.md) | 全版本变更记录（按版本倒序） | 所有人 |
| [**贡献指南**](CONTRIBUTING.md) | 代码贡献流程、文档更新协议、提交规范 | 贡献者 |

---

## 🗂️ 模块手册目录

| 模块文档 | 覆盖范围 |
|----------|----------|
| [modules/core.md](modules/core.md) | 编排器核心：`orchestrator.py` / `orchestrator_state.py` / `planner.py` / `jobs.py` / `outline_format.py` / `main.py` |
| [modules/agents.md](modules/agents.md) | 14 位 Agent + 基础设施：`agents/` 全部文件（base / creative / research / tools） |
| [modules/deai.md](modules/deai.md) | 去AI化引擎：`deai/` 四层流水线、24 类检测规则、审计评分 |
| [modules/api.md](modules/api.md) | FastAPI 后端：`api/` 路由包 + `config/` 配置读写共享层 |
| [modules/cli.md](modules/cli.md) | Typer CLI：`cli/` 全部子命令模块 |
| [modules/frontend.md](modules/frontend.md) | Next.js 前端：`frontend/src/` 路由、组件、hooks、lib |
| [modules/short_story.md](modules/short_story.md) | 短篇生成引擎：`short_story/` pipeline + 14 类型配置 |
| [modules/infra.md](modules/infra.md) | 基础设施：`config/` / `tools/` / `templates/` / `skills/` / `series/` / `daily_novels/` / `tests/` |

---

## 🚀 快速入口

- **新手上手**：阅读 [README.md](../README.md) → [CLI.md](CLI.md)
- **理解架构**：阅读 [架构设计](architecture.md) → [模块手册](modules/)
- **API 集成**：阅读 [API.md](API.md)
- **参与开发**：阅读 [贡献指南](CONTRIBUTING.md) → [版本管理策略](VERSIONING.md)
- **查看变更**：阅读 [变更日志](CHANGELOG.md)

---

## 📌 文档维护规则

1. **代码变更必须同步文档**：任何新增模块、修改接口、变更行为时，须同步更新对应模块文档和 CHANGELOG。
2. **版本号管理**：遵循 [语义化版本](VERSIONING.md)，每次合并到 main 时根据变更类型递增版本号。
3. **CHANGELOG 格式**：按版本倒序排列，每个版本包含 `Added` / `Changed` / `Fixed` / `Removed` / `Deprecated` 分类。
4. **模块文档结构**：每个模块文档包含「概述」「文件清单」「核心类/函数」「设计决策」「依赖关系」五部分。

---

*文档版本：v2.0.0 · 维护者：Story Studio Team*
