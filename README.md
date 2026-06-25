# 🎭 Story Studio

> 本地模型驱动的小说剧本创作智能体团队  
> 7 位 AI Agent 协作创作 · 零数据外泄 · 完全本地化

---

## 🚀 快速开始

### 前置条件

```bash
# 1. 安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 2. 拉取模型
ollama pull qwen3.6-35b:latest   # 主力推理模型 (~22GB)
ollama pull qwen2.5:7b            # 轻量任务模型 (~4.7GB)

# 3. 启动 Ollama
ollama serve
```

### 启动 Story Studio

```bash
cd story-studio
pip install -r requirements.txt
python main.py
```

### 交互示例

```
🎬 /new 写一个发生在赛博朋克东京的侦探故事，主角是一个能"看到"电子设备记忆的退役警察
→ 总策划分析需求 → 团队讨论 → 输出创作企划

🎬 /next
→ 世界观架构师构建世界观 → 角色设计师创建角色 → 总策划评审

🎬 /next  
→ 总策划生成章节大纲 → 文学顾问提建议

🎬 /write 1
→ 场景编剧写第1章 → 编辑润色 → 连续性检查 → 总策划评审

🎬 /status
→ 查看项目状态
```

---

## 🤖 Agent 团队

| Agent | 角色 | 模型 | 职责 |
|-------|------|------|------|
| 🎬 **总策划** (Showrunner) | 主编 | 35B | 任务分配、质量评审、方向把控 |
| 🌍 **世界观架构师** (World Architect) | 设定师 | 35B | 世界观规则、时间线、地理文化 |
| 👤 **角色设计师** (Character Designer) | 造人 | 35B | 角色档案、性格、成长弧线 |
| 📖 **场景编剧** (Scene Writer) | 写手 | 35B | 章节创作、对话、场景描写 |
| ✍️ **编辑** (Editor) | 文案 | 35B | 文风统一、语言润色、逻辑 |
| 🎯 **文学顾问** (Literary Advisor) | 军师 | 7B | 叙事结构、技巧推荐 |
| 🔍 **连续性检查员** (Continuity Keeper) | 纠错 | 35B | 时间/角色/世界观一致性 |

---

## 📚 Series Projects

### 《破镜之后》

女频长篇批量创作系列工程：

```text
series/破镜之后/
├── knowledge/   # 系列圣经、世界模式、情感矛盾库、人物原型、剧情发动机
├── templates/   # 单本长篇种子、人物卡、章节、大纲、封面 brief 模板
├── variants/    # 每本书/每个主题的独立项目
└── tools/new_variant.py
```

定位：从主角被伤害 N 年后切入，以离婚/分手/断亲/出宫/为奴/离开为起点，可写破镜重圆，也可写绝不原谅、爽打脸和大女主登顶。

快速新建一本：

```bash
python3 series/破镜之后/tools/new_variant.py --title "离婚第五年，前夫跪在雨里求我回头" --mode modern --ending no_forgiveness --wound "误会背叛+生死时刻缺席" --years 5
```

### 《不被定义她的主场》

女本位长篇批量创作系列工程：

```text
series/不被定义她的主场/
├── knowledge/   # 女本位系列圣经、不被定义模式、人物原型、女性关系、冲突发动机
├── templates/   # 单本长篇种子、人物卡、章节、大纲、封面 brief 模板
├── variants/    # 每本书/每个主题的独立项目
└── tools/new_variant.py
```

定位：全方位聚焦女主，以女性成长、女性力量、女性自主为叙事主线；女主不被时代、身份、年龄、职业、婚恋、天赋或失败定义，最终建立自己的主场。

快速新建一本：

```bash
python3 series/不被定义她的主场/tools/new_variant.py --title "女钳工她不认命" --mode era --definition D01+D04 --core "六零年代女钳工打破性别工种偏见，成为大国工匠"
```

---

## 🧩 Skills / Tools

### 书籍封面生成

Story Studio 已集成本地 ComfyUI 封面生成能力：

```text
skills/book-cover-generation/SKILL.md
skills/book-cover-generation/README_INTEGRATION.md
tools/book_cover_comfy.py
templates/comfy/book_cover_flux2_klein_with_chinese_text_api.json
```

用途：小说/短篇完稿后，智能体根据正文、大纲、世界观和角色设定设计封面视觉提示词，调用 ComfyUI 生成无字底图，并用 Pillow 自定义节点自动叠加真实中文书名、作者和副标题。

快速调用：

```bash
python3 tools/book_cover_comfy.py --title "关河裂" --subtitle "北朝双雄史诗" --author "Arthur 著" --novel-file "../关河裂_总结.txt"
```

---

## 📋 命令列表

### 创作流程
| 命令 | 说明 |
|------|------|
| `/new <需求>` | 开始新项目 |
| `/next` | 进入下一阶段 |
| `/write [章节号]` | 写指定章节 |
| `/review <章节号>` | 审阅章节 |
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
| `/status` | 系统状态 |
| `/help` | 帮助 |
| `/exit` | 退出 |

---

## 📁 项目结构

```
story-studio/
├── agents/               # 🧠 Agent 模块
│   ├── base.py           #    Agent 基类
│   ├── ollama_client.py  #    Ollama 推理客户端
│   ├── knowledge.py      #    知识库管理器
│   ├── showrunner.py     #    🎬 总策划
│   ├── world_architect.py #   🌍 世界观架构师
│   ├── character_designer.py # 👤 角色设计师
│   ├── scene_writer.py   #    📖 场景编剧
│   ├── editor.py         #    ✍️ 编辑
│   ├── literary_advisor.py #  🎯 文学顾问
│   └── continuity.py     #    🔍 连续性检查员
├── config/               # ⚙️ 配置
│   ├── __init__.py
│   └── settings.yaml
├── knowledge/            # 📚 知识库 (自动生成)
│   ├── world/            #    世界观文档
│   ├── characters/       #    角色档案
│   └── story/            #    故事进度
│       ├── outline.md
│       ├── chapters/     #    章节
│       └── revisions/    #    修订记录
├── output/               # 📦 成品输出
├── orchestrator.py       # 🎭 编排器
├── main.py               # 🚀 入口
├── ARCHITECTURE.md       # 📐 架构设计
└── requirements.txt
```

---

## ⚙️ 配置

编辑 `config/settings.yaml`:

```yaml
ollama_host: "http://localhost:11434"
main_model: "qwen3.6-35b:latest"    # 主力模型 (大)
light_model: "qwen2.5:7b"           # 轻量模型 (小)
max_rounds: 20
```

---

## 📄 License

MIT
