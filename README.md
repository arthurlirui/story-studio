# 🎭 Story Studio

> LLM API 驱动的小说剧本创作智能体团队  
> 10 位 AI Agent 协作创作 · 自动修订质量门 · 可恢复运行 · 多 Job 并发 · REST API

---

## 🚀 快速开始

### 前置条件

- Python ≥ 3.11
- PCL LLM API（或任何 OpenAI 兼容端点）的 API Key

### 安装

```bash
cd story-studio
pip install -e .          # 主依赖（httpx / pyyaml / fastapi / uvicorn）
pip install -e ".[dev]"   # 含 pytest 开发依赖
```

### 配置密钥

`config/settings.yaml` 已在 `.gitignore` 中，不会进版本库。两种方式注入密钥：

```bash
# 方式 1：复制示例配置后填入
cp config/settings.example.yaml config/settings.yaml
# 编辑 settings.yaml，填入 llm_api_key

# 方式 2：用环境变量（settings.yaml 的 llm_api_key 为空时自动 fallback）
export LLM_API_KEY="sk-..."
```

### 启动

```bash
# 交互模式
python main.py

# 一步创建项目
python main.py --new "写一个发生在赛博朋克东京的侦探故事"

# 提交后台 Job（异步生成整本小说）
python main.py --submit "退役警察能看到的电子记忆" "电子记忆"

# 查看所有 Job
python main.py --jobs

# 启动 REST API（可选）
python -m api
# 或：uvicorn api:app --reload
```

### 交互示例

```
🎬 /new 写一个发生在赛博朋克东京的侦探故事，主角是一个能"看到"电子设备记忆的退役警察
→ 总策划分析需求 → 团队讨论 → 输出创作企划

🎬 /next
→ 世界观架构师构建世界观 → 角色设计师创建角色 → 总策划评审

🎬 /next
→ 总策划生成章节大纲 → 文学顾问提建议 → 标题/钩子/爽点设计师补充

🎬 /next（或 /write 1）
→ 场景编剧写第1章 → 编辑润色 → 连续性检查 → 总策划评审
→ 若评审为 REVISE/REJECT，自动回灌评审意见重写（最多 max_rounds 轮）
→ PASS 后文学顾问生成 ≤200 字章节摘要供后续章节参考

🎬 /status
→ 查看项目状态（含累计 token 成本）
```

---

## 🤖 Agent 团队

10 位 Agent，按角色分两层模型路由（可在 `settings.yaml` 的 `agent_models` 里逐个覆盖）：

| Agent | 角色 | 默认 tier | 职责 |
|-------|------|-----------|------|
| 🎬 **总策划** (Showrunner) | 主编 | main | 任务分配、质量评审、方向把控、终审 |
| 🌍 **世界观架构师** (World Architect) | 设定师 | main | 世界观规则、时间线、地理文化 |
| 👤 **角色设计师** (Character Designer) | 造人 | main | 角色档案、性格、成长弧线 |
| 📖 **场景编剧** (Scene Writer) | 写手 | main | 章节创作、对话、场景描写（可并行多个） |
| ✍️ **编辑** (Editor) | 文案 | light | 文风统一、语言润色、逻辑 |
| 🎯 **文学顾问** (Literary Advisor) | 军师 | light | 叙事结构、技巧推荐、章节摘要生成 |
| 🔍 **连续性检查员** (Continuity Keeper) | 纠错 | light | 时间/角色/世界观一致性 |
| 🏷️ **标题设计师** (Title Designer) | 命名 | light | 书名、章节标题 |
| 🪝 **钩子设计师** (Hooker) | 留客 | light | 章节钩子、悬念 |
| 🔥 **爽点设计师** (Climax Designer) | 高潮 | light | 爽点节奏、高潮设计 |

---

## ✨ 核心特性

### 自动修订质量门
每章写作跑完整流水线 scene → edit → continuity → review。若 Showrunner 评审为 REVISE/REJECT，自动把评审意见回灌给场景编剧重写，最多 `max_rounds` 轮（默认 3）。PASS 或耗尽轮次后交付（耗尽时在标题标 ⚠️ 警告但不卡死流程）。终审同理：非 PASS 循环 final-edit，耗尽时在 `_final.md` 头部插警告但仍交付。

### 可恢复运行
`orchestrator_state.py` 把 phase / current_chapter / total_chapters / project_name / 累计成本持久化到 `{knowledge_dir}/run_state.json`。每次 phase 转换和每章写完都保存。崩溃重启后 `/next` 能从盘上产物推断当前阶段，不丢进度。

### 大模型资源利用率
- **Per-agent 模型路由**：meta 类任务（标题/简介/封面 brief）和 light tier agent 走 `light_model`，核心创作走 `main_model`。
- **RunCost 核算**：每次 `think` 的 token 用量按 model 分桶聚合，`/status` 暴露累计 token 和调用次数。
- **连接池**：`LLMClient` 复用 `httpx.AsyncClient`，避免每次 chat 新建 TCP 连接。
- **章节摘要替代首段**：每章 PASS 后用文学顾问生成 ≤200 字摘要，`build_context` 优先用摘要，无摘要回退首段；总长超 `max_context_chars`（默认 60000）时按章节号倒序裁剪最旧摘要。

### 多 Job 并发 + REST API
`jobs.py` 的 `JobRunner` 管理多个并发小说任务，每任务独立 `knowledge/` + `output/`，`asyncio.Semaphore` 限并发，index 持久化到 `jobs/index.json`。`api.py`（FastAPI）暴露 REST 端点供外部驱动。

### 完稿交付物
`phase_complete` 末尾产出：润色版 `_final.md`、清洗版 `_final.txt`（去 markdown、带扉页和章节标题）、≤500 字内容简介 `_synopsis.txt`、封面 brief JSON + 纯英文提示词。

---

## 📋 命令列表

### 创作流程
| 命令 | 说明 |
|------|------|
| `/new <需求>` | 开始新项目 |
| `/next` | 进入下一阶段（自动从盘上推断当前阶段） |
| `/write [章节号]` | 写指定章节 |
| `/review [章节号]` | 审阅章节 |
| `/revise <章节号> <指令>` | 修订章节 |

### Agent 对话
| 命令 | 说明 |
|------|------|
| `/chat <agent> <消息>` | 直接与某 Agent 对话 |
| `/agents` | 列出所有 Agent |
| `/debate <主题>` | 团队讨论 |

### 知识管理
| 命令 | 说明 |
|------|------|
| `/knowledge` | 知识库状态 |
| `/world` | 查看世界观 |
| `/chars` | 查看角色 |
| `/outline` | 查看大纲 |
| `/continuity` | 连续性日志 |

### 系统
| 命令 | 说明 |
|------|------|
| `/status` | 系统状态（含累计 token 成本） |
| `/jobs` | 列出所有后台 Job |
| `/help` | 帮助 |
| `/exit` `/quit` | 退出 |

### CLI Flags
| Flag | 说明 |
|------|------|
| `--new "<需求>"` | 一步创建新项目 |
| `--status` | 查看项目状态 |
| `--submit "<需求>" [项目名]` | 提交后台 Job |
| `--jobs` | 列出所有后台 Job |
| `--job <id>` | 查看单个 Job 状态 |
| `--job-cancel <id>` | 取消 Job |

### REST API
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/novels` | 提交新小说 Job |
| GET | `/novels` | 列出所有 Job |
| GET | `/novels/{id}` | 查看 Job 状态 |
| GET | `/novels/{id}/chapters/{n}` | 读取某章节正文 |
| POST | `/novels/{id}/revise` | 重写指定章节 |
| DELETE | `/novels/{id}` | 取消/删除 Job |
| GET | `/health` | 健康检查 |

---

## 📁 项目结构

```
story-studio/
├── agents/               # 🧠 Agent 模块
│   ├── base.py           #    Agent 基类（last_usage 拷贝）
│   ├── llm_client.py     #    LLM API 客户端（连接池 + 超时重试 + usage 提取）
│   ├── knowledge.py      #    知识库管理器（原子写 + 章节摘要 + 预算裁剪）
│   ├── text_cleaner.py   #    正文清洗（md→txt）
│   ├── showrunner.py     #    🎬 总策划
│   ├── world_architect.py #   🌍 世界观架构师
│   ├── character_designer.py # 👤 角色设计师
│   ├── scene_writer.py   #    📖 场景编剧
│   ├── editor.py         #    ✍️ 编辑
│   ├── literary_advisor.py #  🎯 文学顾问
│   ├── continuity.py     #    🔍 连续性检查员
│   ├── title_designer.py #    🏷️ 标题设计师
│   ├── hooker.py         #    🪝 钩子设计师
│   └── climax_designer.py #   🔥 爽点设计师
├── config/               # ⚙️ 配置
│   ├── __init__.py       #    StudioConfig + load_config（env fallback）
│   ├── settings.yaml     #    本地配置（gitignored，含密钥）
│   └── settings.example.yaml  # 示例配置
├── knowledge/            # 📚 知识库（gitignored）
├── output/               # 📦 成品输出（gitignored）
├── jobs/                 # 📋 Job 工作目录（gitignored）
├── orchestrator.py       # 🎭 编排器（5 phase + 自动修订 + 状态持久化）
├── orchestrator_state.py # 💾 RunState 持久化
├── jobs.py               # 📋 JobRunner（多并发小说任务）
├── api.py                # 🌐 FastAPI REST API
├── main.py               # 🚀 CLI 入口（交互 + flags）
├── run_yubi.py           # 📖 玉璧之战专用 runner
├── pyproject.toml        # 📦 项目元数据 + 依赖 + pytest 配置
└── ARCHITECTURE.md       # 📐 架构设计
```

---

## ⚙️ 配置

编辑 `config/settings.yaml`（从 `settings.example.yaml` 复制）：

```yaml
backend: "llm"
llm_base_url: "https://llmapi.pcl.ac.cn/v1"
llm_api_key: ""           # 留空则从 LLM_API_KEY 环境变量取
main_model: "DeepSeek-V4-Pro"
light_model: "DeepSeek-V4-Pro"
max_rounds: 3             # 每章自动修订上限
scene_writers: 3          # 并行编剧数量
max_context_chars: 60000  # build_context 字符预算

# 可选：per-agent 模型覆盖
agent_models:
  editor: "deepseek-r1-32b"
```

---

## 🧪 测试

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

覆盖：原子写、连续性哨兵守卫、LLM 客户端（超时重试 / usage / 429 退避）、REPL 鲁棒性、RunState 持久化、自动修订循环、终审硬门、phase 推断、per-agent 模型路由、RunCost 核算、章节摘要 + 预算裁剪、JobRunner、FastAPI API、配置加载。

---

## 📚 Series Projects

### 《破镜之后》

女频长篇批量创作系列工程：

```bash
python3 series/破镜之后/tools/new_variant.py --title "离婚第五年，前夫跪在雨里求我回头" --mode modern --ending no_forgiveness --wound "误会背叛+生死时刻缺席" --years 5
```

### 《不被定义她的主场》

女本位长篇批量创作系列工程：

```bash
python3 series/不被定义她的主场/tools/new_variant.py --title "女钳工她不认命" --mode era --core "六零年代女钳工打破性别工种偏见，成为大国工匠"
```

---

## 🧩 Skills / Tools

### 书籍封面生成

```bash
python3 tools/book_cover_comfy.py --title "关河裂" --subtitle "北朝双雄史诗" --author "Arthur 著" --novel-file "../关河裂_总结.txt" --dry-run
```

详见 `skills/book-cover-generation/SKILL.md`。

---

## 📄 License

MIT
