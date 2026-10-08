"use client";

import { useEffect, useState } from "react";
import { useAuth, useRequireAuth } from "@/lib/auth";
import {
  AgentInfo,
  ApiError,
  ApiKey,
  AvailableBusiness,
  KnowledgeSite,
  connectSite,
  createApiKey,
  deleteBusinessConnector,
  deleteSite,
  listAgents,
  listApiKeys,
  listBusinessConnectors,
  listSites,
  recrawlSite,
  revokeApiKey,
  setBusinessConnector,
} from "@/lib/api";

const SITE_STATUS_BADGE: Record<KnowledgeSite["status"], { cls: string; text: string }> = {
  pending: { cls: "badge-warn", text: "queued" },
  crawling: { cls: "badge-warn", text: "reading site…" },
  ready: { cls: "badge-ok", text: "ready" },
  failed: { cls: "badge-error", text: "failed" },
};

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
  const [sites, setSites] = useState<KnowledgeSite[] | null>(null);
  const [siteUrl, setSiteUrl] = useState("");
  const [siteName, setSiteName] = useState("");
  const [siteWantsKey, setSiteWantsKey] = useState(true);
  const [connectingSite, setConnectingSite] = useState(false);
  const [siteKey, setSiteKey] = useState<{ key: string; siteName: string } | null>(null);
  const [busySite, setBusySite] = useState<string | null>(null);
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

  async function refreshSites() {
    if (!token || !isAdmin) return;
    try {
      setSites(await listSites(token));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  useEffect(() => {
    refreshSites();
  }, [token, isAdmin]);

  // While any site is still being read, check back every few seconds so the
  // status flips to "ready" (or "failed") without a manual page refresh.
  const anySiteBusy = sites?.some((s) => s.status === "pending" || s.status === "crawling");
  useEffect(() => {
    if (!anySiteBusy) return;
    const timer = setInterval(refreshSites, 3000);
    return () => clearInterval(timer);
  }, [anySiteBusy, token, isAdmin]);

  async function handleConnectSite(e: React.FormEvent) {
    e.preventDefault();
    if (!token || !siteUrl.trim()) return;
    setConnectingSite(true);
    setError(null);
    try {
      const created = await connectSite(token, {
        url: siteUrl.trim(),
        name: siteName.trim() || undefined,
        create_widget_key: siteWantsKey,
      });
      if (created.api_key) setSiteKey({ key: created.api_key, siteName: created.name });
      setSiteUrl("");
      setSiteName("");
      await Promise.all([refreshSites(), refresh()]);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setConnectingSite(false);
    }
  }

  async function handleSiteAction(id: string, action: "recrawl" | "delete") {
    if (!token) return;
    setBusySite(id);
    setError(null);
    try {
      if (action === "recrawl") await recrawlSite(token, id);
      else await deleteSite(token, id);
      await refreshSites();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusySite(null);
    }
  }

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

      <h2 style={{ marginTop: 24 }}>Connect a website</h2>
      <p className="muted small" style={{ marginTop: 0 }}>
        Give it a site's address and the chat agents answer visitors from that site's own pages —
        no code per site. Works for any website, including ones built with React. Re-index after
        the site changes.
      </p>

      {siteKey && (
        <div className="card" style={{ borderColor: "var(--success)" }}>
          <h2 style={{ color: "var(--success)" }}>Chat key for {siteKey.siteName} — copy it now</h2>
          <p className="muted small">
            This is the only time the full key is shown. Paste it into the website's chat
            settings (for ToleMate: Admin → AI Agent). Keep it on the website's server, never in
            browser code.
          </p>
          <div className="tool-trace" style={{ wordBreak: "break-all" }}>
            {siteKey.key}
          </div>
          <p className="muted small">
            Agent: site_assistant (answers from the website only). Chat endpoint:{" "}
            {process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}/api/v1/public/chat/stream
          </p>
          <button className="btn" style={{ marginTop: 12 }} onClick={() => setSiteKey(null)} type="button">
            Done
          </button>
        </div>
      )}

      {isAdmin ? (
        <div className="card">
          <form onSubmit={handleConnectSite} style={{ display: "grid", gap: 12 }}>
            <input
              className="input"
              type="url"
              required
              placeholder="https://your-website.com"
              value={siteUrl}
              onChange={(e) => setSiteUrl(e.target.value)}
            />
            <input
              className="input"
              placeholder="Name (optional — defaults to the address)"
              value={siteName}
              onChange={(e) => setSiteName(e.target.value)}
            />
            <label className="small" style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input
                type="checkbox"
                checked={siteWantsKey}
                onChange={(e) => setSiteWantsKey(e.target.checked)}
              />
              Also create a chat key for this website
            </label>
            <button className="btn btn-primary" type="submit" disabled={connectingSite || !siteUrl.trim()}>
              {connectingSite ? "Connecting…" : "Connect website"}
            </button>
          </form>
        </div>
      ) : (
        <p className="muted small">Only a platform admin can connect websites.</p>
      )}

      {isAdmin && !sites && <p className="muted small">Loading…</p>}
      {isAdmin && sites && sites.length === 0 && <div className="empty">No websites connected yet.</div>}
      {sites?.map((s) => {
        const badge = SITE_STATUS_BADGE[s.status];
        const busy = busySite === s.id || s.status === "pending" || s.status === "crawling";
        return (
          <div className="card" key={s.id}>
            <div className="row">
              <strong>{s.name}</strong>
              <span className={`badge ${badge.cls}`}>{badge.text}</span>
            </div>
            <p className="muted small" style={{ marginTop: 4 }}>
              {s.url}
              {s.status === "ready" &&
                ` · ${s.pages_count} pages, ${s.chunks_count} sections read` +
                  (s.last_crawled_at ? ` · ${new Date(s.last_crawled_at).toLocaleString()}` : "")}
            </p>
            {s.status === "failed" && s.error && <p className="small" style={{ color: "var(--error)" }}>{s.error}</p>}
            <div className="row" style={{ gap: 8 }}>
              <button className="btn" type="button" disabled={busy} onClick={() => handleSiteAction(s.id, "recrawl")}>
                Re-index
              </button>
              <button
                className="btn btn-danger"
                type="button"
                disabled={busySite === s.id}
                onClick={() => {
                  if (window.confirm(`Remove ${s.name} and forget everything read from it?`)) {
                    handleSiteAction(s.id, "delete");
                  }
                }}
              >
                Remove
              </button>
            </div>
          </div>
        );
      })}

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
