"use client";

import { useEffect, useState } from "react";
import { useRequireAuth } from "@/lib/auth";
import { ApiError, installAgent, listMarketplace, MarketplaceAgent, uninstallAgent } from "@/lib/api";

export default function MarketplacePage() {
  const { token, loading } = useRequireAuth();
  const [agents, setAgents] = useState<MarketplaceAgent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busySlug, setBusySlug] = useState<string | null>(null);

  async function refresh() {
    if (!token) return;
    try {
      setAgents(await listMarketplace(token));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  useEffect(() => {
    refresh();
  }, [token]);

  async function toggle(agent: MarketplaceAgent) {
    if (!token) return;
    setBusySlug(agent.slug);
    setError(null);
    try {
      if (agent.installed) {
        await uninstallAgent(token, agent.slug);
      } else {
        await installAgent(token, agent.slug);
      }
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusySlug(null);
    }
  }

  if (loading || !token) return null;

  return (
    <main className="container">
      <h1>Marketplace</h1>
      <p className="muted" style={{ marginTop: 0 }}>
        Browse every agent registered on the platform and install or remove it for your tenant.
      </p>

      {error && <div className="error-banner">{error}</div>}
      {!agents && !error && <p className="muted small">Loading…</p>}

      <div className="grid grid-2" style={{ marginTop: 16 }}>
        {agents?.map((agent) => (
          <div key={agent.slug} className="card">
            <div className="row">
              <strong>{agent.name}</strong>
              <span className="badge badge-muted">{agent.category}</span>
            </div>
            <p className="muted small">{agent.description}</p>
            <div className="row">
              <span className="muted small">v{agent.version}</span>
              <button
                className={`btn ${agent.installed ? "btn-danger" : "btn-success"}`}
                disabled={busySlug === agent.slug}
                onClick={() => toggle(agent)}
                type="button"
              >
                {busySlug === agent.slug ? "Working…" : agent.installed ? "Uninstall" : "Install"}
              </button>
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
