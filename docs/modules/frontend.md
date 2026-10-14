# 前端 (Next.js + shadcn/ui)

> Web 控制面板：仪表盘、小说管理、章节阅读器（流式生成 + Milkdown 编辑）、大纲结构化编辑、设置页

---

## 文件清单

### 配置

| 文件 | 说明 |
|------|------|
| `frontend/package.json` | Next.js 16 + React 19 + TypeScript 5 + Tailwind 4 + shadcn 4 + Milkdown 7 |
| `frontend/next.config.ts` | `/api/*` 代理到 FastAPI 后端（默认 `localhost:8000`） |
| `frontend/AGENTS.md` | Next.js 16 自动生成规则提示 |

### `src/lib/`（核心工具）

| 文件 | 职责 | 关键导出 |
|------|------|----------|
| `api-client.ts` | 统一 fetch 封装，所有请求经 `/api/*` 代理 | `request<T>()`, `listNovels()`, `createNovel()`, `getChapter()`, `saveChapter()`, `getOutline()`, `getConfig()`, `setConfig()` 等 |
| `sse.ts` | SSE hooks（fetch + ReadableStream，不用 EventSource） | `useChapterStream()`, `useJobEvents()`, `useAgentEvents()` |
| `types.ts` | TypeScript 类型（对齐后端数据类） | `Job`, `Chapter`, `TaskPlan`, `OutlineDoc`, `StudioSettings`, `DeaiSettings` |
| `outline-format.ts` | 客户端大纲 Markdown 渲染（对齐后端 `outline_format.py`） | `renderChapter()`, `renderOutline()` |
| `utils.ts` | shadcn `cn()` helper | `cn()` |

### `src/components/`（组件）

| 文件 | 职责 |
|------|------|
| `markdown-editor.tsx` | Milkdown Crepe WYSIWYG 编辑器封装（SSR 禁用，`onChangeRef` 防闭包失效） |
| `app-sidebar.tsx` | 导航侧边栏（5 导航项 + 主题切换） |
| `theme-provider.tsx` | next-themes 主题 Provider |
| `ui/` | 17 个 shadcn/ui 基础组件（badge/button/card/input/label/progress/scroll-area/select/separator/sheet/sidebar/skeleton/switch/table/tabs/textarea/tooltip） |

### `src/hooks/`

| 文件 | 职责 |
|------|------|
| `use-mobile.ts` | `useIsMobile()` 响应式断点 hook |

### `src/app/`（路由页面）

| 路由文件 | 路径 | 功能 |
|----------|------|------|
| `layout.tsx` | — | 根布局：Geist/Geist_Mono/Noto_Serif_SC 字体 + ThemeProvider + Sidebar |
| `page.tsx` | `/` | 仪表盘：统计卡片 + Job 表格 + 健康徽章 + 条件轮询 |
| `novels/page.tsx` | `/novels` | 小说项目卡片网格 |
| `novels/new/page.tsx` | `/novels/new` | 创建表单（brief/名称/章数/写作模式） |
| `novels/[id]/page.tsx` | `/novels/{id}` | 项目详情：Phase 步进器 + 5 Tab（章节/大纲/角色/智能体/成本）+ SSE 实时更新 |
| `novels/[id]/outline/page.tsx` | `/novels/{id}/outline` | 大纲编辑器：结构化卡片模式 + Markdown 源码模式切换 |
| `novels/[id]/chapters/page.tsx` | `/novels/{id}/chapters` | 章节地图 + 去AI分热力图 |
| `novels/[id]/chapters/[n]/page.tsx` | `/novels/{id}/chapters/{n}` | 章节阅读器 + 编辑器（流式生成 + Milkdown + 1.5s debounce 自动保存） |
| `jobs/page.tsx` | `/jobs` | 后台任务队列表 |
| `settings/page.tsx` | `/settings` | 全局配置：4 Tab（连接模型/生成流水线/调研润色/智能体路由） |
| `error.tsx` | — | 错误边界（带重试） |
| `loading.tsx` | — | 加载骨架屏 |

---

## 核心设计

### API Client (`api-client.ts`)

- 所有请求经 `/api/*` 前缀（Next.js dev proxy → FastAPI）
- `X-API-Key` 从 `localStorage["story_studio_api_key"]` 读取
- `setApiKey()` / `getStoredApiKey()` 管理本地密钥

### SSE Hooks (`sse.ts`)

**不用 `EventSource`**——改用 `fetch` + `ReadableStream`，以在 header 中传递 `X-API-Key`（安全决策：避免 key 出现在 URL query/日志/Referer）。

| Hook | 说明 | 性能优化 |
|------|------|----------|
| `useChapterStream(jobId, chapter)` | token 流式生成 | `requestAnimationFrame` 节流，避免逐 token re-render |
| `useJobEvents(jobId)` | Job 进度 SSE | — |
| `useAgentEvents(jobId)` | 智能体活动日志 | microtask 延迟 setState 避免 effect 同步警告 |

### 大纲编辑器 (`novels/[id]/outline/page.tsx`)

双模式编辑：
- **结构化模式**：逐章卡片（标题/事件列表/角色标签/钩子/字数预估），增删/上下移动/折叠/自动重排章号
- **源码模式**：Milkdown Markdown 编辑器，`renderOutline()` 实时预览
- Dirty 追踪：JSON stringify 比较；`beforeunload` 守卫
- 保存后自动重载结构化数据

### 章节编辑器 (`novels/[id]/chapters/[n]/page.tsx`)

- `useChapterStream` 实时 token 流式生成（闪烁光标）
- 编辑模式：Milkdown + 1.5s debounce 自动保存
- 保存状态指示器：idle / saving / saved / error
- `beforeunload` dirty 守卫
- 流式生成期间禁用编辑
- 上一章/下一章导航
- 去AI分进度条

### 设置页 (`settings/page.tsx`)

4 Tab 分区：

| Tab | 配置项 |
|-----|--------|
| 连接与模型 | backend / LLM base URL / main/light model / Ollama host / API key / 健康检查 |
| 生成流水线 | max_rounds / scene_writers / batch_size / context budget / merge gate rounds / rate limit |
| 调研与润色 | web search provider/endpoint / research/trending 开关 / multi-polish / deai 引擎全部参数 |
| 智能体路由 | 14 个 agent 的 per-agent 模型覆盖（main/light tier 徽章） |

保存时只提交变更字段的 patch。

---

## 设计决策

1. **SSE 用 fetch 不用 EventSource**：API key 不入 URL，安全优先
2. **requestAnimationFrame 节流**：token 流每帧最多一次 re-render，避免高频更新卡顿
3. **Milkdown 动态导入 `ssr: false`**：ProseMirror 不支持 SSR
4. **`onChangeRef` 防闭包失效**：Milkdown 编辑器的 onChange 回调用 ref 而非闭包捕获
5. **outline-format.ts 镜像后端**：前端渲染是预览用途，后端是保存的 source of truth（`tests/test_outline_format.py` 锁定契约）
6. **`Promise.allSettled` 容错并行加载**：单个请求失败不阻塞其他数据加载

---

## 依赖关系

```
frontend/src/lib/api-client.ts ──HTTP──▶ api/ (FastAPI)
frontend/src/lib/sse.ts ────────SSE─────▶ api/stream.py
frontend/src/lib/types.ts ──镜像──▶ 后端数据类 (Job/Chapter/OutlineDoc/StudioSettings)
frontend/src/lib/outline-format.ts ──镜像──▶ outline_format.py
frontend/src/components/markdown-editor.tsx ──▶ @milkdown/crepe
```

---

*模块文档版本：v2.0.0 · 对应代码版本：v2.0.0*
