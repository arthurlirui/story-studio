"""
🔥 Trending Words — 热词研究员

职责：
1. 根据小说所处时代/时间点（era）规划 4 类检索查询（网络流行语 / 微博热搜 / 短视频热梗 / 社会热点话题）
2. 调用 WebSearchProvider 拿原始搜索结果
3. 用 LLM 把原始结果综合成结构化热词清单（每条含词、含义、典型用法、出处年代）
4. 通过 KnowledgeStore.save_world + save_research 落盘，供写作阶段按章节 era 查表注入

模型 tier：light（综合总结不需要 main tier 创造力）。
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from agents.base import Agent
from agents.knowledge import KnowledgeStore
from agents.tools.web_search import WebSearchProvider

logger = logging.getLogger(__name__)

# 4 类检索方向（按平台/语境拆分，覆盖文字、热搜、短视频、社会话题）
DEFAULT_QUERIES = [
    ("slang", "网络流行语", "{era} 网络流行语 热梗 年度词语"),
    ("weibo", "微博热搜", "{era} 微博热搜 流行词 话题"),
    ("video", "短视频热梗", "{era} 抖音 B站 热梗 口头禅 流行语"),
    ("society", "社会热点", "{era} 社会热点 话题 事件 流行"),
]

# era slug 化：去掉空格/标点，仅保留中文与字母数字，供文件名使用
_SLUG_RE = re.compile(r"[^\w\u4e00-\u9fff]+")


def _era_slug(era: str) -> str:
    """把时代字符串转成安全文件名片段（如 '2010年代' → '2010年代'）。"""
    return _SLUG_RE.sub("_", era.strip()).strip("_") or "default"


class TrendingWords(Agent):
    """热词研究员 — 按时代检索网络热词并指导场景应用."""

    @property
    def system_prompt(self) -> str:
        return """# 你是谁

你是 **热词研究员 (Trending Words)**，创作团队的语言田野调查员。
你不直接写小说，而是在动笔前把目标时代「当下的人怎么说话」摸清楚。

# 你的职责

1. **检索规划** — 根据给定的时代/时间点（era），拆出 4 类检索方向：
   - 网络流行语（年度词语、热梗、口头禅）
   - 微博热搜（年度流行词、话题标签）
   - 短视频热梗（抖音/B站/快手传播的梗与口头禅）
   - 社会热点（影响语言的社会事件、话题）
2. **结果综合** — 把零散的搜索结果综合成结构化热词清单
3. **落盘沉淀** — 热词清单写入私有知识库，供后续写作阶段按章节时代查表注入

# 热词清单输出格式

每条热词按以下结构输出，整体 ≤2500 字：

```
## {时代} 热词清单

### 流行语 / 热梗

#### 1. {热词}
- **含义**：一句话解释
- **典型用法**：一句话展示在对话或场景里的自然用法
- **出处年代**：该词兴起的时间段
- **适用角色**：哪类身份/年龄段的角色会用（学生/白领/长辈/网民）

#### 2. {热词}
...
```

# 原则

- **标注年代**：每个热词必须标注出处年代，避免时代错位（唐朝角色不该说"yyds"）
- **给用法不给词表**：每条必须给「典型用法」一句，而不是只堆砌词汇——写作者需要知道怎么用，不是知道有哪些
- **区分语境**：标注适用角色身份，学生和长辈不能用同一套梗
- **宁缺毋滥**：搜索结果不足时，用你已有的常识补全，并在清单开头标注「基于模型内置知识，未联网核实」
- **去水**：剔除明显与时代不符、或已退流行的词；保留该时代真正高频、有辨识度的表达
"""


    async def research(
        self,
        era: str,
        web_search: WebSearchProvider,
        knowledge: KnowledgeStore,
        brief: str = "",
        on_usage: Any | None = None,
    ) -> str:
        """检索指定时代的网络热词并综合成结构化清单。

        Args:
            era: 时代/时间点（如 "2010年代" / "南北朝" / "2024年"）
            web_search: 搜索 provider
            knowledge: 私有 KB
            brief: 小说 brief（题材/主题/风格），用于筛选相关热词
            on_usage: 可选回调，每次 think() 后调用（传入 self），用于累加 token 用量。
                不传时，调用方只能在循环结束后看到最后一次 think() 的 self.last_usage，
                会导致多次 think() 的累计丢失。

        Returns:
            结构化热词清单（Markdown 字符串）
        """
        results: list[str] = []
        era_label = era.strip() or "当代"

        for slug, cn_name, query_tpl in DEFAULT_QUERIES:
            query = query_tpl.format(era=era_label)
            logger.info("TrendingWords: 检索 %s ('%s')", slug, query[:60])

            # 1. 搜索
            try:
                hits = await web_search.search(query, count=5)
            except Exception as e:
                logger.warning("TrendingWords: %s 搜索异常: %s", slug, e)
                hits = []

            # 2. 拼接搜索结果块
            sources_block = ""
            if hits:
                src_lines = []
                for i, h in enumerate(hits, 1):
                    src_lines.append(
                        f"{i}. {h.title}\n   摘要：{h.snippet[:300]}\n   来源：{h.url}"
                    )
                sources_block = "\n\n## 原始搜索结果\n\n" + "\n\n".join(src_lines)
            else:
                sources_block = (
                    "\n\n（未取得联网搜索结果，请基于你的常识给出方向性建议，"
                    "并在清单开头标注「基于模型内置知识，未联网核实」）"
                )

            # 3. 综合成该类热词片段
            prompt = (
                f"小说 brief：\n{brief}\n\n"
                f"目标时代/时间点：{era_label}\n"
                f"请针对「{cn_name}」方向检索并整理该时代的网络热词与流行语。"
                f"{sources_block}\n\n"
                f"按系统提示词中的格式输出（每条含词、含义、典型用法、出处年代、适用角色），"
                f"≤800 字。只保留该时代真正高频、有辨识度的表达。"
            )

            try:
                fragment = await self.think(prompt)
                # C2 修复：每次 think() 后立即上报 usage，避免后续 think() 覆盖 last_usage
                if on_usage is not None:
                    result = on_usage(self)
                    if asyncio.iscoroutine(result):
                        await result
            except Exception as e:
                logger.exception("TrendingWords: %s 综合失败: %s", slug, e)
                fragment = f"### {cn_name}\n\n（检索综合失败：{e}）"

            results.append(f"### {cn_name}\n\n{fragment}")

        # 4. 合并四类成总清单
        combined = f"## {era_label} 热词清单\n\n" + "\n\n".join(results)

        # 5. 落盘（世界层 + 调研层双写）
        try:
            knowledge.save_world("trending_words", combined)
        except OSError as e:
            logger.exception("TrendingWords: 保存 trending_words 失败: %s", e)
        try:
            knowledge.save_research(f"trending_{_era_slug(era_label)}", combined)
        except OSError as e:
            logger.exception("TrendingWords: 保存 research 失败: %s", e)

        return combined
