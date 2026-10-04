"use client";

import { useEffect, useState } from "react";
import { useRequireAuth } from "@/lib/auth";
import { ApiError, listAdminTenants, TenantSummary } from "@/lib/api";

export default function AdminPage() {
  const { token, loading } = useRequireAuth();
  const [tenants, setTenants] = useState<TenantSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) listAdminTenants(token).then(setTenants).catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [token]);

  if (loading || !token) return null;

  return (
    <main className="container">
      <h1>Admin</h1>
      <p className="muted" style={{ marginTop: 0 }}>
        Cross-tenant view — the one place on this platform that isn&apos;t scoped to your own tenant.
      </p>

      {error && <div className="error-banner">{error}</div>}
      {!tenants && !error && <p className="muted small">Loading…</p>}

      {tenants && (
        <div className="card" style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--text-dim)" }}>
                <th style={{ padding: "6px 10px" }}>Tenant</th>
                <th style={{ padding: "6px 10px" }}>Users</th>
                <th style={{ padding: "6px 10px" }}>Plan</th>
                <th style={{ padding: "6px 10px" }}>Usage (mo.)</th>
                <th style={{ padding: "6px 10px" }}>Created</th>
              </tr>
            </thead>
            <tbody>
              {tenants.map((t) => (
                <tr key={t.id} style={{ borderTop: "1px solid var(--border)" }}>
                  <td style={{ padding: "8px 10px" }}>{t.name}</td>
                  <td style={{ padding: "8px 10px" }}>{t.user_count}</td>
                  <td style={{ padding: "8px 10px" }}>
                    <span className="badge badge-muted">{t.plan_slug ?? "none"}</span>
                  </td>
                  <td style={{ padding: "8px 10px" }}>{t.current_period_agent_runs}</td>
                  <td style={{ padding: "8px 10px" }} className="muted">
                    {new Date(t.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
