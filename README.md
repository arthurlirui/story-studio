# 🎭 Story Studio

> 14 位 AI Agent 协作创作 · 去AI化引擎 · 联网搜索 + 时代热词 · 自动修订质量门 · REST API · Milkdown 富文本编辑

---

## 🚀 快速开始

### 前置条件

- Python ≥ 3.12
- LLM API Key（OpenAI 兼容端点，如 PCL / 火山方舟 Coding Plan）

### 安装

```bash
cd story-studio
pip install -e .          # 主依赖（httpx / pyyaml / fastapi / uvicorn）
pip install -e ".[dev]"   # 含 pytest 开发依赖
```

### 配置密钥

```bash
# 方式 1：复制示例配置后填入
cp config/settings.example.yaml config/settings.yaml
# 编辑 settings.yaml，填入 llm_api_key

# 方式 2：用环境变量
export LLM_API_KEY="sk-..."

# 联网搜索（豆包/Bocha）key：写入 .env（已被 .gitignore 忽略）
cp .env.example .env
# 编辑 .env，填入 WEB_SEARCH_API_KEY=...
```

### 启动

```bash
# 统一 CLI（推荐）
pip install -e ".[cli]"                    # 安装 ss 命令
ss --help                                  # 查看所有子命令
ss status                                  # 系统状态
ss submit "写一个赛博朋克侦探故事" --name 赛博侦探 --chapters 20
ss repl                                    # 交互式 REPL

# REST API + SSE（后端）
pip install -e ".[api]"
python -m api                              # http://localhost:8000

# Web 前端（Next.js + shadcn/ui）
cd frontend && npm install && npm run dev  # http://localhost:3000

# 向后兼容
python main.py                              # = ss repl
python main.py --new "写一个赛博朋克侦探故事"  # 旧式 flag 仍可用
```

详见 [docs/CLI.md](docs/CLI.md) 和 [docs/API.md](docs/API.md)。

---

## 🤖 Agent 团队

14 位 Agent + 1 个去AI化引擎，按角色分两层模型路由：

| Agent | 角色 | tier | 职责 |
|-------|------|------|------|
| 🎬 **总策划** (Showrunner) | 主编 | main | 任务分配、质量评审、方向把控 |
| 🌍 **世界观架构师** | 设定师 | main | 世界观规则、时间线、地理文化 |
| 👤 **角色设计师** | 造人 | main | 角色档案、性格、成长弧线、**语言指纹** |
| 👤 **角色心理学家** | 造心 | main | 角色深层动机、心理冲突、行为推演 |
| 📖 **场景编剧** | 写手 | main | 章节创作、对话、**去AI感写作纪律** |
| ✍️ **编辑** | 文案 | light | 文风统一、**8 维度去AI感检测** |
| 🎯 **文学顾问** | 军师 | light | 叙事结构、技巧推荐、章节摘要 |
| 🔍 **连续性检查员** | 纠错 | light | 时间/角色/世界观一致性 |
| 🏷️ **标题设计师** | 命名 | light | 书名、章节标题（7 种番茄验证公式） |
| 🪝 **钩子设计师** | 留客 | light | 12 种钩子类型、**反模板章尾设计** |
| 🔥 **爽点设计师** | 高潮 | light | 8 大爽点原型、情绪循环调度 |
| 💡 **创新顾问** | 亮点 | main | 题材辨识度优化、反同质化创新 |
| 🔎 **选题研究员** | 调研 | light | 按选题方向联网搜集素材，存入研究知识库 |
| 🔥 **热词研究员** | 造梗 | light | 按时代检索网络热词（微博/短视频/流行语），注入场景写作 |

---

## ✨ 核心特性

### 自动修订质量门
每章走 **scene → edit → continuity → review** 流水线，Showrunner 评审为 REVISE/REJECT 时自动回灌重写（最多 3 轮），PASS 或耗尽后交付。

### 可恢复运行
`RunState` JSON 持久化 phase / chapter / 成本，崩溃重启后自动推断当前阶段，不丢进度。

### 大模型资源优化
- Per-agent 模型路由（meta 任务走 `light_model`，核心创作走 `main_model`）
- `RunCost` 按 model 分桶聚合 token 用量
- 连接池复用 `httpx.AsyncClient`
- 章节摘要替代首段（≤200 字），总长超预算时按章节倒序裁剪

### 完稿交付
润色版 `_final.md`、清洗版 `_final.txt`、简介 `_synopsis.txt`、封面 brief JSON + 英文提示词

### 大纲结构化编辑
`outline_format.py` 提供大纲 Markdown ↔ 结构化 `OutlineDoc`（书名/设计说明/逐章五要素：标题、核心事件、出场角色、悬念钩子、字数预估）双向转换，解析容错、渲染格式与写作流水线的正则解析器严格兼容（往返一致性由测试锁定）。前端 `/novels/{id}/outline` 页面支持结构化卡片编辑（增删章节、上下移动、折叠、角色标签输入）与 Markdown 源码模式（Milkdown 实时预览）切换，保存时自动重排章号并同步 `run_state.json` 的总章节数。

### 章节富文本编辑 + 自动保存
前端章节页（`/novels/{id}/chapters/{n}`）集成 Milkdown WYSIWYG 编辑器，支持阅读/编辑模式切换。编辑时 1.5s debounce 自动保存到后端，状态指示器实时显示「保存中/已保存/保存失败」；退出编辑前 flush 未保存内容，`beforeunload` 守卫防止意外丢失。流式生成期间禁用编辑。

### 设置页全局配置
`/settings` 页面四 Tab 分区（连接与模型 / 生成流水线 / 调研与润色 / 智能体路由），通过 `GET/PUT /config` 读写 `settings.yaml`。敏感字段（API Key）脱敏只读，只读字段（目录路径）拒绝写入，可写字段白名单校验。去AI化引擎参数（激进度/字数比/审计阈值/重试上限/提示词版本）、多模型润色、14 个智能体的 per-agent 模型路由均可在此配置，保存后热重载使新任务立即生效。

---

## 🧠 去AI感 (deai)

人味 = **不确定 + 不均匀 + 不完美 + 有语言指纹**，三层体系对抗 AI 文的"太确定、太均匀、太完整、千人一腔"：

### 层一：写作内化（生成时预防）
`scene_writer.py` 内置 **7 条最高写作纪律**：
- AI 禁忌词限量表（不禁/顿时/仿佛/宛如 等，每千字 ≤1 次）
- 句式破局（句长爆发度：每 300 字至少 1 个 ≤5 字短句）
- 不确定性与人味毛边（禁场景末尾升华，允许闲笔和"没想明白"）
- 具体细节配额（每章 ≥3 个"无用但具体"的细节）
- 情绪去标签（禁直接命名情绪，全转动作+生理）
- 对话人味（30% 答非所问，吵架抢话叠话）
- 结构反模板（允许一句话成段，钩子形式轮换）

### 层二：编辑审核（生成后检查）
`editor.py` 内置 **8 维度检测清单**（🔴/🟡 分级 + 量化阈值）：词汇痕迹 → 句式均匀 → 段落模板 → 过度升华 → 细节抽象 → 情绪标签 → 对话失真 → 网文套路。附扩充动作替代速查表（10 种情绪 × 多种生理反应）。

### 层三：引擎工具（批量后处理）
独立 `deai/` 模块：24 类 AI 写作痕迹检测规则（基于 Humanizer-zh），四层流水线：正则扫描 → 规则确定性重写（删除/弱化/同义词变异/段落碎片化/长句拆分）→ LLM 重写兜底 → 反 AI 审计 + 0-50 质量评分。模块组成：

| 文件 | 职责 |
|------|------|
| `engine.py` | DeaiEngine 四层流水线（检测→规则重写→LLM 重写→审计评分） |
| `rules.py` | 24 类 AI 痕迹检测 + 确定性重写规则 |
| `detector.py` / `tencent_detector.py` | AI 文风检测器（本地规则 / 腾讯云 API） |
| `pipeline.py` | `make_engine_from_cfg` + `deai_pass` 封装，供 CLI pipeline 调用 |
| `prompts/rewrite_v1.txt` | LLM 重写提示词（版本化，对应 `deai.prompt_version`） |

引擎参数全部可在设置页或 `settings.yaml` 的 `deai` 段配置：`enabled` / `aggressiveness`（0-1 重写激进度）/ `length_min_ratio` / `length_max_ratio`（润色前后字数合规区间）/ `polish_max_attempts`（重试上限）/ `audit_threshold`（终审评分低于此值触发重写）/ `prompt_version`。

---

## 🔍 联网搜索

内置 `agents/web_search.py` 提供统一搜索接口，支持多 provider 工厂切换：

| Provider | 端点 | 说明 |
|----------|------|------|
| `doubao`（默认） | `https://open.feedcoopapi.com/search_api/web_search` | 火山引擎豆包搜索，中文网页/图片搜索 |
| `bocha` | `https://api.bochaai.com/v1/ai/search` | 博查搜索 |
| `mock` | — | 本地桩，无需 API key，返回空结果 |

- **配置**：`config/settings.yaml` 的 `web_search_provider` / `web_search_api_key` / `web_search_endpoint`；`web_search_api_key` 留空时自动回退读取环境变量 `WEB_SEARCH_API_KEY`（见 `.env`）
- **调用**：`agents.web_search.get_search_provider(cfg)` 工厂返回 provider 实例，`await provider.search(query, count)` 返回 `SearchResult` 列表

---

## 🔥 时代热词 (Trending Words)

`agents/research/trending_words.py` 的热词研究员在 Phase 2.5（`trending_enabled=true` 时）按小说所处时代检索 4 类查询：网络流行语 / 微博热搜 / 短视频热梗 / 社会热点话题。每条热词含词、含义、典型用法、出处年代，落盘到 `world/trending_words.md`，在场景写作阶段按章节 era 查表注入——避免唐朝角色说 yyds，为对话提供时代语感。与联网搜索共用 `WebSearchProvider`，无需额外配置。

---

## 🏗️ 网文方法论

基于番茄小说平台 + 签约作者经验的方法论体系（commit `de71915`），已注入 14 个 Agent 的 system prompt：

| 方法论 | 注入位置 | 核心规则 |
|--------|---------|---------|
| 黄金 300 字开篇 | SceneWriter | 3 秒决定去留，300 字内无冲突 = 80% 流失 |
| 对话 60% 黄金比例 | SceneWriter, Editor | 对话占比 60%，旁白 30%，心理 ≤10% |
| 手机排版规范 | SceneWriter, Editor | 每段 1-2 行，段落短但句长有爆发度 |
| 章尾钩子轮换 | Hooker, SceneWriter | 12 种类型 + 4 种黄金模板，全知切换 ≤2 章连续 |
| 爽点密度 500-800 字 | ClimaxDesigner | 节奏铁律：连续 1500 字无收获=失血 |
| 开篇三不做 | SceneWriter | 不铺垫背景、不写天气风景、不信息轰炸 |
| 语言指纹模板 | CharacterDesigner | 口癖/句式习惯/禁词，农民和教授不能一个腔调 |
| 平台数据指标 | Showrunner | 点击率/完读率>15%/追更率>30%/书架比>1:10 |
| 收益模型 | Showrunner | 广告分成 55%、全勤奖、短剧改编最高 300 万 |

---

## 📋 命令列表

### 创作流程
| 命令 | 说明 |
|------|------|
| `/new <需求>` | 开始新项目 |
| `/next` | 进入下一阶段 |
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
| `/help` | 帮助 |

### REST API + SSE（详见 docs/API.md）
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/novels` | 提交新小说 Job |
| GET  | `/novels` | 列出所有 Job |
| GET  | `/novels/{id}` | 查看 Job 状态 |
| GET  | `/novels/{id}/chapters` | 章节列表（含去AI分/verdict） |
| GET  | `/novels/{id}/chapters/{n}` | 读取章节正文 |
| GET  | `/novels/{id}/outline` | 大纲全文（Markdown） |
| GET  | `/novels/{id}/outline/structured` | 大纲结构化 JSON（书名/章节五要素） |
| PUT  | `/novels/{id}/outline` | 保存大纲（结构化或 Markdown，自动同步 run_state） |
| GET  | `/novels/{id}/world` `/characters` | 知识库读取 |
| GET  | `/novels/{id}/cost` `/quality` | 成本/质量仪表盘 |
| POST | `/novels/{id}/revise` `/batch` | 重写/批次写作 |
| POST | `/novels/{id}/run-all` `/resume` | 执行/恢复 |
| GET  | `/novels/{id}/stream/{chapter}` | **SSE** token 流式生成 |
| GET  | `/novels/{id}/events` | **SSE** job 进度 |
| GET  | `/novels/{id}/agents/events` | **SSE** 智能体活动 |
| GET  | `/config` | 读取全局配置（敏感字段脱敏） |
| PUT  | `/config` | 更新配置字段（白名单校验，写回后热重载） |
| GET  | `/config/paths` | 配置文件路径与 jobs 目录（只读） |
| GET  | `/series` `/genres` | 系列/类型列表 |
| GET  | `/health` | 健康检查 |

> **⚠️ 安全提示**：REST API 使用单一 `X-API-Key` header 鉴权（`config/settings.yaml` 的 `api_key` 字段），前端将密钥存储在 localStorage 中。此方案**仅适合本地开发/单用户部署**，不要直接暴露到公网。如需远程访问，请在前面加反向代理 + HTTPS + 额外鉴权层。

---

## 📁 项目结构

```
story-studio/
├── agents/               # 🧠 14 个 Agent 模块 + 基础设施
│   ├── base.py           #    Agent 基类
│   ├── llm_client.py     #    LLM API 客户端（连接池 + 超时重试）
│   ├── ollama_client.py  #    Ollama 本地模型客户端
│   ├── knowledge.py      #    知识库（双层级：系列 + 变体）
│   ├── coordinator.py    #    BatchCoordinator 批次协调
│   ├── utils.py          #    通用工具（章节大纲提取等）
│   ├── worklog.py        #    工作日志记录
│   ├── creative/         #    创作线 Agent（11 个）
│   │   ├── showrunner.py     #    🎬 总策划
│   │   ├── world_architect.py #   🌍 世界观架构师
│   │   ├── character_designer.py # 👤 角色设计师（语言指纹）
│   │   ├── character_psychologist.py # 👤 角色心理学家
│   │   ├── scene_writer.py   #    📖 场景编剧（去AI感 7 条纪律）
│   │   ├── editor.py         #    ✍️ 编辑（去AI感 8 维度检测）
│   │   ├── literary_advisor.py #  🎯 文学顾问
│   │   ├── continuity.py     #    🔍 连续性检查员
│   │   ├── title_designer.py #    🏷️ 标题设计师
│   │   ├── hooker.py         #    🪝 钩子设计师（反模板）
│   │   └── climax_designer.py #   🔥 爽点设计师
│   ├── research/         #    调研线 Agent（3 个）
│   │   ├── topic_researcher.py #  🔎 选题研究员
│   │   ├── innovator.py      #    💡 创新顾问
│   │   └── trending_words.py #    🔥 热词研究员（时代热词注入）
│   └── tools/            #    工具 Agent
│       ├── web_search.py     #    联网搜索（豆包/博查/Mock）
│       ├── style_polisher.py #    🎨 风格润色器（LoRA 莫言风格）
│       ├── multi_polisher.py #    多模型交叉润色
│       └── text_cleaner.py   #    正文清洗（md→txt）
├── deai/                 # 🧹 去AI化引擎
│   ├── __init__.py       #    双轨说明
│   ├── engine.py         #    DeaiEngine（四层流水线）
│   ├── rules.py          #    24 类 AI 痕迹检测规则
│   ├── detector.py       #    本地 AI 文风检测器
│   ├── tencent_detector.py #  腾讯云 AI 检测 API
│   ├── pipeline.py       #    make_engine_from_cfg + deai_pass 封装
│   └── prompts/          #    LLM 重写提示词（版本化）
│       └── rewrite_v1.txt
├── series/               # 📚 系列工程（10 个创作宇宙）
│   ├── 千行百业/          #    现代职业百态
│   ├── 哥伦布计划/        #    西方热门题材短篇
│   ├── 重生穿越/          #    古代逆袭史诗
│   ├── 破镜之后/          #    女频长篇
│   ├── 不被定义她的主场/   #    女本位长篇
│   └── ...               #    知乎短篇 / 抖音创作 / 轮回怪谈 等
├── skills/               # 🎯 11 个可复用技能包
│   ├── ancient-social-drama/
│   ├── ancient-tragic-romance/
│   ├── chapter-hooks/
│   ├── climax-design/
│   ├── moyan-style/       #   莫言风格（含 LoRA）
│   ├── murakami-style/    #   村上春树风格
│   └── ...
├── templates/            # 📋 封面设计模板
├── tools/                # 🔧 ComfyUI 封面生成
├── config/               # ⚙️ 配置
│   ├── settings.yaml     #    运行配置（gitignored）
│   ├── settings.example.yaml # 示例配置
│   └── io.py             #    配置读写共享逻辑（CLI + API 共用）
├── knowledge/            # 📚 运行时知识库（gitignored）
├── output/               # 📦 成品输出（gitignored）
├── orchestrator.py       # 🎭 编排器（6 phase + 自动修订 + 热词注入）
├── orchestrator_state.py # 💾 RunState 持久化
├── outline_format.py     # 📝 大纲 Markdown ↔ 结构化双向转换
├── planner.py            # 📋 任务计划器（phase → task 映射）
├── jobs.py               # 📋 JobRunner（多并发）
├── api/                  # 🌐 FastAPI REST + SSE API 包
│   ├── __init__.py       #    app 构造 + CORS + 鉴权 + lazy JobRunner
│   ├── legacy.py         #    novels/tasks CRUD
│   ├── knowledge.py      #    知识库 + 质量/成本读取端点
│   ├── series.py         #    系列/类型只读端点
│   ├── stream.py         #    SSE 流式端点（token/job/agent）
│   └── config.py         #    配置读写端点（GET/PUT /config）
├── cli/                  # 💻 Typer 统一 CLI
│   ├── main.py           #    根 app + 全局选项
│   ├── run.py / jobs.py  #    子命令组
│   ├── short.py / short_core.py # 短篇命令
│   ├── pipeline_core.py  #    流水线阶段执行（含 deai 阶段）
│   ├── novels.py / export.py
│   ├── config_cmd.py / agents.py
│   ├── status.py / repl.py / health.py
│   └── _common.py        #    Rich 输出 helpers
├── frontend/             # 🖥️ Next.js + shadcn/ui 前端
│   ├── src/app/          #    仪表盘/小说/章节/任务/设置/大纲编辑
│   ├── src/lib/          #    API client + SSE hooks + 类型 + outline-format
│   └── src/components/   #    shadcn UI + Milkdown Markdown 编辑器
├── short_story/          # 📖 短篇生成引擎
├── daily_novels/         # 📅 日常批量生成 pipeline
├── main.py               # 🚀 兼容入口（委托 cli.main:app）
├── docs/                 # 📖 CLI.md + API.md 文档
├── pyproject.toml        # 📦 项目元数据 + [project.scripts] ss
└── ARCHITECTURE.md       # 📐 架构设计
```

---

## 📚 Series Projects

### 《千行百业》
现代真实职业图景，职场百态与时代烟火。10 部职业题材长篇（急诊科医生、机场管制员、手艺传承人……），每部独立 `series_bible`。

### 《哥伦布计划》
西方热门题材 × 短篇核心梗（狼人/吸血鬼/Mafia/西幻），强钩子+强情绪+快节奏。世界观圣经 v2.0，20 个变体短篇。

### 《重生穿越》
"现代失败者穿越古代逆袭"的故事宇宙。11 部互有关联的长篇，宿命论统一框架 + 山冈庄八式半文白风格。

### 《破镜之后》 & 《不被定义她的主场》
女频长篇批量创作——"破镜"系列从伤害后重逢切入，"主场"系列为女本位觉醒叙事。

---

## 🧪 测试

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

覆盖：agent 模块、自动修订循环、RunState 持久化、RunCost 核算、章节摘要 + 预算裁剪、文本清洗、LLM 客户端、JobRunner、REST API、大纲格式解析/渲染往返一致性、去AI化引擎、配置读写等共 525+ 用例。

---

## 📄 License

MIT
