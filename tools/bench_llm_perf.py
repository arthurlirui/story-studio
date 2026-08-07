"""LLM 模型性能基准 — 面向 story-studio 真实工作负载。

按项目内 LLMClient 实测以下维度：
- TTFT        首 token 延迟（流式）
- stream_tps  流式吞吐（tokens/s，按 chunk 估算）
- small_meta  轻任务延迟（标题/JSON 解析类，~200 tok）
- chapter     真实章节写作（SceneWriter system prompt，max_tokens 4096）
- concurrent  3 路并行章节写作（对应 scene_writers=3 / batch_size=3 的真实拓扑）

用法：
    py -X utf8 tools/bench_llm_perf.py [model ...]
    py -X utf8 tools/bench_llm_perf.py            # 默认跑 settings.yaml 可用全部模型
"""
from __future__ import annotations

import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import load_config  # noqa: E402
from agents.llm_client import LLMClient  # noqa: E402

# ── 测试载荷 ──────────────────────────────────────────────────

_SYS_SCENE_WRITER = "你是 **场景编剧 (Scene Writer)**，创作团队的核心写作者。番茄小说黄金300字开篇、手机排版短段落、章尾钩子。"

PROMPT_SMALL = "为一部都市高武题材网文设计一个书名。只输出书名本身，不超过15字。"

PROMPT_META = (
    "为一部都市高武网文设计第 1-3 章大纲。严格输出 JSON："
    '[{"chapter":1,"title":"...","events":["...","..."],"hook":"..."}]'
)

PROMPT_CHAPTER = (
    "请撰写第 1 章。题材：都市高武。主角陈风，22 岁外卖员，觉醒\'气血感应\'金手指。"
    "开篇 300 字内制造强冲突；对话占比约 60%；段长短句；章末留钩子；1500-3000 字。"
)

# ── 单项测试 ──────────────────────────────────────────────────


async def bench_ttft_and_stream(client: LLMClient, model: str) -> dict:
    """首 token 延迟 + 流式吞吐。"""
    t0 = time.monotonic()
    ttft = None
    chunks = 0
    chars = 0
    async for token in client.generate_stream(
        PROMPT_SMALL, model=model, temperature=0.7, max_tokens=512,
    ):
        if ttft is None:
            ttft = time.monotonic() - t0
        chunks += 1
        chars += len(token)
    total = time.monotonic() - t0
    usage = client.last_usage or {}
    out_tokens = usage.get("completion_tokens") or chars  # 无 usage 时用字符数近似
    gen_time = (total - ttft) if ttft is not None else None
    tps = (out_tokens / gen_time) if gen_time and gen_time > 0 else 0.0
    return {
        "ttft_s": round(ttft or 0, 2),
        "stream_total_s": round(total, 2),
        "completion_tokens": out_tokens,
        "stream_tps": round(tps, 1),
    }


async def bench_nonstream(client: LLMClient, model: str, prompt: str, max_tokens: int) -> dict:
    """非流式端到端延迟。"""
    t0 = time.monotonic()
    out = await client.chat(
        messages=[{"role": "user", "content": prompt}],
        model=model, temperature=0.7, max_tokens=max_tokens,
    )
    total = time.monotonic() - t0
    usage = client.last_usage or {}
    is_error = isinstance(out, str) and out.startswith("[LLM API error")
    return {
        "total_s": round(total, 2),
        "completion_tokens": usage.get("completion_tokens", 0),
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "error": is_error,
        "excerpt": (out or "")[:60].replace("\n", " "),
    }


async def bench_chapter(client: LLMClient, model: str) -> dict:
    """真实章节写作（带 SceneWriter system prompt）。"""
    t0 = time.monotonic()
    out = await client.chat(
        messages=[{"role": "user", "content": PROMPT_CHAPTER}],
        model=model, temperature=0.9, max_tokens=4096,
        system=_SYS_SCENE_WRITER,
    )
    total = time.monotonic() - t0
    usage = client.last_usage or {}
    is_error = isinstance(out, str) and out.startswith("[LLM API error")
    return {
        "total_s": round(total, 2),
        "chars": len(out or ""),
        "completion_tokens": usage.get("completion_tokens", 0),
        "error": is_error,
        "head": (out or "")[:80].replace("\n", " "),
    }


async def bench_concurrent(client: LLMClient, model: str, n: int = 3) -> dict:
    """n 路并行章节写作（模拟批次并行拓扑）。"""
    t0 = time.monotonic()
    tasks = [bench_chapter(client, model) for _ in range(n)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    total = time.monotonic() - t0
    ok = 0
    fails = 0
    worst = 0.0
    for r in results:
        if isinstance(r, Exception):
            fails += 1
            continue
        if r.get("error"):
            fails += 1
        else:
            ok += 1
            worst = max(worst, r["total_s"])
    return {
        "n": n,
        "ok": ok,
        "fail": fails,
        "wall_s": round(total, 2),
        "slowest_s": round(worst, 2),
        "speedup_vs_serial": round(worst * n / total, 2) if total > 0 and ok else 0,
    }


async def run_for_model(cfg, model: str) -> dict:
    client = LLMClient(cfg.llm_base_url, cfg.llm_api_key, model)
    out = {"model": model}
    try:
        out["health"] = await client.check_health()
        out["ttft_stream"] = await bench_ttft_and_stream(client, model)
        out["small"] = await bench_nonstream(client, model, PROMPT_SMALL, 128)
        out["meta_json"] = await bench_nonstream(client, model, PROMPT_META, 1024)
        out["chapter"] = await bench_chapter(client, model)
        out["concurrent3"] = await bench_concurrent(client, model, n=3)
    except Exception as e:  # noqa: BLE001 — 基准报告需要吞异常保证出表
        out["fatal"] = str(e)[:200]
    finally:
        await client.aclose()
    return out


def _fmt(r: dict) -> str:
    lines = [f"\n## {r['model']}  (health={r.get('health')})"]
    if "fatal" in r:
        lines.append(f"  ❌ FATAL: {r['fatal']}")
        return "\n".join(lines)
    s = r["ttft_stream"]
    lines.append(
        f"  TTFT={s['ttft_s']}s  stream={s['stream_total_s']}s "
        f"({s['completion_tokens']}tok, {s['stream_tps']} tok/s)"
    )
    s = r["small"]
    lines.append(f"  small_meta: {s['total_s']}s  ({s['completion_tokens']}tok)  {s['excerpt']}")
    s = r["meta_json"]
    lines.append(f"  meta_json:  {s['total_s']}s  ({s['completion_tokens']}tok)  {s['excerpt']}")
    s = r["chapter"]
    lines.append(
        f"  chapter:    {s['total_s']}s  {s['chars']}字符/{s['completion_tokens']}tok"
        f"{'  ❌ERROR' if s['error'] else ''}"
    )
    lines.append(f"    head: {s['head']}")
    s = r["concurrent3"]
    lines.append(
        f"  concurrent3: wall={s['wall_s']}s ok={s['ok']}/3 fail={s['fail']} "
        f"slowest={s['slowest_s']}s speedup={s['speedup_vs_serial']}x"
    )
    return "\n".join(lines)


async def amain(models: list[str]) -> None:
    cfg = load_config()
    print(f"endpoint: {cfg.llm_base_url}")
    print(f"benchmark models: {', '.join(models)}\n")
    results: list[dict] = []
    for m in models:
        print(f"▶ benching {m} ...", flush=True)
        r = await run_for_model(cfg, m)
        results.append(r)
        print(_fmt(r), flush=True)

    print("\n" + "=" * 70)
    print("汇总（可粘贴到设置决策里）")
    print("=" * 70)
    print(f"{'model':<22} {'TTFT':>6} {'tok/s':>7} {'chapter':>8} {'3并行wall':>10} {'ok':>4}")
    for r in results:
        if "fatal" in r:
            print(f"{r['model']:<22} FATAL {r['fatal'][:50]}")
            continue
        t = r["ttft_stream"]
        c = r["chapter"]
        k = r["concurrent3"]
        print(
            f"{r['model']:<22} {t['ttft_s']:>5.2f}s {t['stream_tps']:>6.1f} "
            f"{c['total_s']:>7.1f}s {k['wall_s']:>9.1f}s {k['ok']:>3}/3"
        )


if __name__ == "__main__":
    cfg = load_config()
    argv = sys.argv[1:]
    models = argv or []
    asyncio.run(amain(models))
