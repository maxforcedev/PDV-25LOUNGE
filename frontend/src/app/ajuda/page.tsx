import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, BookOpenCheck, Clock3, ShieldCheck, Sparkles } from "lucide-react";
import { HelpCenter } from "@/components/marketing/help-center";
import { PublicFooter } from "@/components/marketing/public-footer";
import { PublicHeader } from "@/components/marketing/public-header";

export const metadata: Metadata = {
  title: "Central de Ajuda — CORE PDV",
  description: "Guias rápidos para operar vendas, caixa, estoque, usuários, permissões, relatórios e auditoria no CORE PDV.",
};

export default function HelpPage() {
  return (
    <div className="min-h-screen bg-canvas text-fg">
      <PublicHeader active="help" />
      <main>
        <section className="marketing-hero relative overflow-hidden border-b border-subtle">
          <div className="marketing-grid absolute inset-0 opacity-55" />
          <div className="absolute left-1/2 top-[-260px] size-[560px] -translate-x-1/2 rounded-full bg-primary/15 blur-[120px]" />
          <div className="relative mx-auto max-w-7xl px-4 py-16 text-center sm:px-6 sm:py-20 lg:px-8">
            <div className="mx-auto inline-flex items-center gap-2 rounded-full border border-primary/20 bg-info-surface px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-info-strong">
              <BookOpenCheck className="size-3.5" /> Central de Ajuda CORE PDV
            </div>
            <h1 className="mx-auto mt-6 max-w-4xl text-4xl font-black leading-[1.08] tracking-[-0.045em] text-fg sm:text-5xl">Encontre a resposta e volte para a operação.</h1>
            <p className="mx-auto mt-5 max-w-2xl text-sm leading-7 text-muted sm:text-[15px]">Guias diretos sobre os fluxos que mais importam no dia a dia: vender, abrir e fechar caixa, movimentar estoque, controlar acessos e conferir números.</p>
            <div className="mx-auto mt-8 grid max-w-2xl gap-3 text-left sm:grid-cols-3">
              <div className="rounded-xl border border-subtle bg-surface/80 p-3.5"><Clock3 className="size-4 text-primary" /><strong className="mt-2 block text-[11px] text-fg">Guias rápidos</strong><span className="mt-1 block text-[10px] leading-4 text-muted">Passos curtos para resolver a tarefa.</span></div>
              <div className="rounded-xl border border-subtle bg-surface/80 p-3.5"><ShieldCheck className="size-4 text-primary" /><strong className="mt-2 block text-[11px] text-fg">Regras reais do sistema</strong><span className="mt-1 block text-[10px] leading-4 text-muted">Permissões e backend continuam sendo a fonte de verdade.</span></div>
              <div className="rounded-xl border border-subtle bg-surface/80 p-3.5"><Sparkles className="size-4 text-primary" /><strong className="mt-2 block text-[11px] text-fg">Busca por contexto</strong><span className="mt-1 block text-[10px] leading-4 text-muted">Pesquise por módulo, ação ou dúvida.</span></div>
            </div>
          </div>
        </section>

        <section className="mx-auto max-w-7xl px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
          <HelpCenter />
        </section>

        <section className="border-t border-subtle bg-surface">
          <div className="mx-auto grid max-w-7xl gap-6 px-4 py-14 sm:px-6 md:grid-cols-[1fr_auto] md:items-center lg:px-8">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-primary">Ainda precisa de contexto?</p>
              <h2 className="mt-2 text-xl font-black tracking-tight text-fg">Volte ao sistema e confira empresa, filial e permissões atuais.</h2>
              <p className="mt-2 max-w-2xl text-xs leading-5 text-muted">Muitos comportamentos do CORE PDV dependem do contexto operacional do usuário. Se uma ação não aparecer, confirme primeiro o acesso efetivo da filial.</p>
            </div>
            <Link href="/login" className="inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-primary px-5 text-xs font-bold text-white shadow-lg shadow-primary/20 transition hover:bg-primary-dark">Acessar sistema <ArrowRight className="size-4" /></Link>
          </div>
        </section>
      </main>
      <PublicFooter />
    </div>
  );
}
