"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, Building2, ChevronRight, CreditCard, Headphones, LogOut, Menu, Settings2, ShieldCheck, X } from "lucide-react";
import { useState } from "react";
import { useAuth } from "@/providers/auth-provider";
import { release } from "@/lib/release";

const navigation = [
  { href: "/dashboard", label: "Visao operacional", permission: "platform.dashboard.view", icon: BarChart3 },
  { href: "/tenants", label: "Tenants", permission: "platform.tenants.manage", icon: Building2 },
  { href: "/plans", label: "Planos e limites", permission: "platform.plans.manage", icon: ShieldCheck },
  { href: "/settings", label: "Politicas globais", permission: "platform.settings.manage", icon: Settings2 },
  { href: "/billing", label: "Cobranca", permission: "platform.billing.manage", icon: CreditCard },
  { href: "/support", label: "Support Sessions", permission: "platform.support.manage", icon: Headphones },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, logout, can } = useAuth();
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const allowed = navigation.filter((item) => can(item.permission));
  const current = allowed.find((item) => pathname === item.href || pathname.startsWith(`${item.href}/`));

  return <div className="min-h-screen bg-canvas lg:grid lg:grid-cols-[264px_1fr]">
    {open && <button className="fixed inset-0 z-30 bg-ink/60 lg:hidden" onClick={() => setOpen(false)} aria-label="Fechar menu" />}
    <aside className={`fixed inset-y-0 left-0 z-40 flex w-66 flex-col bg-ink text-white transition-transform lg:sticky lg:top-0 lg:h-screen ${open ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}`}>
      <div className="core-grid flex h-24 items-center justify-between border-b border-white/10 px-6"><div><div className="flex items-center gap-2"><span className="size-2.5 bg-signal" /><span className="text-xl font-black tracking-tight">CORE</span></div><p className="mt-1 font-mono text-[9px] uppercase tracking-[.2em] text-white/50">Platform operations</p></div><button className="p-2 lg:hidden" onClick={() => setOpen(false)}><X size={20} /></button></div>
      <div className="border-b border-white/10 px-6 py-4"><p className="font-mono text-[9px] uppercase tracking-[.14em] text-white/40">Ambiente</p><p className="mt-1 flex items-center gap-2 text-xs font-bold uppercase"><span className="size-1.5 rounded-full bg-signal" />Controle central</p></div>
      <nav className="flex-1 space-y-1 p-3" aria-label="Navegacao principal">{allowed.map((item) => { const active = pathname === item.href || pathname.startsWith(`${item.href}/`); const Icon = item.icon; return <Link key={item.href} href={item.href} onClick={() => setOpen(false)} className={`group flex h-12 items-center gap-3 border-l-2 px-3 text-sm transition ${active ? "border-signal bg-white/8 text-white" : "border-transparent text-white/60 hover:bg-white/5 hover:text-white"}`}><Icon size={18} /><span className="flex-1 font-semibold">{item.label}</span>{active && <ChevronRight size={14} className="text-signal" />}</Link>; })}</nav>
      <div className="border-t border-white/10 p-4"><div className="mb-4 border-b border-white/10 pb-4 font-mono text-[9px] text-white/45"><p className="font-bold text-white/70">CORE PDV v{release.version}</p><p className="mt-1" title={`Commit ${release.commit}`}>build {release.shortCommit} · {release.environment}</p><p className="mt-1 truncate" title={release.buildDate}>{release.buildDate}</p></div><p className="truncate text-sm font-bold">{user?.first_name || user?.email}</p><p className="mt-1 truncate font-mono text-[9px] uppercase tracking-wider text-white/45">{user?.role}</p><button className="mt-4 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-white/60 hover:text-white" onClick={() => void logout()}><LogOut size={15} />Encerrar sessao</button></div>
    </aside>
    <div className="min-w-0"><header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-line bg-paper/95 px-4 backdrop-blur sm:px-6"><div className="flex items-center gap-3"><button className="p-2 lg:hidden" onClick={() => setOpen(true)} aria-label="Abrir menu"><Menu size={21} /></button><div><p className="eyebrow">CORE / OPS</p><p className="text-sm font-bold">{current?.label || "Console operacional"}</p></div></div><div className="hidden items-center gap-2 font-mono text-[10px] uppercase tracking-wider text-steel/60 sm:flex"><span className="size-2 rounded-full bg-signal ring-4 ring-signal/20" />Sessao protegida</div></header><main className="mx-auto max-w-[1500px] p-4 sm:p-6 lg:p-8">{children}</main></div>
  </div>;
}
