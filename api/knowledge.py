"""知识库读取端点 - 为前端项目树 / 大纲 / 世界观 / 角色 / 成本 / 质量面板提供数据源。

所有端点只读，不触发 LLM 调用。
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from api.legacy import _build_orch_for_job, get_runner

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
