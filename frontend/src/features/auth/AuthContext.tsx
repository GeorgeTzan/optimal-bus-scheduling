"use client";
import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
} from "react";

export type UserRole =
  | "admin"
  | "dispatcher"
  | "driver"
  | "fleet_manager"
  | "management"
  | "viewer";
export interface AuthUser {
  id: number;
  email: string;
  fullName: string;
  role: UserRole;
  ktelId: number;
  ktelName?: string;
  permissions: string[];
  sessionId: string;
}
interface AuthContextType {
  user: AuthUser | null;
  isAuthenticated: boolean;
  loading: boolean;
  error: string | null;
  refreshIdentity: () => Promise<void>;
  logout: () => Promise<void>;
  apiFetch: (path: string, options?: RequestInit) => Promise<Response>;
}
const AuthContext = createContext<AuthContextType | null>(null);
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const apiFetch = useCallback(
    async (path: string, options: RequestInit = {}) => {
      const headers = new Headers(options.headers);
      if (
        options.body &&
        !(options.body instanceof FormData) &&
        !headers.has("Content-Type")
      )
        headers.set("Content-Type", "application/json");
      if (
        !["GET", "HEAD", "OPTIONS"].includes(
          (options.method ?? "GET").toUpperCase(),
        )
      ) {
        const csrf = document.cookie
          .split("; ")
          .find((c) => c.startsWith("ktel_csrf="))
          ?.split("=")
          .slice(1)
          .join("=");
        if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
      }
      const response = await fetch(path, {
        ...options,
        headers,
        credentials: "same-origin",
        cache: "no-store",
      });
      if (response.status === 401) setUser(null);
      return response;
    },
    [],
  );
  const refreshIdentity = useCallback(async () => {
    setError(null);
    try {
      const response = await apiFetch("/api/auth/me");
      if (response.status === 401) {
        setUser(null);
        return;
      }
      if (!response.ok) throw new Error("identity_unavailable");
      const identity = (await response.json()) as {
        id: number;
        email: string;
        full_name: string | null;
        role: UserRole;
        ktel_id: number;
        ktel_name: string;
        permissions: string[];
        session_id: string;
      };
      setUser({
        id: identity.id,
        email: identity.email,
        fullName: identity.full_name || identity.email,
        role: identity.role,
        ktelId: identity.ktel_id,
        ktelName: identity.ktel_name,
        permissions: identity.permissions,
        sessionId: identity.session_id,
      });
    } catch (err) {
      setError("identity_unavailable");
      throw err;
    } finally {
      setLoading(false);
    }
  }, [apiFetch]);
  useEffect(() => {
    localStorage.removeItem("ktel_token");
    localStorage.removeItem("ktel_user");
    void refreshIdentity().catch(() => undefined);
  }, [refreshIdentity]);
  const logout = useCallback(async () => {
    setError(null);
    try {
      const response = await apiFetch("/api/auth/logout", { method: "POST" });
      if (!response.ok && response.status !== 401)
        throw new Error("logout_unavailable");
      setUser(null);
    } catch {
      setError("logout_unavailable");
    }
  }, [apiFetch]);
  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        loading,
        error,
        refreshIdentity,
        logout,
        apiFetch,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within an AuthProvider");
  return context;
}
