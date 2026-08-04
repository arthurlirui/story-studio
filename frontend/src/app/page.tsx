"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { listNovels, checkHealth } from "@/lib/api-client";
import { STATUS_LABELS, PHASE_LABELS, type Job } from "@/lib/types";

export default function DashboardPage() {
  const [novels, setNovels] = useState<Job[]>([]);
  const [healthy, setHealthy] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [novelsResp, ok] = await Promise.all([listNovels(), checkHealth()]);
        setNovels(novelsResp.novels);
        setHealthy(ok);
      } catch (e) {
        console.error(e);
        setHealthy(false);
      } finally {
        setLoading(false);
      }
    }
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, []);

  const running = novels.filter((n) => n.status === "running").length;
  const succeeded = novels.filter((n) => n.status === "succeeded").length;
  const failed = novels.filter((n) => n.status === "failed").length;

  return (
    <div className="flex-1 space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">仪表盘</h1>
        <Badge variant={healthy ? "default" : "destructive"}>
          {healthy === null ? "检测中..." : healthy ? "后端在线" : "后端离线"}
        </Badge>
      </div>

      {/* 统计卡片 */}
      <div className="grid gap-4 md:grid-cols-4">
        <StatCard title="总项目" value={novels.length} desc="所有小说任务" />
        <StatCard title="运行中" value={running} desc="正在生成的 Job" />
        <StatCard title="已完成" value={succeeded} desc="成功交付的小说" />
        <StatCard title="失败" value={failed} desc="需要重试的 Job" />
      </div>

      {/* Job 列表 */}
      <Card>
        <CardHeader>
          <CardTitle>项目列表</CardTitle>
          <CardDescription>所有小说生成任务（每 5 秒自动刷新）</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">加载中...</p>
          ) : novels.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-sm text-muted-foreground mb-4">暂无项目</p>
              <Link
                href="/novels/new"
                className="text-sm text-primary hover:underline"
              >
                创建新小说 &raquo;
              </Link>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>项目名</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>阶段</TableHead>
                  <TableHead className="w-[120px]">进度</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {novels.map((n) => (
                  <TableRow key={n.id}>
                    <TableCell className="font-medium">
                      {n.project_name || "(未命名)"}
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={n.status} />
                    </TableCell>
                    <TableCell>{PHASE_LABELS[n.phase] || n.phase}</TableCell>
                    <TableCell>
                      {n.progress[1] > 0 ? (
                        <div className="flex items-center gap-2">
                          <Progress
                            value={(n.progress[0] / n.progress[1]) * 100}
                            className="h-2"
                          />
                          <span className="text-xs text-muted-foreground">
                            {n.progress[0]}/{n.progress[1]}
                          </span>
                        </div>
                      ) : (
                        "-"
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <Link
                        href={`/novels/${n.id}`}
                        className="text-sm text-primary hover:underline"
                      >
                        查看
                      </Link>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function StatCard({
  title,
  value,
  desc,
}: {
  title: string;
  value: number;
  desc: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription>{title}</CardDescription>
        <CardTitle className="text-3xl">{value}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-xs text-muted-foreground">{desc}</p>
      </CardContent>
    </Card>
  );
}

function StatusBadge({ status }: { status: Job["status"] }) {
  const variant =
    status === "running"
      ? "default"
      : status === "succeeded"
        ? "default"
        : status === "failed"
          ? "destructive"
          : "secondary";
  return (
    <Badge variant={variant}>{STATUS_LABELS[status] || status}</Badge>
  );
}
