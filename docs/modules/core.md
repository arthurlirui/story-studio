# 核心编排层 (Core Orchestration)

> 6 Phase 创作引擎、任务计划器、多 Job 调度、运行状态持久化、大纲格式转换

---

## 文件清单

| 文件 | 行数 | 职责 | 关键类/函数 |
|------|------|------|------------|
| `orchestrator.py` | 2154 | 多 Agent 编排引擎，6 Phase 创作流水线 | `StoryOrchestrator` |
| `orchestrator_state.py` | 143 | 运行状态持久化（phase/chapter/cost） | `RunState`, `PHASE_*` 常量 |
| `planner.py` | 396 | 7 任务清单分解与断点恢复 | `TaskPlanner`, `Task`, `TaskPlan` |
| `jobs.py` | 522 | 多 Job 并发管理（Semaphore 限流） | `JobRunner`, `Job` |
| `outline_format.py` | 259 | 大纲 Markdown ↔ 结构化双向转换 | `parse_outline`, `render_outline`, `OutlineDoc` |
| `main.py` | 841 | 兼容入口 + 遗留 REPL | `main()`, `main_interactive()` |
| `export_final.py` | 141 | 一次性导出脚本（已被 `phase_complete` 取代） | `extract_pure_story()` |

---

## 核心设计

### StoryOrchestrator（编排器）

编排器是整个系统的核心，持有全部 14 个 Agent 实例、知识库、工作日志、批次协调器、Web 搜索 provider 和 DeaiEngine。提供 8 个 `phase_*` 异步方法，每个对应一个创作阶段。

**关键方法**：

| 方法 | 说明 |
|------|------|
| `phase_research(brief)` | Phase 0：联网调研（可选，失败不阻断） |
| `phase_innovate(brief)` | Phase 0.5：创新亮点生成 |
| `phase_planning(request)` | Phase 1：策划（需求分析→团队讨论→企划书） |
| `phase_building()` | Phase 2：建立（世界观→角色→心理→审阅） |
| `phase_trending_words(era)` | Phase 2.5：时代热词检索（可选） |
| `phase_outlining(total_chapters)` | Phase 3：大纲（Showrunner→专项设计→文学顾问→确定） |
| `phase_writing(chapter_num)` | Phase 4：单章写作（修订循环 max_rounds=3） |
| `phase_writing_batch(start, count)` | Phase 4：批次并行写作 |
| `phase_complete(review_criteria)` | Phase 5：终审 + 交付 |

**写作循环** (`_write_chapter_with_revisions`)：

```
for round in range(max_rounds):
    SceneWriter → 写/重写
    Editor → 润色
    ContinuityKeeper → 一致性检查
    Showrunner → 评审 → PASS / REVISE / REJECT
    PASS → 保存 + 生成摘要 → 交付
    REVISE/REJECT → 回灌评审意见
耗尽 → 交付但标 ⚠️ 警告
```

每步后保存 round checkpoint，崩溃恢复时从断点续写。

**批次并行写作** (`phase_writing_batch`)：

1. `BatchCoordinator.plan_batch` — 生成交接 brief
2. `asyncio.gather` 多 SceneWriter 并发——每章独立 agent 实例
3. `BatchCoordinator.merge_gate` — 跨章一致性硬门，冲突章定向重写

### RunState（运行状态）

`{knowledge_dir}/run_state.json` 持久化：
- `job_id` / `project_name` / `phase` / `current_chapter` / `total_chapters`
- `cost`：按 model 分桶的 token 用量
- `progress_log`：时间戳事件列表（崩溃恢复审计）

**不持久化** `conversation_log`（体积太大）。`merge_into_orchestrator` 恢复时只覆盖默认值字段，不覆盖已手动设置的值。

### TaskPlanner（任务计划器）

将流水线分解为 7 个有序任务，持久化到 `task_plan.json`：

```
research → innovate → planning → building → trending → outlining → writing → complete
```

- `research_enabled=false` → research/innovate 标记 `skipped`
- `trending_enabled=false` → trending 标记 `skipped`
- `load_plan` 重置 stale `running` → `pending`（否则崩溃任务永久阻塞）
- `run_all` 循环 `next_task` 直到无剩余任务

### JobRunner（多 Job 调度）

- 每个 Job 独立 `{base_dir}/jobs/{job_id}/` 目录（隔离的 knowledge + output）
- `asyncio.Semaphore(max_concurrent)` 限并发（默认 2）
- `index.json` 持久化 Job 列表，进程重启可恢复
- 状态机：`queued → running → succeeded / failed / cancelled / recoverable`
- 重启时：`running` + 有 task_plan → `recoverable`（自动恢复）；无 task_plan → `failed`
- per-job `asyncio.Lock` 防止 API 端点与后台任务并发操作同一 Job

### outline_format（大纲格式转换）

`parse_outline(md)` ↔ `render_outline(doc)` 双向转换：

- `OutlineDoc`：`book_title` / `preamble` / `chapters[]`
- `ChapterOutline`：`num` / `title` / `events[]` / `characters[]` / `hook` / `word_estimate` / `era`
- 解析容错（缺失字段用默认值），渲染严格（格式锁定）
- 支持中文数字章号（第一章~第九百九十九章）和阿拉伯数字

**渲染格式被下游依赖**：`orchestrator._parse_total_chapters` 和 `agents.utils.extract_chapter_outline` 依赖此格式，修改 render 须验证兼容性。往返一致性由 `tests/test_outline_format.py` 锁定。

### main.py（兼容入口）

- 检测遗留 flag（`--new` / `--status` / `--submit` / `--jobs`）→ 转译到 `cli.*`
- 无 flag → 委托 `cli.main.app`（Typer）
- 保留遗留 REPL 实现（841 行，迁移自原始 main.py）

---

## 依赖关系

```
orchestrator.py
  ├── agents/ (全部 14 Agent + KnowledgeStore + WorkLog + BatchCoordinator)
  ├── deai/ (DeaiEngine, lazy)
  ├── orchestrator_state.py (RunState)
  ├── outline_format.py (parse/render)
  ├── agents/utils.py (extract_chapter_outline)
  └── config/ (StudioConfig)

planner.py
  ├── orchestrator.py (phase_* 方法)
  ├── agents/knowledge.py (TaskPlan 持久化)
  └── config/

jobs.py
  ├── orchestrator.py
  ├── planner.py
  ├── config/
  └── agents/llm_client.py (per-job 独立 client)
```

---

## 设计决策

1. **幂等性守卫**：每个 Phase 检查输出产物是否已存在，存在则跳过——崩溃恢复不重跑已完成工作
2. **Phase 推断**：`_infer_phase_from_disk` 在 `run_state.json` 缺失/过期时从磁盘产物推断当前阶段，`/next` 永远不会卡在 idle
3. **per-job 独立 LLM 客户端**：避免连接池共享导致的并发问题，`finally` 中 `aclose()` 防泄漏
4. **export_final.py 是遗留产物**：已被 `phase_complete._finalize_delivery` 取代，功能等价但通用化

---

*模块文档版本：v2.0.0 · 对应代码版本：v2.0.0*
