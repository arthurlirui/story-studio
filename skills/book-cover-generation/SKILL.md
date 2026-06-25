# Skill: Book Cover Generation via ComfyUI

> 让 story-studio 智能体在生成小说时，顺带根据作品内容设计封面提示词，并调用本地 ComfyUI 生成「底图 + 中文书名/作者叠字」的小说封面。

## When to use

在以下场景使用本 skill：

1. 完成小说、短篇、章节合集、项目企划后，需要生成封面图。
2. 用户要求“生成封面”“书籍封面”“小说封面”“配图”“发布图”。
3. daily_novels 生成短篇后，需要附带封面。
4. 项目已有以下任一内容：正文、梗概、大纲、世界观、角色设定、风格说明。

## Design principle

不要让 diffusion 模型直接生成书名文字。封面生成分两步：

```text
小说内容 / 大纲 / 风格说明
  → 智能体提炼 cover brief + English visual prompt
  → ComfyUI 生成无字封面底图
  → BookCoverTextOverlay 自定义节点用 Pillow 添加真实中文书名/副标题/作者
  → 输出最终 PNG
```

理由：FLUX/SDXL 直接生成文字不稳定，容易乱码。真实中文标题必须用后处理叠字。

## Required local components

ComfyUI 自定义节点：

```text
/home/openclaw/comfy/ComfyUI/custom_nodes/book_cover_text_overlay.py
```

工作流模板：

```text
story-studio/templates/comfy/book_cover_flux2_klein_with_chinese_text_api.json
```

调用工具：

```text
story-studio/tools/book_cover_comfy.py
```

默认 ComfyUI：

```text
http://127.0.0.1:8188
```

默认模型文件：

```text
models/diffusion_models/flux-2-klein-base-4b-fp8.safetensors
models/text_encoders/qwen_3_4b_fp4_flux2.safetensors
models/vae/flux2-vae.safetensors
models/loras/[FLUX.2.Klein]BookCover_Redmond.safetensors
```

> 注意：当前 BOOKCOVER-REDMOND-FLUXKLEIN LoRA 与 4B base 存在 shape mismatch；工具仍可跑，但 LoRA 不完整生效。未来下载 FLUX.2 Klein 9B 或换 4B 原生 LoRA 后，可只改 workflow 里的模型/LoRA 名称。

## Agent responsibility split

### Showrunner

- 决定是否需要封面。
- 给出封面定位：类型、目标读者、商业感/文学感、是否系列化。
- 审核封面 brief 是否准确体现作品卖点。

### World Architect

- 提供视觉世界观：时代、地点、建筑、道具、势力符号、色彩禁忌。
- 对历史/奇幻/科幻作品尤其重要。

### Character Designer

- 提供可视觉化人物元素：主角剪影、服装、姿态、关键物件。
- 若人物容易被画崩，优先用背影/剪影/局部特写。

### Scene Writer / Editor

- 从正文提炼封面最强场景：第一钩子、高潮场景、核心意象。
- 避免把太多剧情塞进一张图。

### Cover Designer（虚拟角色，可由 Showrunner 扮演）

输出最终 cover brief + Comfy prompt。

## Cover brief schema

智能体应先产出以下 JSON 或 Markdown 字段：

```json
{
  "title": "关河裂",
  "subtitle": "北朝双雄史诗",
  "author": "Arthur 著",
  "genre": "历史小说 / 北朝战争史诗",
  "mood": "苍凉、雄浑、宿命感",
  "core_visual": "黄河、边塞孤城、风沙骑兵、破旧战旗",
  "composition": "竖版书封，中轴构图，中央远景城池，顶部和底部留出安全区",
  "palette": "深铜、墨黑、暗红、冷金",
  "avoid": "不要生成可读文字、不要现代物件、不要西式城堡、不要乱码标题",
  "positive_prompt": "Book cover, premium novel cover artwork, ...",
  "negative_prompt_notes": "no readable text, no fake letters, no watermark, no logo"
}
```

## Prompt rules

### Positive prompt structure

使用英文视觉提示词，结构如下：

```text
Book cover, premium novel cover artwork, [genre], [era/world], [central subject], [symbolic objects], [composition], [title-safe zones], [lighting], [style], [palette], no readable text, no fake letters, no watermark, no logo
```

### Good examples

历史战争：

```text
Book cover, premium novel cover artwork, cinematic Chinese historical fiction, Northern Dynasties war epic, Yellow River frontier fortress under siege, ancient cavalry silhouettes in wind and dust, torn banners, cold mountains, solemn heroic mood, centered fortress and river composition, title-safe empty space at top and bottom, no readable text, no fake letters, no watermark, no logo, dramatic lighting, high detail, painterly realistic illustration, professional publishing cover design, deep bronze, ink black, muted gold and dark red color palette
```

现代现实：

```text
Book cover, contemporary Chinese realist fiction, small county town in summer rain, wet asphalt street, distant exam notice board, lonely teenager silhouette under an umbrella, warm window lights, restrained emotional atmosphere, clean centered composition, empty space for title at top and author at bottom, no readable text, no fake letters, no watermark, cinematic realism, muted blue gray and warm yellow palette
```

悬疑：

```text
Book cover, social suspense novel, dim apartment corridor, one half-open door with cold light leaking out, red thread evidence board motif subtly reflected on wet floor, lonely detective silhouette, oppressive quiet mood, high contrast noir lighting, centered composition, title-safe empty space, no readable text, no fake letters, no watermark, professional thriller cover design, black, gray, sickly green and dark red palette
```

## Tool usage

### From an existing novel text file

```bash
cd /home/openclaw/.openclaw/workspace/story-studio
python3 tools/book_cover_comfy.py \
  --title "关河裂" \
  --subtitle "北朝双雄史诗" \
  --author "Arthur 著" \
  --novel-file "../关河裂_总结.txt" \
  --prompt "Book cover, premium novel cover artwork, ..." \
  --output-dir "output/covers"
```

### From a cover brief JSON

```bash
python3 tools/book_cover_comfy.py --brief path/to/cover_brief.json
```

### Generate prompt only, no Comfy call

```bash
python3 tools/book_cover_comfy.py --title "等分" --novel-file daily_novels/output/xxx.txt --dry-run
```

## Output files

工具会输出：

```text
output/covers/<safe_title>_<timestamp>_workflow.json
output/covers/<safe_title>_<timestamp>_cover.png
output/covers/<safe_title>_<timestamp>_cover_brief.json
```

其中 workflow.json 是注入 title/prompt 后的实际 Comfy API workflow。

## Integration recommendation

在完整小说生成流程中，封面生成应放在：

```text
完稿 / 保存 TXT 或 Markdown
  → 提炼标题、类型、核心意象
  → 生成 cover brief
  → 调用 tools/book_cover_comfy.py
  → 将封面路径写入 meta.json 或 README
```

Daily novel pipeline 可在 `save_novel()` 之后调用此工具，失败不应阻塞正文保存。

## Quality checklist

智能体生成封面前检查：

- [ ] 书名是真实中文，交给 overlay 节点，不写进图像 prompt。
- [ ] prompt 里包含 `no readable text, no fake letters`。
- [ ] 画面有顶部/底部 title-safe space。
- [ ] 只选一个核心视觉，不堆砌太多人物和场景。
- [ ] 色彩与类型匹配。
- [ ] 作者名、出版社等文字用后处理叠加。

生成后检查：

- [ ] 标题可读。
- [ ] 作者位置不贴边。
- [ ] 底图没有明显乱码文字。
- [ ] 构图适合竖版封面缩略图。
- [ ] 输出路径写入项目元数据。
