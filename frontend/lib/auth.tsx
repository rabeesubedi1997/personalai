"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { bootstrap as apiBootstrap, fetchMe, login as apiLogin, User } from "./api";

const TOKEN_KEY = "personalops_token";

type AuthContextValue = {
  token: string | null;
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  bootstrap: (email: string, password: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let stored: string | null = null;
    try {
      stored = localStorage.getItem(TOKEN_KEY);
    } catch {
      // private browsing / storage blocked — proceed unauthenticated
    }
    if (!stored) {
      setLoading(false);
      return;
    }
    fetchMe(stored)
      .then((me) => {
        setToken(stored);
        setUser(me);
      })
      .catch(() => {
        try {
          localStorage.removeItem(TOKEN_KEY);
        } catch {
          // ignore
        }
      })
      .finally(() => setLoading(false));
  }, []);

  async function doLogin(email: string, password: string) {
    const t = await apiLogin(email, password);
    const me = await fetchMe(t);
    try {
      localStorage.setItem(TOKEN_KEY, t);
    } catch {
      // ignore — session still works for this page load
    }
    setToken(t);
    setUser(me);
  }

  async function doBootstrap(email: string, password: string) {
    await apiBootstrap(email, password);
    await doLogin(email, password);
  }

  function logout() {
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      // ignore
    }
    setToken(null);
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ token, user, loading, login: doLogin, bootstrap: doBootstrap, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

/** Redirects to /login once we know there's no session. Call at the top of
 * any page that requires auth. */
export function useRequireAuth() {
  const { token, loading } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!loading && !token) router.replace("/login");
  }, [loading, token, router]);
  return { token, loading };
}
