# Story Studio API 文档

FastAPI 后端，提供 REST + SSE 流式接口。启动：

```bash
pip install -e ".[api]"
python -m api              # 或 uvicorn api:app --reload
```

默认端口 8000，可用 `STORY_STUDIO_API_PORT` 环境变量覆盖。

## 鉴权

当 `config/settings.yaml` 的 `api_key` 非空时启用：

- REST 请求：`X-API-Key` 请求头
- SSE 请求：`?api_key=` 查询参数（EventSource 无法设 header）
- `/health`、`/docs`、`/openapi.json` 始终开放

```bash
curl -H "X-API-Key: your-key" http://localhost:8000/novels
```

## CORS

开发模式允许 `http://localhost:3000`（Next.js dev server）跨域。
生产环境前端由 FastAPI 静态托管（同源），CORS 不生效。
可用 `STORY_STUDIO_CORS_ORIGINS` 环境变量配置多个源（逗号分隔）。

## 包结构

```
api/
├── __init__.py    app 构造、CORS、鉴权中间件、lazy JobRunner
├── legacy.py      novels/tasks CRUD（迁移自原 api.py）
├── knowledge.py   知识库读取（outline/world/characters/chapters/cost/quality）
├── series.py      系列与短篇类型只读端点
└── stream.py      SSE 流式端点（token/job进度/agent活动）
```

## REST 端点

### Novels（Job 管理）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/novels` | 提交新小说 Job |
| GET | `/novels` | 列出所有 Job |
| GET | `/novels/{id}` | 查看 Job 状态 |
| DELETE | `/novels/{id}` | 取消 Job |
| GET | `/novels/{id}/chapters/{n}` | 读取某章正文 |
| POST | `/novels/{id}/revise` | 重写指定章节 |
| POST | `/novels/{id}/batch` | 批次并行写作 |

### Tasks（任务清单）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/novels/{id}/tasks` | 任务清单 |
| POST | `/novels/{id}/tasks/{n}/run` | 执行单任务 |
| POST | `/novels/{id}/run-all` | 执行所有任务 |
| POST | `/novels/{id}/resume` | 断点恢复 |

### Knowledge（知识库读取）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/novels/{id}/chapters` | 章节列表（号/标题/字数/去AI分/verdict） |
| GET | `/novels/{id}/knowledge/{tree}` | 知识库子树文件列表（world/characters/story/research） |
| GET | `/novels/{id}/cost` | RunState.cost 汇总（per-model token 桶） |
| GET | `/novels/{id}/quality` | 去AI化质量仪表盘数据 |
| GET | `/novels/{id}/outline` | 大纲全文 |
| GET | `/novels/{id}/world` | 世界观文档列表 + 汇总 |
| GET | `/novels/{id}/characters` | 角色档案列表 + 预览 |

### Series & Genres（只读）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/series` | 系列列表（扫 series/ 目录） |
| GET | `/series/{name}/variants` | 某系列的变体目录 |
| GET | `/genres` | 短篇类型列表 |

## SSE 流式端点

用 `sse-starlette` 的 `EventSourceResponse` 桥接 async generator。

### token 流式生成

```
GET /novels/{id}/stream/{chapter}
```

事件类型：
- `start` - `{"chapter": N}`
- `token` - 生成的文本片段
- `done` - `{"chapter": N}`
- `error` - `{"error": "..."}`

桥接 `llm_client.generate_stream`，客户端用 `EventSource` 或 AI SDK `useChat` 消费。

### Job 进度

```
GET /novels/{id}/events
```

事件类型：
- `progress` - 完整 Job JSON（状态变化时推送）
- `error` - job 消失

轮询 job 状态变化，比客户端 polling 省带宽。Job 终态（succeeded/failed/cancelled）后断开。

### 智能体活动

```
GET /novels/{id}/agents/events
```

事件类型：
- `agent` - WorkLog 条目（agent/action/chapter/verdict/excerpt）
- `done` - `{"status": "..."}`

展示哪个 agent 在 think、做了什么--差异化功能。

### Agent 对话

```
POST /novels/{id}/chat
Body: {"message": "...", "agent": "showrunner"}
```

与指定 agent 流式对话，返回 SSE token 流。

## 客户端示例

```javascript
// REST
const novels = await fetch('/api/novels', {
  headers: { 'X-API-Key': 'your-key' }
}).then(r => r.json());

// SSE token 流
const es = new EventSource('/api/novels/JOB_ID/stream/1?api_key=your-key');
es.addEventListener('token', (e) => {
  document.body.textContent += e.data;
});
es.addEventListener('done', () => es.close());
```
