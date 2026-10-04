"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useRef, useState } from "react";
import { useRequireAuth } from "@/lib/auth";
import { ApiError, AgentRunResponse, runAgent } from "@/lib/api";

type Turn = {
  role: "user" | "assistant";
  content: string;
  toolTrace?: AgentRunResponse["tool_trace"];
  status?: string;
  approvalId?: string | null;
};

const STATUS_LABEL: Record<string, { text: string; className: string }> = {
  completed: { text: "completed", className: "badge-ok" },
  awaiting_approval: { text: "awaiting approval", className: "badge-warn" },
  max_iterations_reached: { text: "stopped (iteration limit)", className: "badge-warn" },
  escalated: { text: "escalated", className: "badge-warn" },
  failed: { text: "failed", className: "badge-error" },
};

export default function AgentChatPage() {
  const params = useParams<{ slug: string }>();
  const slug = params.slug;
  const { token, loading } = useRequireAuth();

  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const conversationId = useRef<string | null>(null);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!token || !input.trim() || sending) return;
    const message = input.trim();
    setInput("");
    setError(null);
    setTurns((t) => [...t, { role: "user", content: message }]);
    setSending(true);
    try {
      const res = await runAgent(token, slug, message, conversationId.current);
      conversationId.current = res.conversation_id;
      setTurns((t) => [
        ...t,
        {
          role: "assistant",
          content: res.final_response || "(no response text)",
          toolTrace: res.tool_trace,
          status: res.status,
          approvalId: res.approval_id,
        },
      ]);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError(String(err));
      }
    } finally {
      setSending(false);
    }
  }

  function newConversation() {
    conversationId.current = null;
    setTurns([]);
    setError(null);
  }

  if (loading || !token) return null;

  return (
    <main className="container" style={{ maxWidth: 720 }}>
      <div className="row">
        <div>
          <h1>{slug}</h1>
          <p className="muted small" style={{ marginTop: 0 }}>
            <Link href="/agents" style={{ color: "var(--accent)" }}>
              ← all agents
            </Link>
          </p>
        </div>
        <button className="btn" onClick={newConversation} type="button">
          New conversation
        </button>
      </div>

      <div className="card" style={{ minHeight: 320, marginTop: 16 }}>
        {turns.length === 0 && <div className="empty">Send a message to start.</div>}
        {turns.map((turn, i) => (
          <div key={i} className={`chat-bubble ${turn.role}`}>
            {turn.content}
            {turn.status && STATUS_LABEL[turn.status] && (
              <div style={{ marginTop: 8 }}>
                <span className={`badge ${STATUS_LABEL[turn.status].className}`}>
                  {STATUS_LABEL[turn.status].text}
                </span>
                {turn.approvalId && (
                  <Link
                    href="/approvals"
                    className="small"
                    style={{ marginLeft: 8, color: "var(--accent)" }}
                  >
                    review in Approvals →
                  </Link>
                )}
              </div>
            )}
            {turn.toolTrace && turn.toolTrace.length > 0 && (
              <div className="tool-trace">
                {turn.toolTrace.map((tc, j) => (
                  <div key={j} style={{ marginBottom: j < turn.toolTrace!.length - 1 ? 6 : 0 }}>
                    <span style={{ color: tc.is_error ? "var(--error)" : "var(--success)" }}>
                      {tc.is_error ? "✗" : "✓"} {tc.tool}
                    </span>
                    <div className="muted">{JSON.stringify(tc.arguments)}</div>
                    <div>{tc.result}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
        {sending && <p className="muted small">Thinking…</p>}
      </div>

      {error && <div className="error-banner" style={{ marginTop: 16 }}>{error}</div>}

      <form onSubmit={send} className="row" style={{ marginTop: 16 }}>
        <input
          className="input"
          placeholder="Type a message…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={sending}
        />
        <button className="btn btn-primary" type="submit" disabled={sending || !input.trim()}>
          Send
        </button>
      </form>
    </main>
  );
}
