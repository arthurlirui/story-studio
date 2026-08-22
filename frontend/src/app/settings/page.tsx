"use client";

import { useEffect, useState } from "react";
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
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Loader2, Save, Check, ServerCog, Sliders, Search, Users } from "lucide-react";
import {
  getConfig,
  setConfig,
  setApiKey,
  getStoredApiKey,
  checkHealth,
} from "@/lib/api-client";
import type { StudioSettings, ConfigUpdateResult } from "@/lib/types";

/** 智能体角色清单（与 orchestrator.py 实例化的 role 一致） */
const AGENT_ROLES: { role: string; label: string; tier: "main" | "light" }[] = [
  { role: "showrunner", label: "Showrunner（总编）", tier: "main" },
  { role: "world_architect", label: "World Architect（世界观架构）", tier: "main" },
  { role: "character_designer", label: "Character Designer（角色设计）", tier: "main" },
  { role: "character_psychologist", label: "Character Psychologist（角色心理）", tier: "main" },
  { role: "scene_writer", label: "Scene Writer（场景编剧）", tier: "main" },
  { role: "innovator", label: "Innovator（创新亮点）", tier: "main" },
  { role: "editor", label: "Editor（编辑）", tier: "light" },
  { role: "literary_advisor", label: "Literary Advisor（文学顾问）", tier: "light" },
  { role: "continuity_keeper", label: "Continuity Keeper（连贯性守护）", tier: "light" },
  { role: "title_designer", label: "Title Designer（标题设计）", tier: "light" },
  { role: "hooker", label: "Hooker（悬念钩子）", tier: "light" },
  { role: "climax_designer", label: "Climax Designer（高潮设计）", tier: "light" },
  { role: "topic_researcher", label: "Topic Researcher（主题调研）", tier: "light" },
];

/** 默认配置（加载失败或首次进入时用） */
const DEFAULT_SETTINGS: StudioSettings = {
  backend: "llm",
  llm_base_url: "",
  llm_api_key: "",
  main_model: "",
  light_model: "",
  ollama_host: "http://localhost:11434",
  max_rounds: 3,
  scene_writers: 3,
  batch_size: 3,
  max_context_chars: 60000,
  merge_gate_rounds: 1,
  rate_limit_delay: 0,
  web_search_provider: "doubao",
  web_search_api_key: "",
  web_search_endpoint: "",
  research_enabled: true,
  research_max_topics: 4,
  multi_polish: { enabled: true, max_concurrent: 3, models: [] },
  agent_models: {},
  api_key: "",
  knowledge_dir: "",
  output_dir: "",
};

export default function SettingsPage() {
  // 后端配置
  const [settings, setSettings] = useState<StudioSettings>(DEFAULT_SETTINGS);
  const [savedSettings, setSavedSettings] = useState<StudioSettings>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveResult, setSaveResult] = useState<ConfigUpdateResult | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  // 本地 API 密钥（惰性初始化：client 首渲染从 localStorage 读取）
  const [localKey, setLocalKey] = useState(() => getStoredApiKey() || "");
  const [keySaved, setKeySaved] = useState(false);

  // 后端连接检测
  const [healthStatus, setHealthStatus] = useState<string | null>(null);

  useEffect(() => {
    void loadSettings();
  }, []);

  async function loadSettings() {
    setLoading(true);
    setLoadError(null);
    try {
      const cfg = await getConfig();
      // 防御：后端 settings.yaml 可能没有 multi_polish 字段
      if (!cfg.multi_polish) {
        cfg.multi_polish = { enabled: true, max_concurrent: 3, models: [] };
      }
      if (!cfg.agent_models) {
        cfg.agent_models = {};
      }
      setSettings(cfg);
      setSavedSettings(cfg);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "加载配置失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleHealthCheck() {
    setHealthStatus("检测中...");
    const ok = await checkHealth();
    setHealthStatus(ok ? "后端在线" : "后端离线");
  }

  function handleSaveLocalKey() {
    setApiKey(localKey);
    setKeySaved(true);
    setTimeout(() => setKeySaved(false), 2000);
  }

  /** 收集与 savedSettings 不同的可写字段，组装 patch */
  function buildPatch(): Partial<StudioSettings> {
    const patch: Partial<StudioSettings> = {};
    const keys: (keyof StudioSettings)[] = [
      "backend", "llm_base_url", "main_model", "light_model", "ollama_host",
      "max_rounds", "scene_writers", "batch_size", "max_context_chars",
      "merge_gate_rounds", "rate_limit_delay",
      "web_search_provider", "web_search_endpoint",
      "research_enabled", "research_max_topics",
    ];
    for (const k of keys) {
      if (settings[k] !== savedSettings[k]) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (patch as any)[k] = settings[k];
      }
    }
    // multi_polish：比较 enabled 与 max_concurrent
    if (
      settings.multi_polish.enabled !== savedSettings.multi_polish.enabled ||
      settings.multi_polish.max_concurrent !== savedSettings.multi_polish.max_concurrent
    ) {
      patch.multi_polish = {
        enabled: settings.multi_polish.enabled,
        max_concurrent: settings.multi_polish.max_concurrent,
        models: settings.multi_polish.models,
      };
    }
    // agent_models：全量提交
    if (JSON.stringify(settings.agent_models) !== JSON.stringify(savedSettings.agent_models)) {
      patch.agent_models = settings.agent_models;
    }
    return patch;
  }

  function isDirty(): boolean {
    return Object.keys(buildPatch()).length > 0;
  }

  async function handleSave() {
    const patch = buildPatch();
    if (Object.keys(patch).length === 0) return;
    setSaving(true);
    setSaveError(null);
    setSaveResult(null);
    try {
      const result = await setConfig(patch);
      setSaveResult(result);
      await loadSettings();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  /** 通用字段更新 helper */
  function updateField<K extends keyof StudioSettings>(key: K, value: StudioSettings[K]) {
    setSettings((s) => ({ ...s, [key]: value }));
  }

  if (loading) {
    return <div className="text-muted-foreground flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" /> 加载配置中...</div>;
  }

  if (loadError) {
    return (
      <div className="space-y-4">
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          ⚠️ {loadError}
        </div>
        <Button variant="outline" onClick={() => void loadSettings()}>重试</Button>
      </div>
    );
  }

  const dirty = isDirty();

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">设置</h1>
        {dirty && <span className="text-primary text-sm">● 有未保存更改</span>}
      </div>

      {saveError && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          ⚠️ {saveError}
        </div>
      )}
      {saveResult && (
        <div className="rounded-md border border-emerald-500/50 bg-emerald-500/10 p-3 text-sm text-emerald-700 dark:text-emerald-400 space-y-1">
          <div>✓ 已更新 {saveResult.updated.length} 项：{saveResult.updated.join(", ") || "（无）"}</div>
          {Object.keys(saveResult.rejected).length > 0 && (
            <div className="text-amber-600 dark:text-amber-400">
              被拒字段：{Object.entries(saveResult.rejected).map(([k, v]) => `${k}（${v}）`).join("；")}
            </div>
          )}
        </div>
      )}

      <Tabs defaultValue="connection">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="connection"><ServerCog className="h-4 w-4 mr-1" />连接与模型</TabsTrigger>
          <TabsTrigger value="pipeline"><Sliders className="h-4 w-4 mr-1" />生成流水线</TabsTrigger>
          <TabsTrigger value="research"><Search className="h-4 w-4 mr-1" />调研与润色</TabsTrigger>
          <TabsTrigger value="agents"><Users className="h-4 w-4 mr-1" />智能体路由</TabsTrigger>
        </TabsList>

        {/* ── Tab 1: 连接与模型 ── */}
        <TabsContent value="connection" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">API 密钥（本地）</CardTitle>
              <CardDescription>前端访问后端时携带的 X-API-Key，仅保存在浏览器本地</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex gap-2">
                <Input
                  type="password"
                  placeholder="输入后端 API 密钥"
                  value={localKey}
                  onChange={(e) => setLocalKey(e.target.value)}
                />
                <Button onClick={handleSaveLocalKey} disabled={!localKey}>
                  {keySaved ? <Check className="h-4 w-4" /> : null}
                  {keySaved ? "已保存" : "保存"}
                </Button>
              </div>
              <Button variant="outline" size="sm" onClick={() => void handleHealthCheck()}>
                {healthStatus === "检测中..." ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
                检测后端连接
              </Button>
              {healthStatus && (
                <Badge variant={healthStatus === "后端在线" ? "default" : "destructive"}>
                  {healthStatus}
                </Badge>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">LLM 后端</CardTitle>
              <CardDescription>选择模型后端类型与端点</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label>后端类型</Label>
                <Select
                  value={settings.backend}
                  onValueChange={(v) => updateField("backend", v as "llm" | "ollama")}
                >
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="llm">LLM（OpenAI 兼容）</SelectItem>
                    <SelectItem value="ollama">Ollama（本地）</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="llm_base_url">LLM Base URL</Label>
                <Input
                  id="llm_base_url"
                  value={settings.llm_base_url}
                  onChange={(e) => updateField("llm_base_url", e.target.value)}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="main_model">主模型</Label>
                  <Input
                    id="main_model"
                    value={settings.main_model}
                    onChange={(e) => updateField("main_model", e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="light_model">轻量模型</Label>
                  <Input
                    id="light_model"
                    value={settings.light_model}
                    onChange={(e) => updateField("light_model", e.target.value)}
                  />
                </div>
              </div>
              {settings.backend === "ollama" && (
                <div className="space-y-2">
                  <Label htmlFor="ollama_host">Ollama Host</Label>
                  <Input
                    id="ollama_host"
                    value={settings.ollama_host}
                    onChange={(e) => updateField("ollama_host", e.target.value)}
                  />
                </div>
              )}
              <Separator />
              <div className="space-y-2">
                <Label>LLM API Key</Label>
                <Input value={settings.llm_api_key} disabled />
                <p className="text-xs text-muted-foreground">敏感字段，请在 settings.yaml 中手动修改</p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Tab 2: 生成流水线 ── */}
        <TabsContent value="pipeline" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">生成参数</CardTitle>
              <CardDescription>控制章节写作与修订行为，对新任务生效</CardDescription>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="max_rounds">每章自动修订上限</Label>
                <Input
                  id="max_rounds" type="number" min={1} max={10}
                  value={settings.max_rounds}
                  onChange={(e) => updateField("max_rounds", parseInt(e.target.value) || 0)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="scene_writers">并行编剧数</Label>
                <Input
                  id="scene_writers" type="number" min={1} max={8}
                  value={settings.scene_writers}
                  onChange={(e) => updateField("scene_writers", parseInt(e.target.value) || 0)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="batch_size">批次章节数</Label>
                <Input
                  id="batch_size" type="number" min={1} max={10}
                  value={settings.batch_size}
                  onChange={(e) => updateField("batch_size", parseInt(e.target.value) || 0)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="max_context_chars">上下文字符预算</Label>
                <Input
                  id="max_context_chars" type="number" min={10000} max={200000} step={1000}
                  value={settings.max_context_chars}
                  onChange={(e) => updateField("max_context_chars", parseInt(e.target.value) || 0)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="merge_gate_rounds">融合门重写轮数</Label>
                <Input
                  id="merge_gate_rounds" type="number" min={0} max={5}
                  value={settings.merge_gate_rounds}
                  onChange={(e) => updateField("merge_gate_rounds", parseInt(e.target.value) || 0)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="rate_limit_delay">API 调用间隔（秒）</Label>
                <Input
                  id="rate_limit_delay" type="number" min={0} max={10} step={0.1}
                  value={settings.rate_limit_delay}
                  onChange={(e) => updateField("rate_limit_delay", parseFloat(e.target.value) || 0)}
                />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Tab 3: 调研与润色 ── */}
        <TabsContent value="research" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">调研</CardTitle>
              <CardDescription>网络搜索与主题调研设置</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <Label htmlFor="research_enabled">启用调研</Label>
                  <p className="text-xs text-muted-foreground">关闭则跳过 research/innovate 任务</p>
                </div>
                <Switch
                  id="research_enabled"
                  checked={settings.research_enabled}
                  onCheckedChange={(v) => updateField("research_enabled", v)}
                />
              </div>
              <div className="space-y-2">
                <Label>搜索引擎</Label>
                <Select
                  value={settings.web_search_provider}
                  onValueChange={(v) => updateField("web_search_provider", v as "doubao" | "bocha" | "mock")}
                >
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="doubao">豆包</SelectItem>
                    <SelectItem value="bocha">博查</SelectItem>
                    <SelectItem value="mock">Mock（测试）</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="research_max_topics">调研主题数</Label>
                  <Input
                    id="research_max_topics" type="number" min={1} max={10}
                    value={settings.research_max_topics}
                    onChange={(e) => updateField("research_max_topics", parseInt(e.target.value) || 0)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="web_search_endpoint">搜索 Endpoint（可选）</Label>
                  <Input
                    id="web_search_endpoint"
                    placeholder="留空用默认"
                    value={settings.web_search_endpoint}
                    onChange={(e) => updateField("web_search_endpoint", e.target.value)}
                  />
                </div>
              </div>
              <Separator />
              <div className="space-y-2">
                <Label>搜索 API Key</Label>
                <Input value={settings.web_search_api_key} disabled />
                <p className="text-xs text-muted-foreground">敏感字段，请在 settings.yaml 中手动修改</p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">多模型润色</CardTitle>
              <CardDescription>启用多模型交叉润色以提升文本质量</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <Label htmlFor="mp_enabled">启用多模型润色</Label>
                </div>
                <Switch
                  id="mp_enabled"
                  checked={settings.multi_polish.enabled}
                  onCheckedChange={(v) =>
                    setSettings((s) => ({ ...s, multi_polish: { ...s.multi_polish, enabled: v } }))
                  }
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="mp_concurrent">润色并发数</Label>
                <Input
                  id="mp_concurrent" type="number" min={1} max={8}
                  value={settings.multi_polish.max_concurrent}
                  onChange={(e) =>
                    setSettings((s) => ({
                      ...s,
                      multi_polish: { ...s.multi_polish, max_concurrent: parseInt(e.target.value) || 1 },
                    }))
                  }
                />
              </div>
              {settings.multi_polish.models.length > 0 && (
                <div className="space-y-2">
                  <Label>润色模型列表（只读）</Label>
                  <div className="space-y-1">
                    {settings.multi_polish.models.map((m, i) => (
                      <div key={i} className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Badge variant="secondary">{m.name || "(未命名)"}</Badge>
                        <span>temp={m.temperature}</span>
                        <span>max_tokens={m.max_tokens}</span>
                        <span>prompt={m.prompt_version}</span>
                      </div>
                    ))}
                  </div>
                  <p className="text-xs text-muted-foreground">模型列表请在 settings.yaml 中编辑</p>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Tab 4: 智能体模型路由 ── */}
        <TabsContent value="agents" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">按角色指定模型</CardTitle>
              <CardDescription>
                为各智能体角色单独指定模型，留空则使用默认路由（main tier 用主模型，light tier 用轻量模型）
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {AGENT_ROLES.map(({ role, label, tier }) => (
                <div key={role} className="grid grid-cols-[auto_1fr] items-center gap-3">
                  <div className="flex items-center gap-2 min-w-[220px]">
                    <Badge variant={tier === "main" ? "default" : "secondary"}>{tier}</Badge>
                    <Label className="text-sm">{label}</Label>
                  </div>
                  <Input
                    placeholder={tier === "main" ? settings.main_model : settings.light_model}
                    value={settings.agent_models[role] || ""}
                    onChange={(e) =>
                      setSettings((s) => ({
                        ...s,
                        agent_models: { ...s.agent_models, [role]: e.target.value },
                      }))
                    }
                  />
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* 只读信息 */}
      <Card>
        <CardContent className="pt-6 space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">配置文件路径</span>
            <code className="text-xs">{settings.knowledge_dir ? "config/settings.yaml" : "config/settings.yaml"}</code>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">知识库目录</span>
            <code className="text-xs">{settings.knowledge_dir || "（默认）"}</code>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">输出目录</span>
            <code className="text-xs">{settings.output_dir || "（默认）"}</code>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">后端鉴权 Key</span>
            <code className="text-xs">{settings.api_key ? settings.api_key : "（未设置）"}</code>
          </div>
        </CardContent>
      </Card>

      {/* 底部保存栏 */}
      <div className="flex items-center gap-2 sticky bottom-4">
        <Button onClick={() => void handleSave()} disabled={!dirty || saving}>
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          保存设置
        </Button>
        {dirty && <span className="text-sm text-muted-foreground">有未保存的更改</span>}
      </div>
    </div>
  );
}
