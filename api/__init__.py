"""Story Studio REST API + SSE 流式接口（FastAPI）。

包结构（领域分层，参考 zhanymkanov/fastapi-best-practices）：
- ``api/__init__.py``   组合 app、CORS、鉴权中间件、lazy JobRunner
- ``api/legacy.py``     原 api.py 的 novels/tasks CRUD 端点（迁移自单文件）
- ``api/knowledge.py``  知识库读取端点（outline/world/characters/chapters/cost/quality）
- ``api/series.py``     系列与短篇类型只读端点
- ``api/stream.py``     SSE 流式端点（token 流 / job 进度 / agent 活动）

启动：``python -m api`` 或 ``uvicorn api:app --reload``
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 确保项目根在 sys.path（api 包可能被 uvicorn 直接加载）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 重导出 load_config：测试用 monkeypatch.setattr(api, "load_config", ...) 注入 mock 配置
from config import load_config  # noqa: E402,F401

logger = logging.getLogger(__name__)

# ── 全局 JobRunner（lazy 初始化，与原 api.py 一致）──────────────
_runner: Any | None = None


def get_runner():
    """懒初始化全局 JobRunner。

    复用 config 的 load_config，base_dir 可用 STORY_STUDIO_JOBS_DIR 环境变量覆盖。
    用模块级 load_config（而非函数内 from config import），使测试能
    monkeypatch.setattr(api, "load_config", ...) 注入 mock 配置。
    """
    global _runner
    if _runner is None:
        from jobs import JobRunner
        cfg = load_config()  # 模块级绑定，可被测试 monkeypatch 覆盖
        base_dir = os.environ.get("STORY_STUDIO_JOBS_DIR", "jobs")
        _runner = JobRunner(base_dir=base_dir, cfg=cfg, max_concurrent=2)
    return _runner


def create_app() -> FastAPI:
    """构造 FastAPI app：注册中间件 + 挂载所有 router。"""
    app = FastAPI(
        title="Story Studio API",
        version="1.1",
        description="多 Agent 协作 AI 小说创作平台 REST + SSE 接口",
    )

    # ── CORS：允许前端 dev server（Next.js :3000）跨域调用 ──
    # 生产环境前端由 FastAPI 静态托管（同源），CORS 仅 dev 需要。
    origins = os.environ.get("STORY_STUDIO_CORS_ORIGINS", "http://localhost:3000")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins.split(",")],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── 鉴权中间件（从 legacy 迁移）──
    @app.middleware("http")
    async def api_key_auth(request, call_next):
        from fastapi.responses import JSONResponse
        expected = get_runner().cfg.api_key
        if not expected:
            return await call_next(request)
        path = request.url.path
        # /health /docs /openapi.json 始终开放；SSE 端点也需鉴权
        if path in ("/health", "/", "/docs", "/openapi.json", "/redoc"):
            return await call_next(request)
        # 优先 X-API-Key header；SSE 端点（EventSource 无法设 header）用 query param
        provided = request.headers.get("X-API-Key", "")
        if not provided:
            provided = request.query_params.get("api_key", "")
        if provided != expected:
            return JSONResponse(
                status_code=401,
                content={"detail": "invalid or missing X-API-Key"},
            )
        return await call_next(request)

    # ── 挂载领域 router ──
    from api.legacy import router as novels_router
    from api.knowledge import router as knowledge_router
    from api.series import router as series_router
    from api.stream import router as stream_router

    app.include_router(novels_router, tags=["novels"])
    app.include_router(knowledge_router, tags=["knowledge"])
    app.include_router(series_router, tags=["series"])
    app.include_router(stream_router, tags=["stream"])

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()


def main():
    """``python -m api`` 入口。"""
    import uvicorn
    port = int(os.environ.get("STORY_STUDIO_API_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
