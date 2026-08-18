"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Download, Filter } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { PeriodFilter, type PeriodValue } from "@/components/period-filter";
import { Alert, Button, EmptyState, Field, Pagination, Select, TableLoading } from "@/components/ui";
import { domainLabel } from "@/lib/domain-labels";
import { formatBRL, formatDate, formatQuantity } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { businessMonthToDate } from "@/lib/period";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { ProductPriceComparison, ReportResponse, ReportsOptions } from "@/types";

export type ReportKind =
  | "overview"
  | "sales"
  | "products"
  | "receipts"
  | "operators"
  | "sellers"
  | "commissions"
  | "discounts"
  | "consumptions"
  | "cash"
  | "withdrawals"
  | "stock-consumption"
  | "cancellations"
  | "prices"
  | "result";

const configs: Record<ReportKind, { title: string; description: string; endpoint: string; permission: string }> = {
  overview: { title: "Visão gerencial", description: "Resumo comercial e financeiro da filial.", endpoint: "sales", permission: permissions.viewSalesReport },
  sales: { title: "Vendas", description: "Vendas comerciais, responsáveis e valores históricos.", endpoint: "sales", permission: permissions.viewSalesReport },
  products: { title: "Produtos e desempenho", description: "Desempenho comercial por produto e categoria.", endpoint: "sales", permission: permissions.viewProductsReport },
  receipts: { title: "Recebimentos", description: "Distribuição do total recebido por forma de pagamento.", endpoint: "sales", permission: permissions.viewReceiptsReport },
  operators: { title: "Operadores", description: "Faturamento processado por operador de caixa.", endpoint: "sales", permission: permissions.viewTeamReport },
  sellers: { title: "Atendentes", description: "Faturamento e ticket por atendente responsável.", endpoint: "sales", permission: permissions.viewTeamReport },
  commissions: { title: "Comissões", description: "Valores históricos de comissão atribuídos aos atendentes.", endpoint: "sales", permission: permissions.viewCommission },
  discounts: { title: "Descontos", description: "Descontos manuais por item, na conta e promoções.", endpoint: "sales", permission: permissions.viewDiscountsReport },
  consumptions: { title: "Consumações e cortesias", description: "Referência, valor cobrado e benefício operacional.", endpoint: "consumptions", permission: permissions.viewConsumptionsReport },
  cash: { title: "Caixa", description: "Sessões por interseção temporal e reconciliação completa.", endpoint: "cash", permission: permissions.viewCashReport },
  withdrawals: { title: "Sangrias", description: "Saídas de gaveta, beneficiários e impacto no resultado.", endpoint: "withdrawals", permission: permissions.viewWithdrawalsReport },
  "stock-consumption": { title: "Consumo de estoque", description: "Resumo físico e movimentos reais de saída e reversão.", endpoint: "stock-consumption", permission: permissions.viewStockConsumptionReport },
  cancellations: { title: "Cancelamentos e estornos", description: "Operações canceladas no período do cancelamento.", endpoint: "cancellations", permission: permissions.viewCancellationsReport },
  prices: { title: "Preços por filial", description: "Comparação entre o preço padrão e os preços específicos por filial.", endpoint: "prices", permission: permissions.viewPricesReport },
  result: { title: "Resultado estimado", description: "Receita, CMV histórico, despesas e margem operacional.", endpoint: "operational-result", permission: permissions.viewOperationalResult },
};

function initialPeriod(): PeriodValue {
  return businessMonthToDate();
}

function rows(value: unknown) {
  return Array.isArray(value) ? value as Array<Record<string, unknown>> : [];
}

function money(value: unknown) {
  return Number(value || 0);
}

function hasDelta(value: unknown) {
  return Math.abs(money(value)) >= 0.005;
}

function ReconciliationWarning({ label, value }: { label: string; value: unknown }) {
  if (!hasDelta(value)) return null;
  return <div role="alert" className="rounded-md border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-warning-strong"><strong>{label}:</strong> {formatBRL(String(value))}. Os componentes retornados pelo backend não reconciliam neste recorte.</div>;
}

function Kpi({ label, value, format = "money" }: { label: string; value: unknown; format?: "money" | "number" | "quantity" | "percent" }) {
  const display = format === "money"
    ? formatBRL(String(value || "0"))
    : format === "quantity"
      ? formatQuantity(String(value || "0"))
      : format === "percent"
        ? `${String(value || "0")}%`
        : String(value ?? "0");
  return <div className="rounded-lg border border-dashed border-slate-200 p-4"><span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{label}</span><strong className="mt-2 block text-xl text-dark">{display}</strong></div>;
}

function reportKpis(kind: ReportKind, summary: Record<string, unknown>) {
  const productRows = rows(summary.product_ranking);
  const paymentRows = rows(summary.payment_totals);
  const operatorRows = rows(summary.operator_groups);
  const sellerRows = rows(summary.seller_groups);
  const stockRows = rows(summary.products);
  const definitions: Partial<Record<ReportKind, Array<[string, unknown, "money" | "number" | "quantity" | "percent"]>>> = {
    overview: [["Faturamento efetivo", summary.effective_revenue, "money"], ["Taxa de serviço", summary.service_fee, "money"], ["Total recebido em vendas", summary.total_received_sales, "money"], ["Total cobrado ao cliente", summary.customer_total, "money"], ["Vendas", summary.count, "number"], ["Ticket médio recebido", summary.ticket_average, "money"]],
    sales: [["Faturamento efetivo", summary.effective_revenue, "money"], ["Taxa de serviço", summary.service_fee, "money"], ["Total recebido em vendas", summary.total_received_sales, "money"], ["Total cobrado ao cliente", summary.customer_total, "money"], ["Vendas", summary.count, "number"], ["Ticket médio recebido", summary.ticket_average, "money"]],
    products: [["Faturamento dos produtos", productRows.reduce((total, row) => total + money(row.revenue), 0), "money"], ["Unidades vendidas", productRows.reduce((total, row) => total + money(row.quantity), 0), "quantity"], ["Produtos vendidos", productRows.length, "number"], ["Categorias", rows(summary.category_ranking).length, "number"]],
    receipts: [["Total operacional recebido", summary.total_operational_received, "money"], ["Recebido em vendas", summary.sales_received, "money"], ["Consumações cobradas", summary.consumption_charged, "money"], ["Reversões", summary.reversals, "money"]],
    operators: [["Faturamento efetivo", operatorRows.reduce((total, row) => total + money(row.effective_revenue), 0), "money"], ["Taxa de serviço", operatorRows.reduce((total, row) => total + money(row.service_fee), 0), "money"], ["Total recebido", operatorRows.reduce((total, row) => total + money(row.total_received), 0), "money"], ["Vendas", operatorRows.reduce((total, row) => total + money(row.count), 0), "number"], ["Ticket médio", operatorRows.reduce((total, row) => total + money(row.count), 0) ? operatorRows.reduce((total, row) => total + money(row.total_received), 0) / operatorRows.reduce((total, row) => total + money(row.count), 0) : 0, "money"]],
    sellers: [["Faturamento efetivo", sellerRows.reduce((total, row) => total + money(row.effective_revenue), 0), "money"], ["Taxa de serviço", sellerRows.reduce((total, row) => total + money(row.service_fee), 0), "money"], ["Total recebido", sellerRows.reduce((total, row) => total + money(row.total_received), 0), "money"], ["Vendas", sellerRows.reduce((total, row) => total + money(row.count), 0), "number"], ["Ticket médio", sellerRows.reduce((total, row) => total + money(row.count), 0) ? sellerRows.reduce((total, row) => total + money(row.total_received), 0) / sellerRows.reduce((total, row) => total + money(row.count), 0) : 0, "money"]],
    commissions: [["Comissão histórica", summary.commission, "money"], ["Vendas com comissão", summary.commission_sale_count, "number"], ["Atendentes com comissão", summary.commission_attendant_count, "number"], ["Faturamento efetivo", sellerRows.reduce((total, row) => total + money(row.effective_revenue), 0), "money"]],
    discounts: [["Desconto na conta", summary.account_discount, "money"], ["Desconto por item", summary.item_discount, "money"], ["Promoções", summary.promotion_discount, "money"], ["Vendas afetadas", summary.count, "number"]],
    consumptions: [["Valor de referência", summary.reference, "money"], ["Valor cobrado", summary.charged, "money"], ["Benefício concedido", summary.benefit, "money"], ["Operações", summary.count, "number"], ...(summary.historical_cost !== undefined ? [["Custo histórico", summary.historical_cost, "money"] as [string, unknown, "money"]] : [])],
    cash: [["Recebido operacional no período", summary.operational_received, "money"], ["Recebido em vendas no período", summary.sales_received, "money"], ["Consumações cobradas no período", summary.consumption_charged, "money"], ["Reversões no período", summary.reversals, "money"]],
    withdrawals: [["Total de sangrias", summary.amount, "money"], ["Movimentos", summary.count, "number"]],
    "stock-consumption": [["Consumo bruto", summary.gross_quantity, "quantity"], ["Devoluções", summary.returned_quantity, "quantity"], ["Consumo líquido", summary.net_quantity, "quantity"], ...(summary.estimated_cost !== undefined ? [["Custo estimado pelo custo atual", summary.estimated_cost, "money"] as [string, unknown, "money"]] : [["Produtos físicos", stockRows.length, "number"] as [string, unknown, "number"]])],
    cancellations: [["Faturamento efetivo revertido", summary.reversed_effective_revenue, "money"], ["Taxa de serviço revertida", summary.reversed_service_fee, "money"], ["Total revertido", summary.reversed_total_received, "money"], ["Cancelamentos", summary.count, "number"]],
    result: [["Recebimento operacional", summary.operational_received, "money"], ["CMV histórico de vendas", summary.historical_sales_cogs, "money"], ["CMV histórico de consumações", summary.historical_consumption_cogs, "money"], ["Resultado estimado", summary.estimated_result, "money"], ["Margem estimada", summary.margin, "percent"]],
  };
  return definitions[kind] || [];
}

function StatusBadge({ value }: { value: unknown }) {
  const status = String(value || "");
  const tone = status === "finalized" || status === "open" ? "bg-success/10 text-emerald-700" : status === "cancelled" ? "bg-danger/10 text-red-700" : "bg-slate-100 text-slate-700";
  return <span className={`inline-flex rounded-full px-2 py-1 text-[10px] font-bold ${tone}`}>{domainLabel(status)}</span>;
}

function SalesTable({ kind, data, canViewSales, canViewConsumptions }: { kind: ReportKind; data: ReportResponse<Record<string, unknown>>; canViewSales: boolean; canViewConsumptions: boolean }) {
  if (!data.results.length) return <EmptyState title="Sem registros" description="Nenhuma operação encontrada no período." />;
  return <div className="table-wrap"><table className="data-table"><thead><tr><th>Operação</th><th>{kind === "cancellations" ? "Cancelada em" : "Data"}</th><th>Responsáveis</th><th>Status</th>{kind === "discounts" ? <><th>Por item</th><th>Na conta</th><th>Promoções</th><th>Faturamento efetivo</th><th>Taxa</th><th>Total recebido</th></> : kind === "cancellations" ? <><th>Faturamento efetivo revertido</th><th>Taxa revertida</th><th>Total revertido</th></> : <th>{kind === "consumptions" ? "Valor cobrado" : "Total cobrado"}</th>}<th /></tr></thead><tbody>{data.results.map((row) => {
    const seller = row.seller as { name?: string } | null;
    const operator = row.operator as { name?: string } | null;
    const beneficiary = row.beneficiary as { name?: string } | null;
    const isConsumption = row.operation_type === "consumption" || kind === "consumptions";
    const canOpen = isConsumption ? canViewConsumptions : canViewSales;
    return <tr key={String(row.id)}><td><strong>{String(row.sale_number)}</strong></td><td>{formatDate(String(kind === "cancellations" ? row.cancelled_at : row.created_at))}</td><td>{kind === "consumptions" ? <span>Beneficiário: {beneficiary?.name || "-"}</span> : <><span className="block">Atendente: {seller?.name || "-"}</span><small className="text-slate-500">Operador: {operator?.name || "-"}</small></>}</td><td><StatusBadge value={row.status} /></td>{kind === "discounts" ? <><td>{formatBRL(String(row.item_discount_total || "0"))}</td><td>{formatBRL(String(row.discount || "0"))}</td><td>{formatBRL(String(row.promotion_discount_total || "0"))}</td><td>{formatBRL(String(row.effective_revenue || "0"))}</td><td>{formatBRL(String(row.service_fee_amount || "0"))}</td><td>{formatBRL(String(row.total_received_sales || "0"))}</td></> : kind === "cancellations" ? <><td>{formatBRL(String(row.effective_revenue || "0"))}</td><td>{formatBRL(String(row.service_fee_amount || "0"))}</td><td>{formatBRL(String(row.total_received_sales || "0"))}</td></> : <td>{formatBRL(String(row.total || "0"))}</td>}<td className="text-right">{canOpen ? <Link className="text-xs font-bold text-primary" href={`${isConsumption ? "/consumacoes" : "/vendas"}/${row.id}`}>Detalhes</Link> : <span className="text-[11px] text-slate-400">Sem acesso operacional</span>}</td></tr>;
  })}</tbody></table></div>;
}

function RankingTable({ kind, summary }: { kind: ReportKind; summary: Record<string, unknown> }) {
  const key = kind === "products" ? "product_ranking" : kind === "receipts" ? "payment_totals" : kind === "operators" ? "operator_groups" : "seller_groups";
  const list = rows(summary[key]);
  if (!list.length) return <EmptyState title="Sem dados" description="Nenhum resultado no período selecionado." />;
  const isTeam = ["operators", "sellers", "commissions"].includes(kind);
  const showCommission = isTeam && list.some((row) => row.commission !== undefined);
  return <div className="table-wrap"><table className="data-table"><thead><tr><th>{kind === "products" ? "Produto" : kind === "receipts" ? "Forma de pagamento" : "Pessoa"}</th>{kind === "products" && <th>Unidades</th>}{isTeam && <th>Vendas</th>}<th>{kind === "receipts" ? "Vendas recebidas" : "Faturamento efetivo"}</th>{kind === "receipts" && <><th>Consumações recebidas</th><th>Recebimento bruto</th><th>Reversões</th><th>Recebimento líquido</th></>}{isTeam && <><th>Taxa de serviço</th><th>Total recebido</th><th>Ticket médio efetivo</th><th>Cancelamentos</th></>}{showCommission && <th>Comissão histórica</th>}</tr></thead><tbody>{list.map((row, index) => {
    const user = row.user as { name?: string } | undefined;
    const label = row.product_name || row.name || user?.name || "-";
    const amount = row.revenue || row.effective_revenue || "0";
    return <tr key={String(row.product_id || row.code || user?.name || index)}><td><strong>{String(label)}</strong>{kind === "products" && <small className="block text-slate-500">{String(row.internal_code || "")}</small>}</td>{kind === "products" && <td>{formatQuantity(String(row.quantity || "0"))}</td>}{isTeam && <td>{String(row.count || 0)}</td>}<td>{formatBRL(String(kind === "receipts" ? row.commercial_received : amount))}</td>{kind === "receipts" && <><td>{formatBRL(String(row.consumption_received || "0"))}</td><td>{formatBRL(String(row.gross_received || "0"))}</td><td className="text-danger">{formatBRL(String(row.reversals || "0"))}</td><td><strong>{formatBRL(String(row.net_received || "0"))}</strong></td></>}{isTeam && <><td>{formatBRL(String(row.service_fee || "0"))}</td><td>{formatBRL(String(row.total_received || "0"))}</td><td>{formatBRL(String(row.average || "0"))}</td><td>{String(row.cancellation_count || 0)}<small className="block text-slate-500">{formatBRL(String(row.cancellation_value || "0"))}</small></td></>}{showCommission && <td><strong>{formatBRL(String(row.commission || "0"))}</strong>{row.commission_sale_count !== undefined && <small className="block text-slate-500">{String(row.commission_sale_count)} vendas</small>}</td>}</tr>;
  })}</tbody></table></div>;
}

function CategoryRanking({ summary }: { summary: Record<string, unknown> }) {
  const categories = rows(summary.category_ranking);
  return <section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Classificação por categoria</h2></div>{categories.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Categoria</th><th>Unidades</th><th>Faturamento efetivo</th></tr></thead><tbody>{categories.map((row, index) => <tr key={String(row.category_id || index)}><td><strong>{String(row.category_name || "Sem categoria")}</strong></td><td>{formatQuantity(String(row.quantity || "0"))}</td><td>{formatBRL(String(row.revenue || "0"))}</td></tr>)}</tbody></table></div> : <EmptyState title="Sem categorias" description="Nenhuma categoria teve venda no período." />}</section>;
}

function SalesSections({ summary }: { summary: Record<string, unknown> }) {
  const products = rows(summary.product_ranking);
  const categories = rows(summary.category_ranking);
  const payments = rows(summary.payment_totals);
  const cancellations = (summary.cancellations || {}) as Record<string, unknown>;
  return <div className="grid gap-5 xl:grid-cols-2"><section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Produtos mais vendidos</h2></div>{products.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Produto</th><th>Quantidade</th><th>Faturamento</th></tr></thead><tbody>{products.map((row, index) => <tr key={String(row.product_id || index)}><td><strong>{String(row.product_name)}</strong><small className="block text-slate-500">{String(row.internal_code || "")}</small></td><td>{formatQuantity(String(row.quantity))}</td><td>{formatBRL(String(row.revenue))}</td></tr>)}</tbody></table></div> : <EmptyState title="Sem produtos vendidos" description="Nenhuma venda finalizada no período." />}</section><section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Categorias vendidas</h2></div>{categories.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Categoria</th><th>Quantidade</th><th>Faturamento</th></tr></thead><tbody>{categories.map((row, index) => <tr key={String(row.category_id || index)}><td><strong>{String(row.category_name)}</strong></td><td>{formatQuantity(String(row.quantity))}</td><td>{formatBRL(String(row.revenue))}</td></tr>)}</tbody></table></div> : <EmptyState title="Sem categorias vendidas" description="Nenhuma categoria teve venda no período." />}</section><section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Recebimentos por forma</h2></div>{payments.length ? <div className="divide-y divide-slate-100">{payments.map((row, index) => <div key={String(row.code || index)} className="flex items-center justify-between px-5 py-3 text-sm"><span>{String(row.name)}</span><strong>{formatBRL(String(row.amount))}</strong></div>)}</div> : <EmptyState title="Sem recebimentos" description="Nenhum recebimento finalizado no período." />}</section><section className="card p-5"><h2 className="text-sm font-bold">Cancelamentos</h2><div className="mt-4 flex items-end justify-between gap-4"><div><span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Operações</span><strong className="mt-1 block text-xl">{String(cancellations.count || 0)}</strong></div><div className="text-right"><span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Valor estornado</span><strong className="mt-1 block text-xl text-danger">{formatBRL(String(cancellations.value || "0"))}</strong></div></div></section></div>;
}

function SummaryWarnings({ kind, summary }: { kind: ReportKind; summary: Record<string, unknown> }) {
  const warnings: Array<[string, unknown]> = [];
  if (["overview", "sales"].includes(kind)) warnings.push(["Delta de pagamentos das vendas", summary.payment_reconciliation_delta]);
  if (kind === "receipts") warnings.push(["Delta de reconciliação operacional", summary.reconciliation_delta]);
  if (kind === "discounts") warnings.push(["Delta da reconstrução dos descontos", summary.discount_reconstruction_delta], ["Delta da reconstrução do total recebido", summary.received_reconstruction_delta]);
  if (kind === "consumptions") warnings.push(["Delta de pagamentos das consumações", summary.payment_reconciliation_delta]);
  if (kind === "cancellations") warnings.push(["Delta dos valores revertidos", summary.reconciliation_delta]);
  if (kind === "cash") warnings.push(["Delta de reconciliação operacional do período", summary.reconciliation_delta]);
  if (kind === "result") warnings.push(["Delta de pagamentos das vendas", summary.payment_reconciliation_delta], ["Delta de reconciliação operacional", summary.operational_reconciliation_delta]);
  const visible = warnings.filter(([, value]) => hasDelta(value));
  if (!visible.length) return null;
  return <div className="space-y-2">{visible.map(([label, value]) => <ReconciliationWarning key={label} label={label} value={value} />)}</div>;
}

function DiscountReconstruction({ summary }: { summary: Record<string, unknown> }) {
  const parts: Array<[string, unknown, string]> = [
    ["Bruto", summary.gross, ""],
    ["Promoções", summary.promotion_discount, "-"],
    ["Desconto por item", summary.item_discount, "-"],
    ["Desconto na conta", summary.account_discount, "-"],
    ["Faturamento efetivo", summary.effective_revenue, "="],
    ["Taxa de serviço", summary.service_fee, "+"],
    ["Total recebido em vendas", summary.total_received_sales, "="],
  ];
  return <section className="card overflow-hidden"><div className="card-header"><div><h2 className="text-sm font-bold">Reconstrução financeira</h2><p className="mt-1 text-[11px] text-slate-500">Bruto - promoção - item - conta = faturamento efetivo; + taxa = total recebido.</p></div></div><div className="grid gap-px bg-slate-100 sm:grid-cols-2 xl:grid-cols-7">{parts.map(([label, value, operator]) => <div key={label} className="bg-white p-4"><span className="text-[10px] font-bold uppercase tracking-wide text-slate-500">{operator} {label}</span><strong className="mt-2 block text-base">{formatBRL(String(value || "0"))}</strong></div>)}</div></section>;
}

function ConsumptionFinancials({ summary }: { summary: Record<string, unknown> }) {
  const payments = rows(summary.payment_totals);
  return <section className="card overflow-hidden"><div className="card-header"><div><h2 className="text-sm font-bold">Pagamentos das consumações</h2><p className="mt-1 text-[11px] text-slate-500">Valores cobrados distribuídos por forma de pagamento.</p></div></div>{payments.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Forma</th><th>Valor recebido</th></tr></thead><tbody>{payments.map((row, index) => <tr key={String(row.code || index)}><td><strong>{String(row.name || row.code)}</strong></td><td>{formatBRL(String(row.amount || "0"))}</td></tr>)}</tbody></table></div> : <EmptyState title="Sem pagamentos" description="Nenhuma consumação cobrada por forma de pagamento." />}</section>;
}

function FilteredMethodNotice({ summary }: { summary: Record<string, unknown> }) {
  const method = summary.filtered_payment_method as Record<string, unknown> | undefined;
  if (!method) return null;
  return <div className="rounded-md border border-info/30 bg-info-surface px-4 py-3 text-sm text-info-strong"><strong>Subtotal específico de {String(method.name || method.code)}: {formatBRL(String(method.subtotal || "0"))}.</strong> Este subtotal filtra a forma de pagamento e não representa faturamento integral.</div>;
}

const userTypeLabels: Record<string, string> = { employee: "Funcionário", promoter: "Promoter", dj: "DJ", artist: "Artista", other: "Outro", not_informed: "Não informado" };

function ConsumptionGroups({ summary }: { summary: Record<string, unknown> }) {
  const groups: Array<[string, Array<Record<string, unknown>>, (row: Record<string, unknown>) => string]> = [
    ["Por beneficiário", rows(summary.beneficiary_groups), (row) => String((row.beneficiary as { name?: string })?.name || "Não informado")],
    ["Por tipo de beneficiário", rows(summary.user_type_groups), (row) => userTypeLabels[String(row.user_type)] || String(row.user_type)],
  ];
  return <div className="grid gap-5 xl:grid-cols-2">{groups.map(([title, list, label]) => <section key={title} className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">{title}</h2></div>{list.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>{title.replace("Por ", "")}</th><th>Operações</th><th>Referência</th><th>Cobrado</th><th>Benefício</th></tr></thead><tbody>{list.map((row, index) => <tr key={`${title}-${index}`}><td><strong>{label(row)}</strong></td><td>{String(row.count)}</td><td>{formatBRL(String(row.reference))}</td><td>{formatBRL(String(row.charged))}</td><td>{formatBRL(String(row.benefit))}</td></tr>)}</tbody></table></div> : <EmptyState title="Sem agrupamentos" description="Nenhuma consumação finalizada no período." />}</section>)}</div>;
}

function WithdrawalCategories({ summary }: { summary: Record<string, unknown> }) {
  const categories = rows(summary.by_category);
  if (!categories.length) return null;
  return <section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Resumo por categoria</h2></div><div className="table-wrap"><table className="data-table"><thead><tr><th>Categoria</th><th>Movimentos</th><th>Valor</th></tr></thead><tbody>{categories.map((row, index) => <tr key={String(row.category || index)}><td><strong>{String(row.category_label || row.category)}</strong></td><td>{String(row.count)}</td><td>{formatBRL(String(row.amount))}</td></tr>)}</tbody></table></div></section>;
}

function CashSummarySections({ summary }: { summary: Record<string, unknown> }) {
  const payments = rows(summary.payment_totals);
  return <div className="space-y-5"><div className="grid gap-5 lg:grid-cols-3"><section className="card p-5 text-sm"><h2 className="font-bold">Vendas no período solicitado</h2><div className="mt-4 space-y-2"><p className="flex justify-between"><span>Operações</span><strong>{String(summary.sales_count || 0)}</strong></p><p className="flex justify-between"><span>Faturamento efetivo</span><strong>{formatBRL(String(summary.effective_revenue || "0"))}</strong></p><p className="flex justify-between"><span>Taxa de serviço</span><strong>{formatBRL(String(summary.service_fee || "0"))}</strong></p><p className="flex justify-between border-t border-slate-100 pt-2"><span>Recebido em vendas</span><strong>{formatBRL(String(summary.sales_received || "0"))}</strong></p>{summary.commission !== undefined && <p className="flex justify-between text-danger"><span>Comissão histórica (custo)</span><strong>{formatBRL(String(summary.commission))}</strong></p>}</div></section><section className="card p-5 text-sm"><h2 className="font-bold">Consumações no período solicitado</h2><div className="mt-4 space-y-2"><p className="flex justify-between"><span>Operações</span><strong>{String(summary.consumption_count || 0)}</strong></p><p className="flex justify-between"><span>Consumações cobradas</span><strong>{formatBRL(String(summary.consumption_charged || "0"))}</strong></p></div></section><section className="card p-5 text-sm"><h2 className="font-bold">Eventos financeiros do período</h2><div className="mt-4 space-y-2"><p className="flex justify-between"><span>Recebimento bruto</span><strong>{formatBRL(String(summary.payment_totals ? rows(summary.payment_totals).reduce((total, row) => total + money(row.gross_received), 0) : 0))}</strong></p><p className="flex justify-between text-danger"><span>Reversões</span><strong>- {formatBRL(String(summary.reversals || "0"))}</strong></p><p className="flex justify-between border-t border-slate-100 pt-2"><span>Recebimento operacional</span><strong>{formatBRL(String(summary.operational_received || "0"))}</strong></p><p className="flex justify-between"><span>Entradas manuais</span><strong>{formatBRL(String(summary.manual_entries || "0"))}</strong></p><p className="flex justify-between text-danger"><span>Sangrias</span><strong>- {formatBRL(String(summary.withdrawals || "0"))}</strong></p></div></section></div><section className="card overflow-hidden"><div className="card-header"><div><h2 className="text-sm font-bold">Fontes de recebimento no período solicitado</h2><p className="mt-1 text-[11px] text-slate-500">Vendas + consumações = bruto; bruto - reversões = líquido.</p></div></div>{payments.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Forma</th><th>Vendas</th><th>Consumações</th><th>Bruto</th><th>Reversões</th><th>Líquido</th></tr></thead><tbody>{payments.map((row, index) => <tr key={String(row.code || index)}><td><strong>{String(row.name)}</strong></td><td>{formatBRL(String(row.commercial_received || "0"))}</td><td>{formatBRL(String(row.consumption_received || "0"))}</td><td>{formatBRL(String(row.gross_received || "0"))}</td><td className="text-danger">{formatBRL(String(row.reversals || "0"))}</td><td><strong>{formatBRL(String(row.net_received || "0"))}</strong></td></tr>)}</tbody></table></div> : <EmptyState title="Sem recebimentos" description="Nenhum evento de pagamento no período solicitado." />}</section></div>;
}

function CashTable({ data, canViewCash }: { data: ReportResponse<Record<string, unknown>>; canViewCash: boolean }) {
  if (!data.results.length) return <EmptyState title="Sem sessões" description="Nenhuma sessão intersecta o período." />;
  return <div className="table-wrap"><table className="data-table"><thead><tr><th>Sessão</th><th>Status</th><th>Período</th><th>Vendas</th><th>Consumações</th><th>Gaveta da sessão completa</th><th>Informado</th><th>Diferença</th></tr></thead><tbody>{data.results.map((row) => {
    const register = row.register as { name?: string };
    const operational = row.operational_summary as Record<string, unknown>;
    const sales = (operational?.sales || {}) as Record<string, unknown>;
    const consumptions = (operational?.consumptions || {}) as Record<string, unknown>;
    return <tr key={String(row.id)}><td>{canViewCash ? <Link className="font-bold text-primary" href={`/caixas/sessoes/${row.id}`}>{register.name} #{String(row.id)}</Link> : <strong>{register.name} #{String(row.id)}</strong>}</td><td><StatusBadge value={row.status} /></td><td>{formatDate(String(row.opened_at))}<small className="block text-slate-500">{row.closed_at ? `até ${formatDate(String(row.closed_at))}` : "Em andamento"}</small></td><td>{String(sales.count || 0)}<small className="block text-slate-500">{formatBRL(String(sales.effective_revenue || "0"))} + {formatBRL(String(sales.service_fee || "0"))} de taxa</small></td><td>{String(consumptions.count || 0)}<small className="block text-slate-500">{formatBRL(String(consumptions.charged || "0"))} cobrados</small></td><td><strong>{formatBRL(String(row.expected || "0"))}</strong><small className="block text-slate-500">Vendas {formatBRL(String(row.sale_cash || "0"))} · Consumações {formatBRL(String(row.consumption_cash || "0"))} · Reversões {formatBRL(String(row.cash_reversals || "0"))}</small></td><td>{row.informed == null ? "-" : formatBRL(String(row.informed))}</td><td>{row.difference == null ? "-" : formatBRL(String(row.difference))}</td></tr>;
  })}</tbody></table></div>;
}

function StockConsumption({ data }: { data: ReportResponse<Record<string, unknown>> }) {
  const products = rows(data.summary.products);
  const showCost = products.some((row) => row.estimated_cost !== undefined);
  return <div className="space-y-5"><section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Resumo por produto físico</h2></div>{products.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Produto</th><th>Consumo bruto</th><th>Devoluções</th><th>Consumo líquido</th>{showCost && <th>Custo estimado pelo custo atual</th>}</tr></thead><tbody>{products.map((row, index) => { const product = row.product as { name?: string; unit?: string }; return <tr key={index}><td><strong>{product.name}</strong></td><td>{formatQuantity(String(row.gross_quantity))} {product.unit?.toUpperCase()}</td><td>{formatQuantity(String(row.returned_quantity))}</td><td>{formatQuantity(String(row.net_quantity))}</td>{showCost && <td>{formatBRL(String(row.estimated_cost || "0"))}</td>}</tr>; })}</tbody></table></div> : <EmptyState title="Sem consumo físico" description="Nenhum movimento de consumo no período." />}</section><section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Movimentações detalhadas</h2></div>{data.results.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Data</th><th>Produto</th><th>Origem</th><th>Natureza</th><th>Quantidade</th></tr></thead><tbody>{data.results.map((row, index) => { const product = row.product as { name?: string }; return <tr key={index}><td>{formatDate(String(row.created_at))}</td><td>{product.name}</td><td>{domainLabel(row.origin)}</td><td>{domainLabel(row.nature)}</td><td>{formatQuantity(String(row.quantity))}</td></tr>; })}</tbody></table></div> : <EmptyState title="Sem movimentações" description="Nenhum detalhe no período." />}</section></div>;
}

function ResultStatement({ summary }: { summary: Record<string, unknown> }) {
  const lines: Array<[string, string, boolean?]> = [
    ["Valor bruto a preço de tabela", "gross"],
    ["(-) Descontos promocionais", "promotion_discount"],
    ["(-) Descontos manuais por item", "item_discount"],
    ["(-) Descontos manuais na conta", "account_discount"],
    ["= Faturamento efetivo", "effective_revenue", true],
    ["(+) Taxa de serviço", "service_fee"],
    ["= Total comercial recebido", "total_received_sales", true],
    ["(+) Consumações cobradas", "charged_consumption"],
    ["= Recebimento operacional", "operational_received", true],
    ["(-) CMV histórico de vendas", "historical_sales_cogs"],
    ["(-) CMV histórico de consumações", "historical_consumption_cogs"],
    ["(-) Comissão", "commission"],
    ["(-) Despesas operacionais", "operating_expenses"],
    ["(-) Custo fixo rateado", "fixed_cost"],
    ["= Resultado estimado", "estimated_result", true],
  ];
  return <div className="p-5"><div className="mx-auto max-w-2xl space-y-1">{lines.filter(([, key]) => summary[key] !== undefined).map(([label, key, strong]) => <div key={key} className={`flex items-center justify-between gap-4 rounded-md px-4 py-3 ${strong ? "mt-2 bg-primary/10 text-dark" : "border-b border-slate-100"}`}><span className={strong ? "font-bold" : "text-sm"}>{label}</span><strong>{formatBRL(String(summary[key] || "0"))}</strong></div>)}<div className="flex justify-between px-4 py-3"><span className="text-sm">Margem estimada</span><strong>{String(summary.margin || "0")}%</strong></div><p className="px-4 pt-3 text-xs text-slate-500">{String(summary.notice || "Estimativa operacional; não constitui DRE contábil.")}</p></div></div>;
}

function ReportBody({ kind, data, canViewSales, canViewConsumptions, canViewCash }: { kind: ReportKind; data: ReportResponse<Record<string, unknown>>; canViewSales: boolean; canViewConsumptions: boolean; canViewCash: boolean }) {
  if (kind === "products") return <div className="grid gap-5 xl:grid-cols-2"><section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Classificação por produto</h2></div><RankingTable kind={kind} summary={data.summary} /></section><CategoryRanking summary={data.summary} /></div>;
  if (kind === "receipts") return <div className="space-y-5"><FilteredMethodNotice summary={data.summary} /><section className="card overflow-hidden"><div className="card-header"><div><h2 className="text-sm font-bold">Recebimentos por forma</h2><p className="mt-1 text-[11px] text-slate-500">Vendas, consumações, reversões e recebimento líquido no mesmo recorte.</p></div></div><RankingTable kind={kind} summary={data.summary} /></section></div>;
  if (["operators", "sellers", "commissions"].includes(kind)) return <section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Detalhamento</h2></div><RankingTable kind={kind} summary={data.summary} /></section>;
  if (kind === "stock-consumption") return <StockConsumption data={data} />;
  if (kind === "cash") return <div className="space-y-5"><CashSummarySections summary={data.summary} /><section className="card overflow-hidden"><div className="card-header"><div><h2 className="text-sm font-bold">Sessões de caixa</h2><p className="mt-1 text-[11px] text-slate-500">Resumo superior usa eventos do período solicitado; cada linha abaixo mostra valores da sessão completa.</p></div></div><CashTable data={data} canViewCash={canViewCash} /></section></div>;
  if (kind === "result") return <section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Demonstrativo operacional</h2></div><ResultStatement summary={data.summary} /></section>;
  if (kind === "withdrawals") return <div className="space-y-5"><WithdrawalCategories summary={data.summary} /><section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Sangrias detalhadas</h2></div>{data.results.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Data</th><th>Categoria</th><th>Beneficiário</th><th>Motivo</th><th>Registrado por</th><th>Valor</th></tr></thead><tbody>{data.results.map((row) => { const beneficiary = row.beneficiary as { name?: string } | null; const operator = row.operator as { name?: string }; return <tr key={String(row.id)}><td>{formatDate(String(row.created_at))}</td><td>{String(row.category_label)}</td><td>{beneficiary?.name || "-"}</td><td>{String(row.reason)}</td><td>{operator?.name}</td><td>{formatBRL(String(row.amount))}</td></tr>; })}</tbody></table></div> : <EmptyState title="Sem sangrias" description="Nenhuma sangria no período." />}</section></div>;
  const operations = <section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Operações</h2></div><SalesTable kind={kind} data={data} canViewSales={canViewSales} canViewConsumptions={canViewConsumptions} /></section>;
  if (["sales", "overview"].includes(kind)) return <div className="space-y-5"><SalesSections summary={data.summary} />{operations}</div>;
  if (kind === "discounts") return <div className="space-y-5"><DiscountReconstruction summary={data.summary} />{operations}</div>;
  if (kind === "consumptions") return <div className="space-y-5"><ConsumptionFinancials summary={data.summary} /><ConsumptionGroups summary={data.summary} />{operations}</div>;
  return operations;
}

export function DedicatedReport({ kind }: { kind: ReportKind }) {
  const config = configs[kind];
  const { currentBranch, hasPermission } = useAuth();
  const context = useRef(currentBranch?.id || 0);
  context.current = currentBranch?.id || 0;
  const [period, setPeriod] = useState(initialPeriod);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [appliedFilters, setAppliedFilters] = useState<Record<string, string>>({});
  const [options, setOptions] = useState<ReportsOptions | null>(null);
  const [data, setData] = useState<ReportResponse<Record<string, unknown>> | null>(null);
  const [prices, setPrices] = useState<ProductPriceComparison | null>(null);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState(false);
  const allowed = hasPermission(config.permission);

  function params(nextPeriod = period, nextFilters = appliedFilters) {
    return new URLSearchParams({
      start_datetime: nextPeriod.start,
      end_datetime: nextPeriod.end,
      ...(config.endpoint === "sales" ? { scope: kind } : {}),
      ...Object.fromEntries(Object.entries(nextFilters).filter(([, value]) => value)),
    });
  }

  async function load(nextPeriod = period, nextFilters = filters, token = context.current) {
    if (!currentBranch || !allowed) return;
    if (kind === "prices") setPrices(null);
    else setData(null);
    setError("");
    try {
      if (kind === "prices") {
        const query = new URLSearchParams(Object.entries(nextFilters).filter(([, value]) => value));
        const result = await http.get<ProductPriceComparison>(`products/price-comparison/${query.size ? `?${query}` : ""}`);
        if (context.current === token) {
          setPrices(result);
          setAppliedFilters(nextFilters);
          window.history.replaceState(null, "", `${window.location.pathname}${query.size ? `?${query}` : ""}`);
        }
        return;
      }
      const query = params(nextPeriod, nextFilters);
      const result = await http.get<ReportResponse<Record<string, unknown>>>(`reports/${config.endpoint}/?${query}`);
      if (context.current === token) {
        setData(result);
        setAppliedFilters(nextFilters);
        window.history.replaceState(null, "", `${window.location.pathname}?${query}`);
      }
    } catch (caught) {
      if (context.current === token) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar o relatório.");
    }
  }

  async function loadPage(path: string, token = context.current) {
    try {
      const result = await http.get<ReportResponse<Record<string, unknown>>>(path);
      if (context.current === token) setData(result);
    } catch {
      if (context.current === token) setError("Não foi possível trocar a página.");
    }
  }

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const start = query.get("start_datetime");
    const end = query.get("end_datetime");
    const nextPeriod = start && end ? { start, end } : initialPeriod();
    const nextFilters = Object.fromEntries([...query.entries()].filter(([key]) => !["start_datetime", "end_datetime", "branch", "scope", "export", "page", "page_size"].includes(key)));
    setPeriod(nextPeriod);
    setFilters(nextFilters);
    setAppliedFilters(nextFilters);
    void load(nextPeriod, nextFilters, context.current);
    const token = context.current;
    void http.get<ReportsOptions>("reports/options/").then((result) => {
      if (context.current === token) setOptions(result);
    }).catch(() => {
      if (context.current === token) setOptions(null);
    });
  }, [currentBranch?.id, kind, allowed]);

  async function download() {
    if (!currentBranch || kind === "prices") return;
    setDownloading(true);
    try {
      const base = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:18000/api/v1").replace(/\/$/, "");
      const query = params();
      query.set("export", "csv");
      const response = await fetch(`${base}/reports/${config.endpoint}/?${query}`, { credentials: "include", headers: { "X-Branch-ID": String(currentBranch.id) } });
      if (!response.ok) throw new Error();
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${kind}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("Não foi possível exportar este relatório.");
    } finally {
      setDownloading(false);
    }
  }

  if (!allowed) return <div className="p-6"><Alert message="Você não possui permissão para este relatório." /></div>;
  const productKinds = ["sales", "overview", "products", "receipts", "operators", "sellers", "commissions", "discounts", "consumptions", "stock-consumption", "cancellations"];
  return <><PageHeader title={config.title} description={config.description} action={<div className="flex gap-2"><Link className="btn btn-secondary" href="/relatorios">Central</Link>{kind !== "prices" && hasPermission(permissions.exportReports) && <Button variant="secondary" loading={downloading} onClick={() => void download()}><Download className="size-4" />Exportar</Button>}</div>} /><div className="space-y-5 p-4 sm:p-6 lg:p-8">{error && <Alert message={error} />}{kind === "prices" ? <section className="card p-4"><div className="mb-3 flex items-center gap-2 text-xs font-bold"><Filter className="size-4 text-primary" />Filtros</div><div className="grid gap-3 md:grid-cols-3"><Field label="Categoria"><Select value={filters.category || ""} onChange={(event) => setFilters((current) => ({ ...current, category: event.target.value }))}><option value="">Todas</option>{options?.categories.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field><Field label="Produto"><Select value={filters.product || ""} onChange={(event) => setFilters((current) => ({ ...current, product: event.target.value }))}><option value="">Todos</option>{options?.products.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field><Field label="Status do produto"><Select value={filters.status || ""} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}><option value="">Todos</option><option value="active">Ativo</option><option value="inactive">Inativo</option></Select></Field></div><div className="mt-4 flex justify-end gap-2"><Button variant="secondary" onClick={() => { setFilters({}); void load(period, {}); }}>Limpar filtros</Button><Button onClick={() => void load(period, filters)}>Aplicar filtros</Button></div></section> : <section className="card p-4"><div className="mb-3 flex items-center gap-2 text-xs font-bold"><Filter className="size-4 text-primary" />Filtros</div><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4"><PeriodFilter className="md:col-span-2 xl:col-span-4" value={period} onApply={(next) => { setPeriod(next); void load(next); }} onClear={(next) => { setPeriod(next); setFilters({}); void load(next, {}); }} />
    {productKinds.includes(kind) && <Field label="Categoria"><Select value={filters.category || ""} onChange={(event) => setFilters((current) => ({ ...current, category: event.target.value }))}><option value="">Todas</option>{options?.categories.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>}
    {productKinds.includes(kind) && <Field label="Produto"><Select value={filters.product || ""} onChange={(event) => setFilters((current) => ({ ...current, product: event.target.value }))}><option value="">Todos</option>{options?.products.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>}
    {["sales", "overview", "operators", "discounts", "cancellations", "cash", "withdrawals"].includes(kind) && <Field label="Operador"><Select value={filters.operator || ""} onChange={(event) => setFilters((current) => ({ ...current, operator: event.target.value }))}><option value="">Todos</option>{options?.operators.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>}
    {["sales", "overview", "sellers", "commissions", "discounts", "cancellations"].includes(kind) && <Field label="Atendente"><Select value={filters.seller || ""} onChange={(event) => setFilters((current) => ({ ...current, seller: event.target.value }))}><option value="">Todos</option>{options?.sellers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>}
    {["sales", "overview", "receipts"].includes(kind) && <Field label="Forma de pagamento"><Select value={filters.payment_method || String(options?.payment_methods.find((item) => item.code === filters.payment_method_code)?.id || "")} onChange={(event) => setFilters((current) => ({ ...current, payment_method: event.target.value, payment_method_code: "" }))}><option value="">Todas</option>{options?.payment_methods.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>}
    {["sales", "overview"].includes(kind) && <Field label="Status"><Select value={filters.status || ""} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}><option value="">Todos</option>{options?.sale_statuses.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</Select></Field>}
    {["sales", "overview"].includes(kind) && <Field label="Dia da semana"><Select value={filters.weekday || ""} onChange={(event) => setFilters((current) => ({ ...current, weekday: event.target.value }))}><option value="">Todos</option>{["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"].map((label, index) => <option key={label} value={index}>{label}</option>)}</Select></Field>}
    {["sales", "overview"].includes(kind) && <Field label="Hora"><Select value={filters.hour || ""} onChange={(event) => setFilters((current) => ({ ...current, hour: event.target.value }))}><option value="">Todas</option>{Array.from({ length: 24 }, (_, hour) => <option key={hour} value={hour}>{String(hour).padStart(2, "0")}:00</option>)}</Select></Field>}
    {kind === "consumptions" && <Field label="Tipo de beneficiário"><Select value={filters.user_type || ""} onChange={(event) => setFilters((current) => ({ ...current, user_type: event.target.value }))}><option value="">Todos</option>{options?.user_types.map((item) => <option key={item.value} value={item.value}>{userTypeLabels[item.value] || item.label}</option>)}</Select></Field>}
    {["consumptions", "withdrawals"].includes(kind) && <Field label="Beneficiário"><Select value={filters.beneficiary || ""} onChange={(event) => setFilters((current) => ({ ...current, beneficiary: event.target.value }))}><option value="">Todos</option>{options?.beneficiaries.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>}
    {kind === "consumptions" && <Field label="Status"><Select value={filters.status || ""} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}><option value="">Todos</option>{options?.sale_statuses.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</Select></Field>}
    {kind === "stock-consumption" && <Field label="Origem"><Select value={filters.origin || ""} onChange={(event) => setFilters((current) => ({ ...current, origin: event.target.value }))}><option value="">Todas</option><option value="sale">Venda</option><option value="consumption">Consumação</option><option value="manual_exit">Saída manual</option><option value="reversal">Reversão/cancelamento</option></Select></Field>}
    {["cash", "withdrawals"].includes(kind) && <Field label="Caixa"><Select value={filters.cash_register || ""} onChange={(event) => setFilters((current) => ({ ...current, cash_register: event.target.value }))}><option value="">Todos</option>{options?.cash_registers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>}
    {kind === "withdrawals" && <Field label="Categoria da sangria"><Select value={filters.category || ""} onChange={(event) => setFilters((current) => ({ ...current, category: event.target.value }))}><option value="">Todas</option>{options?.withdrawal_categories.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</Select></Field>}
    {kind === "cash" && <Field label="Status da sessão"><Select value={filters.status || ""} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}><option value="">Todos</option><option value="open">Aberta</option><option value="closed">Fechada</option></Select></Field>}
    {kind === "result" && <Field label="Sessão de caixa"><Select value={filters.cash_session || ""} onChange={(event) => setFilters((current) => ({ ...current, cash_session: event.target.value }))}><option value="">Todas</option>{options?.cash_sessions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>}
  </div></section>}
  {kind === "prices" ? <section className="card overflow-hidden">{!prices ? <TableLoading /> : prices.products.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Produto</th><th>Preço padrão</th>{prices.branches.map((branch) => <th key={branch.id}>{branch.name}</th>)}</tr></thead><tbody>{prices.products.map((product) => <tr key={product.id}><td><strong>{product.name}</strong><small className="block text-slate-500">{product.internal_code}</small></td><td>{formatBRL(product.default_price)}</td>{prices.branches.map((branch) => <td key={branch.id}>{formatBRL(product.prices[String(branch.id)] || product.default_price)}<small className="block text-slate-500">{product.prices[String(branch.id)] ? "Preço da filial" : "Preço padrão"}</small></td>)}</tr>)}</tbody></table></div> : <EmptyState title="Sem produtos" description="Nenhum preço disponível para os filtros selecionados." />}</section> : !data ? <section className="card"><TableLoading /></section> : <><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{reportKpis(kind, data.summary).map(([label, value, format]) => <Kpi key={label} label={label} value={value} format={format} />)}</div><SummaryWarnings kind={kind} summary={data.summary} /><ReportBody kind={kind} data={data} canViewSales={hasPermission(permissions.viewSale) || hasPermission(permissions.cancelSale)} canViewConsumptions={hasPermission(permissions.viewConsumption) || hasPermission(permissions.cancelConsumption)} canViewCash={hasPermission(permissions.viewCashRegister)} />{data.count > data.results.length && <Pagination count={data.count} next={data.next} previous={data.previous} onPage={(path) => void loadPage(path)} />}</>}
  </div></>;
}
