"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { getChapter, listChapters } from "@/lib/api-client";
import { useChapterStream } from "@/lib/sse";
import type { ChapterContent, Chapter } from "@/lib/types";
import { ArrowLeft, ArrowRight, Play, Square } from "lucide-react";

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

  const { tokens, streaming, start, stop } = useChapterStream(id, chapterNum);

  useEffect(() => {
    async function load() {
      try {
        const [ch, list] = await Promise.all([
          getChapter(id, chapterNum),
          listChapters(id),
        ]);
        setContent(ch);
        setChapters(list.chapters);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id, chapterNum]);

  const prevChapter = chapters.find((c) => c.chapter === chapterNum - 1);
  const nextChapter = chapters.find((c) => c.chapter === chapterNum + 1);
  const currentMeta = chapters.find((c) => c.chapter === chapterNum);

  if (loading) {
    return <div className="flex-1 p-6 text-muted-foreground">加载中...</div>;
  }

  return (
    <div className="flex-1 p-6 max-w-4xl mx-auto">
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
            {currentMeta.deai_score !== null && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">去AI分</span>
                <Progress value={currentMeta.deai_score * 2} className="h-2 w-20" />
                <span className="text-sm font-bold">{currentMeta.deai_score}/50</span>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* 流式生成控制 */}
      <div className="flex items-center gap-2 mb-4">
        {!streaming ? (
          <Button size="sm" onClick={start}>
            <Play className="h-4 w-4 mr-1" /> 流式生成本章
          </Button>
        ) : (
          <Button size="sm" variant="destructive" onClick={stop}>
            <Square className="h-4 w-4 mr-1" /> 停止生成
          </Button>
        )}
        {streaming && (
          <span className="text-xs text-muted-foreground animate-pulse">
            生成中...
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
          {/* 流式输出（若有）优先显示，否则显示已存章节 */}
          {tokens ? (
            <div className="prose prose-sm max-w-none whitespace-pre-wrap">
              {tokens}
              {streaming && (
                <span className="inline-block w-2 h-4 bg-primary animate-pulse ml-0.5" />
              )}
            </div>
          ) : content?.content ? (
            <div className="prose prose-sm max-w-none whitespace-pre-wrap leading-loose">
              {content.content}
            </div>
          ) : (
            <p className="text-muted-foreground">
              本章尚未生成。点击"流式生成本章"实时查看 AI 写作过程。
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
