# Agent 层 (Agents)

> 14 位 AI Agent + 基础设施（基类、LLM 客户端、知识库、协调器、工具）

---

## 架构概述

所有 Agent 继承 `Agent` 基类，唯一契约是实现 `system_prompt` 属性。角色知识、行为规范、输出格式全部内化在 system prompt 文本中——不写业务逻辑代码。LLM 客户端通过依赖注入传入（`LLMClient` / `OllamaClient` / `LocalInferenceClient`），鸭子类型接口。

---

## 文件清单

### 基础设施 (`agents/`)

| 文件 | 职责 | 关键类/函数 |
|------|------|------------|
| `__init__.py` | 包入口，re-export 全部公开符号 | — |
| `base.py` | Agent 抽象基类 | `Agent(ABC)` |
| `llm_client.py` | OpenAI 兼容异步 API 客户端 | `LLMClient` |
| `ollama_client.py` | Ollama 本地模型客户端 | `OllamaClient` |
| `local_inference_client.py` | 本地 Qwen+LoRA 推理引擎 | `LocalInferenceClient` |
| `knowledge.py` | 双层级文件知识库 | `KnowledgeStore` |
| `coordinator.py` | 批次并行写作协调器 | `BatchCoordinator` |
| `worklog.py` | JSONL 审计日志 | `WorkLog` |
| `utils.py` | 章节大纲提取工具 | `extract_chapter_outline()` |

### 创作线 Agent (`agents/creative/`)

| 文件 | Agent 名 | 角色 | tier | 核心职责 |
|------|----------|------|------|----------|
| `showrunner.py` | Showrunner | 🎬 总策划 | main | 任务分解、质量评审、方向把控 |
| `world_architect.py` | WorldArchitect | 🌍 世界观架构师 | main | 世界观规则、时间线、地理文化 |
| `character_designer.py` | CharacterDesigner | 👤 角色设计师 | main | 角色档案、性格、成长弧线、语言指纹 |
| `character_psychologist.py` | CharacterPsychologist | 👤 角色心理学家 | main | MBTI/九型人格/依恋类型/防御机制 |
| `scene_writer.py` | SceneWriter | 📖 场景编剧 | main | 章节创作、对话、7 条去AI感写作纪律 |
| `editor.py` | Editor | ✍️ 编辑 | light | 文风统一、8 维度去AI感检测 |
| `literary_advisor.py` | LiteraryAdvisor | 🎯 文学顾问 | light | 叙事结构、技巧推荐、章节摘要 |
| `continuity.py` | ContinuityKeeper | 🔍 连续性检查员 | light | 时间/角色/世界观一致性 |
| `title_designer.py` | TitleDesigner | 🏷️ 标题设计师 | light | 书名/章节标题（7 种验证公式） |
| `hooker.py` | Hooker | 🪝 钩子设计师 | light | 12 种钩子类型、反模板章尾设计 |
| `climax_designer.py` | ClimaxDesigner | 🔥 爽点设计师 | light | 8 大爽点原型、情绪循环调度 |

### 调研线 Agent (`agents/research/`)

| 文件 | Agent 名 | 角色 | tier | 核心职责 |
|------|----------|------|------|----------|
| `topic_researcher.py` | TopicResearcher | 🔎 选题研究员 | light | 联网搜集 4 类素材，存入研究知识库 |
| `innovator.py` | Innovator | 💡 创新顾问 | main | 基于调研生成 5-8 创新亮点 |
| `trending_words.py` | TrendingWords | 🔥 热词研究员 | light | 按时代检索网络热词，注入场景写作 |

### 工具线 (`agents/tools/`)

| 文件 | 职责 | 关键类/函数 |
|------|------|------------|
| `web_search.py` | 联网搜索 provider 抽象 | `WebSearchProvider`, `DoubaoSearchProvider`, `BochaSearchProvider`, `get_search_provider()` |
| `style_polisher.py` | 文学风格润色（LoRA） | `StylePolisher`, `STYLE_REGISTRY` |
| `multi_polisher.py` | 多模型并发润色对比 | `MultiModelPolisher`, `PolishResult` |
| `text_cleaner.py` | Markdown→纯文本清洗 | `clean_chapter_body()`, `strip_existing_title()` |

---

## 核心设计

### Agent 基类

```python
class Agent(ABC):
    def __init__(self, name, role, description, client, model, temperature, max_tokens)
    
    @property
    @abstractmethod
    def system_prompt(self) -> str: ...
    
    async def think(self, prompt, context="", model=None) -> str
    async def review(self, content, instructions="") -> str
    def reset_conversation()
```

- `think()` 组装 system prompt + context + 最近 6 轮对话历史 → `client.chat()`
- `client.last_usage` 拷贝到 `self.last_usage`（成本核算）
- 对话历史上限 50 条，溢出裁剪到最近 30 条
- LLM 错误哨兵（`[LLM API error`）不写入对话历史

### LLMClient

OpenAI 兼容异步客户端，核心特性：

| 特性 | 实现 |
|------|------|
| 连接池 | 懒加载共享 `httpx.AsyncClient` |
| 429 重试 | 指数退避 5-120s，最多 8 次 |
| 超时降级 | 首次超时重试，二次超时减半 max_tokens |
| 传输错误 | `httpx.TransportError` 退避重试 2-30s |
| 流式 | `_stream_chat` 产出 reasoning + content delta |
| 错误哨兵 | 返回 `[LLM API error: ...]` 字符串，不抛异常 |
| Reasoning | 支持 DeepSeek-R1 风格 CoT 字段提取 |

### KnowledgeStore（双层级知识库）

```
{knowledge_dir}/                    ← variant 层（读写）
  world/                            ← 世界观文档
  characters/                       ← 角色档案
  story/
    chapters/                       ← 章节正文
    revisions/                      ← 修订历史
    summaries/                      ← 章节摘要（≤200 字）
    checkpoints/                    ← round 级崩溃恢复
    batch_briefs/                   ← 批次交接 brief
    reviews/                        ← 章节评审 JSON
    agent_worklog.jsonl             ← WorkLog 审计
    outline.md                      ← 大纲
    continuity_log.md               ← 连续性日志
    run_state.json                  ← RunState
  research/                         ← 研究知识库
{series_dir}/                       ← series 层（只读，共享）
  knowledge/world/ ...
  research/ ...
```

- **回退语义**：读取时 variant 有则用 variant，没有则查 series
- **原子写入**：`_atomic_write_text`（tmp + `os.replace`）
- **mtime 缓存**：research / series / world_summary 缓存按 mtime 失效
- **错误哨兵过滤**：LLM 错误标记不写入知识库
- **上下文构建**：`build_context(chapter_num, max_chars=60000)` 分级压缩组装

### BatchCoordinator（批次协调器）

```
plan_batch(start, count)
  → Showrunner 生成 JSON briefs（入场/退场状态/必须揭示/禁止剧透/承接）
  → 持久化到 batch_briefs/
  → 失败降级为空 brief

merge_gate(chapters, batch_id)
  → ContinuityKeeper 跨章一致性审查
  → 返回 VERDICT: PASS|REVISE + JSON 冲突列表
  → 解析失败默认 REVISE（保守）
```

### WebSearchProvider（联网搜索）

三 provider 工厂模式：

| Provider | 端点 | 说明 |
|----------|------|------|
| `DoubaoSearchProvider` | `open.feedcoopapi.com` | 火山引擎豆包搜索，NDJSON 流式 |
| `BochaSearchProvider` | `api.bochaai.com` | 博查搜索 |
| `MockSearchProvider` | — | 本地桩，返回空结果 |

`get_search_provider(cfg)` 按 `cfg.web_search_provider` 工厂返回。任何异常返回空列表 + 警告（不阻断管道）。

---

## 依赖关系

```
agents/creative/* ──▶ agents/base.py ──▶ agents/llm_client.py
agents/research/* ──▶ agents/base.py      agents/ollama_client.py
agents/tools/*    ──▶ agents/base.py      agents/local_inference_client.py

agents/knowledge.py ──▶ agents/llm_client.py (LLM_ERROR_PREFIX)
agents/coordinator.py ──▶ agents/utils.py
agents/tools/web_search.py ──▶ config/ (StudioConfig)
agents/tools/multi_polisher.py ──▶ deai/engine.py (DeaiEngine.audit)
agents/tools/style_polisher.py ──▶ agents/local_inference_client.py
```

---

## 设计决策

1. **Prompt 驱动而非代码驱动**：创作角色是"人"不是"函数"，行为规范用自然语言比代码表达更灵活
2. **错误哨兵而非异常**：LLM 不稳定时优雅降级，不崩溃整个管道
3. **双层级知识库**：同世界观下多部小说共享设定而互不干扰
4. **Research agent 自注入防护**：`KnowledgeStore.get_all_research` 排除 `highlights` 防止 Innovator 读到自己上轮输出
5. **Per-iteration usage callback**：调研 agent 每次 `think()` 后回调 `on_usage`，避免 `last_usage` 被后续调用覆盖
6. **STYLE_REGISTRY 注册模式**：新增写作风格只需注册 LoRA 路径 + prompt，不改代码

---

*模块文档版本：v2.0.0 · 对应代码版本：v2.0.0*
