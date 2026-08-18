"use client";

import Link from "next/link";
import { BarChart3, Banknote, CreditCard, Package, ShieldCheck, Users } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";

const groups = [
  { title: "Visão Gerencial", description: "Decisão rápida e resultado da operação.", icon: BarChart3, reports: [
    ["/relatorios/visao-geral", "Visão geral", permissions.viewSalesReport],
    ["/relatorios/vendas", "Vendas", permissions.viewSalesReport],
    ["/relatorios/resultado", "Resultado estimado", permissions.viewOperationalResult],
  ] },
  { title: "Produtos & Performance", description: "Venda, preço e consumo físico.", icon: Package, reports: [
    ["/relatorios/produtos", "Produtos", permissions.viewProductsReport],
    ["/relatorios/consumo-estoque", "Consumo de estoque", permissions.viewStockConsumptionReport],
    ["/relatorios/precos", "Preços por filial", permissions.viewPricesReport],
  ] },
  { title: "Recebimentos", description: "Formas de pagamento e sessões.", icon: CreditCard, reports: [
    ["/relatorios/recebimentos", "Recebimentos", permissions.viewReceiptsReport],
    ["/relatorios/caixa", "Caixa", permissions.viewCashReport],
  ] },
  { title: "Equipe & Comissão", description: "Responsabilidade operacional separada.", icon: Users, reports: [
    ["/relatorios/operadores", "Operadores", permissions.viewTeamReport],
    ["/relatorios/atendentes", "Atendentes", permissions.viewTeamReport],
    ["/relatorios/comissoes", "Comissões", permissions.viewCommission],
  ] },
  { title: "Custos & Resultado", description: "Custos históricos e saídas financeiras.", icon: Banknote, reports: [
    ["/relatorios/resultado", "Resultado", permissions.viewOperationalResult],
    ["/relatorios/sangrias", "Sangrias", permissions.viewWithdrawalsReport],
    ["/relatorios/consumacoes", "Consumações", permissions.viewConsumptionsReport],
  ] },
  { title: "Auditoria & Controle", description: "Exceções e rastreabilidade.", icon: ShieldCheck, reports: [
    ["/relatorios/descontos", "Descontos", permissions.viewDiscountsReport],
    ["/relatorios/cancelamentos", "Cancelamentos", permissions.viewCancellationsReport],
    ["/auditoria", "AuditLog", permissions.viewAuditLog],
  ] },
] as const;

export function ReportsCenter() {
  const { currentBranch, hasPermission } = useAuth();
  return <><PageHeader title="Central de Relatórios" description={`Análises dedicadas de ${currentBranch?.name || "sua filial"}.`} /><div className="grid gap-5 p-4 sm:p-6 lg:grid-cols-2 lg:p-8 xl:grid-cols-3">{groups.map((group) => { const reports = group.reports.filter((item) => hasPermission(item[2])); if (!reports.length) return null; const Icon = group.icon; return <section key={group.title} className="card overflow-hidden"><div className="card-header"><div className="flex items-center gap-3"><span className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary"><Icon className="size-5" /></span><div><h2 className="text-sm font-bold">{group.title}</h2><p className="mt-1 text-[11px] text-slate-500">{group.description}</p></div></div></div><div className="divide-y divide-slate-100">{reports.map(([href, label]) => <Link key={href} href={href} className="flex items-center justify-between px-5 py-3.5 text-sm font-semibold transition hover:bg-slate-50"><span>{label}</span><span className="text-primary">Ver relatório</span></Link>)}</div></section>; })}</div></>;
}
