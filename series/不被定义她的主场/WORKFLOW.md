# 《不被定义她的主场》批量长篇创作流程

## 1. 新建单本项目

```bash
cd /home/openclaw/.openclaw/workspace/story-studio
python3 series/不被定义她的主场/tools/new_variant.py \
  --title "女钳工她不认命" \
  --mode era \
  --definition D01+D04 \
  --core "六零年代女钳工打破性别工种偏见，成为大国工匠" \
  --heroine-name "林向阳" \
  --heroine-archetype H01 \
  --label "女同志不适合进一车间" \
  --goal "进入一车间成为正式钳工" \
  --skill "机械制图、钳工校准、持续复盘" \
  --arena "红星机械厂一车间" \
  --conflict-engine CE01 \
  --ending collective_change
```

## 2. Agent 分工

### Showrunner / 总策划

负责：确定不被定义方向、核心立意、四卷结构、主场建立方式。

检查：

- 女主是否绝对核心？
- 本书“不被定义”是否明确？
- 结局是否展示女主主场？

### WorldArchitect / 世界观架构师

负责：根据 mode 设计时代/行业/制度背景。

检查：

- 压迫结构是否具体？
- 女主如何进入公共空间/专业空间？
- 旧规则如何反扑？

### CharacterDesigner / 角色设计师

负责：女主、女性盟友、女性反派、旧规则代表、男性盟友。

检查：

- 女性角色是否多元？
- 女性反派是否有利益逻辑？
- 男性角色是否没有抢女主主线？

### LiteraryAdvisor / 女频类型顾问

负责：标题、开篇钩子、章节爽点、情绪共鸣。

检查：

- 是否有女性读者共情入口？
- 是否避免空喊独立？
- 爽点是否来自女主行动？

### SceneWriter / 章节编剧

负责：正文生成。

要求：每章必须有女主行动、爽点、小高潮。

### Editor / 编辑

负责：节奏、文风、情绪、爽点密度。

### ContinuityKeeper / 连续性检查员

负责：检查女主能力成长、主场建设、人物行为一致性。

### Cover Designer / 封面设计

负责：用 cover_brief.json 生成封面。

```bash
python3 tools/book_cover_comfy.py --brief series/不被定义她的主场/variants/<项目>/cover_brief.json
```

## 3. 单本长篇生产顺序

```text
1. new_variant.py 新建项目
2. Showrunner 完成核心卖点和四卷结构
3. WorldArchitect 完成行业/时代/制度规则
4. CharacterDesigner 完成人物卡
5. LiteraryAdvisor 优化标题和第一章钩子
6. Showrunner 生成 chapter_plan.md
7. SceneWriter 逐章生成正文
8. Editor 分卷修订
9. ContinuityKeeper 更新 continuity_log.md
10. Cover Designer 生成封面
```

## 4. 批量选题矩阵

| 编号 | 模式 | 不被定义 | 标题方向 | 主场 |
|---|---|---|---|---|
| UDF-001 | era | D01+D04 | 女钳工她不认命 | 机械厂一车间 |
| UDF-002 | historical | D02+D05 | 通房不低头 | 商号/侯府账房 |
| UDF-003 | wasteland | D02+D04 | 我在废土世界扫垃圾 | 污染治理站 |
| UDF-004 | infinite | D03+D07 | 平平无奇老奶奶杀穿副本 | 无限副本队伍 |
| UDF-005 | modern | D05+D07 | 美艳妻子离婚后 | 女性创业公司 |
| UDF-006 | fantasy | D06+D01 | 无灵根女修开宗立派 | 凡人阵法宗门 |
| UDF-007 | historical | D01+D02 | 女仵作她只验真相 | 县衙/刑部 |
| UDF-008 | modern | D03+D04 | 三十五岁转行做法医 | 法医中心 |
| UDF-009 | era | D03+D07 | 重生七零老太太宠女不宠子 | 家庭新秩序 |
| UDF-010 | fantasy | D04+D06 | 柔弱医修今天也在背地里暴打魔尊 | 医修谷 |

## 5. 启动前必答问题

1. 女主被什么定义？
2. 她为什么不接受这个定义？
3. 她的主动目标是什么？
4. 她有什么能力或将如何获得能力？
5. 旧规则由谁代表？
6. 她会让哪些女性看见新可能？
7. 她最终建立的主场是什么？

这 7 个问题没有答案，不进入正文生成。
