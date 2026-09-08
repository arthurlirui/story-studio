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

接入点：
- deai stage（pipeline_core.run_deai / run_all.run_deai / short_story._phase_deai）
  先跑 engine.process() 规则清洗+LLM重写，再叠 polish_prompt 润色。
- 终审阶段（orchestrator.phase_complete）每轮跑 audit()，评分低于
  cfg.deai.audit_threshold 时触发一轮 process() 重写，由 showrunner 复审。

参数化：aggressiveness / length_band / prompt_version / audit_threshold
均通过 config.DeaiConfig 接入 settings.yaml。
"""

from .engine import DeaiEngine

__all__ = ["DeaiEngine"]
