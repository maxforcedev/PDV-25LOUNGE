import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, BookOpenCheck } from "lucide-react";
import { HelpCenter } from "@/components/marketing/help-center";
import { PublicFooter } from "@/components/marketing/public-footer";
import { PublicHeader } from "@/components/marketing/public-header";

export const metadata: Metadata = {
  title: "Central de Ajuda ",
  description: "Guias para os fluxos de venda, caixa, estoque, usuários, permissões e relatórios do CORE.",
};

export default function HelpPage() {
  return <div className="min-h-screen bg-canvas text-fg"><PublicHeader active="help" /><main><section className="border-b border-subtle bg-surface"><div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8"><BookOpenCheck className="size-6 text-primary" aria-hidden="true" /><p className="marketing-eyebrow mt-5">Central de Ajuda</p><h1 className="mt-4 max-w-3xl text-4xl font-black tracking-[-0.05em] text-fg sm:text-5xl">Orientações para voltar à operação com contexto.</h1><p className="mt-5 max-w-2xl text-sm leading-7 text-muted">Consulte guias sobre venda, caixa, estoque, cadastros, permissões e relatórios do CORE.</p></div></section><section className="mx-auto max-w-7xl px-4 py-12 sm:px-6 sm:py-16 lg:px-8"><HelpCenter /></section><section className="border-t border-subtle bg-surface"><div className="mx-auto flex max-w-7xl flex-col gap-5 px-4 py-14 sm:px-6 sm:flex-row sm:items-center sm:justify-between lg:px-8"><div><h2 className="text-xl font-black tracking-tight text-fg">Precisa de ajuda com a sua operação?</h2><p className="mt-2 text-xs text-muted">Acesse o sistema para conferir empresa, filial e permissões atuais.</p></div><Link href="/login" className="inline-flex items-center gap-2 text-sm font-bold text-primary">Entrar no CORE <ArrowRight className="size-4" /></Link></div></section></main><PublicFooter /></div>;
}
