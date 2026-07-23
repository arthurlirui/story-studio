# 🎭 Story Studio — 小说剧本创作智能体团队

> LLM API 驱动的多 Agent 协作创作系统  
> 10 位 Agent · 自动修订质量门 · 可恢复运行 · 多 Job 并发 · REST API

---

## 1. 概述

**Story Studio** 是一个由 10 个 AI Agent 组成的智能创作团队，每个成员扮演小说/剧本创作链条中的一个专业角色。Agent 通过 OpenAI 兼容的 LLM API（默认 PCL LLM API）推理，支持 per-agent 模型路由、自动修订质量门、运行状态持久化、多 Job 并发和 REST API。

### 核心能力

```
用户需求 → 团队讨论 → 大纲构建 → 章节写作（自动修订） → 终审 → 成品交付
                 ↕                  ↕                        ↕
           世界观/角色数据库    连续性检查 + 章节摘要      清洗版 TXT / 简介 / 封面
```

---

## 2. 智能体团队

### 角色构成

```
┌──────────────────────────────────────────────────────────────┐
│                       🎬 总策划 (Showrunner)                   │
│              主持创作流程、分配任务、评审产出、把控方向              │
└───────────────────────────┬──────────────────────────────────┘
                            │ 协调 / 调度
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                  ▼
┌─────────────────┐ ┌─────────────────┐ ┌──────────────────┐
│ 🌍 世界观架构师   │ │ 👤 角色设计师    │ │ 📖 场景编剧       │
│ World Architect  │ │ Character Design │ │ Scene Writer     │
├─────────────────┤ ├─────────────────┤ ├──────────────────┤
│ • 世界观设定      │ │ • 角色档案创建   │ │ • 章节写作        │
│ • 规则体系        │ │ • 性格一致性     │ │ • 场景描述        │
│ • 时间线管理      │ │ • 成长线设计     │ │ • 对话创作        │
│ • 地理/文化       │ │ • 人际关系图     │ │ • 情节推进        │
└─────────────────┘ └─────────────────┘ └──────────────────┘
          │                    │                    │
          └─────────┬──────────┴──────────┬─────────┘
                    ▼                     ▼
          ┌─────────────────┐ ┌─────────────────────┐
          │ ✍️ 编辑/润色     │ │ 🔍 连续性检查员      │
          │ Editor          │ │ Continuity Keeper   │
          ├─────────────────┤ ├─────────────────────┤
          │ • 文风统一       │ │ • 时间线一致性       │
          │ • 语言润色       │ │ • 角色特征一致性     │
          │ • 逻辑检查       │ │ • 世界观规则检查     │
          │ • 节奏调整       │ │ • 前后矛盾检测       │
          └─────────────────┘ └─────────────────────┘
                          │
                          ▼
          ┌──────────────────────────┐
          │ 🎯 文学顾问               │
          │ Literary Advisor         │
          ├──────────────────────────┤
          │ • 叙事结构建议             │
          │ • 风格指导                 │
          │ • 技巧推荐                 │
          │ • 章节摘要生成（≤200 字）   │
          └──────────────────────────┘

  网文特化设计师（Phase 3 介入）：
  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
  │ 🏷️ 标题设计师    │ │ 🪝 钩子设计师    │ │ 🔥 爽点设计师    │
  │ Title Designer  │ │ Hooker          │ │ Climax Designer │
  │ • 书名/章节标题  │ │ • 章节钩子/悬念  │ │ • 爽点节奏/高潮  │
  └─────────────────┘ └─────────────────┘ └─────────────────┘
```

### 模型路由

按角色分两层（可在 `settings.yaml` 的 `agent_models` 里逐个覆盖）：

- **main tier**（走 `main_model`）：scene_writer / showrunner / world_architect / character_designer
- **light tier**（走 `light_model`）：editor / continuity_keeper / literary_advisor / title_designer / hooker / climax_designer

### 2.1 🎬 总策划 (Showrunner)

**角色定义**: 创作团队的主编/制作人。接收用户需求，分解为创作任务，分派给相应 Agent，审阅产出并反馈。

**职责**:
- 理解用户创作意图
- 拆解任务（世界观 → 角色 → 章节 → 修订）
- 分发任务给对应 Agent
- 汇总评审，决定是否通过或退回修订
- 保持整体叙事方向和创作节奏

**系统提示要点**:
- 你是主编，不是直接写作者
- 每个阶段产出都需要你的审阅
- 关注整体一致性而非局部细节

### 2.2 🌍 世界观架构师 (World Architect)

**角色定义**: 负责构建故事世界的规则、历史、地理、文化等底层设定。

**职责**:
- 设计世界观核心理念（如"科幻废土"、"东方玄幻"、"克苏鲁侦探"）
- 定义世界规则（魔法体系、科技水平、社会结构）
- 创建时间线（纪元、重大历史事件）
- 设计地理/势力分布
- 记录所有设定到知识库

**输出**: 世界观设定文档 (World Bible)

### 2.3 👤 角色设计师 (Character Designer)

**角色定义**: 负责创造和维护所有角色的档案、性格、成长线。

**职责**:
- 根据世界观和故事需求设计角色
- 维护角色档案（外貌、性格、背景、动机、弱點）
- 设计角色关系图谱
- 跟踪角色成长弧线
- 在创作中保证角色行为一致

**输出**: 角色档案库 (Character Sheets)

### 2.4 📖 场景编剧 (Scene Writer)

**角色定义**: 核心创作 Agent，负责实际章节/场景的写作。

**职责**:
- 根据大纲和设定撰写章节
- 描写场景、推进情节
- 创作角色对话
- 控制叙事节奏
- 在章节末尾留下钩子

**输出**: 章节/场景文本

### 2.5 ✍️ 编辑/润色 (Editor)

**角色定义**: 负责文字层面的打磨。

**职责**:
- 统一文风（符合作品基调）
- 语言润色（去除冗余、优化句式）
- 逻辑检查（情节因果、时间顺序）
- 节奏调整（段落长度、对话比例）
- 敏感内容过滤

**输出**: 修订后的章节文本 + 修订说明

### 2.6 🎯 文学顾问 (Literary Advisor)

**角色定义**: 提供叙事技巧和结构建议。

**职责**:
- 分析当前叙事结构
- 推荐写作技巧（如"冰山理论"、"契诃夫之枪"）
- 节奏分析（紧张/舒缓的交替）
- 读者心理预期管理
- 类型文学惯例指导

**输出**: 文学建议报告

### 2.7 🔍 连续性检查员 (Continuity Keeper)

**角色定义**: 最后一道防线，确保一切前后一致。

**职责**:
- 时间线一致性检查
- 角色特征一致性（名字、能力、关系）
- 世界观规则一致性
- 前后术语统一
- 矛盾点标记与报告

**输出**: 连续性检查报告 + 待修正清单

### 2.8 🏷️ 标题设计师 (Title Designer)

**角色定义**: 为作品和各章节设计吸引眼球、契合内容的标题。**Phase 3 介入**。

**职责**:
- 设计全书书名（含副标题、备选方案）
- 为每章设计章节标题（回扣内容、留悬念）
- 兼顾网文平台的"标题党"特性与文学性

**输出**: 书名候选 + 章节标题列表

### 2.9 🪝 钩子设计师 (Hooker)

**角色定义**: 设计每章开篇钩子和结尾悬念。**Phase 3 介入**。

**职责**:
- 章首钩子：3 行内抓住读者
- 章末悬念：留 cliffhanger 推动追更
- 与爽点设计师协同控制节奏

**输出**: 钩子建议（嵌入章节写作 prompt）

### 2.10 🔥 爽点设计师 (Climax Designer)

**角色定义**: 设计爽点节奏与高潮分布，网文特化角色。**Phase 3 介入**。

**职责**:
- 规划全书爽点曲线（章 1 小爽、章 5 中爽、章 10 大爽…）
- 为每章标注爽点类型（打脸 / 装逼 / 逆袭 / 顿悟）
- 与钩子设计师协同，避免爽点疲劳

**输出**: 爽点节奏表（嵌入大纲）

---

### 3.1 标准工作流

```
Phase 1: 策划
─────────────
  用户输入创作需求
    ↓
  Showrunner 分析需求
    ↓
  Team Meeting: Showrunner + World + Character
    → 输出: 创作企划书 (世界观+核心角色+故事主线)

Phase 2: 建立
─────────────
  World Architect → 世界观详细设定 (存入知识库)
  Character Designer → 角色详细档案 (存入知识库)
    ↓
  Showrunner 审阅 → 通过/修订

Phase 3: 大纲
─────────────
  Showrunner + 各 Agent → 章节大纲
    ↓
  Title Designer  → 书名候选
  Hooker          → 钩子节奏建议
  Climax Designer → 爽点节奏表
    ↓
  Literary Advisor → 结构建议
    ↓
  Showrunner → 确定大纲

Phase 4: 写作（自动修订循环，max_rounds=3）
─────────────────────────────────────────
  for round in range(max_rounds):
    Scene Writer → 写/重写章节
      ↓
    Editor → 润色
      ↓
    Continuity Keeper → 一致性检查（哨兵守卫，失败跳过）
      ↓
    Showrunner → 评审 → 解析 PASS / REVISE / REJECT
      ↓
    若 PASS: 保存章节 + 生成章节摘要（literary_advisor）→ 下一章
    若 REVISE/REJECT: 回灌评审意见重写
  耗尽轮次: 仍交付但标 ⚠️ 警告头

  并行模式 (phase_writing_parallel):
    asyncio.gather 多章并行，每章专属 editor/continuity/showrunner 实例
    异常隔离：单章失败不杀整批

Phase 5: 完稿（终审质量门）
──────────────────────────
  Full Editor pass → 整体润色
  Final Continuity check → 最终一致性
  Showrunner → 终审（最多 max_rounds 轮 final-edit）
    ↓ 非PASS → 循环修订
    ↓ 仍非PASS → 头部插 ⚠️ 警告但**仍交付**
  交付物：
    • final_clean.txt  — 清洗版正文（去 AI 痕迹）
    • {project}_synopsis.txt  — ≤500 字内容简介
    • covers/cover_brief.json — 封面设计 brief
    • covers/cover_prompt.txt — 封面英文提示词（dry-run 模式）
```

### 3.2 交互接口

用户可通过三种方式驱动系统：

**REPL（`python main.py`）**

```
/new "<需求>"         — 开始新项目
/next                 — 推进下一阶段（从盘推断 phase）
/write [章号]          — 写作章节
/review [章号]         — 审阅章节
/revise <章号> <指令>  — 指定修改方向后重写
/chat <agent> <消息>   — 直接与某个 Agent 对话
/agents               — 列出所有 Agent
/debate <主题>         — 启动团队讨论
/knowledge            — 查看知识库状态
/world /chars /outline /continuity  — 查看对应知识
/status               — 系统状态（含 cost 摘要）
/jobs                 — 列出后台 Job
/help /exit /quit     — 帮助 / 退出

直接输入文字 = 发送给总策划
```

**CLI 一次性命令**

```
python main.py --new "<需求>"     # 跑完策划阶段
python main.py --status           # 查看状态
python main.py --submit "<需求>"  # 提交后台 Job
python main.py --jobs             # 列出 Job
python main.py --job <id>         # 查看 Job 详情
python main.py --job-cancel <id>  # 取消 Job
```

**REST API（`uvicorn api:app` 或 `python -m api`）**

```
POST   /novels                  — 提交新小说 Job
GET    /novels                  — 列出所有 Job
GET    /novels/{id}             — 查看 Job 状态/进度
GET    /novels/{id}/chapters/{n} — 读取某章正文
POST   /novels/{id}/revise      — 触发修订
DELETE /novels/{id}             — 取消 Job
GET    /health                  — 健康检查
```

---

## 4. 知识库设计

### 4.1 数据结构

```
knowledge/
├── world/                  # 世界观知识
│   ├── settings.md         # 核心理念
│   ├── timeline.md         # 时间线
│   ├── geography.md        # 地理
│   ├── rules.md            # 规则体系
│   └── factions.md         # 势力分布
├── characters/             # 角色知识
│   ├── character_001.md    # 单个角色档案
│   ├── character_002.md
│   └── relationships.md    # 关系图谱
└── story/                  # 故事进度
    ├── outline.md          # 大纲
    ├── chapters/           # 章节存档
    │   ├── chapter_001.md
    │   ├── chapter_002.md
    │   └── ...
    ├── revisions/          # 修订记录
    ├── reviews/            # 章节评审记录 (chapter_NNN_review.json)
    ├── summaries/          # 章节摘要 (chapter_NNN.md，≤200 字)
    ├── continuity_log.md   # 连续性日志
    └── run_state.json      # 运行状态持久化（见 §6）
```

### 4.2 角色档案格式

```markdown
## [角色名]

### 基本信息
- 年龄: XX
- 身份: XX
- 外貌: XX

### 性格特征
- 核心特质: [3-5 个关键词]
- 优点: [...]
- 弱点: [...]
- 口头禅/习惯: [...]

### 背景故事
[...]

### 动机与目标
- 短期目标: ...
- 长期目标: ...
- 核心恐惧: ...

### 关系网络
- [角色A]: 关系描述
- [角色B]: 关系描述

### 成长弧线
- 初始状态: ...
- 关键转变: [...]
- 最终状态: ...

### 出场记录
- 第 1 章: [做了什么/说了什么关键台词]
- 第 3 章: [...
```

### 4.3 世界观文档格式

```markdown
# [世界观名称]

## 核心理念
[一句话概括]

## 核心设定
- 类型: [奇幻/科幻/现实/悬疑...]
- 基调: [黑暗/温暖/幽默/严肃...]
- 时代: [...]

## 世界规则
### [规则领域1]
- 规则 A: ...
- 规则 B: ...

## 时间线
### 纪元一 (XXX年 - XXX年)
- 事件 1: ...
- 事件 2: ...

## 地理
[主要地点描述]

## 文化与社会
[社会结构、价值观等]
```

---

## 5. 技术栈

| 层 | 技术 | 用途 |
|-----|------|------|
| **推理引擎** | LLM API（OpenAI 兼容，默认 PCL LLM API `llmapi.pcl.ac.cn`） | Agent 推理后端 |
| **模型** | per-agent 路由：`main_model` / `light_model` 两档（可在 `agent_models` 逐个覆盖） | 主力 / 轻量任务分流 |
| **HTTP 客户端** | httpx.AsyncClient（连接池复用） | API 调用 |
| **编排层** | Python asyncio + `asyncio.gather`（并行写作） | Agent 协作调度 |
| **知识库** | Markdown / JSON 文件系统（原子写） | 结构化知识存储 |
| **Job 调度** | `JobRunner` + `asyncio.Semaphore` | 多并发小说任务 |
| **REST API** | FastAPI + Uvicorn | 外部驱动接口 |
| **输出** | 清洗版 TXT + 简介 + 封面 brief | 成品交付 |

---

## 6. 运行状态与持久化

### 6.1 RunState

`{knowledge_dir}/run_state.json` 持久化以下字段，使崩溃后可恢复：

```json
{
  "job_id": "...",
  "project_name": "...",
  "phase": "writing",
  "current_chapter": 5,
  "total_chapters": 20,
  "created_at": ...,
  "updated_at": ...,
  "cost": {
    "DeepSeek-V4-Pro": {"prompt": 12345, "completion": 6789, "total": 19134, "calls": 42},
    "Qwen-...": {...}
  }
}
```

- `StoryOrchestrator.__init__` 末尾读盘合并到 `self`
- 每次 phase 转换 + 每章写完都 `_save_state()`
- `conversation_log` 不持久化（体积太大），仅 phase 进度 + cost
- `/next` 在 `phase=="idle"` 时调用 `_infer_phase_from_disk()`，按 `final.md` → chapters → outline → world/character 顺序推断

### 6.2 RunCost

每次 `agent.think` 把 `client.last_usage`（prompt/completion/total tokens）拷到 `agent.last_usage`，`_save_state` 按 model 分桶聚合到 `RunState.cost`。`get_status()` 返回 cost 摘要，Job progress 暴露累计 token。

### 6.3 章节摘要与上下文压缩

每章 PASS 后 `literary_advisor`（light_model）生成 ≤200 字摘要存 `story/summaries/chapter_NNN.md`。`build_context` 优先用摘要替代首段 200 字，超出 `max_context_chars`（默认 60000）按章节号倒序裁剪最旧摘要；outline 截断到 8000 字。长篇不退化的关键机制。

---

## 7. Job 模型与并发

`jobs.py` 的 `JobRunner` 管理多并发小说任务：

- 每个 Job 在 `{base_dir}/jobs/{job_id}/` 下独立 `knowledge/` + `output/` 目录
- `series_knowledge_dir` 跨 Job 共享只读（系列设定复用）
- `asyncio.Semaphore(max_concurrent)` 限并发（默认 2）
- Job index 持久化到 `{base_dir}/jobs/index.json`，进程重启可恢复列表
- 状态机：`queued → running → succeeded / failed / cancelled`

---

## 8. 隐私与密钥

- 推理经外部 LLM API 完成，**数据会上送 API 服务端**——不再宣传"零数据外泄"
- 密钥不进源码：`config/settings.yaml` 已 `.gitignore`，示例见 `config/settings.example.yaml`
- `load_config` 在 `llm_api_key` 为空时回退 `LLM_API_KEY` 环境变量
- 历史仓库里曾出现过密钥，**需在 LLM 服务后台自行轮换**（git 历史不重写）
- 知识库仍为纯文本 Markdown，可版本控制 (Git)

---

## 9. 扩展方向

- [x] **Agent 讨论/辩论模式**: 多 Agent 就情节分歧进行讨论，Showrunner 裁决（`/debate`）
- [ ] **分镜脚本生成**: 支持剧本格式（剧本/分镜/对白表）
- [ ] **人物关系图可视化**: 自动生成角色关系网络图
- [ ] **阅读时长估算**: 根据字数估算各章节阅读时间
- [ ] **多语言创作**: 支持中英文及翻译
- [x] **Web 界面**: FastAPI REST API（`api.py`）；前端待接
- [ ] **ComfyUI 真实渲染**: 当前封面为 `--dry-run` 提示词，未来接 ComfyUI 出图

---

*Designed by Archy · API by Managy · Implemented by Cody*
