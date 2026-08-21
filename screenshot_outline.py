"""用 Playwright Chromium 对大纲编辑页截图。

启动 headless Chromium -> 打开编辑页 -> 等待数据加载 -> 截全页。
输出到 D:/Code/story-studio/docs/screenshots/outline_editor.png
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    # 1. 准备一个有内容的 job（若已存在则复用）
    create_body = json.dumps(
        {"brief": "玉璧之战改编", "project_name": "玉璧之战", "total_chapters": 3}
    ).encode()
    req = urllib.request.Request(
        "http://localhost:8000/novels",
        data=create_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    job_id = json.loads(urllib.request.urlopen(req).read())["job_id"]
    print(f"job_id={job_id}")

    outline_body = json.dumps({
        "structured": {
            "book_title": "玉璧之战",
            "preamble": "节奏螺旋上升，高潮位于全篇 70% 处。整体风格硬核克制，强调感官细节与心理博弈。",
            "chapters": [
                {
                    "num": 1, "title": "黑云压城",
                    "events": [
                        "感官压迫：东魏十万大军压境，恶臭泥泞与马蹄声震碎清晨",
                        "无声对峙：高欢在帅帐审视地图，韦孝宽在城头清点残兵",
                    ],
                    "characters": ["韦孝宽", "高欢", "斛律金", "老卒"],
                    "hook": "高欢下令「三日破城」，韦孝宽点燃第一堆篝火：「三日？能守一日，便是胜利。」",
                    "word_estimate": 2500,
                },
                {
                    "num": 2, "title": "断水与火海",
                    "events": [
                        "水源切断，士兵因焦渴产生幻觉，百姓争水自相残杀",
                        "火攻与反制：火箭如雨，韦孝宽指挥湿泥涂墙、挖防火沟",
                    ],
                    "characters": ["韦孝宽", "李元忠", "东魏火攻将领"],
                    "hook": "井壁坍塌，韦孝宽在枯井底听到微弱水流声，秋雨将至",
                    "word_estimate": 2800,
                },
                {
                    "num": 3, "title": "土山之巅",
                    "events": [
                        "东魏堆筑百尺土山，如怪兽脊背般压迫城头",
                        "李元忠为保护韦孝宽中箭战死，临终塞入带血家书",
                    ],
                    "characters": ["韦孝宽", "李元忠", "段韶", "高欢"],
                    "hook": "高欢远处目睹韦孝宽失声痛哭后继续指挥，眼中闪过一丝恐惧",
                    "word_estimate": 3000,
                },
            ],
        }
    }).encode()
    put_req = urllib.request.Request(
        f"http://localhost:8000/novels/{job_id}/outline",
        data=outline_body,
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    saved = json.loads(urllib.request.urlopen(put_req).read())
    print(f"outline saved: {saved['parsed_chapters']} chapters")

    # 2. Playwright 截图
    out_dir = Path("D:/Code/story-studio/docs/screenshots")
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 1600})
        url = f"http://localhost:3000/novels/{job_id}/outline"
        print(f"opening {url}")
        page.goto(url, wait_until="domcontentloaded")
        # 等待编辑器内容渲染（章节标题出现）
        try:
            page.wait_for_selector("text=黑云压城", timeout=15000)
        except Exception:
            print("warn: 章节标题未及时出现，等待兜底")
            page.wait_for_timeout(3000)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(out_dir / "outline_editor.png"), full_page=True)
        print(f"saved: {out_dir / 'outline_editor.png'}")

        # 再截一张详情页大纲 Tab（带编辑入口）
        detail_url = f"http://localhost:3000/novels/{job_id}"
        page.goto(detail_url, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        # 切到「大纲」Tab
        try:
            page.get_by_role("tab", name="大纲").click()
            page.wait_for_timeout(1000)
        except Exception:
            print("warn: 大纲 tab 点击失败")
        page.screenshot(path=str(out_dir / "novel_detail_outline_tab.png"), full_page=False)
        print(f"saved: {out_dir / 'novel_detail_outline_tab.png'}")

        browser.close()


if __name__ == "__main__":
    main()
