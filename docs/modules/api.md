# API 层 (FastAPI Backend)

> REST + SSE 流式接口，27 端点，配置读写共享层

---

## 文件清单

| 文件 | 职责 | 关键类/函数 |
|------|------|------------|
| `api/__init__.py` | FastAPI app 构造、CORS、鉴权中间件、lazy JobRunner | `create_app()`, `get_runner()`, `app` |
| `api/legacy.py` | Novels/Tasks CRUD（迁移自原 api.py） | `NovelCreate`, `ChapterSave`, `BatchWrite` |
| `api/knowledge.py` | 知识库读取 + 大纲编辑 + 成本/质量仪表盘 | `_build_orch_for_job_id()` |
| `api/series.py` | 系列/类型只读端点 | — |
| `api/stream.py` | SSE 流式端点（token/job/agent） | `EventSourceResponse` |
| `api/config.py` | 配置读写端点（GET/PUT /config） | `apply_update()` |
| `config/io.py` | 配置读写共享逻辑（CLI + API 共用） | `SENSITIVE`, `READONLY`, `mask_config()` |
| `config/__init__.py` | StudioConfig 数据类 + load_config | `StudioConfig`, `DeaiConfig`, `load_config()` |

---

## 核心设计

### App 构造 (`api/__init__.py`)

```python
create_app()
  → FastAPI(title="Story Studio API", version="1.1")
  → CORS (STORY_STUDIO_CORS_ORIGINS, 默认 localhost:3000)
  → api_key_auth 中间件
  → include_router(legacy, knowledge, series, stream, config)
  → /health 端点
```

**鉴权**：
- `cfg.api_key` 非空时启用
- REST：`X-API-Key` header
- SSE：`?api_key=` query 参数（EventSource 无法设 header）
- `/health`、`/docs`、`/openapi.json` 始终开放

**JobRunner 懒加载**：`get_runner()` 单例，`max_concurrent=2`，base_dir 可通过 `STORY_STUDIO_JOBS_DIR` 环境变量覆盖。

### REST 端点概览

#### Novels（Job 管理） — `api/legacy.py`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/novels` | 提交新小说 Job |
| GET | `/novels` | 列出所有 Job |
| GET | `/novels/{id}` | 查看 Job 状态 |
| DELETE | `/novels/{id}` | 取消 Job |
| GET/PUT | `/novels/{id}/chapters/{n}` | 读取/保存章节正文 |
| POST | `/novels/{id}/revise` | 重写指定章节 |
| POST | `/novels/{id}/batch` | 批次并行写作 |
| GET | `/novels/{id}/tasks` | 任务清单 |
| POST | `/novels/{id}/tasks/{n}/run` | 执行单任务 |
| POST | `/novels/{id}/run-all` | 执行所有任务 |
| POST | `/novels/{id}/resume` | 断点恢复 |

#### Knowledge（知识库 + 大纲编辑） — `api/knowledge.py`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/novels/{id}/chapters` | 章节列表（含去AI分/verdict） |
| GET | `/novels/{id}/knowledge/{tree}` | 知识库子树文件列表 |
| GET | `/novels/{id}/cost` | RunState.cost 汇总 |
| GET | `/novels/{id}/quality` | 去AI化质量仪表盘 |
| GET | `/novels/{id}/outline` | 大纲全文（Markdown） |
| GET | `/novels/{id}/outline/structured` | 大纲结构化 JSON |
| PUT | `/novels/{id}/outline` | 保存大纲（自动同步 run_state） |
| GET | `/novels/{id}/world` | 世界观文档 |
| GET | `/novels/{id}/characters` | 角色档案 |

#### Config — `api/config.py`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/config` | 读取全量配置（敏感字段脱敏） |
| PUT | `/config` | 部分更新（白名单校验，热重载） |
| GET | `/config/paths` | 配置文件路径（只读） |

**PUT /config 白名单**：`backend` / `llm_base_url` / `main_model` / `light_model` / `ollama_host` / `max_rounds` / `scene_writers` / `batch_size` / `max_context_chars` / `merge_gate_rounds` / `rate_limit_delay` / `web_search_provider` / `web_search_endpoint` / `research_enabled` / `research_max_topics` / `trending_enabled` / `multi_polish`（递归合并）/ `deai`（递归合并）/ `agent_models`（整体替换）。

#### Series & Genres — `api/series.py`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/series` | 系列列表 |
| GET | `/series/{name}/variants` | 系列变体目录 |
| GET | `/genres` | 短篇类型列表 |

### SSE 流式端点 — `api/stream.py`

| 端点 | 事件类型 | 说明 |
|------|----------|------|
| `GET /novels/{id}/stream/{chapter}` | `start`/`token`/`done`/`error` | token 流式生成 |
| `GET /novels/{id}/events` | `progress`/`error` | Job 进度推送 |
| `GET /novels/{id}/agents/events` | `agent`/`done` | 智能体活动日志 |
| `POST /novels/{id}/chat` | SSE token 流 | 与指定 Agent 对话 |

- 使用 `sse-starlette` 的 `EventSourceResponse` 桥接 async generator
- `sse-starlette` 未安装时返回 503（`_require_sse()` 守卫）
- 每次 yield 检查 `request.is_disconnected()`

### 配置共享层 (`config/io.py`)

CLI（`ss config`）和 API（`GET/PUT /config`）共用此模块，保证脱敏、类型推断、白名单行为一致。

| 概念 | 说明 |
|------|------|
| `SENSITIVE` | `llm_api_key` / `web_search_api_key` / `api_key` — GET 脱敏，PUT 拒绝 |
| `READONLY` | 路径字段 — 返回原值，PUT 拒绝 |
| `_WRITABLE_SCALARS` | 可编辑的标量字段白名单 |
| `coerce_value()` | 字符串类型推断（true/false→bool, 数字→int/float） |
| `apply_update()` | 合并 patch，返回 `(updated_keys, rejected_keys→reason)` |

### StudioConfig (`config/__init__.py`)

核心配置数据类：

```
StudioConfig
  ├── backend: "llm" | "ollama"
  ├── llm_base_url / llm_api_key / main_model / light_model
  ├── ollama_host
  ├── knowledge_dir / series_knowledge_dir / series_research_dir / output_dir
  ├── max_rounds / scene_writers / max_context_chars / batch_size / merge_gate_rounds
  ├── agent_models: dict[str, str]  (per-agent 模型覆盖)
  ├── web_search_provider / web_search_api_key / web_search_endpoint
  ├── research_enabled / research_max_topics / trending_enabled
  ├── api_key (REST 鉴权)
  ├── multi_polish: MultiPolishConfig
  └── deai: DeaiConfig
```

`load_config(config_dir, create_dirs=True)` 构建 StudioConfig：
- �值 → 覆盖 settings.yaml 值 → 环境变量回退（`LLM_API_KEY` / `WEB_SEARCH_API_KEY` / `STORY_STUDIO_API_KEY`）
- `create_dirs=False` 用于只读命令，避免 mkdir 副作用
- `_load_dotenv()` 无依赖 `.env` 加载器

---

## 设计决策

1. **CLI 和 API 共享 config/io.py**：单一真相源，避免两端白名单/脱敏逻辑分叉
2. **PUT /config 热重载**：写回 settings.yaml 后更新 `runner.cfg = load_config()`，新任务立即生效
3. **SSE 鉴权用 query 参数**：EventSource API 不支持自定义 header，安全妥协
4. **per-job orchestrator 构建**：API 端点为每个请求构建独立 orchestrator + LLMClient，`finally` 中 `aclose()`
5. **大纲 PUT 自动同步**：保存大纲后自动更新 `run_state.total_chapters`，前端和后端数据一致
6. **环境变量回退仅当 yaml 缺键**：yaml 值优先于环境变量

---

## 依赖关系

```
api/__init__.py ──▶ config/ (load_config)
                 ──▶ jobs.py (JobRunner)

api/legacy.py  ──▶ orchestrator.py / planner.py / jobs.py / config/
api/knowledge.py ──▶ orchestrator.py / outline_format.py / agents/knowledge.py
api/stream.py  ──▶ orchestrator.py / agents/llm_client.py / agents/worklog.py
api/config.py  ──▶ config/io.py
api/series.py  ──▶ config/ (无 LLM/无状态)

config/io.py   ──▶ config/__init__.py (load_config, StudioConfig)
```

---

*模块文档版本：v2.0.0 · 对应代码版本：v2.0.0*
