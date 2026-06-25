#!/usr/bin/env python3
"""
Book cover generation tool for story-studio.

Pipeline:
  novel/brief -> visual prompt -> ComfyUI workflow -> FLUX cover art -> Pillow Chinese text overlay -> PNG

This tool intentionally keeps title/author out of the diffusion prompt and uses the
BookCoverTextOverlay custom ComfyUI node for real text rendering.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / "templates" / "comfy" / "book_cover_flux2_klein_with_chinese_text_api.json"
DEFAULT_OUTPUT_DIR = ROOT / "output" / "covers"
DEFAULT_COMFY_URL = "http://127.0.0.1:8188"
COMFY_OUTPUT_DIR = Path("/home/openclaw/comfy/ComfyUI/output")


@dataclass
class CoverBrief:
    title: str
    subtitle: str = ""
    author: str = "Arthur 著"
    genre: str = "novel"
    mood: str = "cinematic, emotional"
    core_visual: str = "symbolic central image from the story"
    composition: str = "portrait book cover, centered composition, title-safe empty space at top and bottom"
    palette: str = "muted cinematic color palette"
    avoid: str = "no readable text, no fake letters, no watermark, no logo"
    positive_prompt: str = ""
    seed: int | None = None
    width: int = 768
    height: int = 1152
    steps: int = 20
    title_layout: str = "vertical"
    title_x_percent: float = 50.0
    title_y_percent: float = 36.0
    author_y_percent: float = 85.5
    subtitle_y_percent: float = 75.0
    title_font_size: int = 136
    author_font_size: int = 46
    subtitle_font_size: int = 40
    title_color: str = "#F2D38A"
    author_color: str = "#EEE2C2"
    stroke_color: str = "#160F0A"
    lora_strength: float = 0.85


def safe_filename(s: str, max_len: int = 48) -> str:
    s = re.sub(r"[\\/:*?\"<>|\s]+", "_", s.strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return (s or "untitled")[:max_len]


def read_text(path: str | Path, max_chars: int = 12000) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    text = p.read_text(encoding="utf-8", errors="ignore")
    return text[:max_chars]


def extract_title_from_text(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^#+\s*", "", line)
        line = re.sub(r"^(书名|标题)[:：]\s*", "", line)
        line = re.sub(r"[《》]", "", line)
        if 1 <= len(line) <= 24:
            return line
    return "未命名"


def infer_genre_and_mood(text: str) -> tuple[str, str, str, str]:
    """Small deterministic heuristic. Agents should override with a richer prompt when possible."""
    t = text[:8000]
    rules = [
        (r"北朝|东魏|西魏|高欢|宇文泰|战|城|黄河|骑兵|将军", "Chinese historical war fiction", "solemn, epic, tragic, heroic", "deep bronze, ink black, muted gold, dark red"),
        (r"悬疑|尸体|凶手|警察|侦探|案|真相|门缝|血", "social suspense thriller", "tense, oppressive, mysterious", "black, gray, sickly green, dark red"),
        (r"校园|高考|放榜|同桌|老师|青春|夏天|县城", "contemporary coming-of-age fiction", "warm, bittersweet, nostalgic", "summer blue, warm yellow, soft green, faded white"),
        (r"科幻|AI|机器人|宇宙|飞船|记忆|芯片|未来", "science fiction novel", "vast, lonely, futuristic, philosophical", "deep blue, silver, neon cyan, black"),
        (r"爱情|恋|婚|她|他|心动|离别", "romance novel", "tender, intimate, emotional", "warm rose, cream, dusk purple"),
        (r"志怪|妖|鬼|神|狐|庙|夜|梦", "Chinese supernatural fantasy", "eerie, poetic, ancient, uncanny", "ink black, moon white, cinnabar red, jade green"),
    ]
    for pat, genre, mood, palette in rules:
        if re.search(pat, t):
            return genre, mood, palette, pat
    return "contemporary Chinese literary fiction", "restrained, emotional, cinematic", "muted gray, warm amber, deep blue", "default"


def extract_core_visual(text: str, genre: str) -> str:
    t = text[:10000]
    if "historical" in genre or "war" in genre:
        if re.search(r"玉璧|孤城|城", t):
            return "ancient frontier fortress under siege, wind and dust, distant cavalry silhouettes, torn banners"
        if "黄河" in t:
            return "Yellow River cutting through a cold northern frontier, ancient city walls and cavalry silhouettes"
        return "ancient Chinese battlefield, fortress, banners, cavalry silhouettes, dust and cold mountains"
    if "suspense" in genre:
        return "dim apartment corridor, half-open door, cold light, subtle red evidence thread motif"
    if "coming-of-age" in genre:
        return "small county town in summer, rain-wet street, exam notice board, lonely teenager silhouette"
    if "science fiction" in genre:
        return "solitary human silhouette before a vast futuristic structure, memory fragments and cold light"
    if "romance" in genre:
        return "two distant silhouettes separated by rain and warm window light, intimate emotional atmosphere"
    if "supernatural" in genre:
        return "old temple at night, moonlit mist, subtle foxfire, ancient trees and red talisman motif"
    return "symbolic scene from the story, one lonely figure in a cinematic environment"


def build_prompt(brief: CoverBrief) -> str:
    if brief.positive_prompt.strip():
        prompt = brief.positive_prompt.strip()
    else:
        prompt = (
            f"Book cover, premium novel cover artwork, {brief.genre}, {brief.core_visual}, "
            f"{brief.composition}, {brief.mood}, dramatic lighting, high detail, painterly realistic illustration, "
            f"professional publishing cover design, {brief.palette}, {brief.avoid}"
        )
    # Force text safety even if agent forgot it.
    lower = prompt.lower()
    required = ["no readable text", "no fake letters", "no watermark", "no logo"]
    missing = [x for x in required if x not in lower]
    if missing:
        prompt = prompt.rstrip(" ,.") + ", " + ", ".join(missing)
    return prompt


def brief_from_args(args: argparse.Namespace) -> CoverBrief:
    data: dict[str, Any] = {}
    if args.brief:
        data = json.loads(Path(args.brief).read_text(encoding="utf-8"))

    novel_text = read_text(args.novel_file) if args.novel_file else ""
    if novel_text and not data.get("title") and not args.title:
        data["title"] = extract_title_from_text(novel_text)

    title = args.title or data.get("title") or "未命名"
    subtitle = args.subtitle if args.subtitle is not None else data.get("subtitle", "")
    author = args.author or data.get("author", "Arthur 著")

    if args.prompt:
        data["positive_prompt"] = args.prompt

    if novel_text:
        genre, mood, palette, _ = infer_genre_and_mood(novel_text)
        data.setdefault("genre", genre)
        data.setdefault("mood", mood)
        data.setdefault("palette", palette)
        data.setdefault("core_visual", extract_core_visual(novel_text, genre))

    brief = CoverBrief(
        title=title,
        subtitle=subtitle,
        author=author,
        genre=data.get("genre", "novel"),
        mood=data.get("mood", "cinematic, emotional"),
        core_visual=data.get("core_visual", "symbolic central image from the story"),
        composition=data.get("composition", "portrait book cover, centered composition, title-safe empty space at top and bottom"),
        palette=data.get("palette", "muted cinematic color palette"),
        avoid=data.get("avoid", "no readable text, no fake letters, no watermark, no logo"),
        positive_prompt=data.get("positive_prompt", ""),
        seed=args.seed if args.seed is not None else data.get("seed"),
        width=args.width or int(data.get("width", 768)),
        height=args.height or int(data.get("height", 1152)),
        steps=args.steps or int(data.get("steps", 20)),
        title_layout=args.title_layout or data.get("title_layout", "vertical"),
        lora_strength=float(args.lora_strength if args.lora_strength is not None else data.get("lora_strength", 0.85)),
    )
    # Optional layout/style overrides from JSON only for now.
    for k in [
        "title_x_percent", "title_y_percent", "author_y_percent", "subtitle_y_percent",
        "title_font_size", "author_font_size", "subtitle_font_size",
        "title_color", "author_color", "stroke_color",
    ]:
        if k in data:
            setattr(brief, k, data[k])
    return brief


def load_workflow(template: Path) -> dict[str, Any]:
    return json.loads(template.read_text(encoding="utf-8"))


def inject_workflow(wf: dict[str, Any], brief: CoverBrief, filename_prefix: str) -> dict[str, Any]:
    prompt = build_prompt(brief)
    seed = int(brief.seed if brief.seed is not None else (time.time() * 1000) % 10_000_000_000)

    # Match current template node IDs. Fail loudly if changed.
    wf["2"]["inputs"]["strength_model"] = brief.lora_strength
    wf["5"]["inputs"]["text"] = prompt
    wf["9"]["inputs"]["steps"] = int(brief.steps)
    wf["9"]["inputs"]["width"] = int(brief.width)
    wf["9"]["inputs"]["height"] = int(brief.height)
    wf["10"]["inputs"]["width"] = int(brief.width)
    wf["10"]["inputs"]["height"] = int(brief.height)
    wf["11"]["inputs"]["noise_seed"] = seed

    overlay = wf["14"]["inputs"]
    overlay["title"] = brief.title
    overlay["subtitle"] = brief.subtitle
    overlay["author"] = brief.author
    overlay["title_layout"] = brief.title_layout
    overlay["title_x_percent"] = brief.title_x_percent
    overlay["title_y_percent"] = brief.title_y_percent
    overlay["author_y_percent"] = brief.author_y_percent
    overlay["subtitle_y_percent"] = brief.subtitle_y_percent
    overlay["title_font_size"] = brief.title_font_size
    overlay["author_font_size"] = brief.author_font_size
    overlay["subtitle_font_size"] = brief.subtitle_font_size
    overlay["title_color"] = brief.title_color
    overlay["author_color"] = brief.author_color
    overlay["stroke_color"] = brief.stroke_color

    wf["15"]["inputs"]["filename_prefix"] = filename_prefix
    return wf


def http_json(url: str, data: dict[str, Any] | None = None, timeout: float = 30.0) -> dict[str, Any]:
    if data is None:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ensure_comfy(comfy_url: str) -> None:
    try:
        http_json(comfy_url.rstrip("/") + "/system_stats", timeout=5)
    except Exception as e:
        raise RuntimeError(
            f"ComfyUI is not reachable at {comfy_url}. Start it first, e.g.\n"
            f"  cd /home/openclaw/comfy/ComfyUI && source .venv/bin/activate && "
            f"CUDA_VISIBLE_DEVICES=4 python main.py --listen 127.0.0.1 --port 8188 --gpu-only --disable-auto-launch"
        ) from e


def queue_prompt(comfy_url: str, workflow: dict[str, Any]) -> str:
    payload = {"prompt": workflow, "client_id": str(uuid.uuid4())}
    res = http_json(comfy_url.rstrip("/") + "/prompt", payload, timeout=30)
    if res.get("node_errors"):
        raise RuntimeError(f"Comfy node_errors: {json.dumps(res['node_errors'], ensure_ascii=False)}")
    return res["prompt_id"]


def wait_for_result(comfy_url: str, prompt_id: str, timeout_s: int = 900, poll_s: float = 2.0) -> dict[str, Any]:
    start = time.time()
    while time.time() - start < timeout_s:
        hist = http_json(comfy_url.rstrip("/") + "/history/" + urllib.parse.quote(prompt_id), timeout=20)
        item = hist.get(prompt_id)
        if item:
            status = item.get("status", {})
            if status.get("completed"):
                return item
            if status.get("status_str") == "error":
                raise RuntimeError(f"Comfy execution failed: {json.dumps(status, ensure_ascii=False)}")
        time.sleep(poll_s)
    raise TimeoutError(f"Timed out waiting for Comfy prompt {prompt_id}")


def extract_saved_images(history_item: dict[str, Any]) -> list[dict[str, str]]:
    images: list[dict[str, str]] = []
    for node_out in history_item.get("outputs", {}).values():
        for img in node_out.get("images", []) or []:
            images.append(img)
    return images


def copy_output_image(image_info: dict[str, str], dest: Path) -> Path:
    filename = image_info.get("filename")
    subfolder = image_info.get("subfolder") or ""
    src = COMFY_OUTPUT_DIR / subfolder / filename
    if not src.exists():
        raise FileNotFoundError(src)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate a Chinese-title novel cover through ComfyUI.")
    ap.add_argument("--brief", help="Cover brief JSON file. Fields override inferred defaults.")
    ap.add_argument("--novel-file", help="Novel text/markdown file used for title/genre/prompt inference.")
    ap.add_argument("--title", help="Chinese book title to overlay.")
    ap.add_argument("--subtitle", default=None, help="Subtitle to overlay. Empty string disables it.")
    ap.add_argument("--author", help="Author line to overlay, e.g. 'Arthur 著'.")
    ap.add_argument("--prompt", help="English visual prompt. If omitted, a heuristic prompt is built from novel-file/brief.")
    ap.add_argument("--template", default=str(DEFAULT_TEMPLATE), help="Comfy API workflow template JSON.")
    ap.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory for copied image, brief and workflow.")
    ap.add_argument("--comfy-url", default=os.environ.get("COMFY_URL", DEFAULT_COMFY_URL), help="ComfyUI URL.")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--width", type=int, default=768)
    ap.add_argument("--height", type=int, default=1152)
    ap.add_argument("--steps", type=int, default=20)
    ap.add_argument("--title-layout", choices=["vertical", "horizontal"], default="vertical")
    ap.add_argument("--lora-strength", type=float, default=None)
    ap.add_argument("--dry-run", action="store_true", help="Only write brief/workflow JSON; do not call ComfyUI.")
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args(argv)

    brief = brief_from_args(args)
    brief.positive_prompt = build_prompt(brief)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    stem = f"{safe_filename(brief.title)}_{stamp}"
    filename_prefix = f"story_studio_cover_{safe_filename(brief.title)}_{stamp}"

    wf = inject_workflow(load_workflow(Path(args.template)), brief, filename_prefix)

    brief_path = out_dir / f"{stem}_cover_brief.json"
    workflow_path = out_dir / f"{stem}_workflow.json"
    image_path = out_dir / f"{stem}_cover.png"
    brief_path.write_text(json.dumps(asdict(brief), ensure_ascii=False, indent=2), encoding="utf-8")
    workflow_path.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Brief: {brief_path}")
    print(f"Workflow: {workflow_path}")
    print(f"Prompt: {brief.positive_prompt}")

    if args.dry_run:
        print("Dry run: ComfyUI was not called.")
        return 0

    ensure_comfy(args.comfy_url)
    prompt_id = queue_prompt(args.comfy_url, wf)
    print(f"Comfy prompt_id: {prompt_id}")
    hist = wait_for_result(args.comfy_url, prompt_id, timeout_s=args.timeout)
    imgs = extract_saved_images(hist)
    if not imgs:
        raise RuntimeError("No image outputs found in Comfy history.")
    copy_output_image(imgs[-1], image_path)
    print(f"Cover: {image_path}")

    # Machine-readable final line for callers.
    print(json.dumps({
        "title": brief.title,
        "cover": str(image_path),
        "brief": str(brief_path),
        "workflow": str(workflow_path),
        "prompt_id": prompt_id,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
