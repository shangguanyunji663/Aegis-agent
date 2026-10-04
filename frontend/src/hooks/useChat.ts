/* 会话 + SSE 对话流:三概念共享的唯一聊天引擎。
   流式阶段机:idle → waiting(展信/拨号中) → speaking(逐字) → done;
   token 逐字追加,done 时以后端安全复核后的终稿覆盖。 */

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { clockLine } from "../lib/labels";
import type { ChatStreamEvent, RiskLevel, SessionSummary } from "../lib/types";

export type StreamPhase = "idle" | "waiting" | "speaking";

export interface Turn {
  id: string;
  role: "user" | "assistant";
  content: string;
  risk?: RiskLevel;
  retrieved?: boolean;
  reported?: boolean;
  at?: string;
}

let seq = 0;
const nextId = () => `t${++seq}`;

function parseSseFrames(buffer: string): { events: ChatStreamEvent[]; rest: string } {
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";
  const events: ChatStreamEvent[] = [];
  for (const part of parts) {
    const dataLine = part.split("\n").find((line) => line.startsWith("data:"));
    if (!dataLine) continue;
    try {
      events.push(JSON.parse(dataLine.replace("data:", "").trim()) as ChatStreamEvent);
    } catch {
      /* 半帧或心跳,丢弃 */
    }
  }
  return { events, rest };
}

export function useChat() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [phase, setPhase] = useState<StreamPhase>("idle");
  const [error, setError] = useState<string | null>(null);
  const sendingRef = useRef(false);

  const loadSessions = useCallback(async () => {
    const data = await api.sessions();
    setSessions(data.sessions ?? []);
  }, []);

  const openSession = useCallback(async (id: string) => {
    const data = await api.session(id);
    setSessionId(data.session.id);
    setTurns(
      data.session.messages.map((m) => ({
        id: nextId(),
        role: m.role === "USER" ? "user" : "assistant",
        content: m.content,
      })),
    );
  }, []);

  const newSession = useCallback(() => {
    setSessionId(null);
    setTurns([]);
    setError(null);
    setPhase("idle");
  }, []);

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || sendingRef.current) return;
      sendingRef.current = true;
      setError(null);
      const userTurn: Turn = { id: nextId(), role: "user", content: trimmed, at: clockLine() };
      const assistantTurn: Turn = { id: nextId(), role: "assistant", content: "", at: clockLine() };
      setTurns((prev) => [...prev, userTurn, assistantTurn]);
      setPhase("waiting");

      try {
        const response = await api.chatStream({ session_id: sessionId, message: trimmed });
        if (!response.ok || !response.body) {
          throw new Error(response.status === 401 ? "登录态已失效" : `发送失败(${response.status})`);
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let answer = "";
        let speaking = false;

        const patchAssistant = (patch: Partial<Turn>) =>
          setTurns((prev) =>
            prev.map((t) => (t.id === assistantTurn.id ? { ...t, ...patch } : t)),
          );

        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const { events, rest } = parseSseFrames(buffer);
          buffer = rest;
          for (const payload of events) {
            if (payload.event === "start") {
              setSessionId(payload.session_id);
            } else if (payload.event === "route") {
              patchAssistant({ risk: payload.risk_level });
            } else if (payload.event === "skill" && payload.name === "search_knowledge") {
              patchAssistant({ retrieved: true });
            } else if (payload.event === "report") {
              patchAssistant({ reported: true });
            } else if (payload.event === "token") {
              if (!speaking) {
                speaking = true;
                setPhase("speaking");
              }
              answer += payload.content ?? "";
              patchAssistant({ content: answer });
            } else if (payload.event === "done") {
              const finalAnswer = payload.response?.answer;
              if (finalAnswer) {
                // 安全复核终稿覆盖低风险直播内容
                answer = finalAnswer;
                patchAssistant({ content: finalAnswer });
              }
              if (payload.response?.session_id) setSessionId(payload.response.session_id);
            } else if (payload.event === "error") {
              setError("这一句没能送达,正在重试");
            }
          }
        }
        setPhase("idle");
        await loadSessions();
      } catch (e) {
        setPhase("idle");
        const message = e instanceof Error ? e.message : "发送失败";
        setError(message);
        setTurns((prev) => prev.filter((t) => t.id !== assistantTurn.id || t.content));
      } finally {
        sendingRef.current = false;
      }
    },
    [sessionId, loadSessions],
  );

  useEffect(() => {
    loadSessions().catch(() => { /* 401 由 api 层统一处理 */ });
  }, [loadSessions]);

  return { sessions, sessionId, turns, phase, error, send, openSession, newSession, reloadSessions: loadSessions };
}
