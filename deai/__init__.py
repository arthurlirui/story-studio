"""
deai — 去AI化模块。
全链路四层方法：规则检测→纯规则重写→LLM重写兜底→反AI审计+质量评分。

基于 Humanizer-zh (op7418/Humanizer-zh) 的 24 类 AI 写作痕迹检测体系。

与 agent prompt 的双轨关系：
- 本模块（deai/）是独立的规则引擎 + 后处理工具，适合批量自动化清洗。
- 主流水线中的去AI感通过 agent system prompt 内化实现（SceneWriter 的 7 条
  写作纪律 + Editor 的 8 维度检测清单），在每章写作/润色/终审的逐轮修订中
  自动执行，无需显式调用本模块。
- 双轨互补：prompt 内化侧重"生成时预防"，引擎侧重"生成后清理"。
  未来可将 engine.process() 接入 orchestrator 的终审阶段作为兜底清洗。
"""

from .engine import DeaiEngine

__all__ = ["DeaiEngine"]
