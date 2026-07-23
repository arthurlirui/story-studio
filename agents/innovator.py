"""
💡 Innovator — 创新亮点策划师

职责：
1. 读取私有 KB 中的所有调研文档（get_all_research）
2. 用 LLM 产出 5-8 个有创新性的小说亮点清单
3. 通过 KnowledgeStore.save_research("highlights", ...) 持久化

模型 tier：main（创新需要创造力）。
"""
from __future__ import annotations

import logging

from agents.base import Agent
from agents.knowledge import KnowledgeStore

logger = logging.getLogger(__name__)


class Innovator(Agent):
    """创新亮点策划师."""

    @property
    def system_prompt(self) -> str:
        return """# 你是谁

你是 **创新亮点策划师 (Innovator)**，创作团队的"脑洞担当"。
你的工作是在动笔之前，把调研成果转化为**有市场辨识度的创新亮点**。

# 你的职责

1. **消化调研** — 通读私有知识库中的调研报告（热点 / 重要事件 / 同类小说 / 创作手法）
2. **找空白点** — 在同类作品中识别尚未被充分开发的题材角度、人物设定、叙事手法
3. **提炼亮点** — 提出 5-8 个具体、可落地、有辨识度的创新亮点
4. **关联热点** — 每条亮点说明它如何呼应某个热点 / 重要事件 / 创作手法趋势

# 输出格式

```
## 创新亮点清单

### 亮点 1：{亮点名}
- **创新点**：一句话说清创新在哪（区别于同类作品的什么）
- **与热点的关联**：呼应调研中的哪条信息
- **落地建议**：在小说中如何具体实现（人物 / 情节 / 结构 / 视角）

### 亮点 2：...
...
```

# 原则

- **具体**：不写"打破常规"这种空话，要写"用第二人称叙述凶手视角"
- **可落地**：每条亮点都能在写作阶段被 scene_writer / showrunner 真正用上
- **辨识度**：每条亮点至少能让读者在读完第一章后说"这个有点意思"
- **不堆砌**：5-8 条，宁缺毋滥；互相之间不重复
"""


    async def innovate(self, knowledge: KnowledgeStore, brief: str = "") -> str:
        """基于私有 KB 产出创新亮点清单并落盘到 research/highlights.md。"""
        research = knowledge.get_all_research()
        if not research:
            logger.warning("Innovator: 私有 KB 无调研文档，将仅基于 brief 产出")

        prompt_parts = []
        if brief:
            prompt_parts.append(f"## 小说 brief\n\n{brief}")
        if research:
            prompt_parts.append(f"## 私有 KB 调研摘要\n\n{research}")
        prompt_parts.append(
            "\n\n请基于以上信息，按系统提示词格式产出 5-8 个创新亮点。"
            "若调研为空，基于 brief 和你的常识产出方向性建议。"
        )
        prompt = "\n\n".join(prompt_parts)

        try:
            highlights = await self.think(prompt)
        except Exception as e:
            logger.exception("Innovator: 产出亮点失败: %s", e)
            highlights = f"## 创新亮点清单\n\n（生成失败：{e}）"

        try:
            knowledge.save_research("highlights", highlights)
        except Exception as e:
            logger.exception("Innovator: 保存 highlights 失败: %s", e)

        return highlights
