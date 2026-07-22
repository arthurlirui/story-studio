"""
🔬 Topic Researcher — 热点研究员

职责：
1. 根据小说 brief 规划 4 类检索查询（热点事件 / 重要事件 / 同类小说 / 创作手法）
2. 调用 WebSearchProvider 拿原始搜索结果
3. 用 LLM 把原始结果综合成结构化调研报告（每类 ≤2000 字）
4. 通过 KnowledgeStore.save_research 写入私有 KB

模型 tier：light（综合总结不需要 main tier 创造力）。
"""
from __future__ import annotations

import logging
from typing import Any

from agents.base import Agent
from agents.knowledge import KnowledgeStore
from agents.web_search import WebSearchProvider

logger = logging.getLogger(__name__)

# 4 类调研主题（与 cfg.research_max_topics 对应，默认 4）
DEFAULT_TOPICS = [
    ("hot_events", "热点事件", "当下社会民生热点、流行话题、舆论焦点"),
    ("important_events", "重要事件", "近期影响深远的事件、政策、行业变化"),
    ("similar_novels", "同类小说", "题材/主题相似的优秀小说、网文、影视作品"),
    ("creation_techniques", "创作手法", "同类题材的创作技巧、叙事结构、亮点设计手法"),
]


class TopicResearcher(Agent):
    """热点研究员."""

    @property
    def system_prompt(self) -> str:
        return """# 你是谁

你是 **热点研究员 (Topic Researcher)**，创作团队的调研专家。
你不直接创作小说，而是在动笔之前把当下世界"看清楚"。

# 你的职责

1. **检索规划** — 根据小说 brief 拆出 4 类检索方向：
   - 热点事件（社会民生、舆论焦点）
   - 重要事件（影响深远的事件 / 政策 / 行业变化）
   - 同类小说（题材相似的作品，含网文与影视）
   - 创作手法（同类题材的叙事技巧与亮点设计）
2. **结果综合** — 把零散的搜索结果综合成结构化调研报告
3. **落盘沉淀** — 每类报告写入私有知识库，供后续创新 / 策划 / 写作阶段引用

# 调研报告输出格式

每类报告 ≤2000 字，结构如下：

```
## {主题分类名}

### 关键发现
- 1-3 条核心事实 / 趋势，附来源链接

### 细节
- 补充事实、数据、案例

### 对本作的启示
- 这条信息对本小说创作的具体启发（题材选择 / 角色塑造 / 冲突设计 / 亮点创新）
```

# 原则

- **客观**：陈述事实，不夸大；不确定的信息标注"待核实"
- **相关**：每条信息都要回答"对本作有什么用"
- **简练**：每篇 ≤2000 字，宁缺毋滥
- **降级**：若搜索结果为空，用你已有的常识给出方向性建议，并在报告开头标注"基于模型内置知识，未联网核实"
"""


    async def research(
        self,
        brief: str,
        web_search: WebSearchProvider,
        knowledge: KnowledgeStore,
        topics: list[tuple[str, str, str]] | None = None,
        on_usage: Any | None = None,
    ) -> dict[str, dict[str, Any]]:
        """执行一轮调研。

        Args:
            brief: 小说 brief（题材 / 主题 / 风格描述）
            web_search: 搜索 provider
            knowledge: 私有 KB
            topics: [(topic_slug, 中文名, 描述)]，缺省用 DEFAULT_TOPICS
            on_usage: 可选回调，每次 think() 后调用（传入 self），用于累加 token 用量。
                不传时，调用方只能在循环结束后看到最后一次 think() 的 self.last_usage，
                会导致多次 think() 的累计丢失。

        Returns:
            {topic_slug: {"content": str, "sources": [{title, url}]}}
        """
        topics = topics or DEFAULT_TOPICS
        results: dict[str, dict[str, Any]] = {}

        for slug, cn_name, desc in topics:
            # 1. 构造查询
            query = f"{cn_name} {desc} 题材：{brief[:80]}"
            logger.info("TopicResearcher: 检索 %s ('%s')", slug, query[:60])

            # 2. 搜索
            try:
                hits = await web_search.search(query, count=5)
            except Exception as e:
                logger.warning("TopicResearcher: %s 搜索异常: %s", slug, e)
                hits = []

            # 3. 综合成报告
            sources_block = ""
            if hits:
                src_lines = []
                for i, h in enumerate(hits, 1):
                    src_lines.append(
                        f"{i}. {h.title}\n   摘要：{h.snippet[:300]}\n   来源：{h.url}"
                    )
                sources_block = "\n\n## 原始搜索结果\n\n" + "\n\n".join(src_lines)
            else:
                sources_block = "\n\n（未取得联网搜索结果，请基于你的常识给出方向性建议，并在报告开头标注「基于模型内置知识，未联网核实」）"

            prompt = (
                f"小说 brief：\n{brief}\n\n"
                f"请针对「{cn_name}」方向撰写调研报告。\n"
                f"检索方向说明：{desc}\n"
                f"{sources_block}\n\n"
                f"按系统提示词中的格式输出（关键发现 / 细节 / 对本作的启示），≤2000 字。"
            )

            try:
                report = await self.think(prompt)
                # C2 修复：每次 think() 后立即上报 usage，避免后续 think() 覆盖 last_usage
                if on_usage is not None:
                    on_usage(self)
            except Exception as e:
                logger.exception("TopicResearcher: %s 综合报告失败: %s", slug, e)
                # M8 修复：失败时不写错误占位符到 KB（避免污染下游 build_context）
                report = f"## {cn_name}\n\n（调研综合失败：{e}）"
                results[slug] = {
                    "content": report,
                    "sources": [{"title": h.title, "url": h.url} for h in hits],
                }
                continue

            # 4. 落盘（仅成功路径）
            try:
                knowledge.save_research(slug, report)
            except OSError as e:
                # m10 修复：save_research 仅可能磁盘错误，收窄 except
                logger.exception("TopicResearcher: 保存 %s 失败: %s", slug, e)

            results[slug] = {
                "content": report,
                "sources": [{"title": h.title, "url": h.url} for h in hits],
            }

        return results
