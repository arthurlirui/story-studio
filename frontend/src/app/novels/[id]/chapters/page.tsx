"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { listChapters } from "@/lib/api-client";
import type { Chapter } from "@/lib/types";

export default function ChaptersPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const resp = await listChapters(id);
        setChapters(resp.chapters);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id]);

  function scoreColor(score: number | null): string {
    if (score === null) return "bg-muted";
    if (score >= 40) return "bg-green-500";
    if (score >= 30) return "bg-yellow-500";
    if (score >= 20) return "bg-orange-500";
    return "bg-red-500";
  }

  return (
    <div className="flex-1 space-y-6 p-6">
      <h1 className="text-2xl font-bold">章节地图</h1>

      {loading ? (
        <p className="text-sm text-muted-foreground">加载中...</p>
      ) : chapters.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            暂无章节
          </CardContent>
        </Card>
      ) : (
        <>
          {/* 质量热力图 */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">去AI化质量热力图</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-10 gap-1.5">
                {chapters.map((c) => (
                  <Link
                    key={c.chapter}
                    href={`/novels/${id}/chapters/${c.chapter}`}
                    className="group relative"
                    title={`第${c.chapter}章 · ${c.title || "无标题"} · 去AI分: ${c.deai_score ?? "N/A"}`}
                  >
                    <div
                      className={`aspect-square rounded ${scoreColor(c.deai_score)} flex items-center justify-center text-xs font-bold text-white hover:ring-2 hover:ring-primary transition-all`}
                    >
                      {c.chapter}
                    </div>
                  </Link>
                ))}
              </div>
              <div className="mt-3 flex items-center gap-4 text-xs text-muted-foreground">
                <span>去AI分：</span>
                <span className="flex items-center gap-1"><span className="h-3 w-3 rounded bg-green-500" /> 40+</span>
                <span className="flex items-center gap-1"><span className="h-3 w-3 rounded bg-yellow-500" /> 30+</span>
                <span className="flex items-center gap-1"><span className="h-3 w-3 rounded bg-orange-500" /> 20+</span>
                <span className="flex items-center gap-1"><span className="h-3 w-3 rounded bg-red-500" /> &lt;20</span>
                <span className="flex items-center gap-1"><span className="h-3 w-3 rounded bg-muted" /> 无</span>
              </div>
            </CardContent>
          </Card>

          {/* 章节列表 */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">章节列表（{chapters.length} 章）</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-1">
                {chapters.map((c) => (
                  <Link
                    key={c.chapter}
                    href={`/novels/${id}/chapters/${c.chapter}`}
                    className="flex items-center justify-between rounded px-3 py-2 hover:bg-accent transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-sm font-mono text-muted-foreground w-8">
                        {c.chapter}
                      </span>
                      <span className="text-sm font-medium">{c.title || "(无标题)"}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-muted-foreground">{c.words.toLocaleString()} 字</span>
                      {c.verdict && (
                        <Badge
                          variant={
                            c.verdict === "PASS" ? "default" :
                            c.verdict === "REVISE" ? "secondary" : "destructive"
                          }
                        >
                          {c.verdict}
                        </Badge>
                      )}
                      {c.deai_score !== null && (
                        <span className="text-xs text-muted-foreground">
                          去AI:{c.deai_score}
                        </span>
                      )}
                    </div>
                  </Link>
                ))}
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
