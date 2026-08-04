"use client";

import { useState } from "react";
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
import { setApiKey, checkHealth } from "@/lib/api-client";

export default function SettingsPage() {
  const [key, setKey] = useState("");
  const [saved, setSaved] = useState(false);
  const [healthStatus, setHealthStatus] = useState<string | null>(null);

  function handleSave() {
    setApiKey(key);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  async function handleTest() {
    setHealthStatus("检测中...");
    const ok = await checkHealth();
    setHealthStatus(ok ? "后端在线 ✅" : "后端离线 ❌");
  }

  return (
    <div className="flex-1 space-y-6 p-6 max-w-2xl">
      <h1 className="text-2xl font-bold">设置</h1>

      <Card>
        <CardHeader>
          <CardTitle>API 密钥</CardTitle>
          <CardDescription>
            若后端配置了 api_key 鉴权，在此填入 X-API-Key。留空表示无鉴权。
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="apikey">API Key</Label>
            <Input
              id="apikey"
              type="password"
              placeholder="（无鉴权时留空）"
              value={key}
              onChange={(e) => setKey(e.target.value)}
            />
          </div>
          <div className="flex gap-2">
            <Button onClick={handleSave}>保存</Button>
            {saved && <span className="text-sm text-green-600 self-center">已保存</span>}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>后端连接</CardTitle>
          <CardDescription>
            检测 FastAPI 后端是否在线（默认 http://localhost:8000）
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button onClick={handleTest} variant="outline">检测连接</Button>
          {healthStatus && (
            <span className="ml-3 text-sm">{healthStatus}</span>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>关于</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground space-y-1">
          <p>Story Studio - 多 Agent 协作 AI 小说创作平台</p>
          <p>14 智能体 · 去AI化引擎 · 联网搜索 · 自动修订质量门</p>
          <p>后端：FastAPI + SSE · 前端：Next.js + shadcn/ui</p>
        </CardContent>
      </Card>
    </div>
  );
}
