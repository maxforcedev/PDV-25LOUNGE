"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { clearCsrfToken, getCsrfToken, http } from "@/lib/http";
import { firstAuthorizedRoute, isOperatingPermission } from "@/lib/authorized-routes";
import type { User, UserBranch, UserCompany } from "@/types";

const COMPANY_KEY = "pdv.current_company_id";
const BRANCH_KEY = "pdv.current_branch_id";
const PUBLIC_PATHS = ["/", "/ajuda"];

function isPublicPath(pathname: string) {
  return PUBLIC_PATHS.some((path) => pathname === path || (path !== "/" && pathname.startsWith(`${path}/`)));
}
interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  currentCompany: UserCompany | null;
  setCurrentCompanyId: (id: number) => void;
  currentBranch: UserBranch | null;
  setCurrentBranchId: (id: number) => void;
  hasPermission: (permission: string) => boolean;
  hasAnyPermission: (permissions: readonly string[]) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [companyId, setCompanyId] = useState<number | null>(null);
  const [branchId, setBranchId] = useState<number | null>(null);
  const pathname = usePathname();
  const router = useRouter();
  const currentCompany = user?.companies.find((company) => company.id === companyId) ?? user?.companies[0] ?? null;
  const companyBranches = user?.branches.filter((branch) => branch.company_id === currentCompany?.id) ?? [];
  const activeCompanyBranches = currentCompany?.status === "active" ? companyBranches.filter((branch) => branch.status === "active") : [];
  const currentBranch = activeCompanyBranches.find((branch) => branch.id === branchId) ?? activeCompanyBranches[0] ?? null;

  function applyUser(current: User | null) {
    setUser(current);
    if (!current) return;
    const stored = Number(sessionStorage.getItem(COMPANY_KEY));
    const selected = current.companies.find((company) => company.id === stored) ?? current.companies[0];
    setCompanyId(selected?.id ?? null);
    if (selected) sessionStorage.setItem(COMPANY_KEY, String(selected.id));
    const storedBranch = Number(sessionStorage.getItem(BRANCH_KEY));
    const selectedBranch = selected?.status === "active" ? current.branches.find((branch) => branch.id === storedBranch && branch.company_id === selected.id && branch.status === "active")
      ?? current.branches.find((branch) => branch.company_id === selected.id && branch.status === "active") : undefined;
    setBranchId(selectedBranch?.id ?? null);
    if (selectedBranch) sessionStorage.setItem(BRANCH_KEY, String(selectedBranch.id));
    else sessionStorage.removeItem(BRANCH_KEY);
  }

  async function refreshUser() {
    const current = await http.get<User>("auth/me/");
    applyUser(current);
  }

  useEffect(() => {
    let active = true;
    http.get<User>("auth/me/")
      .then((current) => active && applyUser(current))
      .catch(() => active && applyUser(null))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const handleUnauthorized = () => applyUser(null);
    window.addEventListener("auth:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("auth:unauthorized", handleUnauthorized);
  }, []);

  useEffect(() => {
    if (loading) return;
    if (!user && pathname !== "/login" && !isPublicPath(pathname)) router.replace("/login");
    if (user && pathname === "/login") {
      router.replace(firstAuthorizedRoute(user, currentCompany, currentBranch));
    }
  }, [loading, pathname, router, user, currentCompany, currentBranch]);

  async function login(email: string, password: string) {
    await getCsrfToken(true);
    const authenticated = await http.post<User>("auth/login/", { email, password });
    applyUser(authenticated);
    return authenticated;
  }

  async function logout() {
    await http.logout();
    clearCsrfToken();
    setUser(null);
    setCompanyId(null);
    setBranchId(null);
    sessionStorage.removeItem(COMPANY_KEY);
    sessionStorage.removeItem(BRANCH_KEY);
    router.replace("/login");
  }

  return (
    <AuthContext.Provider value={{
      user, loading, login, logout, refreshUser, currentCompany, currentBranch,
      setCurrentCompanyId: (id) => {
        if (!user?.companies.some((company) => company.id === id)) return;
        setCompanyId(id);
        sessionStorage.setItem(COMPANY_KEY, String(id));
        const selectedCompany = user.companies.find((company) => company.id === id);
        const nextBranch = selectedCompany?.status === "active" ? user.branches.find((branch) => branch.company_id === id && branch.status === "active") : undefined;
        setBranchId(nextBranch?.id ?? null);
        if (nextBranch) sessionStorage.setItem(BRANCH_KEY, String(nextBranch.id));
        else sessionStorage.removeItem(BRANCH_KEY);
      },
      setCurrentBranchId: (id) => {
        if (!activeCompanyBranches.some((branch) => branch.id === id)) return;
        setBranchId(id);
        sessionStorage.setItem(BRANCH_KEY, String(id));
      },
      hasPermission: (permission) => {
        if (!user) return false;
        const operating = isOperatingPermission(permission);
        const source = operating ? currentBranch : currentCompany;
        return !!source && (user.is_superuser || source.permissions.includes(permission));
      },
      hasAnyPermission: (required) => !!user && required.some((permission) => {
        const source = isOperatingPermission(permission) ? currentBranch : currentCompany;
        return !!source && (user.is_superuser || source.permissions.includes(permission));
      }),
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
