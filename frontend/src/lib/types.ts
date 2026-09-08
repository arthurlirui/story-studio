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
  | "trending"
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
  by_model: Record<string, { prompt_tokens: number; completion_tokens: number; total_tokens: number; calls: number }>;
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

// ── 大纲结构化模型（与后端 outline_format.py 对齐） ──────────

/** 单章大纲五要素 */
export interface ChapterOutline {
  num: number;
  title: string;
  events: string[];
  characters: string[];
  hook: string;
  word_estimate: number;
}

/** 整份大纲：书名 + 设计说明 + 章节列表 */
export interface OutlineDoc {
  book_title: string;
  preamble: string;
  chapters: ChapterOutline[];
}

export interface OutlineSaveResult {
  job_id: string;
  saved: boolean;
  total_chapters: number | null;
  parsed_chapters: number;
  outline_chars: number;
}

export const PHASE_LABELS: Record<Phase, string> = {
  idle: "待启动",
  research: "调研",
  innovate: "创新亮点",
  planning: "策划",
  building: "设定",
  trending: "热词",
  outlining: "大纲",
  writing: "写作",
  complete: "完稿",
};

export const PHASE_ORDER: Phase[] = [
  "research",
  "innovate",
  "planning",
  "building",
  "trending",
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

// ── 全局配置（与后端 config/settings.yaml + GET/PUT /config 对齐） ──

/** 多模型润色中的单个模型配置 */
export interface MultiPolishModel {
  name: string;
  temperature: number;
  max_tokens: number;
  prompt_version: string;
}

/** 去AI化引擎配置（与后端 config.DeaiConfig 对齐） */
export interface DeaiSettings {
  enabled: boolean;
  aggressiveness: number;       // 0.0-1.0 规则重写激进程度
  length_min_ratio: number;     // 润色后/原文字数下限
  length_max_ratio: number;     // 润色后/原文字数上限
  polish_max_attempts: number;  // 字数不合规时重试上限
  prompt_version: string;       // LLM 重写提示词版本（对应 deai/prompts/rewrite_{version}.txt）
  audit_threshold: number;      // 终审 audit 评分低于此值触发重写（0-50）
}

/** 全局配置（GET /config 返回，敏感字段已脱敏） */
export interface StudioSettings {
  // 连接与模型
  backend: "llm" | "ollama";
  llm_base_url: string;
  llm_api_key: string; // 脱敏，只读
  main_model: string;
  light_model: string;
  ollama_host: string;
  // 生成流水线
  max_rounds: number;
  scene_writers: number;
  batch_size: number;
  max_context_chars: number;
  merge_gate_rounds: number;
  rate_limit_delay: number;
  // 调研与润色
  web_search_provider: "doubao" | "bocha" | "mock";
  web_search_api_key: string; // 脱敏，只读
  web_search_endpoint: string;
  research_enabled: boolean;
  research_max_topics: number;
  trending_enabled: boolean;
  multi_polish: {
    enabled: boolean;
    max_concurrent: number;
    models: MultiPolishModel[];
  };
  // 去AI化引擎
  deai: DeaiSettings;
  // 智能体模型路由：role -> model_name
  agent_models: Record<string, string>;
  // 只读展示
  api_key: string; // 脱敏，只读
  knowledge_dir: string; // 只读
  output_dir: string; // 只读
}

/** GET /config/paths 返回 */
export interface ConfigPaths {
  config_file: string;
  jobs_dir: string;
}

/** PUT /config 返回 */
export interface ConfigUpdateResult {
  updated: string[];
  rejected: Record<string, string>;
}
