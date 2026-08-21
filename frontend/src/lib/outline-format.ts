// 大纲渲染：与后端 outline_format.render_outline 保持一致的 Markdown 模板。
// 仅用于「源码模式」预览与切换；真正的保存渲染以后端为准（契约测试锁定）。
import type { ChapterOutline, OutlineDoc } from "./types";

export function renderChapter(ch: ChapterOutline): string {
  const lines: string[] = [`## 第${ch.num}章：${ch.title}`.replace(/：$/, "")];
  lines.push("");
  lines.push("*   **核心事件**：");
  ch.events.forEach((ev, i) => {
    lines.push(`    ${i + 1}.  ${ev}`);
  });
  lines.push(`*   **出场角色**：${ch.characters.join("、")}`);
  lines.push(`*   **章节悬念/钩子**：${ch.hook}`);
  lines.push(`*   **字数预估**：${ch.word_estimate}字`);
  return lines.join("\n");
}

export function renderOutline(doc: OutlineDoc): string {
  const parts: string[] = [];
  if (doc.book_title.trim()) parts.push(`# 《${doc.book_title.trim()}》章节大纲`);
  if (doc.preamble.trim()) parts.push(doc.preamble.trim());
  doc.chapters.forEach((ch) => parts.push(renderChapter(ch)));
  return parts.length ? parts.join("\n\n") + "\n" : "";
}
