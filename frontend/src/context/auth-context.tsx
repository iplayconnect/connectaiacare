"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  AuthUser,
  clearAuth,
  getStoredUser,
  getToken,
  persistAuth,
} from "@/lib/auth";

type AuthState = {
  user: AuthUser | null;
  loading: boolean;
  hydrated: boolean;
};

type AuthContextValue = AuthState & {
  login: (email: string, password: string) => Promise<{ ok: true } | { ok: false; reason: string }>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  hasRole: (...roles: AuthUser["role"][]) => boolean;
};

const AuthContext = createContext<AuthContextValue | null>(null);

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:5055";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [hydrated, setHydrated] = useState<boolean>(false);

  // Hidrata o estado a partir do localStorage no mount (client-only).
  useEffect(() => {
    setUser(getStoredUser());
    setHydrated(true);
  }, []);

  const login = useCallback<AuthContextValue["login"]>(async (email, password) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
        cache: "no-store",
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok || body?.status !== "ok") {
        return { ok: false as const, reason: body?.reason || `http_${res.status}` };
      }
      persistAuth(body.token, body.refreshToken, body.user as AuthUser);
      setUser(body.user as AuthUser);
      return { ok: true as const };
    } catch (err) {
      return { ok: false as const, reason: "network_error" };
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback<AuthContextValue["logout"]>(async () => {
    const token = getToken();
    if (token) {
      try {
        await fetch(`${API_BASE}/api/auth/logout`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ allSessions: false }),
          cache: "no-store",
        });
      } catch {
        // Falha de rede no logout não deve bloquear UX — limpamos local.
      }
    }
    clearAuth();
    setUser(null);
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
  }, []);

  const refresh = useCallback<AuthContextValue["refresh"]>(async () => {
    const token = getToken();
    if (!token) {
      setUser(null);
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/api/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      if (!res.ok) {
        clearAuth();
        setUser(null);
        return;
      }
      const body = await res.json();
      if (body?.status === "ok" && body.user) {
        setUser(body.user as AuthUser);
      }
    } catch {
      /* ignore */
    }
  }, []);

  const hasRole = useCallback<AuthContextValue["hasRole"]>(
    (...roles) => !!user && roles.includes(user.role),
    [user],
  );

  const value = useMemo<AuthContextValue>(
    () => ({ user, loading, hydrated, login, logout, refresh, hasRole }),
    [user, loading, hydrated, login, logout, refresh, hasRole],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
