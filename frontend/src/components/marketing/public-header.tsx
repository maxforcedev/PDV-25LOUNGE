import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { BrandWordmark } from "@/components/marketing/brand-wordmark";
import { MarketingThemeToggle } from "@/components/marketing/theme-toggle";

export function PublicHeader({ active }: { active?: "home" | "help" | "plans" | "signup" }) {
  return (
    <header className="sticky top-0 z-40 border-b border-subtle/80 bg-surface/88 backdrop-blur-xl">
      <div className="mx-auto flex h-17 max-w-7xl items-center gap-4 px-4 sm:px-6 lg:px-8">
        <BrandWordmark />

        <nav className="ml-auto hidden items-center gap-1 lg:flex" aria-label="Navegação pública">
          <Link
            href="/planos"
            aria-current={active === "plans" ? "page" : undefined}
            className={`rounded-lg px-3 py-2 text-xs font-semibold transition ${active === "plans" ? "bg-info-surface text-info-strong" : "text-muted hover:bg-surface-muted hover:text-fg"}`}
          >
            Planos
          </Link>
          <Link
            href="/#recursos"
            className="rounded-lg px-3 py-2 text-xs font-semibold text-muted transition hover:bg-surface-muted hover:text-fg"
          >
            Recursos
          </Link>
          <Link
            href="/#operacao"
            className="rounded-lg px-3 py-2 text-xs font-semibold text-muted transition hover:bg-surface-muted hover:text-fg"
          >
            Operação
          </Link>
          <Link
            href="/#seguranca"
            className="rounded-lg px-3 py-2 text-xs font-semibold text-muted transition hover:bg-surface-muted hover:text-fg"
          >
            Segurança
          </Link>
          <Link
            href="/ajuda"
            aria-current={active === "help" ? "page" : undefined}
            className={`rounded-lg px-3 py-2 text-xs font-semibold transition ${active === "help" ? "bg-info-surface text-info-strong" : "text-muted hover:bg-surface-muted hover:text-fg"}`}
          >
            Ajuda
          </Link>
        </nav>

        <div className="ml-auto flex items-center gap-2 lg:ml-3">
          <MarketingThemeToggle />
          <Link
            href="/login"
            className="hidden h-10 items-center justify-center rounded-xl border border-subtle bg-surface px-4 text-xs font-bold text-fg shadow-sm transition hover:border-primary/25 hover:bg-surface-muted sm:inline-flex"
          >
            Entrar
          </Link>
          <Link
            href="/cadastro"
            className="inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-primary px-4 text-xs font-bold text-white shadow-lg shadow-primary/20 transition hover:bg-primary-dark focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/30"
          >
            <span className="hidden sm:inline">Criar conta</span>
            <span className="sm:hidden">Começar</span>
            <ArrowUpRight className="size-3.5" />
          </Link>
        </div>
      </div>
    </header>
  );
}
