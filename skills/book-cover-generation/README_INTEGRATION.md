# Story Studio 封面生成集成指南

本目录把 ComfyUI 书籍封面生成封装成 story-studio 可调用的 skill/tool。

## 文件清单

```text
story-studio/
├── skills/book-cover-generation/SKILL.md
├── skills/book-cover-generation/README_INTEGRATION.md
├── tools/book_cover_comfy.py
├── templates/comfy/book_cover_flux2_klein_with_chinese_text_api.json
└── output/covers/
```

ComfyUI 侧需要：

```text
/home/openclaw/comfy/ComfyUI/custom_nodes/book_cover_text_overlay.py
```

## 手动调用

### 1. ComfyUI 已启动时直接生成

```bash
cd /home/openclaw/.openclaw/workspace/story-studio
python3 tools/book_cover_comfy.py \
  --title "关河裂" \
  --subtitle "北朝双雄史诗" \
  --author "Arthur 著" \
  --novel-file "../关河裂_总结.txt" \
  --output-dir "output/covers"
```

### 2. 只生成 brief/workflow，不调用 Comfy

```bash
python3 tools/book_cover_comfy.py \
  --title "等分" \
  --novel-file "daily_novels/output/2026-06-22_0309_等分.txt" \
  --dry-run
```

### 3. 用智能体自己设计的 prompt

```bash
python3 tools/book_cover_comfy.py \
  --title "关河裂" \
  --subtitle "北朝双雄史诗" \
  --author "Arthur 著" \
  --prompt "Book cover, premium novel cover artwork, cinematic Chinese historical fiction, Northern Dynasties war epic, Yellow River frontier fortress under siege, ancient cavalry silhouettes, title-safe empty space, no readable text, no fake letters, no watermark, no logo, deep bronze and dark red palette" \
  --seed 6222001
```

## 智能体调用协议

Story Studio 智能体在小说完稿后，应先写 `cover_brief.json`，再调用工具。

### cover_brief.json 示例

```json
{
  "title": "关河裂",
  "subtitle": "北朝双雄史诗",
  "author": "Arthur 著",
  "genre": "Chinese historical war fiction",
  "mood": "solemn, epic, tragic, heroic",
  "core_visual": "Yellow River frontier fortress under siege, ancient cavalry silhouettes, torn banners",
  "composition": "portrait book cover, centered fortress and river composition, title-safe empty space at top and bottom",
  "palette": "deep bronze, ink black, muted gold, dark red",
  "avoid": "no readable text, no fake letters, no watermark, no logo",
  "positive_prompt": "Book cover, premium novel cover artwork, cinematic Chinese historical fiction, Northern Dynasties war epic, Yellow River frontier fortress under siege, ancient cavalry silhouettes in wind and dust, torn banners, cold mountains, solemn heroic mood, centered fortress and river composition, title-safe empty space at top and bottom, no readable text, no fake letters, no watermark, no logo, dramatic lighting, high detail, painterly realistic illustration, professional publishing cover design, deep bronze, ink black, muted gold and dark red color palette",
  "seed": 6222001
}
```

调用：

```bash
python3 tools/book_cover_comfy.py --brief path/to/cover_brief.json
```

## 嵌入 daily_novels 的建议

在 `daily_novels/pipeline.py` 的 `save_novel()` 之后可追加：

```python
from pathlib import Path
import subprocess, json

async def maybe_generate_cover(novel_path: Path, meta: dict):
    cmd = [
        "python3", str(WORKSPACE.parent / "tools" / "book_cover_comfy.py"),
        "--title", meta["title"],
        "--subtitle", meta.get("direction", ""),
        "--author", "Arthur 著",
        "--novel-file", str(novel_path),
        "--output-dir", str(WORKSPACE.parent / "output" / "covers"),
    ]
    try:
        proc = subprocess.run(cmd, cwd=str(WORKSPACE.parent), text=True, capture_output=True, timeout=1200)
        if proc.returncode == 0:
            last = proc.stdout.strip().splitlines()[-1]
            cover_info = json.loads(last)
            meta["cover"] = cover_info["cover"]
            return cover_info
    except Exception as e:
        meta["cover_error"] = str(e)
    return None
```

注意：封面失败不应阻塞小说正文保存。

## 启动 ComfyUI

如果工具报 ComfyUI 不可达：

```bash
cd /home/openclaw/comfy/ComfyUI
source .venv/bin/activate
CUDA_VISIBLE_DEVICES=4 python main.py --listen 127.0.0.1 --port 8188 --gpu-only --disable-auto-launch
```

## 模型与 LoRA 更换

默认 workflow 使用：

```text
flux-2-klein-base-4b-fp8.safetensors
qwen_3_4b_fp4_flux2.safetensors
flux2-vae.safetensors
[FLUX.2.Klein]BookCover_Redmond.safetensors
```

换 LoRA 时改：

```json
"2": {
  "class_type": "LoraLoaderModelOnly",
  "inputs": {
    "lora_name": "你的LoRA.safetensors"
  }
}
```

换成 FLUX.2 9B 或其他基座时，复制一份新 workflow 模板，不要直接覆盖默认模板。
