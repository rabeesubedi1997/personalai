"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";

export default function LoginPage() {
  const { token, loading, login, bootstrap } = useAuth();
  const router = useRouter();

  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!loading && token) router.replace("/");
  }, [loading, token, router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await bootstrap(email, password);
      }
      router.replace("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="container" style={{ maxWidth: 420, paddingTop: 80 }}>
      <h1>PersonalOps AI</h1>
      <p className="muted" style={{ marginTop: 0, marginBottom: 32 }}>
        AI Workforce / Operations Agent Platform
      </p>

      <div className="card">
        <div className="row" style={{ marginBottom: 16 }}>
          <button
            className="btn"
            style={{ flex: 1, justifyContent: "center", background: mode === "login" ? "#1e222c" : "transparent" }}
            onClick={() => setMode("login")}
            type="button"
          >
            Sign in
          </button>
          <button
            className="btn"
            style={{ flex: 1, justifyContent: "center", background: mode === "signup" ? "#1e222c" : "transparent" }}
            onClick={() => setMode("signup")}
            type="button"
          >
            Create account
          </button>
        </div>

        <form onSubmit={handleSubmit} style={{ display: "grid", gap: 12 }}>
          <input
            className="input"
            type="email"
            required
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <input
            className="input"
            type="password"
            required
            minLength={6}
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {error && <div className="error-banner">{error}</div>}
          <button className="btn btn-primary" type="submit" disabled={submitting}>
            {submitting ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>
        {mode === "signup" && (
          <p className="muted small" style={{ marginTop: 12, marginBottom: 0 }}>
            Creates a new tenant with you as its platform admin, with the full agent catalog
            pre-installed on the Free plan.
          </p>
        )}
      </div>
    </main>
  );
}
