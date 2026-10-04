"use client";

import { useEffect, useState } from "react";
import { fetchHealth, login, type HealthStatus } from "@/lib/api";

const statusColor = (s: string) => (s === "ok" ? "#2ecc71" : s === "unavailable" ? "#e74c3c" : "#f1c40f");

export default function DashboardPage() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);

  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [loginError, setLoginError] = useState<string | null>(null);

  useEffect(() => {
    fetchHealth().then(setHealth).catch((e) => setHealthError(String(e.message ?? e)));
  }, []);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoginError(null);
    try {
      const t = await login(email, password);
      setToken(t);
    } catch (err: any) {
      setLoginError(err.message ?? String(err));
    }
  }

  return (
    <main style={{ maxWidth: 720, margin: "0 auto", padding: "48px 24px" }}>
      <h1 style={{ fontSize: 28, marginBottom: 4 }}>PersonalOps AI</h1>
      <p style={{ color: "#9aa0a6", marginTop: 0 }}>AI Workforce / Operations Agent Platform — Phase 1</p>

      <section
        style={{
          marginTop: 32,
          padding: 20,
          borderRadius: 12,
          background: "#171a21",
          border: "1px solid #262a33",
        }}
      >
        <h2 style={{ fontSize: 16, marginTop: 0 }}>System Health</h2>
        {healthError && <p style={{ color: "#e74c3c" }}>Could not reach backend: {healthError}</p>}
        {!health && !healthError && <p style={{ color: "#9aa0a6" }}>Checking…</p>}
        {health && (
          <ul style={{ listStyle: "none", padding: 0, display: "grid", gap: 8 }}>
            {(["status", "database", "redis", "ai_provider"] as const).map((key) => (
              <li key={key} style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "#9aa0a6" }}>{key}</span>
                <span style={{ color: statusColor(health[key]), fontWeight: 600 }}>{health[key]}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section
        style={{
          marginTop: 24,
          padding: 20,
          borderRadius: 12,
          background: "#171a21",
          border: "1px solid #262a33",
        }}
      >
        <h2 style={{ fontSize: 16, marginTop: 0 }}>Login</h2>
        {!token ? (
          <form onSubmit={handleLogin} style={{ display: "grid", gap: 12 }}>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Email"
              style={{ padding: 10, borderRadius: 8, border: "1px solid #333", background: "#0f1117", color: "#e6e8eb" }}
            />
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              style={{ padding: 10, borderRadius: 8, border: "1px solid #333", background: "#0f1117", color: "#e6e8eb" }}
            />
            <button
              type="submit"
              style={{ padding: 10, borderRadius: 8, border: "none", background: "#4c8bf5", color: "white", fontWeight: 600 }}
            >
              Sign in
            </button>
            {loginError && <p style={{ color: "#e74c3c" }}>{loginError}</p>}
          </form>
        ) : (
          <p style={{ color: "#2ecc71" }}>Signed in — token acquired.</p>
        )}
      </section>
    </main>
  );
}
