#!/usr/bin/env python3
"""Generate chapters for 《沉默的真相》 using LLM API."""
import json, os, time, re, sys
import requests

API_BASE = "https://llmapi.pcl.ac.cn/v1"
API_KEY = "sk-dLcQBdtUNpw5vxrSP8HjlXfJGb8nP8uYlpSMpfKKTD8QfbbS"
MODEL = "DeepSeek-V4-Pro"
CHAPTER_DIR = "/home/pz03-b-003-pcl/code/story-studio/series/千行百业/variants/04_沉默的真相/knowledge/story/chapters"
os.makedirs(CHAPTER_DIR, exist_ok=True)
# Define all chapters with their outline descriptions
CHAPTERS = [(1,"广州火车站","1995.09,广州火车站广场。林安之看见湖南民工,女人抱孩子哭,男人们蹲地上。工头老周。她蹲下按录音键:你说。章末:BP机响方晓棠催稿。开始关注这群被欠薪的人。"),
(2,"十六个月的工资","去建设局查鸿发建筑,法人赵大伟在东莞。放弃原定稿子做调查。报选题给郑同升,老郑让她带沈渡去东莞。"),
(3,"沈渡","暗房初识,沈渡冲胶卷。林安之:郑总让你跟我去东莞。沈渡:什么时候?明天。行。长途大巴上沈渡给她看尼康FM2。"),
(4,"鸿发工地","东莞暗访,以装修客户进售楼处。工人住宿极差,小伙说老板说了六个下月。沈渡偷拍开裂楼板。回程发现黑色桑塔纳跟踪。"),
(5,"第一次跟踪","回广州桑塔纳跟踪到天河出租屋。BP机收别多管闲事。资料室有人先查过鸿发。方晓棠陪同。老周火车站给工人的欠条印了手印。"),
(6,"陈望秋","找老调查记者陈望秋。60岁的他翻旧报纸,1990东莞血汗工厂报道没发。决定帮她。两天后东莞采访时被保安围殴三根肋骨骨裂住院。"),
(7,"鸿发背后的网","从陈望秋旧资料发现鸿发与三家公司共用注册地址会计事务所。不止欠薪。何志远第一次绕过编辑部找她谈话。"),
(8,"沈渡的底片","沈渡在酒楼门口拍到赵大伟与某人物推杯换盏。底片冲洗时发现暗房放大机被翻过。报社有内鬼。"),
(9,"第一次报道","1996初,第一篇鸿发拖欠工资报道发表在南方周末第六版。反响大。赵大伟托人私下解决。报社信件增多。"),
(10,"退一步","何志远施压。郑同升:可以先放一放。林安之在走廊生命墙将第一篇报道贴最低处:还没完。"),
(11,"老周的电话","1996夏。老周通过阿彪BP机联系林安之。东莞偏僻茶楼见面。老周带工资明细工时记录。采访结束楼下三个陌生男人。"),
(12,"证人","老周成关键证人。林安之整理材料。沈渡按快门与她在稿纸写字形成节律。阿彪偷听到赵大伟手下在找湖南佬。"),
(13,"暗夜","1996冬。老周民房窗户被砸。林安之恐惧。沈渡在天台:如果他沉默只能等,你给了不等机会。老周BP机:我不怕。"),
(14,"天河出租屋","方晓棠视角。出租屋两张床旧风扇墙上地图红笔标记。方晓棠看记者真实生活。发现林安之枕头下父亲照片。"),
(15,"非法的产业链","发现鸿发非个案。空壳公司承包层层转包抽成劣质建材注销跑路。公司注册半年注销。证据指更高层。"),
(16,"那顿饭","1997初春。沈渡在广州高级酒楼拍到赵大伟与同席者,三张底片。林安之:保存好。第二天暗房底片不翼而飞。"),
(17,"底片消失之后","内部泄密。怀疑每个人。郑同升知道内鬼不能说。沈渡将所有重要底片随身携带。"),
(18,"老周失联","1997初。阿彪最后BP机:周哥说去找你送材料没回来。打给赵大伟:不认识。当晚威胁电话。"),
(19,"阿香","去石牌村找证人扑空。路边肠粉店。老板娘阿香:这条街事我都知道,你要找的人昨天被接走了。递纸条地址。"),
(20,"我不怕","跑遍广州东莞。东莞城中村找到阿彪藏匿点:解放鞋半包烟账本。账本末页一行字:致林记者。"),
(21,"回湖南","1997春。回湖南邵阳老周老家。村委会铁皮柜找到:197份签手印工资单,工时记录,银行凭证。院子坐一下午。回广州火车上写终稿。"),
(22,"报道终稿","熬十多天写一万两千字终稿。结尾:他们不是讨钱是讨理。郑同升深夜看完把烟按灭。两个字:登。"),
(23,"撤稿","排版当晚校样排好。11点电话。郑同升接电话5分钟沉默。稿子从校样抽下摔桌。撤。为什么。上面打了招呼。她复印三份藏不同地方。天台上。"),
(24,"天台","沈渡找到她。两人坐看夜景。稿子可撤真相不能。然后呢?还能怎么办?真的在问。沈渡答不上,沉默是答案。何志远第二天谈话。"),
(25,"代价提前算好","何志远:这次撤稿下次撤人。方晓棠:先缓缓。沈渡把重冲印照片放桌上。她看满桌材料,三年前火车站录音带父亲照。"),
(26,"印刷机","撤稿后第一周几乎抑郁。方晓棠每天带肠粉。去印刷厂看凌晨机器无她稿子。回出租屋终稿重抄,末写:本文不予刊登。"),
(27,"石牌村复印机","1997夏。复印百份手稿。阿香肠粉店分发点。民工街坊学生一人传一人。民间传播。写匿名信寄北京调查节目。沈渡将照片重洗三套。"),
(28,"内参","郑同升用内参渠道帮她。报道在体制内另一种形式被见。比发表更危险对郑同升个人。1月后劳动部门启动鸿发调查。"),
(29,"离职","赵大伟立案部分工资追回。林安之被劝退。收拾时郑同升进来推来旧南方周末,三年前第一篇报道第4版右下已发黄。沈渡递辞职信。"),
(30,"安渡照相","1998石牌村小巷。下雨老周推门进。头发白三分一左耳听力无。掏出皱报:林记者谢谢,儿子上大学了。老周走后她在暗房站很久:我做记者不为待报社。末:珠江黄昏沈渡给她拍照她笑了。有人买南方周末走过她看一眼并肩进小巷。落笔:真相会沉默但不会消失,像珠江水流走了还在。")]

def gen_prompt(ch_num, ch_title, ch_desc):
    system = "你是《千行百业》系列小说作者。定位:现代真实职业图景,职场百态与时代烟火。赛道:都市日常(非仕途)职场婚恋。方向二(百业多姿百态),核心共鸣感。"
    system += "风格:精准克制温度。第三人称有限视角跟女主林安之。职业细节真实:调查记者暗访取证保护线人。"
    system += "1990s时代感:BP机寻呼台公用电话,南方周末黄金时代,无智能手机互联网。感情线在危险中并肩作战非英雄救美。"
    system += f"写3000-5000字。格式以'## 第{ch_num}章 {ch_title}'开头。严格按大纲事件节点写。每章至少1个五感描写1个职业特写。章末钩子。对话九零年代口语。"

    user = f"生成《沉默的真相》第{ch_num}章完整正文。\n\n本章大纲:{ch_desc}\n\n"
    user += "规则:职业线感情线双线交织。林安之(29湖南人南方周末调查记者)沈渡(32佛山人摄影记者尼康FM2)。"
    user += "1995-1998广州东莞。核心:鸿发建筑拖欠农民工工资案。"
    user += "关键人物:老周(包工头线人)郑同升(主编)何志远(广告部)陈望秋(老记者)方晓棠(室友)阿彪(线人)阿香(肠粉店)。"
    user += "要求:写3000-5000字,直接输出正文,无解释,格式'## 第{ch_num}章 {ch_title}',章末悬念钩子。"
    user += "职业细节真实,1990s时代感准,感情自然推进。\n\n现在输出第{ch_num}章正文:"
    return system, user

def call_api(system, user):
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {"model": MODEL, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "temperature": 0.82, "max_tokens": 6000}
    try:
        r = requests.post(f"{API_BASE}/chat/completions", headers=headers, json=payload, timeout=180)
        r.raise_for_status()
        d = r.json()
        if "choices" in d and d["choices"]:
            return d["choices"][0]["message"]["content"].strip()
        print(f"  API unexpected: {json.dumps(d, ensure_ascii=False)[:200]}")
        return None
    except Exception as e:
        print(f"  API error: {e}")
        return None

def save_and_count(ch_num, content):
    path = os.path.join(CHAPTER_DIR, f"chapter_{ch_num:03d}.md")
    with open(path, 'w') as f:
        f.write(content)
    ch = sum(1 for c in content if '\u4e00' <= c <= '\u9fff')
    return path, ch

def main():
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    for ch_num, ch_title, ch_desc in CHAPTERS:
        if ch_num < start or ch_num > end:
            continue
        cpath = os.path.join(CHAPTER_DIR, f"chapter_{ch_num:03d}.md")
        if os.path.exists(cpath):
            sz = os.path.getsize(cpath)
            if sz > 500:
                print(f"Chapter {ch_num:03d} exists ({sz} bytes), skip")
                continue
        print(f"\n=== Chapter {ch_num:03d}: {ch_title} ===")
        system, user = gen_prompt(ch_num, ch_title, ch_desc)
        content = call_api(system, user)
        if content:
            path, chars = save_and_count(ch_num, content)
            print(f"  Saved: {path} ({chars} chars, ~{chars//2} words)")
        else:
            print(f"  FAILED")
        time.sleep(2)

if __name__ == "__main__":
    main()
