"use client";

import { useEffect, useState } from "react";
import { useAuth, useRequireAuth } from "@/lib/auth";
import { ApiError, getSubscription, listPlans, Plan, Subscription, updateSubscription } from "@/lib/api";

export default function BillingPage() {
  const { token, loading } = useRequireAuth();
  const { user } = useAuth();
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [switchingTo, setSwitchingTo] = useState<string | null>(null);

  async function refresh() {
    if (!token) return;
    try {
      const [sub, allPlans] = await Promise.all([getSubscription(token), listPlans(token)]);
      setSubscription(sub);
      setPlans(allPlans);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  useEffect(() => {
    refresh();
  }, [token]);

  async function switchPlan(slug: string) {
    if (!token) return;
    setSwitchingTo(slug);
    setError(null);
    try {
      await updateSubscription(token, slug);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSwitchingTo(null);
    }
  }

  if (loading || !token) return null;

  const usagePct = subscription
    ? Math.min(100, (subscription.current_period_agent_runs / subscription.plan.max_agent_runs_per_month) * 100)
    : 0;
  const isAdmin = user?.role === "platform_admin";

  return (
    <main className="container">
      <h1>Billing</h1>
      <p className="muted" style={{ marginTop: 0 }}>
        No real payment processor is connected — switching plans here is self-service selection, not a charge.
      </p>

      {error && <div className="error-banner">{error}</div>}

      {subscription && (
        <div className="card">
          <h2>Current plan</h2>
          <div className="row">
            <strong>{subscription.plan.name}</strong>
            <span className="badge badge-ok">{subscription.status}</span>
          </div>
          <p className="muted small" style={{ margin: "8px 0" }}>
            {subscription.current_period_agent_runs} / {subscription.plan.max_agent_runs_per_month} agent runs this
            month
          </p>
          <div className="progress-bar">
            <div className="progress-bar-fill" style={{ width: `${usagePct}%` }} />
          </div>
        </div>
      )}

      <h2 style={{ marginTop: 24 }}>Available plans</h2>
      {!isAdmin && (
        <p className="muted small">Only a platform admin can change the tenant&apos;s plan.</p>
      )}
      <div className="grid grid-3">
        {plans?.map((plan) => {
          const current = subscription?.plan.slug === plan.slug;
          return (
            <div className="card" key={plan.slug}>
              <strong>{plan.name}</strong>
              <p style={{ fontSize: 22, margin: "8px 0" }}>
                ${plan.price_usd_per_month}
                <span className="muted small">/mo</span>
              </p>
              <ul className="muted small" style={{ paddingLeft: 18, marginTop: 0 }}>
                <li>{plan.max_agent_runs_per_month.toLocaleString()} agent runs/mo</li>
                <li>{plan.max_tool_calls_per_month.toLocaleString()} tool calls/mo</li>
                <li>{plan.max_users} users</li>
              </ul>
              <button
                className={`btn ${current ? "" : "btn-primary"}`}
                disabled={current || !isAdmin || switchingTo === plan.slug}
                onClick={() => switchPlan(plan.slug)}
                type="button"
                style={{ width: "100%", justifyContent: "center" }}
              >
                {current ? "Current plan" : switchingTo === plan.slug ? "Switching…" : "Switch to this plan"}
              </button>
            </div>
          );
        })}
      </div>
    </main>
  );
}
