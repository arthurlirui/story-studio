"""
去AI化规则表：24 类 AI 写作痕迹检测规则。
基于 Humanizer-zh，翻译自 WikiProject AI Cleanup。
"""
from __future__ import annotations
from dataclasses import dataclass, field
import re

CAT_CONTENT = "content"
CAT_LANGUAGE = "language"
CAT_STYLE = "style"
CAT_COMMUNICATION = "comm"

STRATEGY_REPLACE = "replace"
STRATEGY_DELETE = "delete"
STRATEGY_WEAKEN = "weaken"
STRATEGY_REWRITE = "rewrite"

@dataclass
class DeaiRule:
    id: int
    category: str
    name: str
    severity: int
    strategy: str
    patterns: list
    description: str
    examples: list = field(default_factory=list)

RULES: list[DeaiRule] = [
    DeaiRule(1,CAT_CONTENT,"夸大象征意义",5,STRATEGY_DELETE,[r"作为.{1,20}(?:证明|体现|缩影|象征|标志|里程碑)",r"标志着|见证了|凸显了|彰显了|昭示着",r"(?:极其|至关|核心的|关键性的)(?:重要|作用|角色|地位|时刻)",r"反映了更广泛的|不可磨灭的印记|深深植根于",r"为.{1,30}(?:奠定基础|做出贡献)"],"LLM夸大重要性。"),
    DeaiRule(2,CAT_CONTENT,"过度强调知名度",4,STRATEGY_WEAKEN,[r"(?:独立|多家|主流)媒体(?:报道|关注)"],"都市/娱乐圈题材时需处理。"),
    DeaiRule(3,CAT_CONTENT,"肤浅分析(段尾强行点题)",4,STRATEGY_REWRITE,[r"(?:突出|强调|彰显|确保|揭示|展示|暗示)了.{1,40}$",r"为.{1,30}(?:做出贡献|注入活力|增添色彩)"],"段落末尾抽象总结句。"),
    DeaiRule(4,CAT_CONTENT,"宣传/广告式语言",4,STRATEGY_WEAKEN,[r"(?:令人|无比|极其)(?:惊叹|震撼|着迷|陶醉)",r"(?:必游|必去|不可错过|无与伦比)",r"开创性的|突破性的|革命性的"],"旅游/广告腔入侵叙事。"),
    DeaiRule(5,CAT_CONTENT,"模糊归因",4,STRATEGY_DELETE,[r"(?:业内人士|知情者|观察者|分析人士)(?:指出|认为|表示)",r"有人说|据说|传闻|多项研究表明"],"模糊权威。"),
    DeaiRule(6,CAT_CONTENT,"提纲式挑战与展望",3,STRATEGY_DELETE,[r"尽管.+面临.+(?:挑战|困难|问题)",r"展望未来|未来前景|发展趋势"],"公式化结尾。"),
    DeaiRule(7,CAT_LANGUAGE,"AI高频词汇",5,STRATEGY_REPLACE,[r"此外|至关重要|深入探讨|持久的|增强|相互作用",r"复杂[性杂]|关键[的性]|格局|关键性的|织锦",r"宝贵的|充满活力的|展示.{1,10}价值"],"2023年后频率远高于人类。"),
    DeaiRule(8,CAT_LANGUAGE,"系动词回避",3,STRATEGY_REWRITE,[r"作为(?:一个|一种|一项)(?!.{0,5}(?:人|者|角色))",r"拥有(?:一个|着)(?!.{0,10}(?:手|脚|眼|脸|身))",r"设有(?:一个|着)|提供(?:了|着)(?:一个|一种)"],"复杂结构替代是/有。"),
    DeaiRule(9,CAT_LANGUAGE,"否定式排比",5,STRATEGY_REWRITE,[r"不仅仅?是.{1,30}[，,]\s*(?:而是|更是)",r"这不仅是.{1,30}[，,]\s*(?:而是|更是)",r"不是.{1,30}[，,]\s*而是"],"不仅是…更是…过度使用。"),
    DeaiRule(10,CAT_LANGUAGE,"三段式法则",4,STRATEGY_REWRITE,[r"\S+[、，·]\S+[和与及]\S+"],"强行分成三组。"),
    DeaiRule(11,CAT_LANGUAGE,"刻意换词",3,STRATEGY_REPLACE,[r"(主人公|主角|男主|女主|核心人物|中心人物|主要角色)"],"重复惩罚→同义词循环。"),
    DeaiRule(12,CAT_LANGUAGE,"虚假范围",2,STRATEGY_REWRITE,[r"从.{1,40}到.{1,40}"],"两端拼凑。"),
    DeaiRule(13,CAT_STYLE,"破折号过度使用",4,STRATEGY_REPLACE,[r"——|—"],"LLM破折号频率高于人类。"),
    DeaiRule(14,CAT_STYLE,"粗体过度使用",2,STRATEGY_DELETE,[r"\*\*[^*]+\*\*"],"已在text_cleaner处理。"),
    DeaiRule(15,CAT_STYLE,"内联标题列表",3,STRATEGY_REWRITE,[r"^[-*]\s*\*\*.+\*\*[:：]"],"AI列表项入侵。"),
    DeaiRule(16,CAT_STYLE,"标题大小写",1,STRATEGY_REPLACE,[],"英文问题，中文不适用。"),
    DeaiRule(17,CAT_STYLE,"表情符号",2,STRATEGY_DELETE,[r"[\U0001F300-\U0001FAFF\u2600-\u27BF]"],"AI表情装饰。"),
    DeaiRule(18,CAT_STYLE,"弯引号",1,STRATEGY_REPLACE,[r"[\u201c\u201d]"],"转中文引号。"),
    DeaiRule(19,CAT_COMMUNICATION,"协作交流痕迹",5,STRATEGY_DELETE,[r"希望(?:这|以上).{1,30}(?:帮助|参考|启发)",r"如果您?(?:想要|需要|希望).{1,30}(?:请告诉|请随时|欢迎)",r"当然[!！]|一定[!！]|您说得完全正确",r"这是一个.{1,20}(?:概述|总结|介绍)"],"聊天痕迹入侵正文。"),
    DeaiRule(20,CAT_COMMUNICATION,"知识截止日期免责",5,STRATEGY_DELETE,[r"截至.{1,30}(?:为止|目前)",r"根据我(?:最后|[的])?(?:训练|知识|了解)",r"基于(?:现有|可用|当前)(?:信息|资料|数据)"],"AI免责声明。"),
    DeaiRule(21,CAT_COMMUNICATION,"谄媚语气",4,STRATEGY_DELETE,[r"好问题[!！]|很好的问题",r"您说得(?:完全正确|非常对|很对)",r"(?:这|那)是一个(?:非常好|很棒)的(?:观点|问题|想法)"],"过于讨好。"),
    DeaiRule(22,CAT_COMMUNICATION,"填充短语",3,STRATEGY_REPLACE,[r"值得注意的是.{1,30}，?",r"我们可以发现.{1,30}，?",r"为了实现这一目标，?",r"在这个时间点，?",r"整体而言，?"],"无用填充。"),
    DeaiRule(23,CAT_COMMUNICATION,"过度限定",3,STRATEGY_WEAKEN,[r"(?:可能|或许|大概).{0,5}(?:可能|或许|大概)",r"(?:似乎|好像|仿佛).{0,5}(?:似乎|好像|仿佛)",r"在(?:一定|某种|某些)程度[上中]"],"叠床架屋限定语。"),
    DeaiRule(24,CAT_COMMUNICATION,"通用积极结论",5,STRATEGY_DELETE,[r"(?:未来|明天|前景).{1,20}(?:光明|灿烂|美好|可期)",r"激动人心的.{1,20}(?:到来|开启)",r"(?:充满|无限)(?:希望|可能|想象)",r"向正确方向迈出"],"模糊乐观结尾。"),
]