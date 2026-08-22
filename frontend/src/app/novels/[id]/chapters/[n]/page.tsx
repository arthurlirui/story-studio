"use client";

import { use, useEffect, useState, useRef, useCallback } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { getChapter, listChapters, saveChapter } from "@/lib/api-client";
import { useChapterStream } from "@/lib/sse";
import type { ChapterContent, Chapter } from "@/lib/types";
import { ArrowLeft, ArrowRight, Play, Square, Pencil, BookOpen, Check, Loader2 } from "lucide-react";

// ProseMirror 不支持 SSR，动态加载编辑器
const MarkdownEditor = dynamic(() => import("@/components/markdown-editor"), {
  ssr: false,
  loading: () => <div className="text-muted-foreground text-sm">加载编辑器...</div>,
});

type SaveState = "idle" | "saving" | "saved" | "error";

export default function ChapterReaderPage({
  params,
}: {
  params: Promise<{ id: string; n: string }>;
}) {
  const { id, n } = use(params);
  const chapterNum = parseInt(n);
  const [content, setContent] = useState<ChapterContent | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 编辑模式
  const [editMode, setEditMode] = useState(false);
  const [editContent, setEditContent] = useState("");
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [dirty, setDirty] = useState(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latestContent = useRef("");

  const { tokens, streaming, start, stop } = useChapterStream(id, isNaN(chapterNum) ? null : chapterNum);

  useEffect(() => {
    if (isNaN(chapterNum)) {
      Promise.resolve().then(() => {
        setError("无效的章节号");
        setLoading(false);
      });
      return;
    }
    async function load() {
      try {
        const [ch, list] = await Promise.all([
          getChapter(id, chapterNum),
          listChapters(id),
        ]);
        setContent(ch);
        setChapters(list.chapters);
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : "加载失败");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id, chapterNum]);

  // beforeunload 脏数据守卫
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (saveState === "saving" || (editMode && latestContent.current !== (content?.content ?? ""))) {
        e.preventDefault();
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [editMode, saveState, content]);

  // 清理定时器
  useEffect(() => {
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    };
  }, []);

  /** debounce 自动保存：1.5s 无新改动后保存 */
  const scheduleSave = useCallback(
    (markdown: string) => {
      latestContent.current = markdown;
      setDirty(true);
      setSaveState("idle");
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(async () => {
        setSaveState("saving");
        try {
          await saveChapter(id, chapterNum, markdown);
          setSaveState("saved");
          setDirty(false);
          setContent((c) => (c ? { ...c, content: markdown } : c));
        } catch {
          setSaveState("error");
        }
      }, 1500);
    },
    [id, chapterNum],
  );

  const handleEnterEdit = () => {
    setEditContent(content?.content ?? "");
    latestContent.current = content?.content ?? "";
    setSaveState("idle");
    setEditMode(true);
  };

  const handleExitEdit = () => {
    // 退出前 flush 未保存内容
    if (saveTimer.current) {
      clearTimeout(saveTimer.current);
      saveTimer.current = null;
    }
    if (latestContent.current !== (content?.content ?? "")) {
      setSaveState("saving");
      saveChapter(id, chapterNum, latestContent.current)
        .then(() => {
          setSaveState("saved");
          setContent((c) => (c ? { ...c, content: latestContent.current } : c));
        })
        .catch(() => setSaveState("error"));
    }
    setEditMode(false);
  };

  const prevChapter = chapters.find((c) => c.chapter === chapterNum - 1);
  const nextChapter = chapters.find((c) => c.chapter === chapterNum + 1);
  const currentMeta = chapters.find((c) => c.chapter === chapterNum);

  if (loading) {
    return <div className="text-muted-foreground">加载中...</div>;
  }

  if (error) {
    return <div className="text-destructive">{error}</div>;
  }

  const canEdit = !streaming && !!content?.content;

  return (
    <div className="max-w-4xl mx-auto">
      {/* 导航 */}
      <div className="flex items-center justify-between mb-4">
        <Button variant="ghost" size="sm" asChild>
          <Link href={`/novels/${id}/chapters`}>
            <ArrowLeft className="h-4 w-4 mr-1" /> 章节列表
          </Link>
        </Button>
        <div className="flex gap-2">
          {prevChapter && (
            <Button variant="outline" size="sm" asChild>
              <Link href={`/novels/${id}/chapters/${prevChapter.chapter}`}>
                <ArrowLeft className="h-4 w-4" /> 上一章
              </Link>
            </Button>
          )}
          {nextChapter && (
            <Button variant="outline" size="sm" asChild>
              <Link href={`/novels/${id}/chapters/${nextChapter.chapter}`}>
                下一章 <ArrowRight className="h-4 w-4 ml-1" />
              </Link>
            </Button>
          )}
        </div>
      </div>

      {/* 章节元信息 */}
      {currentMeta && (
        <Card className="mb-4">
          <CardContent className="flex items-center justify-between py-3">
            <div className="flex items-center gap-3">
              <span className="text-sm text-muted-foreground">第 {chapterNum} 章</span>
              {currentMeta.verdict && (
                <Badge variant={currentMeta.verdict === "PASS" ? "default" : "secondary"}>
                  {currentMeta.verdict}
                </Badge>
              )}
              <span className="text-xs text-muted-foreground">
                {currentMeta.words.toLocaleString()} 字
              </span>
            </div>
            <div className="flex items-center gap-3">
              {currentMeta.deai_score !== null && (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">去AI分</span>
                  <Progress value={currentMeta.deai_score * 2} className="h-2 w-20" />
                  <span className="text-sm font-bold">{currentMeta.deai_score}/50</span>
                </div>
              )}
              {/* 编辑/阅读模式切换 */}
              {canEdit && (
                <Button
                  variant={editMode ? "default" : "outline"}
                  size="sm"
                  onClick={editMode ? handleExitEdit : handleEnterEdit}
                >
                  {editMode ? (
                    <><BookOpen className="h-4 w-4 mr-1" /> 完成编辑</>
                  ) : (
                    <><Pencil className="h-4 w-4 mr-1" /> 编辑</>
                  )}
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* 流式生成控制 */}
      <div className="flex items-center gap-2 mb-4">
        {!streaming ? (
          <Button size="sm" onClick={start} aria-label="开始流式生成本章" disabled={editMode}>
            <Play className="h-4 w-4 mr-1" /> 流式生成本章
          </Button>
        ) : (
          <Button size="sm" variant="destructive" onClick={stop} aria-label="停止流式生成">
            <Square className="h-4 w-4 mr-1" /> 停止生成
          </Button>
        )}
        {streaming && (
          <span className="text-xs text-muted-foreground animate-pulse">
            生成中...
          </span>
        )}
        {/* 自动保存状态指示 */}
        {editMode && (
          <span className="text-xs text-muted-foreground ml-auto flex items-center gap-1">
            {saveState === "saving" && <><Loader2 className="h-3 w-3 animate-spin" /> 保存中...</>}
            {saveState === "saved" && <><Check className="h-3 w-3 text-emerald-500" /> 已保存</>}
            {saveState === "error" && <span className="text-destructive">保存失败</span>}
            {saveState === "idle" && dirty && "● 未保存"}
          </span>
        )}
      </div>

      {/* 正文 */}
      <Card>
        <CardHeader>
          <CardTitle>
            {currentMeta?.title || `第 ${chapterNum} 章`}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {/* 编辑模式：Milkdown 富文本编辑器 */}
          {editMode && !streaming ? (
            <MarkdownEditor
              defaultValue={editContent}
              onChange={scheduleSave}
              className="min-h-[60vh]"
            />
          ) : tokens ? (
            /* 流式输出优先显示 */
            <div className="prose prose-lg dark:prose-invert max-w-none whitespace-pre-wrap font-serif leading-loose">
              {tokens}
              {streaming && (
                <span className="inline-block w-2 h-4 bg-primary animate-pulse ml-0.5" />
              )}
            </div>
          ) : content?.content ? (
            /* 阅读模式：prose 排版 */
            <div className="prose prose-lg dark:prose-invert max-w-none whitespace-pre-wrap font-serif leading-loose">
              {content.content}
            </div>
          ) : (
            <p className="text-muted-foreground">
              本章尚未生成。点击&ldquo;流式生成本章&rdquo;实时查看 AI 写作过程。
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
