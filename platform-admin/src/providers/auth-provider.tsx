"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { api, clearCsrf, getCsrf } from "@/lib/api";
import type { PlatformUser } from "@/lib/types";

interface AuthContextValue {
  user: PlatformUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<PlatformUser>;
  logout: () => Promise<void>;
  can: (permission: string) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function firstAllowedRoute(user: PlatformUser) {
  const routes = [
    ["platform.dashboard.view", "/dashboard"],
    ["platform.tenants.manage", "/tenants"],
    ["platform.plans.manage", "/plans"],
    ["platform.settings.manage", "/settings"],
    ["platform.billing.manage", "/billing"],
    ["platform.support.manage", "/support"],
  ] as const;
  return routes.find(([permission]) => user.permissions.includes(permission))?.[1] || "/dashboard";
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<PlatformUser | null>(null);
  const [loading, setLoading] = useState(true);
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    let active = true;
    api.get<PlatformUser>("platform/auth/me/")
      .then((value) => { if (active) setUser(value); })
      .catch(() => { if (active) setUser(null); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const unauthorized = () => setUser(null);
    window.addEventListener("platform:unauthorized", unauthorized);
    return () => window.removeEventListener("platform:unauthorized", unauthorized);
  }, []);

  useEffect(() => {
    if (loading) return;
    if (!user && pathname !== "/login") router.replace("/login");
    if (user && pathname === "/login") router.replace(firstAllowedRoute(user));
  }, [loading, pathname, router, user]);

  async function login(email: string, password: string) {
    await getCsrf(true);
    const value = await api.post<PlatformUser>("platform/auth/login/", { email, password }, true);
    setUser(value);
    return value;
  }

  async function logout() {
    try { await api.post<void>("platform/auth/logout/"); } finally {
      clearCsrf();
      setUser(null);
      router.replace("/login");
    }
  }

  return <AuthContext.Provider value={{ user, loading, login, logout, can: (code) => !!user?.permissions.includes(code) }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used within AuthProvider");
  return value;
}
