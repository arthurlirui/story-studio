# 🎭 Story Studio

> 11 位 AI Agent 协作创作 · 去AI化引擎 · 联网搜索 MCP · 自动修订质量门 · REST API

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

11 位 Agent + 1 个去AI化引擎，按角色分两层模型路由：

| Agent | 角色 | tier | 职责 |
|-------|------|------|------|
| 🎬 **总策划** (Showrunner) | 主编 | main | 任务分配、质量评审、方向把控 |
| 🌍 **世界观架构师** | 设定师 | main | 世界观规则、时间线、地理文化 |
| 👤 **角色设计师** | 造人 | main | 角色档案、性格、成长弧线、**语言指纹** |
| 📖 **场景编剧** | 写手 | main | 章节创作、对话、**去AI感写作纪律** |
| ✍️ **编辑** | 文案 | light | 文风统一、**8 维度去AI感检测** |
| 🎯 **文学顾问** | 军师 | light | 叙事结构、技巧推荐、章节摘要 |
| 🔍 **连续性检查员** | 纠错 | light | 时间/角色/世界观一致性 |
| 🏷️ **标题设计师** | 命名 | light | 书名、章节标题（7 种番茄验证公式） |
| 🪝 **钩子设计师** | 留客 | light | 12 种钩子类型、**反模板章尾设计** |
| 🔥 **爽点设计师** | 高潮 | light | 8 大爽点原型、情绪循环调度 |
| 💡 **创新顾问** | 亮点 | light | 题材辨识度优化、反同质化创新 |

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
独立 `deai/` 模块：24 类 AI 写作痕迹检测规则（基于 Humanizer-zh），四层流水线：正则扫描 → 规则确定性重写（删除/弱化/同义词变异/段落碎片化/长句拆分）→ LLM 重写兜底 → 反 AI 审计 + 0-50 质量评分。

---

## 🔍 联网搜索 MCP

项目集成了火山引擎官方 `mcp-server-askecho-search-infinity`，通过 API Key 鉴权接入豆包搜索：

- **工具名**：`mcp__doubao-search__web_search`
- **功能**：中文网页/图片搜索，支持时间范围过滤、权威等级筛选
- **配置**：`~/.zcode/cli/config.json` → `mcp.servers.doubao-search`

---

## 🏗️ 网文方法论

基于番茄小说平台 + 签约作者经验的方法论体系（commit `de71915`），已注入 11 个 Agent 的 system prompt：

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

### REST API + SSE（24 端点，详见 docs/API.md）
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/novels` | 提交新小说 Job |
| GET  | `/novels` | 列出所有 Job |
| GET  | `/novels/{id}` | 查看 Job 状态 |
| GET  | `/novels/{id}/chapters` | 章节列表（含去AI分/verdict） |
| GET  | `/novels/{id}/chapters/{n}` | 读取章节正文 |
| GET  | `/novels/{id}/outline` `/world` `/characters` | 知识库读取 |
| GET  | `/novels/{id}/cost` `/quality` | 成本/质量仪表盘 |
| POST | `/novels/{id}/revise` `/batch` | 重写/批次写作 |
| POST | `/novels/{id}/run-all` `/resume` | 执行/恢复 |
| GET  | `/novels/{id}/stream/{chapter}` | **SSE** token 流式生成 |
| GET  | `/novels/{id}/events` | **SSE** job 进度 |
| GET  | `/novels/{id}/agents/events` | **SSE** 智能体活动 |
| GET  | `/series` `/genres` | 系列/类型列表 |
| GET  | `/health` | 健康检查 |

---

## 📁 项目结构

```
story-studio/
├── agents/               # 🧠 11 个 Agent 模块 + 基础设施
│   ├── base.py           #    Agent 基类
│   ├── llm_client.py     #    LLM API 客户端（连接池 + 超时重试）
│   ├── knowledge.py      #    知识库（双层级：系列 + 变体）
│   ├── text_cleaner.py   #    正文清洗（md→txt）
│   ├── showrunner.py     #    🎬 总策划
│   ├── world_architect.py #   🌍 世界观架构师
│   ├── character_designer.py # 👤 角色设计师（语言指纹）
│   ├── scene_writer.py   #    📖 场景编剧（去AI感 7 条纪律）
│   ├── editor.py         #    ✍️ 编辑（去AI感 8 维度检测）
│   ├── literary_advisor.py #  🎯 文学顾问
│   ├── continuity.py     #    🔍 连续性检查员
│   ├── title_designer.py #    🏷️ 标题设计师
│   ├── hooker.py         #    🪝 钩子设计师（反模板）
│   ├── climax_designer.py #   🔥 爽点设计师
│   ├── innovator.py      #    💡 创新顾问
│   └── style_polisher.py #    🎨 风格润色器（LoRA 莫言风格）
├── deai/                 # 🧹 去AI化引擎
│   ├── __init__.py       #    双轨说明
│   ├── engine.py         #    DeaiEngine（四层流水线）
│   └── rules.py          #    24 类 AI 痕迹检测规则
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
├── knowledge/            # 📚 运行时知识库（gitignored）
├── output/               # 📦 成品输出（gitignored）
├── orchestrator.py       # 🎭 编排器（5 phase + 自动修订）
├── orchestrator_state.py # 💾 RunState 持久化
├── jobs.py               # 📋 JobRunner（多并发）
├── api/                  # 🌐 FastAPI REST + SSE API 包
│   ├── __init__.py       #    app 构造 + CORS + 鉴权
│   ├── legacy.py         #    novels/tasks CRUD
│   ├── knowledge.py      #    知识库读取端点
│   ├── series.py         #    系列/类型只读端点
│   └── stream.py         #    SSE 流式端点
├── cli/                  # 💻 Typer 统一 CLI
│   ├── main.py           #    根 app + 全局选项
│   ├── run.py / jobs.py  #    子命令组
│   ├── novels.py / export.py
│   ├── config_cmd.py / agents.py
│   ├── status.py / repl.py
│   └── _common.py        #    Rich 输出 helpers
├── frontend/             # 🖥️ Next.js + shadcn/ui 前端
│   ├── src/app/          #    仪表盘/小说/章节/任务/设置
│   ├── src/lib/          #    API client + SSE hooks + 类型
│   └── src/components/   #    shadcn UI 组件
├── main.py               # 🚀 兼容入口（委托 cli.main:app）
├── docs/                 # 📖 CLI.md + API.md 文档
├── polish_prompt.txt     # ✨ 独立润色 prompt（含去AI感第 12 条）
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

覆盖：agent 模块、自动修订循环、RunState 持久化、RunCost 核算、章节摘要 + 预算裁剪、文本清洗、LLM 客户端、JobRunner、REST API 等共 330+ 用例。

---

## 📄 License

MIT
