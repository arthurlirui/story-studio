# 《破镜之后》批量长篇创作流程

## 0. 目标

用 story-studio 的多智能体体系，为《破镜之后》系列批量生成不同主题、不同世界模式、不同结局路线的女频长篇。

每本书独立成项，但共享本系列知识库。

---

## 1. 新建单本项目

```bash
cd /home/openclaw/.openclaw/workspace/story-studio
python3 series/破镜之后/tools/new_variant.py \
  --title "离婚第五年，前夫跪在雨里求我回头" \
  --mode modern \
  --ending no_forgiveness \
  --wound "误会背叛+生死时刻缺席" \
  --years 5 \
  --misunderstanding M02 \
  --power-structure P01 \
  --loss "流产病历被藏、事业被封杀" \
  --plot-engine PE02
```

生成目录：

```text
series/破镜之后/variants/离婚第五年_前夫跪在雨里求我回头/
├── README.md
├── seed.json
├── outline.md
├── characters.md
├── chapter_template.md
├── cover_brief.json
├── continuity_log.md
└── chapters/
```

---

## 2. Agent 分工

### Showrunner / 总策划

输入：`seed.json` + 系列知识库。  
输出：核心卖点、结局路线、四卷结构、每卷爆点。

必须检查：

- 是否从 N 年后切入。
- 伤害严重度是否匹配结局。
- 女主是否有主动权。
- 是否与系列已有项目差异化。

### WorldArchitect / 世界观架构师

输入：`world_modes.md` + mode。  
输出：本书世界规则、权力结构、行业/家族/宗门设定。

必须检查：

- 压迫结构是否具体。
- 旧系统如何伤害女主。
- 女主如何获得新秩序。

### CharacterDesigner / 角色设计师

输入：`character_archetypes.md` + seed。  
输出：女主、旧爱、新男主/盟友、反派、家族系统人物卡。

必须检查：

- 每个人有利益动机。
- 旧爱有明确错处和追悔代价。
- 反派不是降智工具。

### LiteraryAdvisor / 女频类型顾问

输入：`style_guide.md` + 参考书单方向。  
输出：标题优化、第一章钩子、章节末钩子、爽点密度建议。

必须检查：

- 是否有强开篇。
- 是否有女频可读性。
- 台词是否够短、狠、有边界。

### SceneWriter / 章节编剧

输入：大纲 + chapter_template。  
输出：逐章正文。

必须检查：

- 每章至少推进一种变化。
- 旧伤不能一次讲完。
- 女主不能无目的被动受虐。

### Editor / 编辑

输入：章节正文。  
输出：节奏、情绪、爽点、逻辑修订。

必须检查：

- 是否拖沓。
- 是否解释过多。
- 是否钩子不足。

### ContinuityKeeper / 连续性检查员

输入：`continuity_log.md` + 所有章节。  
输出：事实一致性、伏笔回收、角色行为一致性报告。

必须检查：

- 年份、旧伤、证据、关系状态一致。
- 原谅/不原谅逻辑不跳。
- 角色没有突然降智或变性格。

### Cover Designer / 封面设计

输入：本书 seed + outline + cover brief。  
输出：`cover_brief.json`，调用 `tools/book_cover_comfy.py` 生成封面。

---

## 3. 单本长篇生产顺序

```text
1. new_variant.py 新建项目
2. Showrunner 完成核心卖点和四卷结构
3. WorldArchitect 完成本书世界规则
4. CharacterDesigner 完成人物卡
5. LiteraryAdvisor 优化标题和第一章钩子
6. Showrunner 生成 chapter_plan.md
7. SceneWriter 按章节生成正文
8. Editor 分卷修订
9. ContinuityKeeper 更新 continuity_log.md
10. Cover Designer 生成封面
11. 输出 txt/md/pdf 或发布格式
```

---

## 4. 批量选题矩阵

| 编号 | 模式 | 伤害 | 结局 | 标题方向 |
|---|---|---|---|---|
| BMA-001 | modern | 离婚+生死缺席 | 绝不原谅 | 离婚第五年，前夫跪在雨里求我回头 |
| BMA-002 | modern | 带球跑+误会 | 破镜重圆 | 离婚半年才怀，孩子真不是你的 |
| BHA-001 | historical | 为奴+侯府偏心 | 绝不原谅 | 为奴三年后，整个侯府跪求我原谅 |
| BHA-002 | historical | 出宫+帝王牺牲 | 不复合和解 | 出宫后的第五年，陛下悔疯了 |
| BFA-001 | fantasy | 剖丹+师门偏心 | 孤身登顶 | 被剖灵骨后，师尊跪求我回宗 |
| BFA-002 | fantasy | 契约献祭 | 破镜重圆/不原谅 | 断契五年后，神君认出了我的孩子 |

---

## 5. 封面生成

本系列可复用 story-studio 的 ComfyUI 封面工具。

```bash
python3 tools/book_cover_comfy.py \
  --brief series/破镜之后/variants/<项目>/cover_brief.json
```

如果 ComfyUI 未启动：

```bash
cd /home/openclaw/comfy/ComfyUI
source .venv/bin/activate
CUDA_VISIBLE_DEVICES=4 python main.py --listen 127.0.0.1 --port 8188 --gpu-only --disable-auto-launch
```

---

## 6. 每本书启动前的必答问题

1. 女主当年被谁伤害？
2. 伤害发生后，她失去了什么不可逆的东西？
3. N 年后，她获得了什么新身份/新权力？
4. 旧人为什么现在必须找她？
5. 当年真相分几层揭开？
6. 旧人若想被原谅，需要付出什么代价？
7. 主角最终是重圆、不原谅、选择新人，还是独自登顶？

只要这 7 个问题没有答案，不进入正文生成。
