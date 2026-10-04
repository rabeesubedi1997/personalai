"use client";

import { useEffect, useState } from "react";
import { useAuth, useRequireAuth } from "@/lib/auth";
import {
  AgentInfo,
  ApiError,
  ApiKey,
  AvailableBusiness,
  createApiKey,
  deleteBusinessConnector,
  listAgents,
  listApiKeys,
  listBusinessConnectors,
  revokeApiKey,
  setBusinessConnector,
} from "@/lib/api";

function embedSnippet(apiKey: string, apiBaseUrl: string): string {
  return `<!-- Paste this where you want the chat widget on your site -->
<script>
  async function askPersonalOpsAgent(message, conversationId) {
    const res = await fetch("${apiBaseUrl}/api/v1/public/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": "${apiKey}",
      },
      body: JSON.stringify({ message, conversation_id: conversationId || undefined }),
    });
    return res.json();
    // response.final_response is what to show the visitor;
    // keep response.conversation_id and pass it back in to continue the chat.
  }
</script>`;
}

export default function IntegrationsPage() {
  const { token, loading } = useRequireAuth();
  const { user } = useAuth();
  const [keys, setKeys] = useState<ApiKey[] | null>(null);
  const [agents, setAgents] = useState<AgentInfo[] | null>(null);
  const [agentSlug, setAgentSlug] = useState("");
  const [label, setLabel] = useState("");
  const [newKey, setNewKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [businesses, setBusinesses] = useState<AvailableBusiness[] | null>(null);
  const [urlDrafts, setUrlDrafts] = useState<Record<string, string>>({});
  const [savingBusiness, setSavingBusiness] = useState<string | null>(null);
  const isAdmin = user?.role === "platform_admin";

  async function refresh() {
    if (!token) return;
    try {
      const [k, a, b] = await Promise.all([
        listApiKeys(token),
        listAgents(token),
        listBusinessConnectors(token),
      ]);
      setKeys(k);
      setAgents(a);
      setBusinesses(b);
      if (!agentSlug && a.length > 0) setAgentSlug(a[0].name);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  useEffect(() => {
    refresh();
  }, [token]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!token || !agentSlug || !label.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const created = await createApiKey(token, agentSlug, label.trim());
      setNewKey(created.api_key);
      setLabel("");
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setCreating(false);
    }
  }

  async function handleRevoke(id: string) {
    if (!token) return;
    try {
      await revokeApiKey(token, id);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  async function handleSaveBusinessConnector(slug: string) {
    if (!token) return;
    const url = (urlDrafts[slug] ?? "").trim();
    if (!url) return;
    setSavingBusiness(slug);
    setError(null);
    try {
      await setBusinessConnector(token, slug, url);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSavingBusiness(null);
    }
  }

  async function handleDisconnectBusiness(slug: string) {
    if (!token) return;
    setSavingBusiness(slug);
    setError(null);
    try {
      await deleteBusinessConnector(token, slug);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSavingBusiness(null);
    }
  }

  if (loading || !token) return null;

  return (
    <main className="container">
      <h1>Integrations</h1>
      <p className="muted" style={{ marginTop: 0 }}>
        Two directions of "connect": point a business agent at its real data source below, and/or
        embed one in your own site as a chat widget further down.
      </p>

      {error && <div className="error-banner">{error}</div>}

      <h2 style={{ marginTop: 8 }}>Business data connections</h2>
      <p className="muted small" style={{ marginTop: 0 }}>
        Each business agent ships with sample/mock data so it works out of the box. Point one at a
        real business's API below and it switches from mock to real data immediately — no code
        change, no redeploy. Leave a business unconfigured and it keeps using its mock data.
      </p>
      {!businesses && <p className="muted small">Loading…</p>}
      {businesses?.map((b) => (
        <div className="card" key={b.business_slug}>
          <div className="row">
            <strong>{b.name}</strong>
            <span className={`badge ${b.connector ? "badge-ok" : "badge-muted"}`}>
              {b.connector ? "connected to real API" : "using mock data"}
            </span>
          </div>
          <p className="muted small" style={{ marginTop: 4 }}>{b.description}</p>
          {b.connector ? (
            <>
              <p className="muted small">Base URL: {b.connector.base_url}</p>
              {isAdmin && (
                <button
                  className="btn btn-danger"
                  type="button"
                  disabled={savingBusiness === b.business_slug}
                  onClick={() => handleDisconnectBusiness(b.business_slug)}
                >
                  {savingBusiness === b.business_slug ? "Disconnecting…" : "Disconnect (revert to mock)"}
                </button>
              )}
            </>
          ) : (
            isAdmin && (
              <div className="row" style={{ gap: 8 }}>
                <input
                  className="input"
                  placeholder="https://your-real-api.example.com"
                  value={urlDrafts[b.business_slug] ?? ""}
                  onChange={(e) =>
                    setUrlDrafts((prev) => ({ ...prev, [b.business_slug]: e.target.value }))
                  }
                />
                <button
                  className="btn btn-primary"
                  type="button"
                  disabled={savingBusiness === b.business_slug || !(urlDrafts[b.business_slug] ?? "").trim()}
                  onClick={() => handleSaveBusinessConnector(b.business_slug)}
                >
                  {savingBusiness === b.business_slug ? "Connecting…" : "Connect"}
                </button>
              </div>
            )
          )}
        </div>
      ))}

      <h2 style={{ marginTop: 24 }}>Connect AI Agent (embed a chat widget elsewhere)</h2>
      {!isAdmin && (
        <p className="muted small">Only a platform admin can create or revoke agent API keys.</p>
      )}

      {newKey && (
        <div className="card" style={{ borderColor: "var(--success)" }}>
          <h2 style={{ color: "var(--success)" }}>Key created — copy it now</h2>
          <p className="muted small">
            This is the only time the full key is shown. Store it somewhere safe.
          </p>
          <div className="tool-trace" style={{ wordBreak: "break-all" }}>
            {newKey}
          </div>
          <h2 style={{ marginTop: 20 }}>Embed this on your site</h2>
          <div className="tool-trace" style={{ whiteSpace: "pre-wrap" }}>
            {embedSnippet(newKey, process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000")}
          </div>
          <button className="btn" style={{ marginTop: 12 }} onClick={() => setNewKey(null)} type="button">
            Done
          </button>
        </div>
      )}

      {isAdmin && (
        <div className="card">
          <h2>Create a new key</h2>
          <form onSubmit={handleCreate} style={{ display: "grid", gap: 12 }}>
            <select
              className="input"
              value={agentSlug}
              onChange={(e) => setAgentSlug(e.target.value)}
            >
              {agents?.map((a) => (
                <option key={a.name} value={a.name}>
                  {a.name}
                </option>
              ))}
            </select>
            <input
              className="input"
              placeholder="Label (e.g. ToleMate website widget)"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            />
            <button className="btn btn-primary" type="submit" disabled={creating || !agentSlug}>
              {creating ? "Creating…" : "Create key"}
            </button>
          </form>
        </div>
      )}

      <h2 style={{ marginTop: 24 }}>Existing keys</h2>
      {!keys && <p className="muted small">Loading…</p>}
      {keys && keys.length === 0 && <div className="empty">No API keys yet.</div>}
      {keys?.map((k) => (
        <div className="card" key={k.id}>
          <div className="row">
            <strong>{k.label}</strong>
            <span className={`badge ${k.is_active ? "badge-ok" : "badge-muted"}`}>
              {k.is_active ? "active" : "revoked"}
            </span>
          </div>
          <p className="muted small">
            agent: {k.agent_slug} · key: {k.key_prefix}… · created{" "}
            {new Date(k.created_at).toLocaleDateString()}
            {k.last_used_at && ` · last used ${new Date(k.last_used_at).toLocaleString()}`}
          </p>
          {isAdmin && k.is_active && (
            <button className="btn btn-danger" onClick={() => handleRevoke(k.id)} type="button">
              Revoke
            </button>
          )}
        </div>
      ))}
    </main>
  );
}
