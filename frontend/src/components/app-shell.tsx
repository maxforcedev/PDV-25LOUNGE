"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  BadgePercent,
  Banknote,
  BarChart3,
  Boxes,
  Building2,
  ChevronDown,
  ClipboardList,
  CreditCard,
  FileSearch,
  GitBranch,
  LayoutDashboard,
  LogOut,
  Maximize2,
  Menu,
  Minimize2,
  Moon,
  Package,
  PanelLeftClose,
  PanelLeftOpen,
  ReceiptText,
  ShieldCheck,
  ShieldX,
  ShoppingCart,
  Sun,
  Tags,
  UserRound,
  Users,
  X,
} from "lucide-react";
import { useAuth } from "@/providers/auth-provider";
import { initials } from "@/lib/format";
import { permissions } from "@/lib/permissions";
import { Alert, Spinner } from "@/components/ui";

const mainNavigation = [
  { href: "/dashboard", label: "Visão geral", icon: LayoutDashboard },
  { href: "/sobre-mim", label: "Sobre mim", icon: UserRound },
];

const adminNavigation = [
  {
    href: "/empresas",
    label: "Empresas",
    icon: Building2,
    requiredPermissions: [permissions.viewCompany, permissions.changeCompany],
  },
  {
    href: "/filiais",
    label: "Filiais",
    icon: GitBranch,
    requiredPermissions: [
      permissions.viewBranch,
      permissions.addBranch,
      permissions.changeBranch,
    ],
  },
  {
    href: "/perfis",
    label: "Perfis de acesso",
    icon: ShieldCheck,
    requiredPermissions: [permissions.viewAccessProfile],
  },
  {
    href: "/usuarios",
    label: "Usuários",
    icon: Users,
    requiredPermissions: [permissions.viewUser],
  },
  {
    href: "/usuarios/bloqueios",
    label: "Bloqueios de acesso",
    icon: ShieldX,
    requiredPermissions: [permissions.viewPermissionBlock],
  },
  {
    href: "/categorias",
    label: "Categorias",
    icon: Tags,
    requiredPermissions: [permissions.viewCategory],
  },
  {
    href: "/produtos",
    label: "Produtos",
    icon: Package,
    requiredPermissions: [permissions.viewProduct],
  },
  {
    href: "/estoque",
    label: "Estoque",
    icon: Boxes,
    requiredPermissions: [permissions.viewInventory],
  },
  {
    href: "/estoque/movimentacoes",
    label: "Movimentações",
    icon: LayoutDashboard,
    requiredPermissions: [permissions.viewInventoryHistory],
  },
  {
    href: "/caixas",
    label: "Operação de caixa",
    icon: Banknote,
    requiredPermissions: [permissions.viewCashRegister],
  },
  {
    href: "/pdv",
    label: "PDV",
    icon: ShoppingCart,
    requiredPermissions: [
      permissions.createSale,
      permissions.createConsumption,
    ],
  },
  {
    href: "/vendas",
    label: "Vendas",
    icon: ReceiptText,
    requiredPermissions: [permissions.viewSale],
  },
  {
    href: "/consumacoes",
    label: "Consumações",
    icon: ClipboardList,
    requiredPermissions: [permissions.viewConsumption],
  },
  {
    href: "/formas-de-pagamento",
    label: "Formas de pagamento",
    icon: CreditCard,
    requiredPermissions: [permissions.viewPaymentMethod],
  },
  {
    href: "/promocoes",
    label: "Promoções",
    icon: BadgePercent,
    requiredPermissions: [
      permissions.viewPromotion,
      permissions.changePromotion,
    ],
  },
  {
    href: "/relatorios",
    label: "Relatórios",
    icon: BarChart3,
    requiredPermissions: [
      permissions.viewSalesReport,
      permissions.viewConsumptionsReport,
      permissions.viewCashReport,
      permissions.viewWithdrawalsReport,
      permissions.viewInventoryReport,
      permissions.viewOperationalResult,
      permissions.viewStockConsumptionReport,
    ],
  },
  {
    href: "/auditoria",
    label: "Auditoria",
    icon: FileSearch,
    requiredPermissions: [permissions.viewAuditLog],
  },
];

function Sidebar({ onNavigate, collapsed = false }: { onNavigate?: () => void; collapsed?: boolean }) {
  const pathname = usePathname();
  const { hasAnyPermission } = useAuth();
  const navigation = [
    ...mainNavigation,
    ...adminNavigation.filter((item) =>
      hasAnyPermission(item.requiredPermissions),
    ),
  ];
  const activeHref = navigation
    .filter(
      ({ href }) =>
        pathname === href ||
        (href !== "/dashboard" && pathname.startsWith(`${href}/`)),
    )
    .sort((left, right) => right.href.length - left.href.length)[0]?.href;
  return (
    <div className="flex h-full flex-col bg-dark text-white">
      <div className={`flex h-18 items-center gap-3 border-b border-white/8 ${collapsed ? "justify-center px-2" : "px-6"}`}>
        <div className="flex size-9 items-center justify-center rounded-lg bg-primary text-white shadow-lg shadow-primary/20">
          <ShieldCheck className="size-5" />
        </div>
        {!collapsed && <div>
          <strong className="block text-sm tracking-wide">Core PDV</strong>
          <span className="text-[10px] uppercase tracking-[0.18em] text-slate-400">
            Administração
          </span>
        </div>}
      </div>
      <nav className="flex-1 overflow-y-auto px-3 py-6" aria-label="Menu principal">
        {!collapsed && <p className="mb-2 px-3 text-[10px] font-bold uppercase tracking-[0.16em] text-slate-500">
          Gestão
        </p>}
        <div className="space-y-1">
          {navigation.map(({ href, label, icon: Icon }) => {
            const active = activeHref === href;
            return (
              <Link
                key={href}
                href={href}
                onClick={onNavigate}
                title={collapsed ? label : undefined}
                aria-label={collapsed ? label : undefined}
                className={`flex items-center rounded-md py-2.5 text-[13px] font-medium transition ${collapsed ? "justify-center px-2" : "gap-3 px-3"} ${active ? "bg-primary text-white shadow-md shadow-black/10" : "text-slate-300 hover:bg-white/6 hover:text-white"}`}
              >
                <Icon className="size-[17px] shrink-0" />
                {!collapsed && <span>{label}</span>}
              </Link>
            );
          })}
        </div>
      </nav>
      {!collapsed && <div className="border-t border-white/8 px-6 py-4 text-[10px] text-slate-500">
        Ambiente administrativo
      </div>}
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const {
    user,
    logout,
    currentCompany,
    currentBranch,
    setCurrentCompanyId,
    setCurrentBranchId,
  } = useAuth();
  const [drawer, setDrawer] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState("");
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [collapsed, setCollapsed] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [fullscreenSupported, setFullscreenSupported] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const pathname = usePathname();
  useEffect(() => setDrawer(false), [pathname]);
  useEffect(() => {
    setTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light");
    setCollapsed(localStorage.getItem("pdv.sidebar_collapsed") === "true");
    setFullscreenSupported(Boolean(document.fullscreenEnabled));
    const updateFullscreen = () => setFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", updateFullscreen);
    return () => document.removeEventListener("fullscreenchange", updateFullscreen);
  }, []);
  useEffect(() => {
    if (!drawer) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDrawer(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", closeOnEscape);
      menuButtonRef.current?.focus();
    };
  }, [drawer]);

  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("pdv.theme", next);
    setTheme(next);
  }

  function toggleSidebar() {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem("pdv.sidebar_collapsed", String(next));
  }

  async function toggleFullscreen() {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen();
    } catch {
      setFullscreenSupported(false);
    }
  }

  async function handleLogout() {
    setLoggingOut(true);
    setLogoutError("");
    try {
      await logout();
    } catch (caught) {
      setLogoutError(
        caught instanceof Error
          ? caught.message
          : "Não foi possível encerrar a sessão.",
      );
      setLoggingOut(false);
      setProfileOpen(false);
    }
  }

  return (
    <div className={`min-h-screen bg-canvas transition-[padding] duration-200 ${collapsed ? "lg:pl-20" : "lg:pl-65"}`}>
      <aside className={`fixed inset-y-0 left-0 z-40 hidden transition-[width] duration-200 lg:block ${collapsed ? "w-20" : "w-65"}`}>
        <Sidebar collapsed={collapsed} />
      </aside>
      {drawer && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            className="absolute inset-0 bg-slate-950/45"
            aria-label="Fechar menu"
            onClick={() => setDrawer(false)}
          />
          <aside className="absolute inset-y-0 left-0 w-[82vw] max-w-72 shadow-2xl">
            <Sidebar onNavigate={() => setDrawer(false)} />
            <button
              className="absolute right-3 top-4 icon-button text-slate-300 hover:bg-white/10 hover:text-white"
              onClick={() => setDrawer(false)}
              aria-label="Fechar menu"
            >
              <X className="size-5" />
            </button>
          </aside>
        </div>
      )}
      <header className="sticky top-0 z-30 flex min-h-18 items-center border-b border-slate-200 bg-white/95 px-4 py-2 backdrop-blur sm:px-6 lg:px-8">
        <button
          ref={menuButtonRef}
          className="icon-button mr-2 lg:hidden"
          onClick={() => setDrawer(true)}
          aria-label="Abrir menu"
        >
          <Menu className="size-5" />
        </button>
        <button className="icon-button mr-3 hidden lg:inline-flex" onClick={toggleSidebar} title={collapsed ? "Expandir menu lateral" : "Recolher menu lateral"} aria-label={collapsed ? "Expandir menu lateral" : "Recolher menu lateral"}>
          {collapsed ? <PanelLeftOpen className="size-5" /> : <PanelLeftClose className="size-5" />}
        </button>
        <div className="hidden sm:block">
          <p className="text-xs font-semibold text-dark">
            Painel administrativo
          </p>
          <p className="mt-0.5 text-[11px] text-slate-400">
            Operação e acessos em um só lugar
          </p>
        </div>
        <div className="ml-auto mr-2 grid min-w-0 max-w-[55vw] gap-1 sm:w-72 sm:max-w-none sm:grid-cols-2">
          <label className="sr-only" htmlFor="current-company">
            Empresa atual
          </label>
          <select
            id="current-company"
            className="input h-9 truncate text-xs font-semibold"
            value={currentCompany?.id || ""}
            onChange={(event) =>
              setCurrentCompanyId(Number(event.target.value))
            }
            disabled={!user?.companies.length}
          >
            {!user?.companies.length && (
              <option value="">Sem empresa vinculada</option>
            )}
            {user?.companies.map((company) => (
              <option key={company.id} value={company.id}>
                {company.trade_name}
                {company.status === "inactive" ? " (inativa)" : ""}
              </option>
            ))}
          </select>
          <label className="sr-only" htmlFor="current-branch">
            Filial atual
          </label>
          <select
            id="current-branch"
            className="input h-9 truncate text-xs font-semibold"
            value={currentBranch?.id || ""}
            onChange={(event) => setCurrentBranchId(Number(event.target.value))}
            disabled={
              currentCompany?.status !== "active" ||
              !user?.branches.some(
                (branch) =>
                  branch.company_id === currentCompany?.id &&
                  branch.status === "active",
              )
            }
          >
            {!currentBranch && <option value="">Sem filial ativa</option>}
            {user?.branches
              .filter((branch) => branch.company_id === currentCompany?.id)
              .map((branch) => (
                <option
                  key={branch.id}
                  value={branch.id}
                  disabled={branch.status === "inactive"}
                >
                  {branch.name}
                  {branch.status === "inactive" ? " (inativa)" : ""}
                </option>
              ))}
          </select>
        </div>
        <button className="icon-button mr-1" onClick={toggleTheme} title={theme === "dark" ? "Usar tema claro" : "Usar tema escuro"} aria-label={theme === "dark" ? "Usar tema claro" : "Usar tema escuro"}>
          {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
        </button>
        {fullscreenSupported && <button className="icon-button mr-1 hidden sm:inline-flex" onClick={() => void toggleFullscreen()} title={fullscreen ? "Sair da tela cheia" : "Usar tela cheia"} aria-label={fullscreen ? "Sair da tela cheia" : "Usar tela cheia"}>
          {fullscreen ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
        </button>}
        <div className="relative">
          <button
            onClick={() => setProfileOpen((value) => !value)}
            className="flex items-center gap-2.5 rounded-md p-1.5 text-left transition hover:bg-slate-50"
            aria-expanded={profileOpen}
          >
            <span className="flex size-9 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary">
              {initials(user?.first_name || "", user?.last_name || "")}
            </span>
            <span className="hidden max-w-40 sm:block">
              <strong className="block truncate text-xs text-dark">
                {user?.first_name || "Usuário"} {user?.last_name || ""}
              </strong>
              <span className="block truncate text-[10px] text-slate-400">
                {user?.email}
              </span>
            </span>
            <ChevronDown className="hidden size-3.5 text-slate-400 sm:block" />
          </button>
          {profileOpen && (
            <div className="absolute right-0 mt-2 w-56 rounded-lg border border-slate-200 bg-white p-2 shadow-xl">
              <div className="border-b border-slate-100 px-2 py-2 sm:hidden">
                <p className="truncate text-xs font-semibold">{user?.email}</p>
              </div>
              <Link
                href="/sobre-mim"
                onClick={() => setProfileOpen(false)}
                className="flex w-full items-center gap-2 rounded-md px-3 py-2.5 text-xs font-medium text-slate-600 hover:bg-slate-50 hover:text-dark"
              >
                <UserRound className="size-4" />
                Sobre mim
              </Link>
              <button
                onClick={handleLogout}
                disabled={loggingOut}
                className="flex w-full items-center gap-2 rounded-md px-3 py-2.5 text-left text-xs font-medium text-danger hover:bg-danger/5 disabled:opacity-50"
              >
                {loggingOut ? <Spinner /> : <LogOut className="size-4" />}Sair
                da sessão
              </button>
            </div>
          )}
        </div>
      </header>
      {logoutError && (
        <div className="px-4 pt-4 sm:px-6 lg:px-8">
          <Alert message={logoutError} />
        </div>
      )}
      <main>{children}</main>
    </div>
  );
}
