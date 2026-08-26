"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  clearCsrfToken,
  clearSupportSessionId,
  getCsrfToken,
  http,
  primeSupportSessionId,
  setSupportSessionId,
} from "@/lib/http";
import {
  firstAuthorizedRoute,
  isOperatingPermission,
} from "@/lib/authorized-routes";
import { permissions } from "@/lib/permissions";
import type {
  SupportSessionContext,
  BranchFeature,
  BranchFeatureState,
  User,
  UserBranch,
  UserCompany,
} from "@/types";

const COMPANY_KEY = "pdv.current_company_id";
const BRANCH_KEY = "pdv.current_branch_id";
const PUBLIC_PATHS = ["/", "/ajuda", "/planos", "/cadastro"];
const SUPPORT_FRAGMENT = /^#support-session=(\d+)$/;

function isPublicPath(pathname: string) {
  return PUBLIC_PATHS.some(
    (path) =>
      pathname === path || (path !== "/" && pathname.startsWith(`${path}/`)),
  );
}
interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  supportSession: SupportSessionContext | null;
  endSupportSession: () => Promise<void>;
  availableCompanies: UserCompany[];
  currentCompany: UserCompany | null;
  setCurrentCompanyId: (id: number) => void;
  currentBranch: UserBranch | null;
  setCurrentBranchId: (id: number) => void;
  hasPermission: (permission: string) => boolean;
  hasAnyPermission: (permissions: readonly string[]) => boolean;
  hasFeature: (feature: BranchFeature) => boolean;
  featureState: (feature: BranchFeature) => BranchFeatureState | null;
}

const AuthContext = createContext<AuthContextValue | null>(null);
function isReadPermission(permission: string) {
  return permission.includes(".view") || permission.endsWith(".report.view");
}
function companyFromSupportSession(
  session: SupportSessionContext,
  permissionScopes: User["permission_scopes"],
): UserCompany {
  const supportCompanyPermissions = Object.values(permissions).filter(
    (permission) => !isOperatingPermission(permission, permissionScopes),
  );
  return {
    id: session.company,
    trade_name: session.company_name?.trim() || `Empresa ${session.company}`,
    status: "active",
    is_owner: false,
    effective_status: "ACTIVE",
    can_operate: true,
    access_profile: { id: null, name: "Sessão de suporte" },
    permissions:
      session.mode === "READ_ONLY"
        ? supportCompanyPermissions.filter(isReadPermission)
        : supportCompanyPermissions,
  };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [companyId, setCompanyId] = useState<number | null>(null);
  const [branchId, setBranchId] = useState<number | null>(null);
  const [supportSession, setSupportSession] =
    useState<SupportSessionContext | null>(null);
  const pathname = usePathname();
  const router = useRouter();
  const permanentCompanies = user?.companies ?? [];
  const supportTargetCompany = supportSession
    ? (permanentCompanies.find(
        (company) => company.id === supportSession.company,
      ) ??
      (!supportSession.impersonated_user
        ? companyFromSupportSession(supportSession, user?.permission_scopes ?? {})
        : null))
    : null;
  const availableCompanies = supportSession
    ? supportTargetCompany
      ? [supportTargetCompany]
      : []
    : permanentCompanies;
  const currentCompany =
    availableCompanies.find((company) => company.id === companyId) ??
    availableCompanies[0] ??
    null;
  const companyBranches =
    user?.branches
      .filter((branch) => branch.company_id === currentCompany?.id)
      .map((branch) =>
        supportSession?.mode === "READ_ONLY"
          ? {
              ...branch,
              permissions: branch.permissions.filter(isReadPermission),
            }
          : branch,
      ) ?? [];
  const activeCompanyBranches =
    currentCompany?.status === "active"
      ? companyBranches.filter((branch) => branch.status === "active")
      : [];
  const currentBranch =
    activeCompanyBranches.find((branch) => branch.id === branchId) ??
    activeCompanyBranches[0] ??
    null;

  function applyUser(current: User | null) {
    setUser(current);
    if (!current) {
      setSupportSession(null);
      return;
    }
    const supportSessionData = current.support_session ?? null;
    if (Object.prototype.hasOwnProperty.call(current, "support_session")) {
      setSupportSession(supportSessionData);
      if (supportSessionData?.id) setSupportSessionId(supportSessionData.id);
      else clearSupportSessionId();
    }
    const stored = Number(sessionStorage.getItem(COMPANY_KEY));
    const selected =
      current.companies.find(
        (company) => company.id === supportSessionData?.company,
      ) ??
      current.companies.find((company) => company.id === stored) ??
      current.companies[0];
    const selectedCompanyId =
      supportSessionData?.company ?? selected?.id ?? null;
    setCompanyId(selectedCompanyId);
    if (selectedCompanyId)
      sessionStorage.setItem(COMPANY_KEY, String(selectedCompanyId));
    const storedBranch = Number(sessionStorage.getItem(BRANCH_KEY));
    const selectedBranch =
      (selected?.status ?? "active") === "active" && selectedCompanyId
        ? (current.branches.find(
            (branch) =>
              branch.id === storedBranch &&
              branch.company_id === selectedCompanyId &&
              branch.status === "active",
          ) ??
          current.branches.find(
            (branch) =>
              branch.company_id === selectedCompanyId &&
              branch.status === "active",
          ))
        : undefined;
    setBranchId(selectedBranch?.id ?? null);
    if (selectedBranch)
      sessionStorage.setItem(BRANCH_KEY, String(selectedBranch.id));
    else sessionStorage.removeItem(BRANCH_KEY);
  }

  async function refreshUser() {
    const current = await http.get<User>("auth/me/");
    applyUser(current);
  }

  useEffect(() => {
    let active = true;
    const fragmentMatch = window.location.hash.startsWith("#support-session=")
      ? window.location.hash.match(SUPPORT_FRAGMENT)
      : null;
    const fragmentId = fragmentMatch ? Number(fragmentMatch[1]) : 0;
    const supportFragment =
      Number.isSafeInteger(fragmentId) && fragmentId > 0 ? fragmentMatch : null;
    if (window.location.hash.startsWith("#support-session=")) {
      window.history.replaceState(
        window.history.state,
        "",
        `${window.location.pathname}${window.location.search}`,
      );
      if (supportFragment) primeSupportSessionId(supportFragment[1]);
      else clearSupportSessionId();
    }
    http
      .get<User>("auth/me/")
      .then((current) => active && applyUser(current))
      .catch(() => {
        if (supportFragment) clearSupportSessionId();
        if (active) applyUser(null);
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const handleUnauthorized = () => applyUser(null);
    const handleInvalidSupport = () => {
      clearSupportSessionId();
      applyUser(null);
      router.replace("/");
    };
    window.addEventListener("auth:unauthorized", handleUnauthorized);
    window.addEventListener("support:invalid", handleInvalidSupport);
    return () => {
      window.removeEventListener("auth:unauthorized", handleUnauthorized);
      window.removeEventListener("support:invalid", handleInvalidSupport);
    };
  }, [router]);

  useEffect(() => {
    if (loading) return;
    if (!user && pathname !== "/login" && !isPublicPath(pathname))
      router.replace("/login");
    if (user && pathname === "/login") {
      router.replace(firstAuthorizedRoute(user, currentCompany, currentBranch));
    }
  }, [loading, pathname, router, user, currentCompany, currentBranch]);

  async function login(email: string, password: string) {
    await getCsrfToken(true);
    const authenticated = await http.post<User>("auth/login/", {
      email,
      password,
    });
    applyUser(authenticated);
    return authenticated;
  }

  async function logout() {
    await http.logout();
    clearCsrfToken();
    clearSupportSessionId();
    setUser(null);
    setCompanyId(null);
    setBranchId(null);
    sessionStorage.removeItem(COMPANY_KEY);
    sessionStorage.removeItem(BRANCH_KEY);
    router.replace("/login");
  }

  async function endSupportSession() {
    if (!supportSession) return;
    const ended = await http.postWithoutSupport<SupportSessionContext>(
      `platform/support-sessions/${supportSession.id}/end/`,
    );
    if (ended.id !== supportSession.id || !ended.ended_at) {
      throw new Error(
        "O servidor não confirmou o encerramento da sessão de suporte.",
      );
    }
    clearSupportSessionId();
    setSupportSession(null);
    setUser(null);
    setCompanyId(null);
    setBranchId(null);
    sessionStorage.removeItem(COMPANY_KEY);
    sessionStorage.removeItem(BRANCH_KEY);
    router.replace("/");
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login,
        logout,
        refreshUser,
        supportSession,
        endSupportSession,
        availableCompanies,
        currentCompany,
        currentBranch,
        setCurrentCompanyId: (id) => {
          if (!availableCompanies.some((company) => company.id === id)) return;
          setCompanyId(id);
          sessionStorage.setItem(COMPANY_KEY, String(id));
          const selectedCompany = availableCompanies.find(
            (company) => company.id === id,
          );
          const nextBranch =
            selectedCompany?.status === "active"
              ? user?.branches.find(
                  (branch) =>
                    branch.company_id === id && branch.status === "active",
                )
              : undefined;
          setBranchId(nextBranch?.id ?? null);
          if (nextBranch)
            sessionStorage.setItem(BRANCH_KEY, String(nextBranch.id));
          else sessionStorage.removeItem(BRANCH_KEY);
        },
        setCurrentBranchId: (id) => {
          if (!activeCompanyBranches.some((branch) => branch.id === id)) return;
          setBranchId(id);
          sessionStorage.setItem(BRANCH_KEY, String(id));
        },
        hasPermission: (permission) => {
          if (!user) return false;
          if (
            supportSession?.mode === "READ_ONLY" &&
            !isReadPermission(permission)
          )
            return false;
          const operating = isOperatingPermission(permission, user.permission_scopes);
          const source = operating ? currentBranch : currentCompany;
          return (
            !!source &&
            (user.is_superuser || source.permissions.includes(permission))
          );
        },
        hasAnyPermission: (required) =>
          !!user &&
          required.some((permission) => {
            if (
              supportSession?.mode === "READ_ONLY" &&
              !isReadPermission(permission)
            )
              return false;
            const source = isOperatingPermission(permission, user.permission_scopes)
              ? currentBranch
              : currentCompany;
            return (
              !!source &&
              (user.is_superuser || source.permissions.includes(permission))
            );
          }),
        hasFeature: (feature) => Boolean(currentBranch?.features?.[feature]?.enabled),
        featureState: (feature) => currentBranch?.features?.[feature] ?? null,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
