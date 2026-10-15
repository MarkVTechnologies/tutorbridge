import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { api, ApiError } from "./api";
import type { Me, Role } from "./types";

interface AuthState {
  me: Me | null;
  loading: boolean;
  refresh: () => Promise<void>;
  setMe: (me: Me | null) => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await api.get<Me>("/auth/me/");
      } catch (e) {
        if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return null;
        throw e;
      }
    },
    staleTime: 60_000,
  });
  const refresh = useCallback(async () => {
    await qc.invalidateQueries({ queryKey: ["me"] });
  }, [qc]);
  const setMe = useCallback((me: Me | null) => qc.setQueryData(["me"], me), [qc]);
  const logout = useCallback(async () => {
    await api.post("/auth/logout/");
    qc.clear();
    qc.setQueryData(["me"], null);
  }, [qc]);
  return <AuthContext.Provider value={{ me: q.data ?? null, loading: q.isLoading, refresh, setMe, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}

export function homeFor(me: Me): string {
  if (me.role === "parent") return "/parent";
  if (me.role === "tutor") return "/tutor";
  return "/staff";
}

export function hasPerm(me: Me | null, code: string) {
  return !!me?.permissions.includes(code);
}

/** Route guard: signed in, right role, and (for staff) a 2FA'd session. */
export function RequireAuth({ roles, children }: { roles?: Role[] | "staff"; children: ReactNode }) {
  const { me, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <div className="p-10 text-center text-slate-500">Loading…</div>;
  if (!me) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />;
  if (me.is_staff_member && (me.needs_2fa_setup || !me.two_factor_ok) && !loc.pathname.startsWith("/account/2fa")) {
    return <Navigate to="/account/2fa" replace />;
  }
  if (roles === "staff" && !me.is_staff_member) return <Navigate to={homeFor(me)} replace />;
  if (Array.isArray(roles) && !roles.includes(me.role)) return <Navigate to={homeFor(me)} replace />;
  return <>{children}</>;
}
