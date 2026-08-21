"""知识库端点 - 为前端项目树 / 大纲 / 世界观 / 角色 / 成本 / 质量面板提供数据源。

只读端点不触发 LLM 调用；大纲 PUT 端点只落盘文件并同步 run_state。
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.legacy import _build_orch_for_job, get_runner
from agents.knowledge import _atomic_write_text
from outline_format import ChapterOutline, OutlineDoc, parse_outline, render_outline

router = APIRouter()


@router.get("/novels/{job_id}/chapters")
async def list_chapters(job_id: str):
    """列出某 job 的所有章节（号、标题、字数、去AI分、verdict）。"""
    runner = get_runner()
    job = runner.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    kd = Path(job.knowledge_dir)
    chap_dir = kd / "story" / "chapters"
    chapters = []
    if chap_dir.exists():
        for f in sorted(chap_dir.glob("chapter_*.md")):
            num = int(f.stem.split("_")[1])
            content = f.read_text(encoding="utf-8")
            # 标题：首个 # 行或首行
            title = ""
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
                if line:
                    title = line[:50]
                    break
            # 读取该章的评审 verdict（若存在）
            verdict = None
            reviews = _load_reviews(kd, num)
            if reviews:
                verdict = reviews[-1].get("verdict")
            # 去AI分（若 polished 存在且有 report）
            score = _load_deai_score(kd, num)
            chapters.append({
                "chapter": num, "title": title, "words": len(content),
                "verdict": verdict, "deai_score": score,
            })
    return {"job_id": job_id, "chapters": chapters}


@router.get("/novels/{job_id}/knowledge/{tree}")
async def get_knowledge_tree(job_id: str, tree: str):
    """返回知识库某子树的文件列表。

    tree 可选：world | characters | story | research
    """
    runner = get_runner()
    job = runner.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    valid = {"world", "characters", "story", "research"}
    if tree not in valid:
        raise HTTPException(status_code=400, detail=f"tree must be one of {valid}")
    kd = Path(job.knowledge_dir)
    sub = kd / tree
    files = []
    if sub.exists():
        for f in sorted(sub.rglob("*.md")):
            rel = f.relative_to(sub)
            files.append({
                "name": str(rel),
                "words": len(f.read_text(encoding="utf-8")),
                "modified": f.stat().st_mtime,
            })
    return {"job_id": job_id, "tree": tree, "files": files}


@router.get("/novels/{job_id}/cost")
async def get_cost(job_id: str):
    """返回 RunState.cost 汇总（per-model token 桶）。"""
    runner = get_runner()
    job = runner.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    kd = Path(job.knowledge_dir)
    state_path = kd / "run_state.json"
    if not state_path.exists():
        return {"job_id": job_id, "cost": None, "message": "无 run_state.json"}
    state = json.loads(state_path.read_text(encoding="utf-8"))
    return {"job_id": job_id, "cost": state.get("cost", {})}


@router.get("/novels/{job_id}/quality")
async def get_quality(job_id: str):
    """去AI化质量仪表盘数据（每章分数 + verdict 分布）。"""
    runner = get_runner()
    job = runner.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    kd = Path(job.knowledge_dir)
    chap_dir = kd / "story" / "chapters"
    chapters = []
    verdict_counts = {"PASS": 0, "REVISE": 0, "REJECT": 0}
    if chap_dir.exists():
        for f in sorted(chap_dir.glob("chapter_*.md")):
            num = int(f.stem.split("_")[1])
            reviews = _load_reviews(kd, num)
            verdict = reviews[-1].get("verdict") if reviews else None
            if verdict in verdict_counts:
                verdict_counts[verdict] += 1
            score = _load_deai_score(kd, num)
            chapters.append({"chapter": num, "verdict": verdict, "deai_score": score})
    return {
        "job_id": job_id,
        "chapters": chapters,
        "verdict_summary": verdict_counts,
        "total_chapters": len(chapters),
    }


@router.get("/novels/{job_id}/outline")
async def get_outline(job_id: str):
    """返回大纲全文。"""
    orch, client = await _build_orch_for_job_id(job_id)
    try:
        outline = orch.knowledge.load_outline()
        return {"job_id": job_id, "outline": outline or ""}
    finally:
        await client.aclose()


# ── 大纲结构化读取/保存（前端大纲编辑器数据源） ────────────────


@router.get("/novels/{job_id}/outline/structured")
async def get_outline_structured(job_id: str):
    """返回解析为结构化 JSON 的大纲（书名/设计说明/逐章五要素）。

    大纲为空时 chapters 为空数组，前端据此进入「从零创建」态。
    """
    kd = _job_knowledge_dir(job_id)
    path = kd / "story" / "outline.md"
    md = path.read_text(encoding="utf-8") if path.exists() else ""
    doc = parse_outline(md)
    return {"job_id": job_id, **_doc_to_json(doc)}


class ChapterPayload(BaseModel):
    num: int = Field(0, description="章号（按列表顺序自动重排）")
    title: str = Field("", max_length=200)
    events: list[str] = Field(default_factory=list)
    characters: list[str] = Field(default_factory=list)
    hook: str = Field("")
    word_estimate: int = Field(2500, ge=0, le=100000)


class OutlineStructuredPayload(BaseModel):
    book_title: str = Field("", max_length=200)
    preamble: str = Field("")
    chapters: list[ChapterPayload] = Field(default_factory=list)


class OutlineSaveRequest(BaseModel):
    """二选一：structured（结构化保存，服务端渲染）或 outline（Markdown 原文保存）。"""

    structured: OutlineStructuredPayload | None = None
    outline: str | None = None


@router.put("/novels/{job_id}/outline")
async def save_outline(job_id: str, req: OutlineSaveRequest):
    """保存大纲（结构化或 Markdown 原文），并同步 run_state 的总章节数。

    渲染格式由 outline_format.render_outline 保证与写作流水线的
    解析器兼容（tests/test_outline_format.py 锁定契约）。
    """
    if req.structured is None and req.outline is None:
        raise HTTPException(status_code=422, detail="structured 与 outline 必须提供其一")

    if req.structured is not None:
        doc = OutlineDoc(
            book_title=req.structured.book_title.strip(),
            preamble=req.structured.preamble.strip(),
            chapters=[
                ChapterOutline(
                    num=i + 1,  # 按列表顺序重排章号
                    title=c.title.strip(),
                    events=[e.strip() for e in c.events if e.strip()],
                    characters=[c.strip() for c in c.characters if c.strip()],
                    hook=c.hook.strip(),
                    word_estimate=c.word_estimate,
                )
                for i, c in enumerate(req.structured.chapters)
            ],
        )
        md = render_outline(doc)
    else:
        md = req.outline

    kd = _job_knowledge_dir(job_id)
    story_dir = kd / "story"
    story_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(story_dir / "outline.md", md)

    parsed = parse_outline(md)
    total_chapters = _sync_run_state_total_chapters(kd, md)
    return {
        "job_id": job_id,
        "saved": True,
        "total_chapters": total_chapters,
        "parsed_chapters": len(parsed.chapters),
        "outline_chars": len(md),
    }


def _job_knowledge_dir(job_id: str) -> Path:
    runner = get_runner()
    job = runner.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return Path(job.knowledge_dir)


def _doc_to_json(doc: OutlineDoc) -> dict:
    return {
        "book_title": doc.book_title,
        "preamble": doc.preamble,
        "chapters": [
            {
                "num": c.num,
                "title": c.title,
                "events": c.events,
                "characters": c.characters,
                "hook": c.hook,
                "word_estimate": c.word_estimate,
            }
            for c in doc.chapters
        ],
    }


def _sync_run_state_total_chapters(kd: Path, md: str) -> int | None:
    """大纲章节数变化时同步 run_state.json 的 total_chapters。

    仅在能从大纲解析出章节数且与现值不同才更新；run_state 不存在则跳过。
    返回同步后的总章节数（无法解析返回 None）。
    """
    from orchestrator import StoryOrchestrator

    parsed_total = StoryOrchestrator._parse_total_chapters(md)
    if parsed_total is None:
        return None
    state_path = kd / "run_state.json"
    if not state_path.exists():
        return parsed_total
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        return parsed_total
    if data.get("total_chapters") == parsed_total:
        return parsed_total
    data["total_chapters"] = parsed_total
    _atomic_write_text(state_path, json.dumps(data, ensure_ascii=False, indent=2))
    return parsed_total


@router.get("/novels/{job_id}/world")
async def get_world(job_id: str):
    """返回世界观文档列表 + 汇总。"""
    orch, client = await _build_orch_for_job_id(job_id)
    try:
        docs = orch.knowledge.list_world_docs()
        summary = orch.knowledge.get_world_summary()
        return {"job_id": job_id, "docs": docs, "summary": summary[:5000]}
    finally:
        await client.aclose()


@router.get("/novels/{job_id}/characters")
async def get_characters(job_id: str):
    """返回角色档案列表 + 各角色内容预览。"""
    orch, client = await _build_orch_for_job_id(job_id)
    try:
        names = orch.knowledge.list_characters()
        chars = []
        for name in names:
            content = orch.knowledge.load_character(name)
            chars.append({"name": name, "preview": content[:500], "words": len(content)})
        return {"job_id": job_id, "characters": chars}
    finally:
        await client.aclose()


async def _build_orch_for_job_id(job_id: str):
    """封装 _build_orch_for_job + job 查找。"""
    runner = get_runner()
    job = runner.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return await _build_orch_for_job(job)


def _load_reviews(kd: Path, chapter: int) -> list[dict]:
    """读取某章的评审记录（chapter_NNN_review.json）。"""
    review_path = kd / "story" / "reviews" / f"chapter_{chapter:03d}_review.json"
    if not review_path.exists():
        return []
    try:
        data = json.loads(review_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        return [data]
    except (json.JSONDecodeError, ValueError):
        return []


def _load_deai_score(kd: Path, chapter: int) -> int | None:
    """从去AI化报告读取该章的质量分（0-50）。

    报告路径：output/deai_report/{name}_ai_report.md
    报告内含 "质量评分: NN" 或 "quality_score: NN" 行。
    """
    report_dir = kd / "output" / "deai_report"
    if not report_dir.exists():
        return None
    for f in report_dir.glob(f"*chapter_{chapter:03d}*_ai_report.md"):
        text = f.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            # 兼容多种格式
            for prefix in ("质量评分", "quality_score", "去AI分", "score"):
                if prefix in line.lower() or prefix in line:
                    digits = "".join(c for c in line if c.isdigit())
                    if digits:
                        return int(digits)
    return None
