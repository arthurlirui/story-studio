"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { createNovel } from "@/lib/api-client";

export default function NewNovelPage() {
  const router = useRouter();
  const [brief, setBrief] = useState("");
  const [name, setName] = useState("");
  const [chapters, setChapters] = useState("");
  const [mode, setMode] = useState<"sequential" | "batch">("sequential");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit() {
    if (!brief.trim()) {
      setError("请输入创作需求");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const resp = await createNovel({
        brief,
        project_name: name,
        total_chapters: chapters ? parseInt(chapters) : undefined,
        write_mode: mode,
      });
      router.push(`/novels/${resp.job_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "提交失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex-1 space-y-6 p-6 max-w-2xl">
      <h1 className="text-2xl font-bold">创建新小说</h1>

      <Card>
        <CardHeader>
          <CardTitle>创作需求</CardTitle>
          <CardDescription>
            描述你想创作的小说--题材、风格、核心冲突、目标读者
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="brief">创作需求</Label>
            <textarea
              id="brief"
              className="flex min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              placeholder="例：一个关于急诊室医生的故事，探讨生死抉择与人性，都市现实主义风格，目标番茄小说平台..."
              value={brief}
              onChange={(e) => setBrief(e.target.value)}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="name">项目名（书名）</Label>
              <Input
                id="name"
                placeholder="可选"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="chapters">目标章节数</Label>
              <Input
                id="chapters"
                type="number"
                min={1}
                max={200}
                placeholder="默认 10"
                value={chapters}
                onChange={(e) => setChapters(e.target.value)}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label>写作模式</Label>
            <Tabs value={mode} onValueChange={(v) => setMode(v as "sequential" | "batch")}>
              <TabsList>
                <TabsTrigger value="sequential">逐章串行</TabsTrigger>
                <TabsTrigger value="batch">批次并行</TabsTrigger>
              </TabsList>
              <TabsContent value="sequential" className="text-xs text-muted-foreground mt-1">
                一章一章写，连续性最佳，速度较慢
              </TabsContent>
              <TabsContent value="batch" className="text-xs text-muted-foreground mt-1">
                每批 batch_size 章并行写，速度快，需融合门检查
              </TabsContent>
            </Tabs>
          </div>

          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}

          <div className="flex gap-2">
            <Button onClick={handleSubmit} disabled={submitting}>
              {submitting ? "提交中..." : "提交生成任务"}
            </Button>
            <Button variant="outline" onClick={() => router.back()}>
              取消
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <p className="text-xs text-muted-foreground">
            提交后，14 个 AI 智能体将协作完成：调研 {">"} 创新亮点 {">"} 策划{" "}
            {">"} 世界观/角色设定 {">"} 大纲 {">"} 章节写作（自动修订质量门）{">"}{" "}
            终审去AI化 {">"} 交付。
            全程可恢复，崩溃后可断点续跑。
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
