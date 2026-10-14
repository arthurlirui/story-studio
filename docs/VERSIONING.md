# 版本管理策略

> Story Studio 采用语义化版本（Semantic Versioning）规范

---

## 版本号格式

```
MAJOR.MINOR.PATCH
```

| 段 | 递增条件 | 示例 |
|----|----------|------|
| **MAJOR** | 不兼容的 API/架构变更 | Agent 接口重构、配置格式不兼容变更、CLI 命令删除/重命名 |
| **MINOR** | 向后兼容的功能新增 | 新增 Agent、新增 API 端点、新增 CLI 子命令、新增配置字段 |
| **PATCH** | 向后兼容的缺陷修复 | Bug 修复、性能优化、文档更新、依赖升级 |

---

## 版本号位置

版本号在以下位置同步维护：

| 位置 | 字段 | 当前值 |
|------|------|--------|
| `pyproject.toml` | `version` | `2.0.0` |
| `docs/INDEX.md` | 顶部标注 | `v2.0.0` |
| `docs/architecture.md` | 顶部标注 | `v2.0.0` |
| `docs/CHANGELOG.md` | 最新版本标题 | `## v2.0.0` |

---

## 发布流程

### 1. 确定版本号

根据本次合并到 main 的变更类型决定递增哪一段：

- 有 `BREAKING CHANGE` 或不兼容变更 → MAJOR
- 有 `feat:` 新功能 → MINOR
- 仅 `fix:` / `docs:` / `chore:` / `refactor:` → PATCH

### 2. 更新版本号

- 修改 `pyproject.toml` 的 `version`
- 修改 `docs/INDEX.md` 顶部版本标注
- 修改 `docs/architecture.md` 顶部版本标注

### 3. 更新 CHANGELOG

在 `docs/CHANGELOG.md` 顶部新增版本段落：

```markdown
## v2.0.1 — 2026-10-14

### Fixed
- 修复 XXX 在 YYY 场景下的 ZZZ 问题

### Changed
- 优化 AAA 的 BBB 性能
```

### 4. 提交

```bash
git add -A
git commit -m "release: v2.0.1"
```

---

## CHANGELOG 分类

| 分类 | 说明 |
|------|------|
| `Added` | 新增的功能、模块、端点、配置项 |
| `Changed` | 已有功能的变更、接口调整（向后兼容） |
| `Deprecated` | 标记将在未来版本移除的功能 |
| `Removed` | 已移除的功能（通常伴随 MAJOR 递增） |
| `Fixed` | Bug 修复 |
| `Security` | 安全相关修复 |
| `Docs` | 文档更新（可合并到 Changed） |

---

## 预发布版本

如需预发布，使用后缀：

- `v2.1.0-alpha.1` — 内部测试
- `v2.1.0-beta.1` — 外部测试
- `v2.1.0-rc.1` — 发布候选

预发布版本不更新 `pyproject.toml` 的正式 version，仅在 CHANGELOG 中记录。

---

## Git 提交规范

遵循 Conventional Commits：

```
<type>(<scope>): <subject>

<body>

<footer>
```

| type | 说明 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `docs` | 文档变更 |
| `refactor` | 重构（不改功能） |
| `chore` | 构建/工具变更 |
| `test` | 测试相关 |
| `perf` | 性能优化 |

**scope** 可选，标识影响模块：`agents` / `cli` / `api` / `deai` / `frontend` / `config` / `orchestrator` 等。

**footer** 用于标注 `BREAKING CHANGE:` 或关联 issue。

---

*版本管理策略版本：v1.0 · 生效日期：2026-10-13*
