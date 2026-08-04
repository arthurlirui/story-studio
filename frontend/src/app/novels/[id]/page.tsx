"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getNovel, getCost, getOutline, getCharacters } from "@/lib/api-client";
import {
  PHASE_ORDER,
  PHASE_LABELS,
  STATUS_LABELS,
  type Job,
  type CostSummary,
} from "@/lib/types";
import { Check, Loader2, Circle } from "lucide-react";

export default function NovelDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [job, setJob] = useState<Job | null>(null);
  const [cost, setCost] = useState<CostSummary | null>(null);
  const [outline, setOutline] = useState<string>("");
  const [chars, setChars] = useState<{ name: string; preview: string; words: number }[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [j, c, o, ch] = await Promise.all([
          getNovel(id),
          getCost(id),
          getOutline(id),
          getCharacters(id),
        ]);
        setJob(j);
        setCost(c.cost);
        setOutline(o.outline);
        setChars(ch.characters);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [id]);

  if (loading) {
    return <div className="flex-1 p-6 text-muted-foreground">加载中...</div>;
  }

  if (!job) {
    return <div className="flex-1 p-6 text-destructive">项目不存在</div>;
  }

  const currentPhaseIdx = PHASE_ORDER.indexOf(job.phase);

  return (
    <div className="flex-1 space-y-6 p-6">
      {/* 顶部信息 */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">{job.project_name || "(未命名)"}</h1>
          <p className="text-sm text-muted-foreground mt-1">{job.brief}</p>
        </div>
        <Badge variant={job.status === "failed" ? "destructive" : "default"}>
          {STATUS_LABELS[job.status]}
        </Badge>
      </div>

      {/* Phase Stepper */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">创作流水线</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-1 overflow-x-auto pb-2">
            {PHASE_ORDER.map((phase, idx) => {
              const done = idx < currentPhaseIdx;
              const current = idx === currentPhaseIdx;
              return (
                <div key={phase} className="flex items-center">
                  <div className="flex flex-col items-center gap-1 min-w-[80px]">
                    <div
                      className={`flex h-8 w-8 items-center justify-center rounded-full border-2 ${
                        done
                          ? "border-primary bg-primary text-primary-foreground"
                          : current
                            ? "border-primary text-primary animate-pulse"
                            : "border-muted text-muted-foreground"
                      }`}
                    >
                      {done ? (
                        <Check className="h-4 w-4" />
                      ) : current ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Circle className="h-4 w-4" />
                      )}
                    </div>
                    <span
                      className={`text-xs ${
                        current ? "font-semibold text-primary" : "text-muted-foreground"
                      }`}
                    >
                      {PHASE_LABELS[phase]}
                    </span>
                  </div>
                  {idx < PHASE_ORDER.length - 1 && (
                    <div
                      className={`h-0.5 w-8 ${
                        done ? "bg-primary" : "bg-muted"
                      }`}
                    />
                  )}
                </div>
              );
            })}
          </div>
          {job.progress[1] > 0 && (
            <div className="mt-4 flex items-center gap-2">
              <Progress value={(job.progress[0] / job.progress[1]) * 100} className="h-2" />
              <span className="text-xs text-muted-foreground whitespace-nowrap">
                {job.progress[0]}/{job.progress[1]}
              </span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 内容标签页 */}
      <Tabs defaultValue="chapters">
        <TabsList>
          <TabsTrigger value="chapters">章节</TabsTrigger>
          <TabsTrigger value="outline">大纲</TabsTrigger>
          <TabsTrigger value="characters">角色</TabsTrigger>
          <TabsTrigger value="cost">成本</TabsTrigger>
        </TabsList>

        <TabsContent value="chapters">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">章节列表</CardTitle>
              <CardDescription>点击章节查看正文与流式生成</CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild variant="outline">
                <Link href={`/novels/${id}/chapters`}>查看章节地图</Link>
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="outline">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">大纲</CardTitle>
            </CardHeader>
            <CardContent>
              <pre className="whitespace-pre-wrap text-sm font-sans max-h-[400px] overflow-y-auto">
                {outline || "(暂无大纲)"}
              </pre>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="characters">
          <div className="grid gap-3 md:grid-cols-2">
            {chars.length === 0 ? (
              <p className="text-sm text-muted-foreground">暂无角色档案</p>
            ) : (
              chars.map((c) => (
                <Card key={c.name}>
                  <CardHeader>
                    <CardTitle className="text-base">{c.name}</CardTitle>
                    <CardDescription>{c.words} 字</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm text-muted-foreground line-clamp-3">
                      {c.preview}
                    </p>
                  </CardContent>
                </Card>
              ))
            )}
          </div>
        </TabsContent>

        <TabsContent value="cost">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Token 成本</CardTitle>
              <CardDescription>按模型分桶的累计用量</CardDescription>
            </CardHeader>
            <CardContent>
              {cost ? (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-xs text-muted-foreground">总调用次数</p>
                      <p className="text-2xl font-bold">{cost.total_calls}</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">总 Token 数</p>
                      <p className="text-2xl font-bold">{cost.total_tokens.toLocaleString()}</p>
                    </div>
                  </div>
                  <div className="space-y-2">
                    {Object.entries(cost.by_model).map(([model, bucket]) => (
                      <div key={model} className="flex items-center justify-between border-b pb-2">
                        <span className="text-sm font-medium">{model}</span>
                        <div className="text-right text-xs text-muted-foreground">
                          <div>{bucket.calls} 次 · {bucket.total.toLocaleString()} tokens</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">暂无成本数据</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
