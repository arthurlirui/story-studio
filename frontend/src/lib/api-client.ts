// API 客户端：封装 fetch + X-API-Key + 错误处理
// 所有请求经 Next.js rewrites 代理到 FastAPI 后端（/api/* -> :8000/*）

const API_BASE = "/api";

function getApiKey(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("story_studio_api_key") || null;
}

export function setApiKey(key: string): void {
  if (typeof window !== "undefined") {
    localStorage.setItem("story_studio_api_key", key);
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options.headers as Record<string, string>) || {}),
  };
  const apiKey = getApiKey();
  if (apiKey) {
    headers["X-API-Key"] = apiKey;
  }

  const resp = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(detail.detail || `HTTP ${resp.status}`);
  }
  return resp.json() as Promise<T>;
}

// ── Novels / Jobs ──────────────────────────────────────────

import type { Job, NovelCreate, ChapterContent, TaskPlan, CostSummary, QualityData, Chapter } from "./types";

export async function listNovels(): Promise<{ novels: Job[] }> {
  return request("/novels");
}

export async function getNovel(jobId: string): Promise<Job> {
  return request(`/novels/${jobId}`);
}

export async function createNovel(data: NovelCreate): Promise<{ job_id: string; status: string }> {
  return request("/novels", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function cancelNovel(jobId: string): Promise<{ job_id: string; status: string }> {
  return request(`/novels/${jobId}`, { method: "DELETE" });
}

export async function runAllTasks(jobId: string): Promise<unknown> {
  return request(`/novels/${jobId}/run-all`, { method: "POST" });
}

export async function resumeNovel(jobId: string): Promise<unknown> {
  return request(`/novels/${jobId}/resume`, { method: "POST" });
}

// ── Chapters ───────────────────────────────────────────────

export async function listChapters(jobId: string): Promise<{ job_id: string; chapters: Chapter[] }> {
  return request(`/novels/${jobId}/chapters`);
}

export async function getChapter(jobId: string, chapterNum: number): Promise<ChapterContent> {
  return request(`/novels/${jobId}/chapters/${chapterNum}`);
}

// ── Tasks ──────────────────────────────────────────────────

export async function getTasks(jobId: string): Promise<{ job_id: string; plan: TaskPlan | null; summary?: unknown }> {
  return request(`/novels/${jobId}/tasks`);
}

// ── Knowledge ──────────────────────────────────────────────

export async function getOutline(jobId: string): Promise<{ job_id: string; outline: string }> {
  return request(`/novels/${jobId}/outline`);
}

export async function getWorld(jobId: string): Promise<{ job_id: string; docs: string[]; summary: string }> {
  return request(`/novels/${jobId}/world`);
}

export async function getCharacters(jobId: string): Promise<{
  job_id: string;
  characters: { name: string; preview: string; words: number }[];
}> {
  return request(`/novels/${jobId}/characters`);
}

export async function getCost(jobId: string): Promise<{ job_id: string; cost: CostSummary | null }> {
  return request(`/novels/${jobId}/cost`);
}

export async function getQuality(jobId: string): Promise<QualityData> {
  return request(`/novels/${jobId}/quality`);
}

export async function getKnowledgeTree(
  jobId: string,
  tree: "world" | "characters" | "story" | "research",
): Promise<{ job_id: string; tree: string; files: { name: string; words: number; modified: number }[] }> {
  return request(`/novels/${jobId}/knowledge/${tree}`);
}

// ── Series & Genres ────────────────────────────────────────

import type { Series, Genre } from "./types";

export async function listSeries(): Promise<{ series: Series[] }> {
  return request("/series");
}

export async function listGenres(): Promise<{ genres: Genre[] }> {
  return request("/genres");
}

// ── Health ─────────────────────────────────────────────────

export async function checkHealth(): Promise<boolean> {
  try {
    await request<{ status: string }>("/health");
    return true;
  } catch {
    return false;
  }
}
