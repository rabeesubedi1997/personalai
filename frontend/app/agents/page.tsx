"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRequireAuth } from "@/lib/auth";
import { AgentInfo, listAgents } from "@/lib/api";

export default function AgentsPage() {
  const { token, loading } = useRequireAuth();
  const [agents, setAgents] = useState<AgentInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) listAgents(token).then(setAgents).catch((e) => setError(String(e.message ?? e)));
  }, [token]);

  if (loading || !token) return null;

  return (
    <main className="container">
      <h1>Agents</h1>
      <p className="muted" style={{ marginTop: 0 }}>
        Agents installed for your tenant. Need a different one?{" "}
        <Link href="/marketplace" style={{ color: "var(--accent)" }}>
          Browse the marketplace
        </Link>
        .
      </p>

      {error && <div className="error-banner">{error}</div>}
      {!agents && !error && <p className="muted small">Loading…</p>}
      {agents && agents.length === 0 && (
        <div className="empty">
          No agents installed. Visit the{" "}
          <Link href="/marketplace" style={{ color: "var(--accent)" }}>
            marketplace
          </Link>{" "}
          to install one.
        </div>
      )}

      <div className="grid grid-2" style={{ marginTop: 16 }}>
        {agents?.map((agent) => (
          <Link
            key={agent.name}
            href={`/agents/${agent.name}`}
            className="card"
            style={{ textDecoration: "none", display: "block" }}
          >
            <strong>{agent.name}</strong>
            <p className="muted small">{agent.description}</p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {agent.allowed_tools.map((tool) => (
                <span key={tool} className="badge badge-muted">
                  {tool}
                </span>
              ))}
            </div>
          </Link>
        ))}
      </div>
    </main>
  );
}
