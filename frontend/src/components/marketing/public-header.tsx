"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowUpRight, Menu, X } from "lucide-react";
import { BrandWordmark } from "@/components/marketing/brand-wordmark";
import { MarketingThemeToggle } from "@/components/marketing/theme-toggle";

type PublicPage = "home" | "solutions" | "contact" | "help" | "plans";
const links = [["Soluções", "/solucoes", "solutions"], ["Integrações", "/#integracoes", ""], ["Segmentos", "/#segmentos", ""], ["Planos", "/planos", "plans"], ["Ajuda", "/ajuda", "help"]] as const;

export function PublicHeader({ active }: { active?: PublicPage }) {
  const [open, setOpen] = useState(false);
  const menu = useRef<HTMLDivElement>(null);
  useEffect(() => {
    function close(event: MouseEvent | KeyboardEvent) {
      if (event instanceof KeyboardEvent && event.key === "Escape") setOpen(false);
      if (event instanceof MouseEvent && menu.current && !menu.current.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", close); document.addEventListener("keydown", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
  }, []);
  return <header className="sticky top-0 z-40 border-b border-subtle bg-surface"><div className="mx-auto flex min-h-17 max-w-7xl items-center gap-3 px-4 sm:px-6 lg:px-8"><BrandWordmark /><nav className="ml-auto hidden items-center gap-1 lg:flex" aria-label="Navegação pública">{links.map(([label, href, page]) => <Link key={label} href={href} aria-current={active === page ? "page" : undefined} className={`rounded-md px-3 py-2 text-xs font-semibold transition ${active === page ? "text-primary" : "text-muted hover:text-fg"}`}>{label}</Link>)}</nav><div className="ml-auto flex items-center gap-2 lg:ml-3"><MarketingThemeToggle /><Link href="/login" className="hidden h-10 items-center justify-center rounded-xl border border-subtle px-4 text-xs font-bold text-fg transition hover:bg-surface-muted sm:inline-flex">Entrar</Link><Link href="/contato" className="inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-primary px-4 text-xs font-bold text-white transition hover:bg-primary-dark"><span className="hidden sm:inline">Solicitar demonstração</span><span className="sm:hidden">Contato</span><ArrowUpRight className="size-3.5" /></Link><div ref={menu} className="relative lg:hidden"><button type="button" className="flex size-10 items-center justify-center rounded-xl border border-subtle text-fg" aria-label={open ? "Fechar menu" : "Abrir menu"} aria-expanded={open} aria-controls="public-mobile-menu" onClick={() => setOpen((value) => !value)}>{open ? <X className="size-4" /> : <Menu className="size-4" />}</button>{open && <nav id="public-mobile-menu" className="absolute right-0 top-12 grid w-56 border border-subtle bg-surface p-2 shadow-lg" aria-label="Navegação pública móvel">{links.map(([label, href]) => <Link key={label} href={href} className="rounded-md px-3 py-3 text-sm font-semibold text-fg hover:bg-surface-muted" onClick={() => setOpen(false)}>{label}</Link>)}<Link href="/login" className="rounded-md px-3 py-3 text-sm font-semibold text-fg hover:bg-surface-muted sm:hidden" onClick={() => setOpen(false)}>Entrar</Link></nav>}</div></div></div></header>;
}
