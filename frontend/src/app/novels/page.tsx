"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { listNovels } from "@/lib/api-client";
import { STATUS_LABELS, PHASE_LABELS, type Job } from "@/lib/types";

export default function NovelsPage() {
  const [novels, setNovels] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const resp = await listNovels();
        setNovels(resp.novels);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return (
    <div className="flex-1 space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">小说项目</h1>
        <Button asChild>
          <Link href="/novels/new">创建新小说</Link>
        </Button>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">加载中...</p>
      ) : novels.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <p className="text-muted-foreground mb-4">还没有小说项目</p>
            <Button asChild>
              <Link href="/novels/new">创建第一部小说</Link>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {novels.map((n) => (
            <Link key={n.id} href={`/novels/${n.id}`}>
              <Card className="hover:border-primary transition-colors cursor-pointer">
                <CardHeader>
                  <CardTitle className="text-lg">
                    {n.project_name || "(未命名)"}
                  </CardTitle>
                  <p className="text-xs text-muted-foreground">
                    {STATUS_LABELS[n.status]} · {PHASE_LABELS[n.phase] || n.phase}
                  </p>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground line-clamp-2">
                    {n.brief}
                  </p>
                  {n.progress[1] > 0 && (
                    <p className="text-xs text-muted-foreground mt-2">
                      进度: {n.progress[0]}/{n.progress[1]}
                    </p>
                  )}
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
