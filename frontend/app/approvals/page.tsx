"use client";

import { useEffect, useState } from "react";
import { useRequireAuth } from "@/lib/auth";
import { Approval, ApiError, approveApproval, listApprovals, rejectApproval } from "@/lib/api";

const STATUS_BADGE: Record<Approval["status"], string> = {
  pending: "badge-warn",
  executed: "badge-ok",
  rejected: "badge-error",
  failed: "badge-error",
};

export default function ApprovalsPage() {
  const { token, loading } = useRequireAuth();
  const [approvals, setApprovals] = useState<Approval[] | null>(null);
  const [filter, setFilter] = useState<string>("");
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    if (!token) return;
    try {
      setApprovals(await listApprovals(token, filter || undefined));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  useEffect(() => {
    refresh();
  }, [token, filter]);

  async function decide(id: string, action: "approve" | "reject") {
    if (!token) return;
    setBusyId(id);
    setError(null);
    try {
      const note = notes[id] || undefined;
      if (action === "approve") await approveApproval(token, id, note);
      else await rejectApproval(token, id, note);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  }

  if (loading || !token) return null;

  return (
    <main className="container">
      <h1>Approvals</h1>
      <p className="muted" style={{ marginTop: 0 }}>
        Sensitive or critical tool calls wait here for a human decision before they run.
      </p>

      <div className="row" style={{ marginBottom: 16 }}>
        <select className="input" style={{ width: 200 }} value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="executed">Executed</option>
          <option value="rejected">Rejected</option>
          <option value="failed">Failed</option>
        </select>
      </div>

      {error && <div className="error-banner">{error}</div>}
      {!approvals && !error && <p className="muted small">Loading…</p>}
      {approvals && approvals.length === 0 && <div className="empty">Nothing here.</div>}

      {approvals?.map((approval) => (
        <div className="card" key={approval.id}>
          <div className="row">
            <strong>{approval.tool_name}</strong>
            <span className={`badge ${STATUS_BADGE[approval.status]}`}>{approval.status}</span>
          </div>
          <p className="muted small">
            via {approval.agent_name} · {new Date(approval.created_at).toLocaleString()}
          </p>
          <div className="tool-trace">{JSON.stringify(approval.arguments)}</div>

          {approval.result && (
            <p className="small" style={{ color: "var(--success)" }}>
              Result: {approval.result.content}
            </p>
          )}
          {approval.error && <p className="small" style={{ color: "var(--error)" }}>Error: {approval.error}</p>}
          {approval.decision_note && <p className="muted small">Note: {approval.decision_note}</p>}

          {approval.status === "pending" && (
            <div style={{ marginTop: 12 }}>
              <input
                className="input"
                placeholder="Optional note"
                value={notes[approval.id] || ""}
                onChange={(e) => setNotes((n) => ({ ...n, [approval.id]: e.target.value }))}
                style={{ marginBottom: 8 }}
              />
              <div className="row">
                <button
                  className="btn btn-success"
                  disabled={busyId === approval.id}
                  onClick={() => decide(approval.id, "approve")}
                  type="button"
                >
                  Approve
                </button>
                <button
                  className="btn btn-danger"
                  disabled={busyId === approval.id}
                  onClick={() => decide(approval.id, "reject")}
                  type="button"
                >
                  Reject
                </button>
              </div>
            </div>
          )}
        </div>
      ))}
    </main>
  );
}
