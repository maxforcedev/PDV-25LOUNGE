"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  BadgePercent,
  Banknote,
  BarChart3,
  Boxes,
  ChevronDown,
  ClipboardList,
  CircleHelp,
  CreditCard,
  GitBranch,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Maximize2,
  Menu,
  Minimize2,
  Moon,
  Package,
  MonitorSmartphone,
  PanelLeftClose,
  PanelLeftOpen,
  ShieldCheck,
  ShoppingCart,
  Sun,
  Tags,
  Layers,
  LayoutGrid,
  Truck,
  ContactRound,
  WalletCards,
  UserRound,
  Users,
  X,
} from "lucide-react";
import { useAuth } from "@/providers/auth-provider";
import { permissions, reportMenuPermissions } from "@/lib/permissions";
import { release } from "@/lib/release";
import { Alert, Spinner } from "@/components/ui";
import { useBranding } from "@/providers/branding-provider";
import { BrandWordmark } from "@/components/marketing/brand-wordmark";
import { UserAvatar } from "@/components/user-avatar";
import type { BranchFeature, FeaturePermissionAlternative } from "@/types";

type NavItem = { href: string; label: string; icon: typeof LayoutDashboard; requiredPermissions: readonly string[]; requiredFeatures?: readonly BranchFeature[]; anyFeature?: boolean; alternatives?: readonly FeaturePermissionAlternative[] };

const mainNavigation: NavItem[] = [
  {
    href: "/dashboard",
    label: "Visão geral",
    icon: LayoutDashboard,
    requiredPermissions: [permissions.viewDashboard],
  },
];

const operationNavigation: NavItem[] = [
  { href: "/pdv", label: "PDV", icon: ShoppingCart, requiredPermissions: [], alternatives: [{ permission: permissions.createSale, features: ["counter", "cash_register"] }, { permission: permissions.createConsumption, features: ["consumption"] }] },
  { href: "/mesas", label: "Mesas", icon: LayoutGrid, requiredPermissions: [permissions.viewCommands], requiredFeatures: ["tables"] },
  { href: "/comandas", label: "Comandas", icon: ClipboardList, requiredPermissions: [permissions.viewCommands], requiredFeatures: ["commands"] },
  { href: "/caixas", label: "Caixa", icon: Banknote, requiredPermissions: [permissions.viewCashRegister], requiredFeatures: ["cash_register"] },
];

const productionNavigation: NavItem[] = [];

const cadastrosNavigation: NavItem[] = [
  { href: "/produtos", label: "Produtos", icon: Package, requiredPermissions: [permissions.viewProduct] },
  { href: "/categorias", label: "Categorias", icon: Tags, requiredPermissions: [permissions.viewCategory] },
  { href: "/modificadores", label: "Modificadores", icon: Layers, requiredPermissions: [permissions.viewModifiers] },
  { href: "/fornecedores", label: "Fornecedores", icon: Truck, requiredPermissions: [permissions.viewSupplier] },
  { href: "/clientes", label: "Clientes", icon: ContactRound, requiredPermissions: [permissions.viewCustomer] },
  { href: "/formas-de-pagamento", label: "Formas de pagamento", icon: CreditCard, requiredPermissions: [permissions.viewPaymentMethod] },
  { href: "/promocoes", label: "Promoções", icon: BadgePercent, requiredPermissions: [permissions.viewPromotion, permissions.changePromotion] },
];

const suprimentosNavigation: NavItem[] = [
  { href: "/compras", label: "Compras", icon: ClipboardList, requiredPermissions: [permissions.viewPurchase] },
  { href: "/contas-a-pagar", label: "Contas a pagar", icon: WalletCards, requiredPermissions: [permissions.managePurchasePayables] },
  { href: "/estoque", label: "Estoque", icon: Boxes, requiredPermissions: [permissions.viewInventory] },
];

const gestaoNavigation: NavItem[] = [
  { href: "/usuarios", label: "Usuários", icon: Users, requiredPermissions: [permissions.viewUser] },
  { href: "/perfis", label: "Perfis de acesso", icon: ShieldCheck, requiredPermissions: [permissions.viewAccessProfile] },
  { href: "/filiais", label: "Meu negócio", icon: GitBranch, requiredPermissions: [permissions.viewBranch, permissions.addBranch, permissions.changeBranch] },
  { href: "/pos-dispositivos", label: "Dispositivos POS", icon: MonitorSmartphone, requiredPermissions: [permissions.viewPosDevices, permissions.managePosDevices] },
];

const relatoriosNavigation: NavItem[] = [
  { href: "/relatorios", label: "Relatórios", icon: BarChart3, requiredPermissions: reportMenuPermissions },
];

type NavSection = { title: string; items: NavItem[] };

const navSections: NavSection[] = [
  { title: "Operação", items: operationNavigation },
  { title: "Produção", items: productionNavigation },
  { title: "Cadastros", items: cadastrosNavigation },
  { title: "Suprimentos", items: suprimentosNavigation },
  { title: "Gestão", items: gestaoNavigation },
  { title: "Relatórios", items: relatoriosNavigation },
];

const adminNavigation: NavItem[] = [
  ...operationNavigation,
  ...productionNavigation,
  ...cadastrosNavigation,
  ...suprimentosNavigation,
  ...gestaoNavigation,
  ...relatoriosNavigation,
];

function Sidebar({
  onNavigate,
  collapsed = false,
}: {
  onNavigate?: () => void;
  collapsed?: boolean;
}) {
  const pathname = usePathname();
  const { hasAnyPermission, hasFeature, hasPermission, currentCompany } = useAuth();
  const restrictedOwner = Boolean(currentCompany?.is_owner && !currentCompany.can_operate);
  const navigation = restrictedOwner ? [{
    href: "/assinatura",
    label: "Assinatura",
    icon: CreditCard,
    requiredPermissions: [],
  }] : [
    ...mainNavigation.filter(
      (item) =>
        !item.requiredPermissions.length ||
        hasAnyPermission(item.requiredPermissions),
    ),
    ...(currentCompany?.is_owner ? [{
      href: "/assinatura",
      label: "Assinatura",
      icon: CreditCard,
      requiredPermissions: [],
    }] : []),
    ...adminNavigation.filter((item) => {
      const featuresAllowed = !item.requiredFeatures || (
        item.anyFeature
          ? item.requiredFeatures.some(hasFeature)
          : item.requiredFeatures.every(hasFeature)
      );
      const alternativesAllowed = item.alternatives?.some(({ permission, features }) =>
        hasPermission(permission) && features.every(hasFeature)
      );
      return item.alternatives
        ? alternativesAllowed
        : featuresAllowed && hasAnyPermission(item.requiredPermissions);
    }),
  ];
  const activeHref = navigation
    .filter(
      ({ href }) =>
        pathname === href ||
        (href !== "/dashboard" && pathname.startsWith(`${href}/`)),
    )
    .sort((left, right) => right.href.length - left.href.length)[0]?.href;
  return (
    <div className="flex h-full flex-col bg-operational-canvas text-operational-fg">
      <div
        className={`flex h-18 items-center gap-3 border-b border-white/8 ${collapsed ? "justify-center px-2" : "px-6"}`}
      >
        <BrandWordmark href="/dashboard" compact={collapsed} dark className="text-operational-fg" imageClassName={collapsed ? "h-9 max-w-10" : "h-14 !w-72 max-w-full"} />
      </div>
      <nav
        className="flex-1 overflow-y-auto px-3 py-6"
        aria-label="Menu principal"
      >
        {!collapsed && (
          <p className="mb-2 px-3 text-[10px] font-bold uppercase tracking-[0.16em] text-operational-muted">
            Principal
          </p>
        )}
        <div className="space-y-1">
          {navigation.filter(item => !navSections.some(s => s.items.includes(item))).map(({ href, label, icon: Icon }) => {
            const active = activeHref === href;
            return (
              <Link
                key={href}
                href={href}
                onClick={onNavigate}
                title={collapsed ? label : undefined}
                aria-label={collapsed ? label : undefined}
                className={`flex items-center rounded-md py-2.5 text-[13px] font-medium transition focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus ${collapsed ? "justify-center px-2" : "gap-3 px-3"} ${active ? "bg-primary text-white shadow-md shadow-black/10" : "text-operational-muted hover:bg-white/6 hover:text-operational-fg"}`}
              >
                <Icon className="size-[17px] shrink-0" />
                {!collapsed && <span>{label}</span>}
              </Link>
            );
          })}
        </div>
        {navSections.map((section) => {
          const sectionItems = navigation.filter(item => section.items.includes(item));
          if (!sectionItems.length) return null;
          return (
            <div key={section.title} className="mt-6">
              {!collapsed && (
                <p className="mb-2 px-3 text-[10px] font-bold uppercase tracking-[0.16em] text-operational-muted">
                  {section.title}
                </p>
              )}
              <div className="space-y-1">
                {sectionItems.map(({ href, label, icon: Icon }) => {
                  const active = activeHref === href;
                  return (
                    <Link
                      key={href}
                      href={href}
                      onClick={onNavigate}
                      title={collapsed ? label : undefined}
                      aria-label={collapsed ? label : undefined}
                      className={`flex items-center rounded-md py-2.5 text-[13px] font-medium transition focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus ${collapsed ? "justify-center px-2" : "gap-3 px-3"} ${active ? "bg-primary text-white shadow-md shadow-black/10" : "text-operational-muted hover:bg-white/6 hover:text-operational-fg"}`}
                    >
                      <Icon className="size-[17px] shrink-0" />
                      {!collapsed && <span>{label}</span>}
                    </Link>
                  );
                })}
              </div>
            </div>
          );
        })}
      </nav>
      {!collapsed && (
        <div className="border-t border-white/8 px-6 py-4 text-[10px] text-operational-muted">
          <p className="font-semibold text-operational-fg">CORE PDV v{release.version}</p>
          <p className="mt-1" title={`Commit ${release.commit}`}>
            build {release.shortCommit} · {release.environment}
          </p>
          <p className="mt-0.5 truncate" title={release.buildDate}>{release.buildDate}</p>
        </div>
      )}
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const {
    user,
    logout,
    currentCompany,
    currentBranch,
    availableCompanies,
    setCurrentCompanyId,
    setCurrentBranchId,
    supportSession,
    endSupportSession,
  } = useAuth();
  const branding = useBranding();
  const [drawer, setDrawer] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState("");
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [collapsed, setCollapsed] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [fullscreenSupported, setFullscreenSupported] = useState(false);
  const [endingSupport, setEndingSupport] = useState(false);
  const [supportError, setSupportError] = useState("");
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const pathname = usePathname();
  useEffect(() => setDrawer(false), [pathname]);
  useEffect(() => {
    setTheme(
      document.documentElement.dataset.theme === "dark" ? "dark" : "light",
    );
    setCollapsed(localStorage.getItem("pdv.sidebar_collapsed") === "true");
    setFullscreenSupported(Boolean(document.fullscreenEnabled));
    const updateFullscreen = () =>
      setFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", updateFullscreen);
    return () =>
      document.removeEventListener("fullscreenchange", updateFullscreen);
  }, []);
  useEffect(() => {
    if (!drawer) return;
    const previous = document.body.style.overflow;
    const menuButton = menuButtonRef.current;
    document.body.style.overflow = "hidden";
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDrawer(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", closeOnEscape);
      menuButton?.focus();
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

  async function handleEndSupport() {
    setEndingSupport(true);
    setSupportError("");
    try {
      await endSupportSession();
    } catch (caught) {
      setSupportError(caught instanceof Error ? caught.message : "Não foi possível encerrar a sessão de suporte.");
      setEndingSupport(false);
    }
  }

  return (
    <div
      className={`min-h-screen bg-canvas transition-[padding] duration-200 ${collapsed ? "lg:pl-20" : "lg:pl-65"}`}
    >
      <aside
        className={`fixed inset-y-0 left-0 z-40 hidden transition-[width] duration-200 lg:block ${collapsed ? "w-20" : "w-65"}`}
      >
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
              className="absolute right-3 top-4 icon-button text-operational-muted hover:bg-white/10 hover:text-operational-fg"
              onClick={() => setDrawer(false)}
              aria-label="Fechar menu"
            >
              <X className="size-5" />
            </button>
          </aside>
        </div>
      )}
      <div className="sticky top-0 z-30">
      {supportSession && (
        <div role="status" className="border-b border-warning/35 bg-warning-surface px-4 py-2.5 text-warning-strong sm:px-6 lg:px-8">
          <div className="mx-auto flex max-w-[1600px] flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 text-xs">
              <strong className="font-extrabold">Sessão de suporte ativa · {supportSession.mode === "READ_ONLY" ? "somente leitura" : "leitura e escrita"}</strong>
              <span className="ml-2 block text-[11px] sm:inline">{supportSession.actor_email || "Equipe de suporte"} em {supportSession.company_name || currentCompany?.trade_name || `empresa ${supportSession.company}`}</span>
              {supportError && <span className="mt-1 block font-semibold text-danger-strong" role="alert">{supportError}</span>}
            </div>
            <button type="button" className="btn h-8 shrink-0 border border-warning/40 bg-surface px-3 text-[11px] text-warning-strong hover:bg-warning-surface" onClick={() => void handleEndSupport()} disabled={endingSupport}>
              {endingSupport && <Spinner />} Encerrar sessão
            </button>
          </div>
        </div>
      )}
      <header className="flex min-h-18 items-center border-b border-subtle bg-surface/95 px-4 py-2 backdrop-blur sm:px-6 lg:px-8">
        <button
          ref={menuButtonRef}
          className="icon-button mr-2 lg:hidden"
          onClick={() => setDrawer(true)}
          aria-label="Abrir menu"
        >
          <Menu className="size-5" />
        </button>
        <button
          className="icon-button mr-3 hidden lg:inline-flex"
          onClick={toggleSidebar}
          title={collapsed ? "Expandir menu lateral" : "Recolher menu lateral"}
          aria-label={
            collapsed ? "Expandir menu lateral" : "Recolher menu lateral"
          }
        >
          {collapsed ? (
            <PanelLeftOpen className="size-5" />
          ) : (
            <PanelLeftClose className="size-5" />
          )}
        </button>
        <div className="hidden sm:block">
          <p className="text-xs font-semibold text-fg">Painel {branding.platform_name}</p>
          <p className="mt-0.5 text-[11px] text-muted">
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
            disabled={!availableCompanies.length || !!supportSession}
          >
            {!availableCompanies.length && (
              <option value="">Sem empresa vinculada</option>
            )}
            {availableCompanies.map((company) => (
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
        <button
          className="icon-button mr-1"
          onClick={toggleTheme}
          title={theme === "dark" ? "Usar tema claro" : "Usar tema escuro"}
          aria-label={theme === "dark" ? "Usar tema claro" : "Usar tema escuro"}
        >
          {theme === "dark" ? (
            <Sun className="size-4" />
          ) : (
            <Moon className="size-4" />
          )}
        </button>
        {fullscreenSupported && (
          <button
            className="icon-button mr-1 hidden sm:inline-flex"
            onClick={() => void toggleFullscreen()}
            title={fullscreen ? "Sair da tela cheia" : "Usar tela cheia"}
            aria-label={fullscreen ? "Sair da tela cheia" : "Usar tela cheia"}
          >
            {fullscreen ? (
              <Minimize2 className="size-4" />
            ) : (
              <Maximize2 className="size-4" />
            )}
          </button>
        )}
        <div className="relative">
          <button
            onClick={() => setProfileOpen((value) => !value)}
            className="flex items-center gap-2.5 rounded-md p-1.5 text-left transition hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/20"
            aria-expanded={profileOpen}
          >
            <UserAvatar user={user} />
            <span className="hidden max-w-40 sm:block">
              <strong className="block truncate text-xs text-fg">
                {user?.first_name || "Usuário"} {user?.last_name || ""}
              </strong>
              <span className="block truncate text-[10px] text-muted">
                {user?.email}
              </span>
            </span>
            <ChevronDown className="hidden size-3.5 text-muted sm:block" />
          </button>
          {profileOpen && (
            <div className="absolute right-0 mt-2 w-56 rounded-lg border border-subtle bg-surface-raised p-2 shadow-xl">
              <div className="border-b border-subtle px-2 py-2 sm:hidden">
                <p className="truncate text-xs font-semibold">{user?.email}</p>
              </div>
              <Link
                href="/ajuda"
                onClick={() => setProfileOpen(false)}
                className="flex w-full items-center gap-2 rounded-md px-3 py-2.5 text-xs font-medium text-muted hover:bg-surface-muted hover:text-fg"
              >
                <CircleHelp className="size-4" />
                Central de ajuda
              </Link>
              <Link
                href="/perfil"
                onClick={() => setProfileOpen(false)}
                className="flex w-full items-center gap-2 rounded-md px-3 py-2.5 text-xs font-medium text-muted hover:bg-surface-muted hover:text-fg"
              >
                <UserRound className="size-4" />
                Meu perfil
              </Link>
              <Link
                href="/perfil/alterar-senha"
                onClick={() => setProfileOpen(false)}
                className="flex w-full items-center gap-2 rounded-md px-3 py-2.5 text-xs font-medium text-muted hover:bg-surface-muted hover:text-fg"
              >
                <KeyRound className="size-4" />
                Alterar senha
              </Link>
              {currentCompany?.is_owner && (
                <Link
                  href="/assinatura"
                  onClick={() => setProfileOpen(false)}
                  className="flex w-full items-center gap-2 rounded-md px-3 py-2.5 text-xs font-medium text-muted hover:bg-surface-muted hover:text-fg"
                >
                  <CreditCard className="size-4" />
                  Assinatura
                </Link>
              )}
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
      </div>
      {logoutError && (
        <div className="px-4 pt-4 sm:px-6 lg:px-8">
          <Alert message={logoutError} />
        </div>
      )}
      <main>{children}</main>
    </div>
  );
}
