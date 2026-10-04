"use client";

import { useEffect, useState } from "react";
import { useRequireAuth } from "@/lib/auth";
import { ApiError, listNotifications, markNotificationRead, Notification } from "@/lib/api";

export default function NotificationsPage() {
  const { token, loading } = useRequireAuth();
  const [notifications, setNotifications] = useState<Notification[] | null>(null);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    if (!token) return;
    try {
      setNotifications(await listNotifications(token, unreadOnly || undefined));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  useEffect(() => {
    refresh();
  }, [token, unreadOnly]);

  async function markRead(id: string) {
    if (!token) return;
    try {
      await markNotificationRead(token, id);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  if (loading || !token) return null;

  return (
    <main className="container">
      <h1>Notifications</h1>

      <label className="row small muted" style={{ marginBottom: 16, cursor: "pointer" }}>
        <input
          type="checkbox"
          checked={unreadOnly}
          onChange={(e) => setUnreadOnly(e.target.checked)}
          style={{ marginRight: 8 }}
        />
        Unread only
      </label>

      {error && <div className="error-banner">{error}</div>}
      {!notifications && !error && <p className="muted small">Loading…</p>}
      {notifications && notifications.length === 0 && <div className="empty">Nothing here.</div>}

      {notifications?.map((n) => (
        <div className="card" key={n.id}>
          <div className="row">
            <strong>{n.subject}</strong>
            <span className={`badge ${n.channel === "web" ? "badge-muted" : "badge-warn"}`}>{n.channel}</span>
          </div>
          <p style={{ margin: "8px 0" }}>{n.message}</p>
          <div className="row">
            <span className="muted small">{new Date(n.created_at).toLocaleString()}</span>
            {!n.is_read && (
              <button className="btn" onClick={() => markRead(n.id)} type="button">
                Mark read
              </button>
            )}
          </div>
        </div>
      ))}
    </main>
  );
}
