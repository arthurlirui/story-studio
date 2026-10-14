# 去AI化引擎 (Deai Engine)

> 独立的后处理模块：24 类 AI 写作痕迹检测 + 四层流水线（扫描→规则重写→LLM 重写→审计评分）

---

## 文件清单

| 文件 | 职责 | 关键类/函数 |
|------|------|------------|
| `__init__.py` | 模块入口，双轨哲学说明，re-export `DeaiEngine` | — |
| `engine.py` | 四层流水线核心引擎 | `DeaiEngine`, `ScanResult`, `DeaiReport` |
| `rules.py` | 24 类 AI 痕迹检测规则定义 | `DeaiRule`, `RULES` 列表 |
| `detector.py` | AI 文风检测器（多后端） | `AIDetector`, `AIDetectionResult` |
| `tencent_detector.py` | 腾讯云 AIGC 检测后端 | `TencentAIDetector` |
| `pipeline.py` | 生产阶段封装（CLI/orchestrator 共用） | `make_engine_from_cfg()`, `deai_pass()` |
| `prompts/rewrite_v1.txt` | LLM 重写提示词（版本化） | — |

---

## 核心设计

### 四层流水线 (`DeaiEngine.process`)

```
输入文本
  │
  ▼
┌─────────────────────────────────────────────────┐
│ 层一：规则扫描 (scan)                             │
│  遍历 24 类 RULES，re.findall 检测               │
│  输出：ScanResult 列表（按 severity 降序）        │
│  纯诊断，不修改文本                              │
└──────────────────┬──────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────┐
│ 层二：规则确定性重写 (rewrite_rules)              │
│  2a. DELETE 策略：删除匹配句子                    │
│  2b. WEAKEN 策略：弱化匹配片段                    │
│  2c. 同义词变异（概率 aggr*0.5，仅行首）          │
│  2d. REPLACE 策略：删除高频 AI 词                 │
│  2e. 填充词删除（值得注意的是/事实上…）          │
│  2f. 段落碎片化（6+ 行随机拆分，概率 aggr*0.25）  │
│  2g. 长句拆分（>100 字在逗号处断开，概率 aggr*0.5）│
│  纯确定性，无 LLM 调用                           │
└──────────────────┬──────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────┐
│ 层三：LLM 重写兜底 (rewrite_llm)                  │
│  仅当扫描结果含 STRATEGY_REWRITE 规则时触发       │
│  收集 ≤5 个样本段，加 [N] 锚点                    │
│  填充 prompts/rewrite_{version}.txt 模板          │
│  client.chat() → 解析 [N] 前缀响应 → 替换段       │
│  精确匹配失败时回退到归一化块匹配                  │
└──────────────────┬──────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────┐
│ 层四：反 AI 审计 + 质量评分 (audit)                │
│  重新扫描原文和处理后文本                          │
│  improvement = severity_weighted(原) - (处理后)   │
│  score = 0-50（45=无痕迹, 30+reduction_ratio*20） │
│  评级：≥45 优秀 / ≥35 良好 / <35 需修订           │
└─────────────────────────────────────────────────┘
```

### 24 类检测规则

规则分 4 大类，每条携带 severity (1-5) 和 strategy (replace/delete/weaken/rewrite)：

| 类别 | 规则示例 |
|------|----------|
| content (内容) | 夸大象征意义、通用积极结论、协作交流痕迹 |
| language (语言) | 否定式排比（不仅是…更是…）、填充词、高频 AI 词 |
| style (风格) | 破折号过度使用、句式均匀、段落模板化 |
| comm (交流) | 过度升华、抽象细节、情绪标签 |

### 内置替换表

| 表 | 用途 | 示例 |
|----|------|------|
| `SYNONYM_TABLE` | 同义词变异（概率触发） | 然而→但/可 |
| `WEAKEN_TABLE` | 弱化修饰词 | 无比→很, 极其→很 |
| `FILLER_PATTERNS` | 填充词删除 | 值得注意的是/事实上/不可否认 |

### AI 检测器 (detector.py)

多后端优先级：`tencent` → `huggingface`

| 后端 | 模型/API | 说明 |
|------|----------|------|
| 腾讯云 | `TextModeration` (TEXT_AIGC) | 0.05 元/次，40/s 限流，TC3-HMAC-SHA256 签名 |
| HuggingFace | `AnFerever/chinese-ai-detector-bert` | BERT 分类器，512 token 上限，CUDA/CPU |

`check_before_after()` 对比润色前后 AI 分数，判定 effective/slight/ineffective。

### 生产集成 (pipeline.py)

```python
engine = make_engine_from_cfg(cfg, llm_client)  # cfg.deai.enabled=False → None
processed, audit = deai_pass(engine, original, seed)
```

被三处调用：
- `cli/pipeline_core.py` 的 `run_deai` 阶段
- `orchestrator.py` 的 `phase_complete` 终审质量门
- `short_story/engine.py` 的 `_phase_deai` 阶段

---

## 配置参数

`settings.yaml` 的 `deai` 段：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `enabled` | `true` | false 时 deai 阶段回退裸润色 |
| `aggressiveness` | `0.4` | 0-1 规则重写激进度 |
| `length_min_ratio` | `0.90` | 润色后/前字数比下限 |
| `length_max_ratio` | `1.15` | 润色后/前字数比上限 |
| `polish_max_attempts` | `4` | 短篇逐节润色重试次数 |
| `prompt_version` | `"v1"` | 对应 `prompts/rewrite_{version}.txt` |
| `audit_threshold` | `35` | 终审评分低于此值触发重写 |

全部参数可在前端设置页或 `PUT /config` 配置。

---

## 设计决策

1. **双轨哲学**：去AI化不是只靠后处理——层一（SceneWriter 7 条写作纪律）和层二（Editor 8 维度检测）在生成时预防，deai 引擎是层三的后处理兜底
2. **确定性优先**：层二纯规则不调 LLM，成本低、可复现；LLM 只在需要语义重写时触发
3. **提示词版本化**：`prompt_version` 对应文件路径，可 A/B 测试不同重写策略
4. **可复现 RNG**：`process()` 接受 seed 参数，同 seed 同输入产出相同结果
5. **腾讯云签名自实现**：不依赖 SDK，`sign_v3()` 实现 TC3-HMAC-SHA256

---

## 依赖关系

```
deai/engine.py
  ├── deai/rules.py (RULES, DeaiRule)
  └── agents/llm_client.py (LLM_ERROR_PREFIX, client.chat)

deai/detector.py
  ├── deai/tencent_detector.py (TencentAIDetector)
  └── transformers (lazy, optional)

deai/pipeline.py
  ├── deai/engine.py (DeaiEngine)
  └── config/ (DeaiConfig)
```

---

*模块文档版本：v2.0.0 · 对应代码版本：v2.0.0*
