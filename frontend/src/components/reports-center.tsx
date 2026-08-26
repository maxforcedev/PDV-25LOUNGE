"use client";

import Link from "next/link";
import { BarChart3, Banknote, CreditCard, Package, ShieldCheck, Users, Boxes, ClipboardList, ReceiptText } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";

const groups = [
  { title: "Vendas", description: "Faturamento, formas de pagamento e cancelamentos.", icon: ReceiptText, reports: [
    ["/relatorios/vendas", "Vendas", permissions.viewSalesReport],
    ["/relatorios/recebimentos", "Formas de pagamento", permissions.viewReceiptsReport],
    ["/relatorios/cancelamentos", "Cancelamentos", permissions.viewCancellationsReport],
    ["/relatorios/atendentes", "Atendentes", permissions.viewTeamReport],
    ["/relatorios/produtos", "Produtos", permissions.viewProductsReport],
    ["/relatorios/consumacoes", "Consumação", permissions.viewConsumptionsReport],
  ] },
  { title: "Financeiro", description: "Faturamento, taxas, comissões, custos e margem.", icon: Banknote, reports: [
    ["/relatorios/resultado", "Faturamento", permissions.viewOperationalResult],
    ["/relatorios/visao-geral", "Visão geral", permissions.viewSalesReport],
    ["/relatorios/comissoes", "Comissões", permissions.viewCommission],
    ["/relatorios/consumo-estoque", "Custos", permissions.viewStockConsumptionReport],
  ] },
  { title: "Estoque", description: "Posição, movimentações, perdas e transferências.", icon: Boxes, reports: [
    ["/relatorios/estoque-avancado", "Posição de estoque", permissions.viewAdvancedInventory],
    ["/relatorios/precos", "Preços por filial", permissions.viewPricesReport],
  ] },
  { title: "Inventários", description: "Realizados, sistema x contado, faltas e sobras.", icon: ClipboardList, reports: [
    ["/relatorios/estoque-avancado", "Inventários realizados", permissions.viewAdvancedInventory],
  ] },
  { title: "Compras", description: "Compras, fornecedores, custos e contas a pagar.", icon: Package, reports: [
    ["/relatorios/produtos", "Fornecedores", permissions.viewProductsReport],
  ] },
  { title: "Auditoria & Controle", description: "Exceções e rastreabilidade.", icon: ShieldCheck, reports: [
    ["/relatorios/descontos", "Descontos", permissions.viewDiscountsReport],
    ["/relatorios/sangrias", "Sangrias", permissions.viewWithdrawalsReport],
    ["/relatorios/caixa", "Caixa", permissions.viewCashReport],
    ["/auditoria", "Auditoria", permissions.viewAuditLog],
  ] },
] as const;

export function ReportsCenter() {
  const { currentBranch, hasPermission } = useAuth();
  return <><PageHeader title="Central de Relatórios" description={`Análises dedicadas de ${currentBranch?.name || "sua filial"}.`} /><div className="grid gap-5 p-4 sm:p-6 lg:grid-cols-2 lg:p-8 xl:grid-cols-3">{groups.map((group) => { const reports = group.reports.filter((item) => hasPermission(item[2])); if (!reports.length) return null; const Icon = group.icon; return <section key={group.title} className="card overflow-hidden"><div className="card-header"><div className="flex items-center gap-3"><span className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary"><Icon className="size-5" /></span><div><h2 className="text-sm font-bold">{group.title}</h2><p className="mt-1 text-[11px] text-slate-500">{group.description}</p></div></div></div><div className="divide-y divide-slate-100">{reports.map(([href, label]) => <Link key={href + label} href={href} className="flex items-center justify-between px-5 py-3.5 text-sm font-semibold transition hover:bg-slate-50"><span>{label}</span><span className="text-primary">Ver relatório</span></Link>)}</div></section>; })}</div></>;
}
