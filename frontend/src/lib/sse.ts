// SSE hooks：封装 fetch + ReadableStream 消费后端流式端点
// 三类流：token 生成、job 进度、agent 活动
//
// P0 修复：用 fetch + ReadableStream 替代 EventSource，
// 在 header 中传 X-API-Key（而非 URL query param 明文传递），
// 避免 API Key 暴露于浏览器历史、服务器日志、Referer header。

"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { Job, WorkLogEntry } from "./types";

const API_BASE = "/api";

function getApiKey(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("story_studio_api_key") || null;
}

function authHeaders(): Record<string, string> {
  const k = getApiKey();
  return k ? { "X-API-Key": k } : {};
}

// ── 通用 SSE 解析器：从 fetch Response 的 ReadableStream 中解析 SSE 事件 ──

interface SSEEvent {
  event: string;
  data: string;
}

async function* parseSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<SSEEvent> {
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      if (signal?.aborted) break;
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // SSE 事件以双换行分隔
      const events = buffer.split("\n\n");
      buffer = events.pop() || "";

      for (const rawEvent of events) {
        const lines = rawEvent.split("\n");
        let event = "message";
        let data = "";

        for (const line of lines) {
          if (line.startsWith("event:")) {
            event = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            data += (data ? "\n" : "") + line.slice(5).trim();
          }
        }

        if (event || data) {
          yield { event, data };
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

// ── useChapterStream: token 流式生成 ────────────────────────

export function useChapterStream(jobId: string | null, chapter: number | null) {
  const [tokens, setTokens] = useState<string>("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  // RAF 节流：避免逐 token 触发 re-render（P1 修复：长章节海量 re-render）
  const bufferRef = useRef<string>("");
  const rafRef = useRef<number | null>(null);

  const flushBuffer = useCallback(() => {
    rafRef.current = null;
    if (bufferRef.current) {
      setTokens((prev) => prev + bufferRef.current);
      bufferRef.current = "";
    }
  }, []);

  const start = useCallback(() => {
    if (!jobId || chapter === null) return;
    setTokens("");
    setError(null);
    setStreaming(true);
    bufferRef.current = "";

    const controller = new AbortController();
    abortRef.current = controller;

    (async () => {
      try {
        const resp = await fetch(
          `${API_BASE}/novels/${jobId}/stream/${chapter}`,
          {
            headers: { ...authHeaders(), Accept: "text/event-stream" },
            signal: controller.signal,
          },
        );

        if (!resp.ok) {
          const detail = await resp.json().catch(() => ({ detail: resp.statusText }));
          setError(detail.detail || `HTTP ${resp.status}`);
          setStreaming(false);
          return;
        }

        if (!resp.body) {
          setError("无响应体");
          setStreaming(false);
          return;
        }

        const reader = resp.body.getReader();

        for await (const evt of parseSSEStream(reader, controller.signal)) {
          if (evt.event === "start") {
            setStreaming(true);
          } else if (evt.event === "token") {
            bufferRef.current += evt.data;
            if (rafRef.current === null) {
              rafRef.current = requestAnimationFrame(flushBuffer);
            }
          } else if (evt.event === "done") {
            flushBuffer();
            setStreaming(false);
            break;
          } else if (evt.event === "error") {
            setError(evt.data || "流式生成错误");
            setStreaming(false);
            break;
          }
        }
      } catch (e) {
        if (e instanceof Error && e.name === "AbortError") {
          // 用户主动停止，非错误
        } else {
          setError(e instanceof Error ? e.message : "连接错误");
        }
        setStreaming(false);
      } finally {
        if (rafRef.current !== null) {
          cancelAnimationFrame(rafRef.current);
          flushBuffer();
        }
      }
    })();
  }, [jobId, chapter, flushBuffer]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setStreaming(false);
  }, []);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
      }
    };
  }, []);

  return { tokens, streaming, error, start, stop };
}

// ── useJobEvents: job 进度 SSE ────────────────────────

export function useJobEvents(jobId: string | null) {
  const [job, setJob] = useState<Job | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!jobId) return;

    const controller = new AbortController();
    abortRef.current = controller;

    (async () => {
      try {
        const resp = await fetch(
          `${API_BASE}/novels/${jobId}/events`,
          {
            headers: { ...authHeaders(), Accept: "text/event-stream" },
            signal: controller.signal,
          },
        );

        if (!resp.ok || !resp.body) return;

        const reader = resp.body.getReader();

        for await (const evt of parseSSEStream(reader, controller.signal)) {
          if (evt.event === "progress") {
            try {
              setJob(JSON.parse(evt.data));
            } catch {
              // 忽略 JSON 解析错误
            }
          }
        }
      } catch {
        // 连接断开时静默（fetch 版无自动重连，调用方可重新触发）
      }
    })();

    return () => controller.abort();
  }, [jobId]);

  return job;
}

// ── useAgentEvents: 智能体活动日志流 ────────────────────────

export function useAgentEvents(jobId: string | null) {
  const [entries, setEntries] = useState<WorkLogEntry[]>([]);
  const [done, setDone] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!jobId) return;

    // 重置状态（在异步操作前调用以避免 effect 内同步 setState 警告）
    const controller = new AbortController();
    abortRef.current = controller;

    // 用微任务延迟 setState，避免 effect 体内同步调用
    Promise.resolve().then(() => {
      if (!controller.signal.aborted) {
        setEntries([]);
        setDone(false);
      }
    });

    (async () => {
      try {
        const resp = await fetch(
          `${API_BASE}/novels/${jobId}/agents/events`,
          {
            headers: { ...authHeaders(), Accept: "text/event-stream" },
            signal: controller.signal,
          },
        );

        if (!resp.ok || !resp.body) return;

        const reader = resp.body.getReader();

        for await (const evt of parseSSEStream(reader, controller.signal)) {
          if (evt.event === "agent") {
            try {
              const entry = JSON.parse(evt.data);
              setEntries((prev) => [...prev, entry]);
            } catch {
              // 忽略 JSON 解析错误
            }
          } else if (evt.event === "done") {
            setDone(true);
            break;
          }
        }
      } catch {
        // 静默
      }
    })();

    return () => controller.abort();
  }, [jobId]);

  return { entries, done };
}
