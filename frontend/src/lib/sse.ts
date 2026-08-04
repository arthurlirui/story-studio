// SSE hooks：封装 EventSource 消费后端流式端点
// 三类流：token 生成、job 进度、agent 活动

"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { Job, WorkLogEntry } from "./types";

const API_BASE = "/api";

function getApiKey(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("story_studio_api_key") || null;
}

// ── SSE 不支持自定义 header（EventSource 限制），通过 query param 传 key ──
function keyParam(): string {
  const k = getApiKey();
  return k ? `?api_key=${encodeURIComponent(k)}` : "";
}

// ── useChapterStream: token 流式生成 ────────────────────────

export function useChapterStream(jobId: string | null, chapter: number | null) {
  const [tokens, setTokens] = useState<string>("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sourceRef = useRef<EventSource | null>(null);

  const start = useCallback(() => {
    if (!jobId || chapter === null) return;
    setTokens("");
    setError(null);
    setStreaming(true);

    const url = `${API_BASE}/novels/${jobId}/stream/${chapter}${keyParam()}`;
    const es = new EventSource(url);
    sourceRef.current = es;

    es.addEventListener("start", () => setStreaming(true));
    es.addEventListener("token", (e) => {
      setTokens((prev) => prev + e.data);
    });
    es.addEventListener("done", () => {
      setStreaming(false);
      es.close();
    });
    es.addEventListener("error", (e) => {
      // EventSource error 事件无 data，需检查 readyState
      if (es.readyState === EventSource.CLOSED) {
        setStreaming(false);
      } else {
        setError("流式连接错误");
      }
    });
  }, [jobId, chapter]);

  const stop = useCallback(() => {
    sourceRef.current?.close();
    setStreaming(false);
  }, []);

  useEffect(() => {
    return () => sourceRef.current?.close();
  }, []);

  return { tokens, streaming, error, start, stop };
}

// ── useJobEvents: job 进度轮询式 SSE ────────────────────────

export function useJobEvents(jobId: string | null) {
  const [job, setJob] = useState<Job | null>(null);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!jobId) return;
    const url = `${API_BASE}/novels/${jobId}/events${keyParam()}`;
    const es = new EventSource(url);
    sourceRef.current = es;

    es.addEventListener("progress", (e) => {
      try {
        setJob(JSON.parse(e.data));
      } catch {}
    });
    es.addEventListener("error", () => {
      // 连接断开时 EventSource 会自动重连
    });

    return () => es.close();
  }, [jobId]);

  return job;
}

// ── useAgentEvents: 智能体活动日志流 ────────────────────────

export function useAgentEvents(jobId: string | null) {
  const [entries, setEntries] = useState<WorkLogEntry[]>([]);
  const [done, setDone] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!jobId) return;
    setEntries([]);
    setDone(false);
    const url = `${API_BASE}/novels/${jobId}/agents/events${keyParam()}`;
    const es = new EventSource(url);
    sourceRef.current = es;

    es.addEventListener("agent", (e) => {
      try {
        const entry = JSON.parse(e.data);
        setEntries((prev) => [...prev, entry]);
      } catch {}
    });
    es.addEventListener("done", () => {
      setDone(true);
      es.close();
    });

    return () => es.close();
  }, [jobId]);

  return { entries, done };
}
