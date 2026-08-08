"use client";

import { use, useEffect, useState, useCallback, useRef } from "react";
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
import {
  getNovel,
  getCost,
  getOutline,
  getCharacters,
  cancelNovel,
  resumeNovel,
  runAllTasks,
} from "@/lib/api-client";
import { useJobEvents, useAgentEvents } from "@/lib/sse";
import {
  PHASE_ORDER,
  PHASE_LABELS,
  STATUS_LABELS,
  type Job,
  type CostSummary,
} from "@/lib/types";
import { Check, Loader2, Circle } from "lucide-react";

function safeProgress(progress: [number, number] | undefined): [number, number] {
  if (!progress || !Array.isArray(progress) || progress.length < 2) return [0, 0];
  return [progress[0] || 0, progress[1] || 0];
}

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
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // SSE 增量更新（P1 修复：替代 setInterval 轮询）
  const sseJob = useJobEvents(id);
  // 智能体活动日志流（P0 修复：接入死代码）
  const { entries: agentEntries } = useAgentEvents(id);

  // 合并 SSE 更新（用 ref + 微任务避免 effect 内同步 setState）
  const sseJobRef = useRef<Job | null>(null);
  useEffect(() => {
    sseJobRef.current = sseJob;
    if (sseJob) {
      Promise.resolve().then(() => setJob(sseJob));
    }
  }, [sseJob]);

  const refreshStaticData = useCallback(async () => {
    try {
      const [j, c, o, ch] = await Promise.allSettled([
        getNovel(id),
        getCost(id),
        getOutline(id),
        getCharacters(id),
      ]);
      if (j.status === "fulfilled") setJob(j.value);
      if (c.status === "fulfilled") setCost(c.value.cost);
      if (o.status === "fulfilled") setOutline(o.value.outline);
      if (ch.status === "fulfilled") setChars(ch.value.characters);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    Promise.resolve().then(refreshStaticData);
  }, [refreshStaticData]);

  // 当 job 完成时刷新静态数据
  const jobStatus = job?.status;
  const prevStatusRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (prevStatusRef.current !== jobStatus && (jobStatus === "succeeded" || jobStatus === "failed")) {
      prevStatusRef.current = jobStatus;
      Promise.resolve().then(refreshStaticData);
    }
  }, [jobStatus, refreshStaticData]);

  async function handleCancel() {
    setActionError(null);
    try {
      await cancelNovel(id);
      refreshStaticData();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "取消失败");
    }
  }

  async function handleResume() {
    setActionError(null);
    try {
      await resumeNovel(id);
      refreshStaticData();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "恢复失败");
    }
  }

  async function handleRunAll() {
    setActionError(null);
    try {
      await runAllTasks(id);
      refreshStaticData();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "启动失败");
    }
  }

  if (loading) {
    return <div className="flex-1 p-6 text-muted-foreground">加载中...</div>;
  }

  if (!job) {
    return <div className="flex-1 p-6 text-destructive">{error || "项目不存在"}</div>;
  }

  const currentPhaseIdx = PHASE_ORDER.indexOf(job.phase);
  const [progDone, progTotal] = safeProgress(job.progress);
  const isRunning = job.status === "running";

  return (
    <div className="flex-1 space-y-6 p-6">
      {/* 顶部信息 */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">{job.project_name || "(未命名)"}</h1>
          <p className="text-sm text-muted-foreground mt-1">{job.brief}</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={job.status === "failed" ? "destructive" : "default"}>
            {STATUS_LABELS[job.status]}
          </Badge>
          {isRunning && (
            <Button size="sm" variant="destructive" onClick={handleCancel}>
              取消
            </Button>
          )}
          {(job.status === "failed" || job.status === "cancelled") && (
            <Button size="sm" variant="outline" onClick={handleResume}>
              恢复
            </Button>
          )}
          {job.status === "queued" && (
            <Button size="sm" onClick={handleRunAll}>
              启动
            </Button>
          )}
        </div>
      </div>

      {actionError && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive" role="alert">
          ⚠️ {actionError}
        </div>
      )}

      {/* Phase Stepper — P1 修复：a11y 加 role="list" + aria-current */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">创作流水线</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-1 overflow-x-auto pb-2" role="list" aria-label="创作阶段进度">
            {PHASE_ORDER.map((phase, idx) => {
              const done = idx < currentPhaseIdx;
              const current = idx === currentPhaseIdx;
              return (
                <div key={phase} className="flex items-center" role="listitem">
                  <div className="flex flex-col items-center gap-1 min-w-[80px]">
                    <div
                      className={`flex h-8 w-8 items-center justify-center rounded-full border-2 ${
                        done
                          ? "border-primary bg-primary text-primary-foreground"
                          : current
                            ? "border-primary text-primary animate-pulse"
                            : "border-muted text-muted-foreground"
                      }`}
                      aria-current={current ? "step" : undefined}
                      aria-label={`${PHASE_LABELS[phase]} ${done ? "已完成" : current ? "进行中" : "未开始"}`}
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
          {progTotal > 0 && (
            <div className="mt-4 flex items-center gap-2">
              <Progress value={(progDone / progTotal) * 100} className="h-2" />
              <span className="text-xs text-muted-foreground whitespace-nowrap">
                {progDone}/{progTotal}
              </span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 内容标签页 — P0 修复：新增"智能体"Tab 接入 useAgentEvents */}
      <Tabs defaultValue="chapters">
        <TabsList>
          <TabsTrigger value="chapters">章节</TabsTrigger>
          <TabsTrigger value="outline">大纲</TabsTrigger>
          <TabsTrigger value="characters">角色</TabsTrigger>
          <TabsTrigger value="agents">智能体</TabsTrigger>
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

        <TabsContent value="agents">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">智能体活动日志</CardTitle>
              <CardDescription>14 个 AI 智能体的实时工作记录</CardDescription>
            </CardHeader>
            <CardContent>
              {agentEntries.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  暂无活动记录。运行任务后此处将实时显示各智能体的写作、评审、检查等操作。
                </p>
              ) : (
                <div className="space-y-2 max-h-[400px] overflow-y-auto">
                  {agentEntries.map((entry, i) => (
                    <div key={i} className="flex items-start gap-3 rounded-md border p-2 text-sm">
                      {entry.agent && (
                        <Badge variant="secondary" className="shrink-0">
                          {entry.agent}
                        </Badge>
                      )}
                      <div className="flex-1 min-w-0">
                        {entry.action && (
                          <span className="text-xs text-muted-foreground">{entry.action}</span>
                        )}
                        {entry.verdict && (
                          <Badge
                            variant={entry.verdict === "PASS" ? "default" : entry.verdict === "REJECT" ? "destructive" : "secondary"}
                            className="ml-2 text-xs"
                          >
                            {entry.verdict}
                          </Badge>
                        )}
                        {entry.excerpt && (
                          <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{entry.excerpt}</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
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
                          <div>{bucket.calls} 次 · {bucket.total_tokens.toLocaleString()} tokens</div>
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
