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
  products: { title: "Produtos & Performance", description: "Performance comercial por produto e categoria.", endpoint: "sales", permission: permissions.viewProductsReport },
  receipts: { title: "Recebimentos", description: "Distribuição do total recebido por forma de pagamento.", endpoint: "sales", permission: permissions.viewReceiptsReport },
  operators: { title: "Operadores", description: "Faturamento processado por operador de caixa.", endpoint: "sales", permission: permissions.viewTeamReport },
  sellers: { title: "Atendentes", description: "Faturamento e ticket por atendente responsável.", endpoint: "sales", permission: permissions.viewTeamReport },
  commissions: { title: "Comissões", description: "Snapshots de comissão atribuídos aos atendentes.", endpoint: "sales", permission: permissions.viewCommission },
  discounts: { title: "Descontos", description: "Descontos manuais por item, na conta e promoções.", endpoint: "sales", permission: permissions.viewDiscountsReport },
  consumptions: { title: "Consumações & Cortesias", description: "Referência, valor cobrado e benefício operacional.", endpoint: "consumptions", permission: permissions.viewConsumptionsReport },
  cash: { title: "Caixa", description: "Sessões por interseção temporal e reconciliação completa.", endpoint: "cash", permission: permissions.viewCashReport },
  withdrawals: { title: "Sangrias", description: "Saídas de gaveta, beneficiários e impacto no resultado.", endpoint: "withdrawals", permission: permissions.viewWithdrawalsReport },
  "stock-consumption": { title: "Consumo de estoque", description: "Resumo físico e movimentos reais de saída e reversão.", endpoint: "stock-consumption", permission: permissions.viewStockConsumptionReport },
  cancellations: { title: "Cancelamentos & Estornos", description: "Operações canceladas no período do cancelamento.", endpoint: "cancellations", permission: permissions.viewCancellationsReport },
  prices: { title: "Preços por filial", description: "Comparação entre preço padrão e overrides por filial.", endpoint: "prices", permission: permissions.viewPricesReport },
  result: { title: "Resultado estimado", description: "Receita, CMV histórico, despesas e margem operacional.", endpoint: "operational-result", permission: permissions.viewOperationalResult },
};

function initialPeriod(): PeriodValue {
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, "0");
  return {
    start: `${now.getFullYear()}-${pad(now.getMonth() + 1)}-01T00:00:00`,
    end: `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T23:59:59`,
  };
}

function rows(value: unknown) {
  return Array.isArray(value) ? value as Array<Record<string, unknown>> : [];
}

function money(value: unknown) {
  return Number(value || 0);
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
    overview: [["Faturamento efetivo", summary.effective_revenue, "money"], ["Vendas", summary.count, "number"], ["Ticket médio", summary.average, "money"], ["Descontos totais", summary.total_discount, "money"]],
    sales: [["Faturamento efetivo", summary.effective_revenue, "money"], ["Vendas", summary.count, "number"], ["Ticket médio", summary.average, "money"], ["Total cobrado", summary.customer_total, "money"]],
    products: [["Faturamento dos produtos", productRows.reduce((total, row) => total + money(row.revenue), 0), "money"], ["Unidades vendidas", productRows.reduce((total, row) => total + money(row.quantity), 0), "quantity"], ["Produtos vendidos", productRows.length, "number"], ["Categorias", rows(summary.category_ranking).length, "number"]],
    receipts: [["Total recebido", paymentRows.reduce((total, row) => total + money(row.amount), 0), "money"], ["Formas utilizadas", paymentRows.length, "number"]],
    operators: [["Faturamento processado", operatorRows.reduce((total, row) => total + money(row.effective_revenue), 0), "money"], ["Vendas processadas", operatorRows.reduce((total, row) => total + money(row.count), 0), "number"], ["Operadores", operatorRows.length, "number"]],
    sellers: [["Faturamento atendido", sellerRows.reduce((total, row) => total + money(row.effective_revenue), 0), "money"], ["Vendas", sellerRows.reduce((total, row) => total + money(row.count), 0), "number"], ["Atendentes", sellerRows.length, "number"]],
    commissions: [["Comissão gerada", summary.commission, "money"], ["Vendas com atendente", sellerRows.reduce((total, row) => total + money(row.count), 0), "number"], ["Atendentes", sellerRows.filter((row) => money(row.commission) > 0).length, "number"], ["Faturamento base", sellerRows.reduce((total, row) => total + money(row.effective_revenue), 0), "money"]],
    discounts: [["Desconto na conta", summary.account_discount, "money"], ["Desconto por item", summary.item_discount, "money"], ["Promoções", summary.promotion_discount, "money"], ["Vendas afetadas", summary.count, "number"]],
    consumptions: [["Valor de referência", summary.reference, "money"], ["Valor cobrado", summary.charged, "money"], ["Benefício concedido", summary.subsidy, "money"], ["Quantidade consumida", summary.quantity, "quantity"]],
    cash: [["Sessões", summary.count, "number"], ["Faturamento efetivo", summary.effective_revenue, "money"], ["Vendas", summary.sales_count, "number"], ["Taxa de serviço", summary.service_fee, "money"]],
    withdrawals: [["Total de sangrias", summary.amount, "money"], ["Movimentos", summary.count, "number"]],
    "stock-consumption": [["Consumo bruto", summary.gross_quantity, "quantity"], ["Devoluções", summary.returned_quantity, "quantity"], ["Consumo líquido", summary.net_quantity, "quantity"], ["Produtos físicos", stockRows.length, "number"]],
    cancellations: [["Valor estornado", summary.value, "money"], ["Cancelamentos", summary.count, "number"]],
    result: [["Faturamento efetivo", summary.effective_revenue, "money"], ["CMV histórico", summary.cogs, "money"], ["Resultado estimado", summary.result, "money"], ["Margem estimada", summary.margin, "percent"]],
  };
  return definitions[kind] || [];
}

function StatusBadge({ value }: { value: unknown }) {
  const status = String(value || "");
  const tone = status === "finalized" || status === "open" ? "bg-success/10 text-emerald-700" : status === "cancelled" ? "bg-danger/10 text-red-700" : "bg-slate-100 text-slate-700";
  return <span className={`inline-flex rounded-full px-2 py-1 text-[10px] font-bold ${tone}`}>{domainLabel(status)}</span>;
}

function SalesTable({ kind, data }: { kind: ReportKind; data: ReportResponse<Record<string, unknown>> }) {
  if (!data.results.length) return <EmptyState title="Sem registros" description="Nenhuma operação encontrada no período." />;
  return <div className="table-wrap"><table className="data-table"><thead><tr><th>Operação</th><th>Data</th><th>Responsáveis</th><th>Status</th>{kind === "discounts" ? <><th>Por item</th><th>Na conta</th><th>Promoções</th></> : <th>{kind === "cancellations" ? "Valor estornado" : kind === "consumptions" ? "Valor cobrado" : "Total cobrado"}</th>}<th /></tr></thead><tbody>{data.results.map((row) => {
    const seller = row.seller as { name?: string } | null;
    const operator = row.operator as { name?: string } | null;
    const beneficiary = row.beneficiary as { name?: string } | null;
    return <tr key={String(row.id)}><td><strong>{String(row.sale_number)}</strong></td><td>{formatDate(String(row.cancelled_at || row.created_at))}</td><td>{kind === "consumptions" ? <span>Beneficiário: {beneficiary?.name || "-"}</span> : <><span className="block">Atendente: {seller?.name || "-"}</span><small className="text-slate-500">Operador: {operator?.name || "-"}</small></>}</td><td><StatusBadge value={row.status} /></td>{kind === "discounts" ? <><td>{formatBRL(String(row.item_discount_total || "0"))}</td><td>{formatBRL(String(row.discount || "0"))}</td><td>{formatBRL(String(row.promotion_discount_total || "0"))}</td></> : <td>{formatBRL(String(row.total || "0"))}</td>}<td className="text-right"><Link className="text-xs font-bold text-primary" href={`/vendas/${row.id}`}>Detalhes</Link></td></tr>;
  })}</tbody></table></div>;
}

function RankingTable({ kind, summary }: { kind: ReportKind; summary: Record<string, unknown> }) {
  const key = kind === "products" ? "product_ranking" : kind === "receipts" ? "payment_totals" : kind === "operators" ? "operator_groups" : "seller_groups";
  const list = rows(summary[key]);
  if (!list.length) return <EmptyState title="Sem dados" description="Nenhum resultado no período selecionado." />;
  const totalReceipts = list.reduce((total, row) => total + money(row.amount), 0);
  return <div className="table-wrap"><table className="data-table"><thead><tr><th>{kind === "products" ? "Produto" : kind === "receipts" ? "Forma de pagamento" : "Pessoa"}</th>{kind === "products" && <th>Unidades</th>}{["operators", "sellers", "commissions"].includes(kind) && <th>Vendas</th>}<th>{kind === "receipts" ? "Recebido" : "Faturamento efetivo"}</th>{kind === "receipts" && <th>Participação</th>}{["operators", "sellers"].includes(kind) && <th>Ticket médio</th>}{kind === "commissions" && <th>Comissão</th>}</tr></thead><tbody>{list.map((row, index) => {
    const user = row.user as { name?: string } | undefined;
    const label = row.product_name || row.name || user?.name || "-";
    const amount = row.revenue || row.amount || row.effective_revenue || "0";
    return <tr key={String(row.product_id || row.code || user?.name || index)}><td><strong>{String(label)}</strong>{kind === "products" && <small className="block text-slate-500">{String(row.internal_code || "")}</small>}</td>{kind === "products" && <td>{formatQuantity(String(row.quantity || "0"))}</td>}{["operators", "sellers", "commissions"].includes(kind) && <td>{String(row.count || 0)}</td>}<td>{formatBRL(String(amount))}</td>{kind === "receipts" && <td>{totalReceipts ? `${(money(row.amount) * 100 / totalReceipts).toFixed(1)}%` : "0%"}</td>}{["operators", "sellers"].includes(kind) && <td>{formatBRL(String(row.average || "0"))}</td>}{kind === "commissions" && <td><strong>{formatBRL(String(row.commission || "0"))}</strong></td>}</tr>;
  })}</tbody></table></div>;
}

function CashTable({ data }: { data: ReportResponse<Record<string, unknown>> }) {
  if (!data.results.length) return <EmptyState title="Sem sessões" description="Nenhuma sessão intersecta o período." />;
  return <div className="table-wrap"><table className="data-table"><thead><tr><th>Sessão</th><th>Status</th><th>Período</th><th>Vendas</th><th>Faturamento</th><th>Esperado em dinheiro</th><th>Informado</th><th>Diferença</th></tr></thead><tbody>{data.results.map((row) => {
    const register = row.register as { name?: string };
    const operational = row.operational_summary as Record<string, unknown>;
    const sales = (operational?.sales || {}) as Record<string, unknown>;
    return <tr key={String(row.id)}><td><Link className="font-bold text-primary" href={`/caixas/sessoes/${row.id}`}>{register.name} #{String(row.id)}</Link></td><td><StatusBadge value={row.status} /></td><td>{formatDate(String(row.opened_at))}<small className="block text-slate-500">{row.closed_at ? `até ${formatDate(String(row.closed_at))}` : "Em andamento"}</small></td><td>{String(sales.count || 0)}</td><td>{formatBRL(String(sales.effective_revenue || "0"))}</td><td>{formatBRL(String(row.expected || "0"))}</td><td>{row.informed == null ? "-" : formatBRL(String(row.informed))}</td><td>{row.difference == null ? "-" : formatBRL(String(row.difference))}</td></tr>;
  })}</tbody></table></div>;
}

function StockConsumption({ data }: { data: ReportResponse<Record<string, unknown>> }) {
  const products = rows(data.summary.products);
  return <div className="space-y-5"><section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Resumo por produto físico</h2></div>{products.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Produto</th><th>Consumo bruto</th><th>Devoluções</th><th>Consumo líquido</th></tr></thead><tbody>{products.map((row, index) => { const product = row.product as { name?: string; unit?: string }; return <tr key={index}><td><strong>{product.name}</strong></td><td>{formatQuantity(String(row.gross_quantity))} {product.unit?.toUpperCase()}</td><td>{formatQuantity(String(row.returned_quantity))}</td><td>{formatQuantity(String(row.net_quantity))}</td></tr>; })}</tbody></table></div> : <EmptyState title="Sem consumo físico" description="Nenhum movimento de consumo no período." />}</section><section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Movimentações detalhadas</h2></div>{data.results.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Data</th><th>Produto</th><th>Origem</th><th>Natureza</th><th>Quantidade</th></tr></thead><tbody>{data.results.map((row, index) => { const product = row.product as { name?: string }; return <tr key={index}><td>{formatDate(String(row.created_at))}</td><td>{product.name}</td><td>{domainLabel(row.origin)}</td><td>{domainLabel(row.nature)}</td><td>{formatQuantity(String(row.quantity))}</td></tr>; })}</tbody></table></div> : <EmptyState title="Sem movimentações" description="Nenhum detalhe no período." />}</section></div>;
}

function ResultStatement({ summary }: { summary: Record<string, unknown> }) {
  const lines: Array<[string, string, boolean?]> = [
    ["Valor bruto a preço de tabela", "gross"],
    ["(-) Descontos promocionais", "promotion_discount"],
    ["(-) Descontos manuais por item", "item_discount"],
    ["(-) Descontos manuais na conta", "account_discount"],
    ["= Faturamento efetivo", "effective_revenue", true],
    ["Taxa de serviço", "service_fee"],
    ["Total cobrado", "customer_total"],
    ["(-) CMV histórico", "cogs"],
    ["(-) Comissão", "commission"],
    ["(-) Despesas operacionais", "operating_expenses"],
    ["(-) Custo fixo rateado", "fixed_cost"],
    ["= Resultado estimado", "result", true],
  ];
  return <div className="p-5"><div className="mx-auto max-w-2xl space-y-1">{lines.filter(([, key]) => summary[key] !== undefined).map(([label, key, strong]) => <div key={key} className={`flex items-center justify-between gap-4 rounded-md px-4 py-3 ${strong ? "mt-2 bg-primary/10 text-dark" : "border-b border-slate-100"}`}><span className={strong ? "font-bold" : "text-sm"}>{label}</span><strong>{formatBRL(String(summary[key] || "0"))}</strong></div>)}<div className="flex justify-between px-4 py-3"><span className="text-sm">Margem estimada</span><strong>{String(summary.margin || "0")}%</strong></div><p className="px-4 pt-3 text-xs text-slate-500">{String(summary.notice || "Estimativa operacional; não constitui DRE contábil.")}</p></div></div>;
}

function ReportBody({ kind, data }: { kind: ReportKind; data: ReportResponse<Record<string, unknown>> }) {
  if (["products", "receipts", "operators", "sellers", "commissions"].includes(kind)) return <section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Detalhamento</h2></div><RankingTable kind={kind} summary={data.summary} /></section>;
  if (kind === "stock-consumption") return <StockConsumption data={data} />;
  if (kind === "cash") return <section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Sessões de caixa</h2></div><CashTable data={data} /></section>;
  if (kind === "result") return <section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Demonstrativo operacional</h2></div><ResultStatement summary={data.summary} /></section>;
  if (kind === "withdrawals") return <section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Sangrias detalhadas</h2></div>{data.results.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Data</th><th>Categoria</th><th>Beneficiário</th><th>Motivo</th><th>Registrado por</th><th>Valor</th></tr></thead><tbody>{data.results.map((row) => { const beneficiary = row.beneficiary as { name?: string } | null; const operator = row.operator as { name?: string }; return <tr key={String(row.id)}><td>{formatDate(String(row.created_at))}</td><td>{String(row.category_label)}</td><td>{beneficiary?.name || "-"}</td><td>{String(row.reason)}</td><td>{operator?.name}</td><td>{formatBRL(String(row.amount))}</td></tr>; })}</tbody></table></div> : <EmptyState title="Sem sangrias" description="Nenhuma sangria no período." />}</section>;
  return <section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Operações</h2></div><SalesTable kind={kind} data={data} /></section>;
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
    setData(null);
    setError("");
    try {
      if (kind === "prices") {
        const result = await http.get<ProductPriceComparison>("products/price-comparison/");
        if (context.current === token) setPrices(result);
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

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const start = query.get("start_datetime");
    const end = query.get("end_datetime");
    const nextPeriod = start && end ? { start, end } : initialPeriod();
    const nextFilters = Object.fromEntries([...query.entries()].filter(([key]) => !["start_datetime", "end_datetime", "branch", "scope"].includes(key)));
    setPeriod(nextPeriod);
    setFilters(nextFilters);
    setAppliedFilters(nextFilters);
    void load(nextPeriod, nextFilters, context.current);
    void http.get<ReportsOptions>("reports/options/").then(setOptions).catch(() => setOptions(null));
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
  return <><PageHeader title={config.title} description={config.description} action={<div className="flex gap-2"><Link className="btn btn-secondary" href="/relatorios">Central</Link>{kind !== "prices" && hasPermission(permissions.exportReports) && <Button variant="secondary" loading={downloading} onClick={() => void download()}><Download className="size-4" />Exportar</Button>}</div>} /><div className="space-y-5 p-4 sm:p-6 lg:p-8">{error && <Alert message={error} />}{kind !== "prices" && <section className="card p-4"><div className="mb-3 flex items-center gap-2 text-xs font-bold"><Filter className="size-4 text-primary" />Filtros</div><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4"><PeriodFilter className="md:col-span-2 xl:col-span-4" value={period} onApply={(next) => { setPeriod(next); void load(next); }} onClear={(next) => { setPeriod(next); setFilters({}); void load(next, {}); }} />
    {productKinds.includes(kind) && <Field label="Categoria"><Select value={filters.category || ""} onChange={(event) => setFilters((current) => ({ ...current, category: event.target.value }))}><option value="">Todas</option>{options?.categories.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>}
    {productKinds.includes(kind) && <Field label="Produto"><Select value={filters.product || ""} onChange={(event) => setFilters((current) => ({ ...current, product: event.target.value }))}><option value="">Todos</option>{options?.products.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>}
    {["sales", "overview", "operators", "discounts", "cancellations", "cash", "withdrawals"].includes(kind) && <Field label="Operador"><Select value={filters.operator || ""} onChange={(event) => setFilters((current) => ({ ...current, operator: event.target.value }))}><option value="">Todos</option>{options?.operators.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>}
    {["sales", "overview", "sellers", "commissions", "discounts", "cancellations"].includes(kind) && <Field label="Atendente"><Select value={filters.seller || ""} onChange={(event) => setFilters((current) => ({ ...current, seller: event.target.value }))}><option value="">Todos</option>{options?.sellers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>}
    {["sales", "overview", "receipts"].includes(kind) && <Field label="Forma de pagamento"><Select value={filters.payment_method || String(options?.payment_methods.find((item) => item.code === filters.payment_method_code)?.id || "")} onChange={(event) => setFilters((current) => ({ ...current, payment_method: event.target.value, payment_method_code: "" }))}><option value="">Todas</option>{options?.payment_methods.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>}
    {["sales", "overview"].includes(kind) && <Field label="Status"><Select value={filters.status || ""} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}><option value="">Todos</option>{options?.sale_statuses.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</Select></Field>}
    {["sales", "overview"].includes(kind) && <Field label="Dia da semana"><Select value={filters.weekday || ""} onChange={(event) => setFilters((current) => ({ ...current, weekday: event.target.value }))}><option value="">Todos</option>{["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"].map((label, index) => <option key={label} value={index}>{label}</option>)}</Select></Field>}
    {["sales", "overview"].includes(kind) && <Field label="Hora"><Select value={filters.hour || ""} onChange={(event) => setFilters((current) => ({ ...current, hour: event.target.value }))}><option value="">Todas</option>{Array.from({ length: 24 }, (_, hour) => <option key={hour} value={hour}>{String(hour).padStart(2, "0")}:00</option>)}</Select></Field>}
    {kind === "consumptions" && <Field label="Tipo de beneficiário"><Select value={filters.user_type || ""} onChange={(event) => setFilters((current) => ({ ...current, user_type: event.target.value }))}><option value="">Todos</option>{options?.user_types.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</Select></Field>}
    {["consumptions", "withdrawals"].includes(kind) && <Field label="Beneficiário"><Select value={filters.beneficiary || ""} onChange={(event) => setFilters((current) => ({ ...current, beneficiary: event.target.value }))}><option value="">Todos</option>{options?.beneficiaries.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>}
    {kind === "consumptions" && <Field label="Status"><Select value={filters.status || ""} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}><option value="">Todos</option>{options?.sale_statuses.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</Select></Field>}
    {kind === "stock-consumption" && <Field label="Origem"><Select value={filters.origin || ""} onChange={(event) => setFilters((current) => ({ ...current, origin: event.target.value }))}><option value="">Todas</option><option value="sale">Venda</option><option value="consumption">Consumação</option><option value="manual_exit">Saída manual</option><option value="reversal">Reversão/cancelamento</option></Select></Field>}
    {["cash", "withdrawals"].includes(kind) && <Field label="Caixa"><Select value={filters.cash_register || ""} onChange={(event) => setFilters((current) => ({ ...current, cash_register: event.target.value }))}><option value="">Todos</option>{options?.cash_registers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>}
    {kind === "withdrawals" && <Field label="Categoria da sangria"><Select value={filters.category || ""} onChange={(event) => setFilters((current) => ({ ...current, category: event.target.value }))}><option value="">Todas</option>{options?.withdrawal_categories.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</Select></Field>}
    {kind === "cash" && <Field label="Status da sessão"><Select value={filters.status || ""} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}><option value="">Todos</option><option value="open">Aberta</option><option value="closed">Fechada</option></Select></Field>}
    {kind === "result" && <Field label="Sessão de caixa"><Select value={filters.cash_session || ""} onChange={(event) => setFilters((current) => ({ ...current, cash_session: event.target.value }))}><option value="">Todas</option>{options?.cash_sessions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>}
  </div></section>}
  {kind === "prices" ? <section className="card overflow-hidden">{!prices ? <TableLoading /> : prices.products.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Produto</th><th>Preço padrão</th>{prices.branches.map((branch) => <th key={branch.id}>{branch.name}</th>)}</tr></thead><tbody>{prices.products.map((product) => <tr key={product.id}><td><strong>{product.name}</strong><small className="block text-slate-500">{product.internal_code}</small></td><td>{formatBRL(product.default_price)}</td>{prices.branches.map((branch) => <td key={branch.id}>{formatBRL(product.prices[String(branch.id)] || product.default_price)}<small className="block text-slate-500">{product.prices[String(branch.id)] ? "Preço da filial" : "Preço padrão"}</small></td>)}</tr>)}</tbody></table></div> : <EmptyState title="Sem produtos" description="Nenhum preço disponível." />}</section> : !data ? <section className="card"><TableLoading /></section> : <><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{reportKpis(kind, data.summary).map(([label, value, format]) => <Kpi key={label} label={label} value={value} format={format} />)}</div><ReportBody kind={kind} data={data} />{data.count > data.results.length && <Pagination count={data.count} next={data.next} previous={data.previous} onPage={(path) => http.get<ReportResponse<Record<string, unknown>>>(path).then(setData).catch(() => setError("Não foi possível trocar a página."))} />}</>}
  </div></>;
}
