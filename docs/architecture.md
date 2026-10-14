# Story Studio 架构设计

> 版本：v2.0.0 · 更新日期：2026-10-13

---

## 1. 系统全景

Story Studio 是一个多 Agent 协作的小说创作平台，核心设计思想是**将创作流程分解为专业角色分工**，每个 Agent 扮演创作链条中的一个职能，由编排器按阶段调度。

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          用户交互层                                      │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌──────────┐               │
│  │ CLI (ss) │  │ REST API │  │ Web 前端  │  │  REPL    │               │
│  │  Typer   │  │ FastAPI  │  │ Next.js   │  │ 交互式   │               │
│  └────┬─────┘  └────┬─────┘  └─────┬─────┘  └────┬─────┘               │
│       │              │              │              │                     │
└───────┼──────────────┼──────────────┼──────────────┼────────────────────┘
        │              │              │              │
        ▼              ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          编排层                                          │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐                   │
│  │ JobRunner   │  │ TaskPlanner  │  │  StoryOrch    │                   │
│  │ 多 Job 并发 │──▶│ 7 任务清单  │──▶│ 6 Phase 引擎 │                   │
│  │ Semaphore   │  │ 断点恢复    │  │ 自动修订循环  │                   │
│  └─────────────┘  └──────────────┘  └───────┬───────┘                   │
│                                             │                            │
│  ┌─────────────────────────────────────────┘                            │
│  │  RunState 持久化  ·  BatchCoordinator 批次协调  ·  WorkLog 审计     │
└──┼──────────────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          Agent 层 (14 位)                                │
│                                                                         │
│  创作线 (11)           调研线 (3)            工具线 (4)                  │
│  ┌────────────┐       ┌──────────────┐      ┌──────────────┐           │
│  │Showrunner  │       │TopicResearch │      │WebSearch     │           │
│  │WorldArch   │       │Innovator     │      │StylePolisher │           │
│  │CharDesigner│       │TrendingWords │      │MultiPolisher │           │
│  │CharPsych   │       └──────────────┘      │TextCleaner   │           │
│  │SceneWriter │                             └──────────────┘           │
│  │Editor      │       模型路由: main / light 两档                       │
│  │LitAdvisor  │       per-agent 可覆盖                                     │
│  │Continuity  │                                                         │
│  │TitleDesign │                                                         │
│  │Hooker      │                                                         │
│  │ClimaxDesign│                                                         │
│  └────────────┘                                                         │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          基础设施层                                      │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐            │
│  │LLMClient  │  │OllamaClient│  │LocalInfer │  │DeaiEngine │            │
│  │云端 API   │  │本地 Ollama │  │LoRA 风格  │  │去AI化引擎 │            │
│  │连接池+重试│  │            │  │单例缓存   │  │四层流水线 │            │
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘            │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────┐          │
│  │ KnowledgeStore — 双层级文件知识库 (series + variant)      │          │
│  │ world / characters / story / research / checkpoints      │          │
│  └───────────────────────────────────────────────────────────┘          │
│                                                                         │
│  ┌─────────────┐  ┌──────────────────────────────┐                      │
│  │StudioConfig │  │ WebSearchProvider             │                      │
│  │settings.yaml│  │ Doubao / Bocha / Mock         │                      │
│  └─────────────┘  └──────────────────────────────┘                      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 核心设计决策

### 2.1 Agent 抽象：极简契约 + Prompt 驱动

所有创作 Agent 继承 `Agent` 基类，唯一契约是实现 `system_prompt` 属性。不写任何业务逻辑代码——角色知识、行为规范、输出格式全部内化在 system prompt 文本中。这使得新增 Agent 成本极低（只需写一段 prompt），但也要求 prompt 质量极高。

**设计理由**：创作角色是"人"而不是"函数"，行为规范用自然语言比代码表达更灵活。LLM 的 instruction-following 能力已经足够强，不需要硬编码行为逻辑。

### 2.2 三层崩溃恢复

| 层级 | 持久化 | 粒度 | 恢复机制 |
|------|--------|------|----------|
| RunState | `run_state.json` | Phase + Chapter + Cost | `merge_into_orchestrator` |
| TaskPlan | `task_plan.json` | 7 任务状态 | `load_plan` 重置 stale running→pending |
| Round Checkpoint | `story/checkpoints/` | 每章每步 (write/edit/review) | `load_round_checkpoint` 跳过已完成步骤 |

每个 Phase 有幂等性守卫——如果输出产物已存在则跳过。这保证崩溃恢复不会重跑已完成的工作。

### 2.3 双模式写作：串行 vs 批次并行

- **串行模式** (`phase_writing`)：逐章写作，每章走 scene→edit→continuity→review 修订循环
- **批次并行模式** (`phase_writing_batch`)：三阶段流程
  1. `BatchCoordinator.plan_batch` — Showrunner 生成交接 brief（入场/退场状态/必须揭示/禁止剧透/承接）
  2. `asyncio.gather` 多 SceneWriter 并发写——每章独立的 editor/continuity/showrunner 实例避免共享 history 污染
  3. `BatchCoordinator.merge_gate` — ContinuityKeeper 跨章一致性硬门，冲突章定向重写

### 2.4 双层级知识库

```
series/千行百业/knowledge/    ← 只读，系列级共享世界观
variants/03_雷雨请绕飞/knowledge/  ← 读写，变体级独立故事
```

`KnowledgeStore` 在每个读取方法中实现 variant→series 回退：变体有则用变体，没有则查系列。写操作只写变体层。这让同一世界观下的多部小说共享设定而互不干扰。

### 2.5 模型路由：Per-Agent 两档

```
main_model  → 核心创作（SceneWriter / Showrunner / WorldArchitect / CharacterDesigner / Innovator）
light_model → 元任务（Editor / Continuity / TitleDesigner / Hooker / ClimaxDesigner / ...）
```

`settings.yaml` 的 `agent_models` 字段可为每个角色单独指定模型，覆盖默认 tier 分配。这控制了成本——meta 任务不需要最强模型。

### 2.6 去AI化：三层防御

| 层 | 位置 | 机制 |
|----|------|------|
| 层一：写作内化 | `scene_writer.py` system prompt | 7 条写作纪律（禁忌词限量、句长爆发、不确定人味、具体细节配额、情绪去标签、对话人味、结构反模板） |
| 层二：编辑审核 | `editor.py` system prompt | 8 维度检测清单（词汇痕迹/句式均匀/段落模板/过度升华/细节抽象/情绪标签/对话失真/网文套路） |
| 层三：引擎工具 | `deai/` 独立模块 | 四层流水线（正则扫描→规则重写→LLM 重写→审计评分 0-50） |

### 2.7 错误哨兵约定

LLM 调用失败不抛异常，返回 `[LLM API error: ...]` 字符串哨兵。消费方（Agent、KnowledgeStore、MultiPolisher）通过前缀匹配检测并降级处理——不写入知识库、不追加到对话历史、标记为失败结果。这让整个管道在 LLM 不稳定时仍能优雅降级而非崩溃。

---

## 3. 数据流

### 3.1 创作流水线（6 Phase）

```
Phase 0: 调研（可选）
  TopicResearcher → 联网搜索 4 类素材 → 存入 research/
  Innovator → 基于调研生成 5-8 创新亮点

Phase 1: 策划
  Showrunner → 分析需求 → 团队讨论（World + Character）→ 创作企划书

Phase 2: 建立
  WorldArchitect → 世界观详细设定
  CharacterDesigner → 角色档案
  CharacterPsychologist → 角色心理深度（MBTI / 依恋类型 / 防御机制）
  Showrunner → 审阅

Phase 2.5: 热词（可选）
  TrendingWords → 按时代检索 4 类热词 → world/trending_words.md

Phase 3: 大纲
  Showrunner → 章节大纲
  TitleDesigner / Hooker / ClimaxDesigner → 专项设计
  LiteraryAdvisor → 结构建议
  Showrunner → 确定

Phase 4: 写作（自动修订循环，max_rounds=3）
  for round in range(max_rounds):
    SceneWriter → 写/重写章节
    Editor → 润色
    ContinuityKeeper → 一致性检查
    Showrunner → 评审 → PASS / REVISE / REJECT
    PASS → 保存 + 生成摘要 → 下一章
    REVISE/REJECT → 回灌评审意见重写

Phase 5: 完稿
  Editor → 全文润色
  ContinuityKeeper → 最终一致性
  Showrunner → 终审（DeaiEngine audit 质量门）
  交付：final.md / final.txt / synopsis / cover_brief
```

### 3.2 上下文压缩

长篇小说面临上下文窗口限制。`build_context` 采用分级压缩：

1. 系列 + 研究知识库（带预算截断）
2. 世界观摘要（500 字/文档）
3. 角色摘要
4. 大纲截断到 8000 字
5. 章节摘要（≤200 字/章，bisect 预算裁剪，超 `max_context_chars` 按章号倒序丢弃最旧）
6. 连续性日志

这是长篇不退化的关键机制——用摘要替代全文，保证后续章节写作时上下文可控。

### 3.3 成本核算

每次 `agent.think` 将 `client.last_usage`（prompt/completion/total tokens）拷到 `agent.last_usage`，编排器在 `asyncio.Lock` 保护下按 model 分桶聚合到 `RunState.cost`。Job progress 暴露累计 token。

---

## 4. 模块依赖关系

```
cli/ ──▶ config/ ──▶ agents/ ──▶ orchestrator ──▶ planner ──▶ jobs
 │                     │              │
 │                     ├──▶ deai/     ├──▶ outline_format
 │                     │              │
api/ ──▶ config/       ├──▶ agents/tools/web_search
 │                     │
 └──▶ agents/          ├──▶ agents/creative/ (11 agents)
      orchestrator     ├──▶ agents/research/ (3 agents)
      planner          └──▶ agents/tools/ (4 tools)
      jobs

frontend/ ──HTTP/SSE──▶ api/
```

**关键依赖约束**：
- `outline_format.py` 的 render 格式被 `orchestrator._parse_total_chapters`、`agents.utils.extract_chapter_outline` 依赖——修改 render 必须验证下游解析器
- `config/io.py` 是 CLI 和 API 的共享配置读写层——白名单修改需同步两端
- `deai/pipeline.py` 被 `cli/pipeline_core.py`、`orchestrator.py`、`short_story/engine.py` 三处调用

---

## 5. 技术栈

| 层 | 技术 | 用途 |
|-----|------|------|
| 推理引擎 | LLM API（OpenAI 兼容，默认 PCL） | Agent 推理后端 |
| 本地推理 | Ollama / Qwen+LoRA (torch/peft) | 本地模型 / 风格润色 |
| HTTP | httpx.AsyncClient（连接池） | API 调用 |
| 编排 | Python asyncio + gather | 并发调度 |
| CLI | Typer + Rich | 命令行 |
| API | FastAPI + sse-starlette + Uvicorn | REST + SSE |
| 前端 | Next.js 16 + React 19 + shadcn/ui + Milkdown 7 | Web 界面 |
| 知识库 | Markdown / JSON 文件系统（原子写） | 结构化存储 |
| 配置 | YAML (pyyaml) + .env | 运行配置 |
| 测试 | pytest | 525+ 用例 |

---

## 6. 并发安全设计

代码中多处标注了 P0/P1 修复注释，记录已解决的竞态条件：

| 问题 | 解决方案 |
|------|----------|
| Job index 并发写入损坏 | `threading.Lock` + 唯一临时文件名 + `os.replace` |
| 并行写作共享 agent history 污染 | 每章独立构造 editor/continuity/showrunner 实例 |
| Cost 聚合并发竞争 | `asyncio.Lock` 保护 `run_cost` |
| 同一 Job 的 API 端点与后台任务并发 | per-job `asyncio.Lock` |
| LLM 客户端连接池泄漏 | `finally` 块中 `aclose()` |

---

## 7. 扩展点

- **新增 Agent**：在 `agents/creative/` 或 `agents/research/` 新增文件，定义 `system_prompt` 属性，在 `orchestrator.py` 构造并注入
- **新增搜索 Provider**：继承 `WebSearchProvider`，实现 `search()` 方法，在 `get_search_provider` 工厂注册
- **新增写作风格**：在 `STYLE_REGISTRY` 注册 LoRA 路径 + system prompt
- **新增短篇类型**：在 `short_story/skill_configs/` 新增 JSON 配置
- **新增去AI化规则**：在 `deai/rules.py` 的 `RULES` 列表追加 `DeaiRule`
- **新增 API 端点**：在 `api/` 对应路由模块新增，或新建路由包并 `include_router`

---

*架构版本：v2.0.0 · 对应代码版本：v2.0.0*
