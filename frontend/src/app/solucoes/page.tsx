import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { PublicFooter } from "@/components/marketing/public-footer";
import { PublicHeader } from "@/components/marketing/public-header";
import { ProductEvidence } from "@/components/marketing/product-evidence";

export const metadata: Metadata = { title: "Soluções ", description: "Conheça os fluxos de operação e gestão conectados pelo CORE." };

const sections = [
  ["CORE POS / Vendas", "No CORE POS, venda, operadores, caixa, atendimento e permissões operacionais fazem parte da rotina de quem está atendendo.", "Venda → pagamento → caixa", "/site/screenshots/core-pos-venda.webp", "Tela real do CORE POS na venda rápida"],
  ["Mesas e comandas", "Organize o atendimento, os pedidos e o fechamento de mesas e comandas no ritmo da sua casa.", "Atendimento → pedido → fechamento", "/site/screenshots/mesas-comandas.webp", "Tela real de mesas e comandas no CORE"],
  ["Pagamentos", "O pagamento acompanha a venda para manter a operação em um único fluxo, com uma arquitetura preparada para múltiplos provedores.", "Venda → pagamento → registro", "/site/screenshots/pagamentos.webp", "Tela real de pagamentos no CORE"],
  ["Estoque e compras", "Compras, entradas, movimentações, transferências, perdas e inventários apoiam a rastreabilidade entre abastecimento e venda.", "Compra → entrada → estoque → venda", "/site/screenshots/estoque-compras.webp", "Tela real de estoque e compras no CORE"],
  ["Gestão e relatórios", "No CORE Backoffice, a gestão acompanha cadastros, estoque, compras, relatórios, financeiro, filiais e usuários.", "Operação → acompanhamento → decisão", "/site/screenshots/backoffice-relatorios.webp", "Tela real de relatórios no CORE Backoffice"],
  ["Multiempresa e multifilial", "Empresa, filiais, usuários e dispositivos mantêm o controle organizado conforme a estrutura da operação.", "Empresa → filiais → usuários → dispositivos", "/site/screenshots/filiais-usuarios.webp", "Tela real de filiais e usuários no CORE"],
  ["Segurança e auditoria", "Perfis, permissões, contexto de filial e auditoria reforçam o controle de cada ação operacional.", "Pessoa → permissão → contexto → registro", "/site/screenshots/auditoria.webp", "Tela real de auditoria no CORE"],
] as const;

export default function SolutionsPage() {
  return <div className="min-h-screen bg-canvas text-fg"><PublicHeader active="solutions" /><main><section className="border-b border-subtle bg-surface"><div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8"><p className="marketing-eyebrow">Soluções CORE</p><h1 className="mt-4 max-w-3xl text-4xl font-black tracking-[-0.05em] text-fg sm:text-5xl">Fluxos reais para quem opera e para quem acompanha.</h1><p className="mt-5 max-w-2xl text-sm leading-7 text-muted">CORE POS concentra a operação. CORE Backoffice concentra gestão e controle. As soluções acompanham o caminho que a informação percorre.</p></div></section><div className="mx-auto max-w-7xl space-y-16 px-4 py-16 sm:px-6 lg:px-8">{sections.map(([title, description, flow, src, alt], index) => <section key={title} id={title === "Pagamentos" ? "pagamentos" : title === "CORE POS / Vendas" ? "core-pos-vendas" : title === "Gestão e relatórios" ? "gestao-e-relatorios" : undefined} className="grid gap-8 border-b border-subtle pb-16 lg:grid-cols-[0.8fr_1.2fr] lg:items-center"><div className={index % 2 ? "lg:order-2" : ""}><p className="marketing-eyebrow">{flow}</p><h2 className="mt-4 text-2xl font-black tracking-[-0.04em] text-fg">{title}</h2><p className="mt-4 text-sm leading-7 text-muted">{description}</p></div><ProductEvidence title={title} src={src} alt={alt} /></section>)}</div><section className="border-t border-subtle bg-surface"><div className="mx-auto flex max-w-7xl flex-col gap-5 px-4 py-14 sm:px-6 sm:flex-row sm:items-center sm:justify-between lg:px-8"><h2 className="text-2xl font-black tracking-tight text-fg">Quer validar o CORE no seu fluxo?</h2><Link href="/contato" className="inline-flex items-center gap-2 text-sm font-bold text-primary">Solicitar demonstração <ArrowRight className="size-4" /></Link></div></section></main><PublicFooter /></div>;
}
