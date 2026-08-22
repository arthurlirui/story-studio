"use client";

import { use, useEffect, useMemo, useState, useCallback } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  getOutlineStructured,
  saveOutlineStructured,
  saveOutlineRaw,
} from "@/lib/api-client";
import { renderOutline } from "@/lib/outline-format";
import type { ChapterOutline, OutlineDoc } from "@/lib/types";
import {
  ArrowLeft,
  ArrowDown,
  ArrowUp,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  Loader2,
  Plus,
  Save,
  Trash2,
  X,
} from "lucide-react";

const DEFAULT_WORD_ESTIMATE = 2500;

// ProseMirror 不支持 SSR，动态加载编辑器
const MarkdownEditor = dynamic(() => import("@/components/markdown-editor"), {
  ssr: false,
  loading: () => <div className="text-muted-foreground text-sm">加载编辑器...</div>,
});

function emptyChapter(num: number): ChapterOutline {
  return {
    num,
    title: "",
    events: [],
    characters: [],
    hook: "",
    word_estimate: DEFAULT_WORD_ESTIMATE,
  };
}

function cloneDoc(doc: OutlineDoc): OutlineDoc {
  return {
    book_title: doc.book_title,
    preamble: doc.preamble,
    chapters: doc.chapters.map((c) => ({ ...c, events: [...c.events], characters: [...c.characters] })),
  };
}

/** 章号按列表顺序重排（服务端保存时也会重排，前端展示保持一致） */
function renumber(chapters: ChapterOutline[]): ChapterOutline[] {
  return chapters.map((c, i) => (c.num === i + 1 ? c : { ...c, num: i + 1 }));
}

export default function OutlineEditorPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [doc, setDoc] = useState<OutlineDoc>({ book_title: "", preamble: "", chapters: [] });
  const [savedDoc, setSavedDoc] = useState<OutlineDoc>({ book_title: "", preamble: "", chapters: [] });
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [mode, setMode] = useState<"structured" | "source">("structured");
  const [sourceText, setSourceText] = useState("");
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());
  const [charInput, setCharInput] = useState<Record<number, string>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await getOutlineStructured(id);
      const next: OutlineDoc = {
        book_title: data.book_title || "",
        preamble: data.preamble || "",
        chapters: (data.chapters || []).map((c) => ({
          num: c.num,
          title: c.title || "",
          events: c.events || [],
          characters: c.characters || [],
          hook: c.hook || "",
          word_estimate: c.word_estimate || DEFAULT_WORD_ESTIMATE,
        })),
      };
      setDoc(next);
      setSavedDoc(cloneDoc(next));
      setSourceText("");
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    // 微任务延迟，避免 effect 内同步 setState（与详情页 refreshStaticData 同一模式）
    Promise.resolve().then(load);
  }, [load]);

  const dirty = useMemo(
    () => JSON.stringify(doc) !== JSON.stringify(savedDoc) || (mode === "source" && sourceText !== ""),
    [doc, savedDoc, mode, sourceText],
  );

  // 离开页面前提示未保存更改
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (dirty) {
        e.preventDefault();
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  const chapters = doc.chapters;
  const totalWords = useMemo(
    () => chapters.reduce((sum, c) => sum + (c.word_estimate || 0), 0),
    [chapters],
  );

  // ── 结构化模式操作 ─────────────────────────────────────────

  const updateChapter = (idx: number, patch: Partial<ChapterOutline>) => {
    setDoc((d) => ({
      ...d,
      chapters: d.chapters.map((c, i) => (i === idx ? { ...c, ...patch } : c)),
    }));
  };

  const addChapter = () => {
    setDoc((d) => ({
      ...d,
      chapters: renumber([...d.chapters, emptyChapter(d.chapters.length + 1)]),
    }));
  };

  const removeChapter = (idx: number) => {
    const ch = chapters[idx];
    if (!window.confirm(`确定删除「第${ch.num}章：${ch.title || "未命名"}」吗？后续章节将自动重新编号。`)) return;
    setDoc((d) => ({ ...d, chapters: renumber(d.chapters.filter((_, i) => i !== idx)) }));
    setCollapsed((s) => {
      const next = new Set<number>();
      s.forEach((n) => next.add(n > idx ? n - 1 : n));
      return next;
    });
  };

  const moveChapter = (idx: number, dir: -1 | 1) => {
    const target = idx + dir;
    if (target < 0 || target >= chapters.length) return;
    setDoc((d) => {
      const list = [...d.chapters];
      [list[idx], list[target]] = [list[target], list[idx]];
      return { ...d, chapters: renumber(list) };
    });
    setCollapsed((s) => {
      const next = new Set(s);
      const a = next.has(idx), b = next.has(target);
      if (a) {
        next.add(target);
      } else {
        next.delete(target);
      }
      if (b) {
        next.add(idx);
      } else {
        next.delete(idx);
      }
      return next;
    });
  };

  const toggleCollapse = (idx: number) => {
    setCollapsed((s) => {
      const next = new Set(s);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  const addCharacter = (idx: number) => {
    const raw = (charInput[idx] || "").trim();
    if (!raw) return;
    const names = raw.split(/[、，,;；\s]+/).filter(Boolean);
    updateChapter(idx, {
      characters: [...chapters[idx].characters, ...names.filter((n) => !chapters[idx].characters.includes(n))],
    });
    setCharInput((m) => ({ ...m, [idx]: "" }));
  };

  const removeCharacter = (idx: number, name: string) => {
    updateChapter(idx, { characters: chapters[idx].characters.filter((c) => c !== name) });
  };

  // ── 模式切换 ───────────────────────────────────────────────

  const switchToSource = () => {
    if (dirty && !window.confirm("有未保存的修改。切换到源码模式将把当前结构化内容渲染为 Markdown，未保存的修改会保留在渲染结果中。继续？")) {
      return;
    }
    setSourceText(renderOutline(doc));
    setMode("source");
  };

  const switchToStructured = () => {
    // 源码模式下文本由后端解析；切换前确认（未保存的源码修改会丢失渲染保真度）
    if (sourceText !== "" && !window.confirm("切换回结构化模式后，源码中的修改需要先保存再重新加载才能生效。继续？")) {
      return;
    }
    setMode("structured");
  };

  // ── 保存 ───────────────────────────────────────────────────

  const handleSave = async () => {
    setSaving(true);
    setSaveError(null);
    setSaveMessage(null);
    try {
      let result;
      if (mode === "source") {
        result = await saveOutlineRaw(id, sourceText);
        if (result.parsed_chapters === 0 && sourceText.trim()) {
          setSaveError("已保存，但未能从文本中解析出任何章节，格式可能与写作流水线不兼容。");
        }
        // 重新加载结构化数据以同步编辑器状态
        await load();
        setMode("structured");
      } else {
        const payload: OutlineDoc = {
          book_title: doc.book_title,
          preamble: doc.preamble,
          chapters: renumber(doc.chapters),
        };
        result = await saveOutlineStructured(id, payload);
        setDoc(payload);
        setSavedDoc(cloneDoc(payload));
      }
      setSaveMessage(
        `保存成功：${result.parsed_chapters} 章 · ${result.outline_chars} 字` +
          (result.total_chapters != null ? ` · 总章节数已同步为 ${result.total_chapters}` : ""),
      );
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    if (!window.confirm("放弃所有未保存的修改，恢复到上次保存的版本？")) return;
    setDoc(cloneDoc(savedDoc));
    setSourceText("");
    setSaveMessage(null);
    setSaveError(null);
  };

  // ── 渲染 ───────────────────────────────────────────────────

  if (loading) {
    return <div className="text-muted-foreground">加载中...</div>;
  }

  if (loadError) {
    return (
      <div className="space-y-4">
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          ⚠️ {loadError}
        </div>
        <Button variant="outline" asChild>
          <Link href={`/novels/${id}`}>返回项目详情</Link>
        </Button>
      </div>
    );
  }

  const isEmpty = chapters.length === 0;

  return (
    <div className="space-y-4">
      {/* 顶栏 */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" asChild aria-label="返回项目详情">
            <Link href={`/novels/${id}`}>
              <ArrowLeft className="h-4 w-4" />
            </Link>
          </Button>
          <div>
            <h1 className="text-xl font-bold">大纲编辑</h1>
            <p className="text-xs text-muted-foreground mt-0.5">
              共 {chapters.length} 章 · 预估总字数 {totalWords.toLocaleString()}
              {dirty && <span className="ml-2 text-primary">● 有未保存更改</span>}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" disabled={!dirty} onClick={handleReset}>
            重置
          </Button>
          {mode === "structured" ? (
            <Button variant="outline" size="sm" onClick={switchToSource}>
              源码模式
            </Button>
          ) : (
            <Button variant="outline" size="sm" onClick={switchToStructured}>
              结构化模式
            </Button>
          )}
          <Button size="sm" onClick={handleSave} disabled={saving || (!dirty && mode === "structured")}>
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            保存
          </Button>
        </div>
      </div>

      {saveMessage && (
        <div className="rounded-md border border-emerald-500/50 bg-emerald-500/10 p-3 text-sm text-emerald-700 dark:text-emerald-400" role="status">
          ✓ {saveMessage}
        </div>
      )}
      {saveError && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive" role="alert">
          <CircleAlert className="mr-1 inline h-4 w-4" />
          {saveError}
        </div>
      )}

      {mode === "source" ? (
        /* ── 源码模式（Milkdown 富文本编辑器） ── */
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">
            直接编辑 Markdown，实时预览。保存时由后端解析；章节头需为「## 第N章：标题」，字段为加粗的核心事件/出场角色/章节悬念钩子/字数预估。
          </p>
          {/* key 随 sourceText 的"已保存基准"变化时重建编辑器，确保外部重置/切换同步 */}
          <MarkdownEditor
            key={`outline-source-${mode}`}
            defaultValue={sourceText}
            onChange={setSourceText}
            placeholder="大纲 Markdown 源码..."
            className="min-h-[65vh] border rounded-md"
          />
        </div>
      ) : (
        /* ── 结构化模式 ── */
        <div className="space-y-4">
          {/* 书名 + 设计说明 */}
          <Card>
            <CardContent className="space-y-3 pt-4">
              <div className="grid gap-3 md:grid-cols-[1fr_2fr]">
                <div className="space-y-1.5">
                  <Label htmlFor="book-title">书名</Label>
                  <Input
                    id="book-title"
                    value={doc.book_title}
                    onChange={(e) => setDoc((d) => ({ ...d, book_title: e.target.value }))}
                    placeholder="如：玉璧之战"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="preamble">设计说明（章节列表前的自由文本）</Label>
                  <Textarea
                    id="preamble"
                    value={doc.preamble}
                    onChange={(e) => setDoc((d) => ({ ...d, preamble: e.target.value }))}
                    placeholder="整体节奏、高潮位置、视角等全局说明"
                    className="min-h-16"
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {isEmpty && (
            <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
              大纲尚未生成。可以手动逐章创建，或先运行创作流水线的大纲阶段。
            </div>
          )}

          {/* 章节卡片 */}
          {chapters.map((ch, idx) => {
            const isCollapsed = collapsed.has(idx);
            return (
              <Card key={`ch-${idx}-${ch.num}`}>
                <CardHeader className="pb-3">
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      className="text-muted-foreground hover:text-foreground"
                      onClick={() => toggleCollapse(idx)}
                      aria-label={isCollapsed ? "展开章节" : "折叠章节"}
                      aria-expanded={!isCollapsed}
                    >
                      {isCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                    </button>
                    <Badge variant="secondary" className="shrink-0">第{ch.num}章</Badge>
                    <Input
                      value={ch.title}
                      onChange={(e) => updateChapter(idx, { title: e.target.value })}
                      placeholder="章节标题"
                      className="font-medium"
                      aria-label={`第${ch.num}章标题`}
                    />
                    <div className="flex shrink-0 items-center gap-0.5">
                      <Button variant="ghost" size="icon" onClick={() => moveChapter(idx, -1)} disabled={idx === 0} aria-label="上移">
                        <ArrowUp className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="icon" onClick={() => moveChapter(idx, 1)} disabled={idx === chapters.length - 1} aria-label="下移">
                        <ArrowDown className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="icon" onClick={() => removeChapter(idx)} aria-label="删除章节" className="text-destructive hover:text-destructive">
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                {!isCollapsed && (
                  <CardContent className="space-y-4">
                    {/* 核心事件 */}
                    <div className="space-y-1.5">
                      <Label>核心事件</Label>
                      <div className="space-y-2">
                        {ch.events.map((ev, ei) => (
                          <div key={ei} className="flex items-start gap-2">
                            <Badge variant="outline" className="mt-2 shrink-0 tabular-nums">{ei + 1}</Badge>
                            <Textarea
                              value={ev}
                              onChange={(e) => {
                                const events = [...ch.events];
                                events[ei] = e.target.value;
                                updateChapter(idx, { events });
                              }}
                              className="min-h-12"
                              aria-label={`核心事件 ${ei + 1}`}
                            />
                            <Button
                              variant="ghost"
                              size="icon"
                              className="mt-1 shrink-0 text-muted-foreground hover:text-destructive"
                              onClick={() => updateChapter(idx, { events: ch.events.filter((_, j) => j !== ei) })}
                              aria-label="删除事件"
                            >
                              <X className="h-4 w-4" />
                            </Button>
                          </div>
                        ))}
                        <Button variant="outline" size="sm" onClick={() => updateChapter(idx, { events: [...ch.events, ""] })}>
                          <Plus className="h-3.5 w-3.5" /> 添加事件
                        </Button>
                      </div>
                    </div>

                    <div className="grid gap-4 md:grid-cols-2">
                      {/* 出场角色 */}
                      <div className="space-y-1.5">
                        <Label>出场角色</Label>
                        <div className="flex flex-wrap gap-1.5">
                          {ch.characters.map((name) => (
                            <Badge key={name} variant="secondary" className="gap-1 pr-1">
                              {name}
                              <button
                                type="button"
                                onClick={() => removeCharacter(idx, name)}
                                className="rounded-full hover:bg-muted-foreground/20"
                                aria-label={`移除角色 ${name}`}
                              >
                                <X className="h-3 w-3" />
                              </button>
                            </Badge>
                          ))}
                        </div>
                        <Input
                          value={charInput[idx] || ""}
                          onChange={(e) => setCharInput((m) => ({ ...m, [idx]: e.target.value }))}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              e.preventDefault();
                              addCharacter(idx);
                            }
                          }}
                          onBlur={() => addCharacter(idx)}
                          placeholder="输入角色名，回车添加（可一次粘贴多个，顿号分隔）"
                          aria-label={`第${ch.num}章添加角色`}
                        />
                      </div>

                      {/* 字数预估 */}
                      <div className="space-y-1.5">
                        <Label htmlFor={`words-${idx}`}>字数预估</Label>
                        <div className="flex items-center gap-2">
                          <Input
                            id={`words-${idx}`}
                            type="number"
                            min={0}
                            max={100000}
                            value={ch.word_estimate}
                            onChange={(e) => updateChapter(idx, { word_estimate: Number(e.target.value) || 0 })}
                            className="w-28"
                          />
                          <span className="text-sm text-muted-foreground">字</span>
                        </div>
                      </div>
                    </div>

                    {/* 悬念/钩子 */}
                    <div className="space-y-1.5">
                      <Label htmlFor={`hook-${idx}`}>章节悬念/钩子</Label>
                      <Textarea
                        id={`hook-${idx}`}
                        value={ch.hook}
                        onChange={(e) => updateChapter(idx, { hook: e.target.value })}
                        placeholder="本章结尾留给下一章的悬念"
                        className="min-h-12"
                      />
                    </div>
                  </CardContent>
                )}
              </Card>
            );
          })}

          <Button variant="outline" onClick={addChapter} className="w-full border-dashed">
            <Plus className="h-4 w-4" /> 添加章节
          </Button>
        </div>
      )}
    </div>
  );
}
