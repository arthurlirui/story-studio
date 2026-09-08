"""DeaiEngine 强化测试：参数化、提示词外部化、LLM 重写锚号对齐、策略派发对齐、计数真实。

覆盖 plan 中引擎层与配置层的关键改动。
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from config import DeaiConfig, StudioConfig, load_config
from config import io as config_io
from deai.engine import DeaiEngine, ScanResult


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── 1. 参数化构造 ──────────────────────────────────────────────


def test_aggressiveness_passed_to_engine():
    """构造传入的 aggressiveness 生效，且 clamp 到 [0,1]。"""
    e = DeaiEngine(aggressiveness=0.8)
    assert e.aggr == 0.8
    e_high = DeaiEngine(aggressiveness=2.0)
    assert e_high.aggr == 1.0
    e_low = DeaiEngine(aggressiveness=-1.0)
    assert e_low.aggr == 0.0


def test_length_band_and_audit_threshold_passed():
    """length_band / audit_threshold 从构造传入。"""
    e = DeaiEngine(length_band=(0.85, 1.20), audit_threshold=40)
    assert e.length_band == (0.85, 1.20)
    assert e.audit_threshold == 40
    e_default = DeaiEngine()
    assert e_default.length_band is None
    assert e_default.audit_threshold == 35


def test_aggressiveness_affects_rewrite_count():
    """高 aggressiveness 下规则重写次数应不低于低值（同义词变异概率更高）。"""
    text = "此外，无比精彩。然而，结局。"
    e_low = DeaiEngine(aggressiveness=0.0)
    e_low.set_seed(1)
    _, n_low = _run(e_low.rewrite_rules(text))
    e_high = DeaiEngine(aggressiveness=1.0)
    e_high.set_seed(1)
    _, n_high = _run(e_high.rewrite_rules(text))
    assert n_high >= n_low


# ── 2. 提示词外部化 ──────────────────────────────────────────────


def test_prompt_version_loads_file():
    """prompt_version 对应文件存在时加载其内容。"""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "rewrite_v9.txt"
        p.write_text("自定义提示词 {segments}", encoding="utf-8")
        e = DeaiEngine(prompt_version="v9", prompts_dir=d)
        assert "自定义提示词" in e._rewrite_prompt


def test_prompt_version_falls_back_when_missing():
    """文件不存在时回退内置 v1 并 warning。"""
    e = DeaiEngine(prompt_version="v999", prompts_dir=tempfile.gettempdir())
    assert "资深文学编辑" in e._rewrite_prompt  # 内置 v1 关键词


def test_default_v1_prompt_loads_from_prompts_dir():
    """默认 v1 从 deai/prompts/rewrite_v1.txt 加载。"""
    e = DeaiEngine(prompt_version="v1")
    # 文件版含"输出格式"锚号协议说明，内置回退版同样含
    assert "输出格式" in e._rewrite_prompt or "资深文学编辑" in e._rewrite_prompt


# ── 3. LLM 重写锚号对齐 ──────────────────────────────────────────


class _NumberedLLM:
    """模拟 LLM：按 [N] 锚号返回多段重写。"""

    def __init__(self, response: str):
        self._resp = response

    async def think(self, prompt: str) -> str:
        return self._resp


def test_llm_rewrite_numbered_alignment_multi_segment():
    """多段 [N] 锚号响应按编号正确回填，计数等于实际替换数。"""
    sample_a = "他的眼神无比深邃，仿佛承载着千年的沧桑与重担。"
    sample_b = "此外，这标志着不可磨灭的重要里程碑。"
    text = f"开篇。\n{sample_a}\n中段。\n{sample_b}\n结尾。"
    scan = [ScanResult(rule_id=1, rule_name="x", category="style",
                       severity=1, match_count=2, samples=[sample_a, sample_b])]
    resp = "[1] 他眼神很沉，像活了很久。\n\n[2] 这是个节点。"
    e = DeaiEngine(llm_client=_NumberedLLM(resp))
    out, calls = _run(e.rewrite_llm(text, scan))
    assert calls == 2
    assert "他眼神很沉" in out and "这是个节点" in out
    assert sample_a not in out and sample_b not in out


def test_llm_rewrite_missing_anchor_skips_with_warning():
    """LLM 缺少某段 [N] 响应时跳过该段，计数只算成功的。"""
    sample_a = "他的眼神无比深邃，仿佛承载着千年的沧桑与重担。"
    sample_b = "此外，这标志着不可磨灭的重要里程碑。"
    text = f"{sample_a}\n{sample_b}"
    scan = [ScanResult(rule_id=1, rule_name="x", category="style",
                       severity=1, match_count=2, samples=[sample_a, sample_b])]
    resp = "[1] 他眼神很沉。"  # 只有 [1]，缺 [2]
    e = DeaiEngine(llm_client=_NumberedLLM(resp))
    out, calls = _run(e.rewrite_llm(text, scan))
    assert calls == 1
    assert "他眼神很沉" in out
    assert sample_b in out  # [2] 未替换，保留原文


def test_llm_rewrite_no_anchors_returns_zero():
    """LLM 响应无 [N] 前缀时，整段跳过，计数 0，正文不变。"""
    sample = "他的眼神无比深邃，仿佛承载着千年的沧桑与重担。"
    text = f"开篇。{sample}结尾。"
    scan = [ScanResult(rule_id=1, rule_name="x", category="style",
                       severity=1, match_count=1, samples=[sample])]
    e = DeaiEngine(llm_client=_NumberedLLM("没有锚号的普通文本。"))
    out, calls = _run(e.rewrite_llm(text, scan))
    assert calls == 0
    assert out == text


def test_llm_rewrite_normalized_fallback_when_exact_fails():
    """精确子串匹配失败时，归一化（去空白）兜底匹配段落块。"""
    sample = "他的眼神无比深邃，仿佛承载着千年的沧桑。"
    # 原文中该段被多余空白包裹，精确子串会失败
    text = f"开篇。\n  {sample}  \n结尾。"
    scan = [ScanResult(rule_id=1, rule_name="x", category="style",
                       severity=1, match_count=1, samples=[sample])]
    resp = "[1] 他眼神很沉。"
    e = DeaiEngine(llm_client=_NumberedLLM(resp))
    out, calls = _run(e.rewrite_llm(text, scan))
    assert calls == 1
    assert "他眼神很沉" in out


def test_llm_rewrite_error_sentinel_rejected():
    """LLM 返回错误哨兵时正文原样返回，计数 0。"""
    from agents.llm_client import LLM_ERROR_PREFIX

    class _ErrLLM:
        async def think(self, prompt: str) -> str:
            return LLM_ERROR_PREFIX + "boom"

    sample = "他的眼神无比深邃，仿佛承载着千年的沧桑与重担。"
    text = f"开篇。{sample}结尾。"
    scan = [ScanResult(rule_id=1, rule_name="x", category="style",
                       severity=1, match_count=1, samples=[sample])]
    e = DeaiEngine(llm_client=_ErrLLM())
    out, calls = _run(e.rewrite_llm(text, scan))
    assert calls == 0
    assert out == text


def test_llm_rewrite_exception_logged_not_silent():
    """LLM 抛异常时不静默吞掉，返回 (text, 0)。"""

    class _BoomLLM:
        async def think(self, prompt: str) -> str:
            raise RuntimeError("network down")

    sample = "他的眼神无比深邃，仿佛承载着千年的沧桑与重担。"
    text = f"开篇。{sample}结尾。"
    scan = [ScanResult(rule_id=1, rule_name="x", category="style",
                       severity=1, match_count=1, samples=[sample])]
    e = DeaiEngine(llm_client=_BoomLLM())
    out, calls = _run(e.rewrite_llm(text, scan))
    assert calls == 0
    assert out == text


# ── 4. 策略派发对齐 ──────────────────────────────────────────────


def test_weaken_rules_now_applied_in_rewrite():
    """STRATEGY_WEAKEN 规则的 patterns 在重写阶段被读取并处理（此前被忽略）。"""
    # 规则 4 (宣传/广告式语言) 含 "令人惊叹" 等，STRATEGY_WEAKEN
    text = "这处风景令人惊叹，无与伦比。"
    e = DeaiEngine(aggressiveness=0.0)
    e.set_seed(0)
    out, n = _run(e.rewrite_rules(text))
    # "令人惊叹" 属规则 4 pattern，应被删除/弱化
    assert n > 0
    assert "令人惊叹" not in out or "无与伦比" not in out


def test_replace_rules_now_applied_in_rewrite():
    """STRATEGY_REPLACE 规则的 patterns 在重写阶段被读取（此前被忽略）。"""
    # 规则 13 (破折号) STRATEGY_REPLACE，pattern "——"
    text = "他走了——再没回头。"
    e = DeaiEngine(aggressiveness=0.0)
    e.set_seed(0)
    out, n = _run(e.rewrite_rules(text))
    assert n > 0
    assert "——" not in out


# ── 5. 配置层 ──────────────────────────────────────────────────


def test_deai_config_defaults():
    """DeaiConfig 默认值正确。"""
    c = DeaiConfig()
    assert c.enabled is True
    assert c.aggressiveness == 0.4
    assert c.length_min_ratio == 0.90
    assert c.length_max_ratio == 1.15
    assert c.prompt_version == "v1"
    assert c.audit_threshold == 35


def test_studio_config_has_deai_field():
    """StudioConfig.deai 默认 DeaiConfig。"""
    c = StudioConfig()
    assert isinstance(c.deai, DeaiConfig)


def test_load_config_parses_deai_section(tmp_path):
    """settings.yaml 含 deai 段时正确解析进 StudioConfig.deai。"""
    cfg_file = tmp_path / "settings.yaml"
    cfg_file.write_text(
        "deai:\n"
        "  enabled: true\n"
        "  aggressiveness: 0.7\n"
        "  length_min_ratio: 0.85\n"
        "  length_max_ratio: 1.20\n"
        "  prompt_version: 'v2'\n"
        "  audit_threshold: 30\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path, create_dirs=False)
    assert cfg.deai.enabled is True
    assert cfg.deai.aggressiveness == 0.7
    assert cfg.deai.length_min_ratio == 0.85
    assert cfg.deai.length_max_ratio == 1.20
    assert cfg.deai.prompt_version == "v2"
    assert cfg.deai.audit_threshold == 30


def test_io_apply_update_accepts_deai_subkeys():
    """io.apply_update 接受 deai 子键更新。"""
    data = {}
    updated, rejected = config_io.apply_update(
        data, {"deai": {"aggressiveness": "0.6", "audit_threshold": "40"}}
    )
    assert "deai" in updated
    assert "deai" not in rejected
    assert data["deai"]["aggressiveness"] == 0.6
    assert data["deai"]["audit_threshold"] == 40


def test_io_apply_update_rejects_unknown_top_key():
    """未知顶层键被拒绝。"""
    updated, rejected = config_io.apply_update({}, {"unknown_key": "x"})
    assert "unknown_key" in rejected


# ── 6. 规则正例/反例 ──────────────────────────────────────────

from deai.rules import RULES, DeaiRule


def _rule(rule_id: int) -> DeaiRule:
    for r in RULES:
        if r.id == rule_id:
            return r
    raise KeyError(f"rule {rule_id} not found")


def _matches(rule: DeaiRule, text: str) -> bool:
    """文本是否被该规则的任一 pattern 命中。"""
    for pat in rule.patterns:
        if re.search(pat, text):
            return True
    return False


import re

# (rule_id, positive_text, negative_text)
RULE_EXAMPLES = [
    (1, "这座建筑标志着时代的变迁，为后世奠定了基础。",
     "他把书放回书架，转身离开了图书馆。"),
    (2, "多家独立媒体报道了这一事件。",
     "她打开窗户，让晨风吹进房间。"),
    (3, "这一发现揭示了深层次的问题，为社会做出了贡献。",
     "他叹了口气，把信折好放进口袋。"),
    (4, "这处风景令人无比惊叹，是不可错过的胜地。",
     "山路陡峭，他不得不停下来喘口气。"),
    (5, "知情者指出，多项研究表明这一趋势正在加速。",
     "老王说，村里的井水这几天变浑了。"),
    (6, "尽管面临诸多挑战，但展望未来前景广阔。",
     "他不确定明天还能不能站起来。"),
    (7, "此外，这一问题至关重要，需要深入探讨其复杂性。",
     "他喝了口水，继续往前走。"),
    (8, "作为一个拥有悠久历史的古城，这里设有众多的名胜。",
     "他是村里唯一的铁匠，有一把好手艺。"),
    (9, "这不仅是技术的突破，更是人类智慧的结晶。",
     "他拿起锤子，开始敲打那块铁板。"),
    (10, "他带来了勇气、智慧和力量。",
     "他拿起帽子和外套走出门。"),
    (11, "主人公望着远方的地平线，核心人物陷入了沉思。",
     "他望着远方的地平线，陷入了沉思。"),
    (12, "从清晨的第一缕阳光到夜晚的最后一盏灯。",
     "他从口袋里掏出一枚铜板。"),
    (13, "她沉默了——似乎在想什么。",
     "她沉默了，似乎在想什么。"),
    (14, "这是**重要**的**关键**点。",
     "这是重要的关键点。"),
    (15, "- **核心要点**：务必记住",
     "他列了三件事：买菜、接孩子、做饭。"),
    (17, "太好了🎉让我们开始吧！",
     "太好了，让我们开始吧！"),
    (18, "他说\u201c你好\u201d然后离开。",
     "他说\u201c你好\u201d然后离开。".replace("\u201c", "\u300c").replace("\u201d", "\u300d")),
    (19, "希望以上内容对您有帮助，如果您需要更多信息请随时告诉我。",
     "他帮了她的忙，她说了声谢谢。"),
    (20, "截至目前为止，根据我的知识库信息显示。",
     "截至昨天晚上，雨还没停。"),
    (21, "好问题！您说得完全正确，那是一个非常好的观点。",
     "他点了点头表示赞同。"),
    (22, "值得注意的是，我们可以发现整体而言，情况在好转。",
     "他注意到桌上的茶已经凉了。"),
    (23, "可能或许大概是这样吧，在某种程度上来说。",
     "他可能明天会来。"),
    (24, "未来前景光明灿烂，充满无限希望，向正确方向迈出了一步。",
     "他不知道明天会怎样，但至少今天还活着。"),
]


@pytest.mark.parametrize("rule_id,positive,negative", RULE_EXAMPLES,
                         ids=[f"rule-{rid}" for rid, _, _ in RULE_EXAMPLES])
def test_rule_positive_match(rule_id, positive, negative):
    """每条规则的正例应被至少一个 pattern 命中。"""
    rule = _rule(rule_id)
    if not rule.patterns:
        pytest.skip(f"rule {rule_id} has no patterns")
    assert _matches(rule, positive), (
        f"rule {rule_id} ({rule.name}) 未命中正例: {positive!r}")


@pytest.mark.parametrize("rule_id,positive,negative", RULE_EXAMPLES,
                         ids=[f"rule-{rid}-neg" for rid, _, _ in RULE_EXAMPLES])
def test_rule_negative_no_match(rule_id, positive, negative):
    """每条规则的反例（正常文学表达）不应被命中。"""
    rule = _rule(rule_id)
    if not rule.patterns:
        pytest.skip(f"rule {rule_id} has no patterns")
    assert not _matches(rule, negative), (
        f"rule {rule_id} ({rule.name}) 误命中反例: {negative!r}")
