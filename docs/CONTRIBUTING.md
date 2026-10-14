# 贡献指南

> 欢迎为 Story Studio 贡献代码和文档。请阅读以下规范后再提交。

---

## 1. 开发环境

```bash
# 克隆仓库
git clone https://github.com/arthurlirui/story-studio.git
cd story-studio

# 安装主依赖 + 开发依赖
pip install -e ".[dev,cli,api]"

# 前端开发
cd frontend && npm install

# 配置密钥
cp config/settings.example.yaml config/settings.yaml
# 编辑 settings.yaml 填入 llm_api_key

# 运行测试
pytest tests/ -v
```

---

## 2. Git 提交规范

遵循 [Conventional Commits](https://www.conventionalcommits.org/)：

```
<type>(<scope>): <subject>

<body 可选>

<footer 可选>
```

### type

| type | 说明 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `docs` | 文档变更 |
| `refactor` | 重构（不改功能） |
| `chore` | 构建/工具变更 |
| `test` | 测试相关 |
| `perf` | 性能优化 |

### scope

标识影响模块：`agents` / `cli` / `api` / `deai` / `frontend` / `config` / `orchestrator` / `planner` / `jobs` / `outline` / `short-story` / `tools` / `skills` / `series` 等。

### 示例

```
feat(agents): 新增角色心理学家 Agent

fix(deai): 修复润色后字数超限未触发重试的问题

docs(api): 更新 REST API 端点文档
```

---

## 3. 代码规范

### Python

- Python ≥ 3.11，类型注解鼓励但不强制
- 异步优先：新增 I/O 操作使用 `async/await`
- 错误处理：LLM 调用失败返回哨兵字符串（`[LLM API error: ...]`），不抛异常
- 原子写入：文件写入使用 `agents.knowledge._atomic_write_text`（tmp + `os.replace`）
- 导入：重模块（orchestrator）在函数体内部导入，保持 `ss --help` 秒级响应

### TypeScript / React (前端)

- 函数组件 + Hooks
- SSE 使用 `fetch` + `ReadableStream`（不用 `EventSource`，以传递 `X-API-Key` header）
- API key 存 `localStorage`，不放入 URL

### 测试

- 新增功能必须附带测试
- 测试文件放 `tests/`，命名 `test_<模块>.py`
- 使用 `pytest` 框架，异步测试用 `_run(coro)` helper
- 运行：`pytest tests/ -v`

---

## 4. 文档更新协议

**代码变更必须同步文档**。这是 Story Studio 的硬性要求。

### 4.1 何时更新文档

| 变更类型 | 需更新的文档 |
|----------|-------------|
| 新增模块/文件 | `docs/modules/<对应文档>.md` + `docs/INDEX.md` |
| 新增/修改 API 端点 | `docs/API.md` + `docs/modules/api.md` |
| 新增/修改 CLI 命令 | `docs/CLI.md` + `docs/modules/cli.md` |
| 架构变更 | `docs/architecture.md` |
| 新增 Agent | `docs/modules/agents.md` + `README.md` Agent 表 |
| 配置项变更 | `docs/modules/infra.md` + `config/settings.example.yaml` |
| 任何版本变更 | `docs/CHANGELOG.md` |

### 4.2 模块文档结构

每个 `docs/modules/*.md` 文件遵循统一结构：

```markdown
# 模块名称

> 一句话概述

## 文件清单
| 文件 | 职责 | 关键类/函数 |
|------|------|------------|
| ... | ... | ... |

## 核心设计
...

## 依赖关系
...

## 设计决策
...
```

### 4.3 CHANGELOG 更新

在 `docs/CHANGELOG.md` 顶部（最新版本段落内）添加条目。如果当前没有未发布的版本段落，先按 [版本管理策略](VERSIONING.md) 创建新版本段落。

---

## 5. 版本发布流程

详见 [版本管理策略](VERSIONING.md)。

简要步骤：

1. 确定版本号递增类型（MAJOR / MINOR / PATCH）
2. 更新 `pyproject.toml` 的 `version`
3. 更新 `docs/INDEX.md` 和 `docs/architecture.md` 顶部版本标注
4. 在 `docs/CHANGELOG.md` 顶部新增版本段落
5. 提交：`git commit -m "release: vX.Y.Z"`

---

## 6. 分支策略

- `main`：稳定分支，所有合并到 main 的代码应通过测试
- 功能开发：从 main 切出 `feat/<功能名>` 分支
- Bug 修复：从 main 切出 `fix/<问题描述>` 分支
- 合并方式：直接 merge 到 main（小型项目可不用 PR）

---

## 7. 安全注意事项

- **密钥不进源码**：`settings.yaml` 已 `.gitignore`，示例配置用 `settings.example.yaml`
- **环境变量回退**：`LLM_API_KEY` / `WEB_SEARCH_API_KEY` / `STORY_STUDIO_API_KEY`
- **历史密钥**：如历史提交中曾出现密钥，需在 LLM 服务后台轮换
- **API 鉴权**：REST API 使用 `X-API-Key` header，仅适合本地/单用户部署
- **前端密钥**：API key 存浏览器 `localStorage`，不放入 URL/query string
- **提交前检查**：`git diff` 确认无密钥泄露，`pretty_exceptions_show_locals=False` 防止 traceback 泄露

---

*贡献指南版本：v1.0 · 生效日期：2026-10-13*
