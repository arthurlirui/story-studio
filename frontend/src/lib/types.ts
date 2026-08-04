// 与后端 API 对齐的 TypeScript 类型定义

export type JobStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "recoverable";

export type Phase =
  | "idle"
  | "research"
  | "innovate"
  | "planning"
  | "building"
  | "outlining"
  | "writing"
  | "complete";

export type Verdict = "PASS" | "REVISE" | "REJECT" | null;

export interface Job {
  id: string;
  brief: string;
  status: JobStatus;
  phase: Phase;
  progress: [number, number];
  task_progress: [number, number] | null;
  created_at: number;
  updated_at: number;
  knowledge_dir: string;
  output_dir: string;
  project_name: string;
  write_mode: "sequential" | "batch";
  result: Record<string, unknown> | null;
  error: string | null;
}

export interface NovelCreate {
  brief: string;
  project_name?: string;
  total_chapters?: number;
  write_mode?: "sequential" | "batch";
}

export interface Chapter {
  chapter: number;
  title: string;
  words: number;
  verdict: Verdict;
  deai_score: number | null;
}

export interface ChapterContent {
  chapter: number;
  content: string;
}

export interface TaskItem {
  id: number;
  name: string;
  phase: Phase;
  status: string;
  result_excerpt?: string;
  error?: string;
}

export interface TaskPlan {
  job_id: string;
  brief: string;
  total_chapters: number;
  write_mode: string;
  tasks: TaskItem[];
}

export interface CostSummary {
  by_model: Record<string, { prompt: number; completion: number; total: number; calls: number }>;
  total_calls: number;
  total_tokens: number;
}

export interface QualityData {
  job_id: string;
  chapters: { chapter: number; verdict: Verdict; deai_score: number | null }[];
  verdict_summary: { PASS: number; REVISE: number; REJECT: number };
  total_chapters: number;
}

export interface Series {
  name: string;
  variants: { name: string; has_outline: boolean }[];
  has_bible: boolean;
}

export interface Genre {
  slug: string;
  genre: string;
  genre_name_zh: string;
  category: string;
  default_pov: string;
  word_range: number[];
}

export interface AgentInfo {
  name: string;
  role: string;
  description: string;
  model: string;
}

export interface WorkLogEntry {
  ts?: string;
  agent?: string;
  action?: string;
  chapter?: number | null;
  verdict?: string;
  excerpt?: string;
}

export const PHASE_LABELS: Record<Phase, string> = {
  idle: "待启动",
  research: "调研",
  innovate: "创新亮点",
  planning: "策划",
  building: "设定",
  outlining: "大纲",
  writing: "写作",
  complete: "完稿",
};

export const PHASE_ORDER: Phase[] = [
  "research",
  "innovate",
  "planning",
  "building",
  "outlining",
  "writing",
  "complete",
];

export const STATUS_LABELS: Record<JobStatus, string> = {
  queued: "排队中",
  running: "运行中",
  succeeded: "成功",
  failed: "失败",
  cancelled: "已取消",
  recoverable: "可恢复",
};
