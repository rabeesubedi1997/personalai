"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRequireAuth } from "@/lib/auth";
import { fetchHealth, getSubscription, HealthStatus, Subscription } from "@/lib/api";

const statusColor = (s: string) => (s === "ok" ? "badge-ok" : s === "unavailable" ? "badge-error" : "badge-warn");

const QUICK_LINKS = [
  { href: "/agents", title: "Agents", desc: "Run an installed agent and see it work in real time." },
  { href: "/marketplace", title: "Marketplace", desc: "Browse, install, and uninstall agents." },
  { href: "/approvals", title: "Approvals", desc: "Review actions waiting on human sign-off." },
  { href: "/billing", title: "Billing", desc: "Current plan, usage, and available tiers." },
  { href: "/notifications", title: "Notifications", desc: "What the platform has told you." },
];

export default function DashboardPage() {
  const { token, loading } = useRequireAuth();
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [subscription, setSubscription] = useState<Subscription | null>(null);

  useEffect(() => {
    fetchHealth().then(setHealth).catch((e) => setHealthError(String(e.message ?? e)));
  }, []);

  useEffect(() => {
    if (token) getSubscription(token).then(setSubscription).catch(() => {});
  }, [token]);

  if (loading || !token) return null;

  const usagePct = subscription
    ? Math.min(100, (subscription.current_period_agent_runs / subscription.plan.max_agent_runs_per_month) * 100)
    : 0;

  return (
    <main className="container">
      <h1>Dashboard</h1>
      <p className="muted" style={{ marginTop: 0 }}>AI Workforce / Operations Agent Platform</p>

      <div className="grid grid-2" style={{ marginTop: 24 }}>
        <div className="card">
          <h2>System Health</h2>
          {healthError && <div className="error-banner">Could not reach backend: {healthError}</div>}
          {!health && !healthError && <p className="muted small">Checking…</p>}
          {health && (
            <div style={{ display: "grid", gap: 8 }}>
              {(["status", "database", "redis", "ai_provider"] as const).map((key) => (
                <div className="row" key={key}>
                  <span className="muted small">{key}</span>
                  <span className={`badge ${statusColor(health[key])}`}>{health[key]}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="card">
          <h2>Plan & Usage</h2>
          {!subscription ? (
            <p className="muted small">Loading…</p>
          ) : (
            <>
              <div className="row">
                <span>{subscription.plan.name}</span>
                <span className="badge badge-ok">{subscription.status}</span>
              </div>
              <p className="muted small" style={{ margin: "8px 0" }}>
                {subscription.current_period_agent_runs} / {subscription.plan.max_agent_runs_per_month} agent runs
                this month
              </p>
              <div className="progress-bar">
                <div className="progress-bar-fill" style={{ width: `${usagePct}%` }} />
              </div>
              <Link href="/billing" className="btn small" style={{ marginTop: 12, display: "inline-flex" }}>
                Manage plan →
              </Link>
            </>
          )}
        </div>
      </div>

      <h2 style={{ marginTop: 32 }}>Quick links</h2>
      <div className="grid grid-3">
        {QUICK_LINKS.map((link) => (
          <Link key={link.href} href={link.href} className="card" style={{ textDecoration: "none" }}>
            <strong>{link.title}</strong>
            <p className="muted small" style={{ marginBottom: 0 }}>
              {link.desc}
            </p>
          </Link>
        ))}
      </div>
    </main>
  );
}
