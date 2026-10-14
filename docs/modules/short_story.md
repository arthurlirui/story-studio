# 短篇生成引擎 (Short Story Engine)

> 番茄小说平台短篇生成管线，独立于 14 Agent 主编排器，支持 14 种类型配置

---

## 文件清单

| 文件 | 职责 | 关键类/函数 |
|------|------|------------|
| `short_story/engine.py` | 短篇生成引擎核心 | `ShortStoryPipeline`, `StoryPlan`, `SectionPlan`, `WorldviewCard`, `StoryResult`, `SkillConfigStore`, `QualityChecker` |
| `short_story/__init__.py` | 包标记 | — |
| `short_story/skill_configs/*.json` | 14 种类型配置 | — |
| `short_story/trend_scout.py` | 跨平台热点信号采集 | `TrendScout`, `TrendSignal`, `TrendReport` |
| `short_story/batch50.py` | 批量 50 篇生成 | — |
| `short_story/run_batch.py` | 批量运行入口 | — |
| `short_story/run_zhihu20.py` | 知乎短篇批量 20 篇 | — |
| `short_story/test_full.py` | 端到端集成测试 | — |
| `short_story/test_quick.py` | 快速冒烟测试 | — |
| `short_story/test_run.py` | 运行测试 | — |

---

## 核心设计

### 三阶段管线

```
_phase_plan → _phase_write → _phase_deai
```

| 阶段 | 说明 |
|------|------|
| `_phase_plan` | LLM 生成 JSON 计划（标题/简介/主角/分节/世界观卡片），`QualityChecker` 验证 |
| `_phase_write` | 逐节生成，携带前节末尾 3 行作为连续性上下文，429 退避重试 |
| `_phase_deai` | 逐节去AI化：先 `deai_pass` 规则清洗，再 LLM 润色 + 字数合规重试/截断 |

### 数据模型

```python
@dataclass
class WorldviewCard:
    time / place / rules / society / golden_finger / mood_curve

@dataclass
class SectionPlan:
    section / scene / word_target / climax_level

@dataclass
class StoryPlan:
    genre / title / synopsis / word_count / pov / protagonist
    sections: list[SectionPlan]
    worldview_card: WorldviewCard
    build_context()  # 组装前节上下文
```

### 字数合规

| 区间 | 行为 |
|------|------|
| 90%-115% (TARGET) | 通过 |
| 80%-130% (ACCEPT) | 通过 |
| 超出 | 附加硬约束重试（最多 `polish_max_attempts` 次），仍超则截断 |
| 不足 | 附加硬约束重试，仍不足则保留原文 |

### 14 种类型配置 (`skill_configs/`)

| 文件 | 类型 | 类别 |
|------|------|------|
| `xianxia.json` | 仙侠 | 男频 |
| `modern_romance.json` | 现代言情 | 女频 |
| `ancient_palace.json` | 古代宫斗 | 女频 |
| `horror_rules.json` | 恐怖规则 | 男频 |
| `urban_system.json` | 都市系统 | 男频 |
| `apocalypse_scifi.json` | 末世科幻 | 男频 |
| `fierce_female.json` | 爽文大女主 | 女频 |
| `folk_occult.json` | 民俗灵异 | 男频 |
| `quick_transmig.json` | 快穿 | 女频 |
| `farming_business.json` | 种田经商 | 女频 |
| `cute_baby.json` | 萌宝 | 女频 |
| `urban_martial.json` | 都市高武 | 男频 |
| `history_kingdom.json` | 历史王国 | 男频 |
| `rebirth_era.json` | 重生年代 | 女频 |

每个配置定义：`category` / `default_pov` / `word_range` / `section_target` / `climax_density` / `section_order`（类型专属节奏序列）/ `golden_fingers` / `title_formulas` / `hook_templates` / `mood_defaults` / `quality_checks`。

### TrendScout（热点侦察）

跨平台采集热榜信号（番茄/起点/七猫/晋江/红果），产出 `TrendReport` 带热度分级和推荐方向。被 `ss short trends` CLI 调用。

---

## 设计决策

1. **独立于主编排器**：短篇不需要 14 Agent 协作，用更轻量的单 LLM 管线
2. **类型配置数据驱动**：领域知识外化到 JSON，不改代码即可新增类型
3. **section_order 节奏序列**：每个类型有专属的故事节拍（如仙侠：废柴羞辱→奇遇激活→首次突破→…→飞升留白）
4. **deai 集成**：复用主项目的 `deai.pipeline.make_engine_from_cfg` + `deai_pass`
5. **提示词懒加载**：`_get_polish_template()` 类级缓存，首次使用才读文件

---

## 依赖关系

```
short_story/engine.py
  ├── deai/ (pipeline.make_engine_from_cfg, deai_pass)
  ├── config/ (StudioConfig, DeaiConfig)
  └── agents/llm_client.py (LLMClient)

short_story/trend_scout.py
  └── agents/tools/web_search.py

cli/short.py ──▶ short_story/engine.py
cli/short_core.py ──▶ short_story/engine.py
```

---

*模块文档版本：v2.0.0 · 对应代码版本：v2.0.0*
