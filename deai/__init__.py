"""
deai — 去AI化模块。
全链路四层方法：规则检测→纯规则重写→LLM重写兜底→反AI审计+质量评分。

基于 Humanizer-zh (op7418/Humanizer-zh) 的 24 类 AI 写作痕迹检测体系。
"""

from .engine import DeaiEngine

__all__ = ["DeaiEngine"]
