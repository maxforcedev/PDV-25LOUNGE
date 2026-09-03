"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Filter, ReceiptText, Truck, WalletCards } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { PeriodFilter, type PeriodValue } from "@/components/period-filter";
import { ReportExportAction } from "@/components/report-export-action";
import { Alert, Button, EmptyState, Field, Input, Pagination, Select, TableLoading } from "@/components/ui";
import { formatDate, formatDecimalBRL as formatBRL } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { businessMonthToDate } from "@/lib/period";
import { permissions } from "@/lib/permissions";
import { payableStatusLabels, purchaseStatusLabels, purchaseTypeLabels } from "@/lib/purchases";
import { useAuth } from "@/providers/auth-provider";
import type { ReportResponse } from "@/types";

type ReportKind = "purchases" | "suppliers" | "payables";
type Row = Record<string, unknown>;
type SupplierOption = { id: number; name: string; status: string; historical: boolean };

const configs: Record<ReportKind, { title: string; description: string; endpoint: string; permission: string }> = {
  purchases: {
    title: "Compras",
    description: "Pedidos e entradas diretas da filial no período.",
    endpoint: "purchases",
    permission: permissions.viewPurchase,
  },
  suppliers: {
    title: "Fornecedores",
    description: "Fornecedores relevantes, vínculos ativos e histórico de compras autorizado.",
    endpoint: "suppliers",
    permission: permissions.viewSupplier,
  },
  payables: {
    title: "Contas a pagar",
    description: "Parcelas originadas em compras, vencimentos e baixas registradas.",
    endpoint: "payables",
    permission: permissions.managePurchasePayables,
  },
};

function initialPeriod(): PeriodValue {
  return businessMonthToDate();
}

function text(value: unknown) {
  return value == null || value === "" ? "-" : String(value);
}

function money(value: unknown) {
  return formatBRL(String(value || "0"));
}

function reportPath(url: string) {
  const parsed = new URL(url);
  const marker = "/api/v1/";
  const index = parsed.pathname.indexOf(marker);
  return `${index >= 0 ? parsed.pathname.slice(index + marker.length) : parsed.pathname.replace(/^\//, "")}${parsed.search}`;
}

function supplierLabel(item: SupplierOption) {
  if (item.status === "inactive") return `${item.name} (Inativo)`;
  if (item.historical) return `${item.name} (Arquivado)`;
  return item.name;
}

function statusLabel(kind: ReportKind, status: unknown) {
  const value = String(status || "");
  if (kind === "purchases") return purchaseStatusLabels[value as keyof typeof purchaseStatusLabels] || value;
  if (kind === "payables") return payableStatusLabels[value as keyof typeof payableStatusLabels] || value;
  return value === "active" ? "Ativo" : value === "inactive" ? "Inativo" : value;
}

function StatusPill({ kind, status }: { kind: ReportKind; status: unknown }) {
  const value = String(status || "");
  const tone = value === "RECEIVED" || value === "PAID" || value === "active"
    ? "bg-success/10 text-success-strong"
    : value === "CANCELLED" || value === "inactive"
      ? "bg-danger/10 text-danger-strong"
      : "bg-warning/15 text-warning-strong";
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-semibold ${tone}`}>{statusLabel(kind, status)}</span>;
}

function Kpi({ label, value }: { label: string; value: string }) {
  return <section className="card p-4"><span className="text-[11px] font-semibold uppercase tracking-wide text-muted">{label}</span><strong className="mt-1 block text-xl">{value}</strong></section>;
}

export function PhaseThreeReport({ kind }: { kind: ReportKind }) {
  const config = configs[kind];
  const { currentBranch, hasPermission } = useAuth();
  const allowed = hasPermission(config.permission);
  const canViewCosts = hasPermission(permissions.viewPurchaseCosts);
  const context = useRef(0);
  const requestId = useRef(0);
  context.current = currentBranch?.id || 0;
  const [period, setPeriod] = useState(initialPeriod);
  const [appliedPeriod, setAppliedPeriod] = useState(initialPeriod);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [appliedFilters, setAppliedFilters] = useState<Record<string, string>>({});
  const [options, setOptions] = useState<SupplierOption[]>([]);
  const [data, setData] = useState<ReportResponse<Row> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  function query(nextPeriod = appliedPeriod, nextFilters = appliedFilters) {
    return new URLSearchParams({
      start_datetime: nextPeriod.start,
      end_datetime: nextPeriod.end,
      ...Object.fromEntries(Object.entries(nextFilters).filter(([, value]) => value)),
    });
  }

  async function loadOptions(nextPeriod: PeriodValue, token: number) {
    try {
      const result = await http.get<{ suppliers: SupplierOption[] }>(
        `reports/purchase-options/?${new URLSearchParams({ scope: kind, start_datetime: nextPeriod.start, end_datetime: nextPeriod.end })}`,
      );
      if (context.current === token) setOptions(result.suppliers);
    } catch {
      if (context.current === token) setOptions([]);
    }
  }

  async function load(nextPeriod = period, nextFilters = filters, token = context.current) {
    if (!currentBranch || !allowed) return;
    const id = ++requestId.current;
    setLoading(true);
    setError("");
    const nextQuery = query(nextPeriod, nextFilters);
    try {
      const result = await http.get<ReportResponse<Row>>(`reports/${config.endpoint}/?${nextQuery}`);
      if (context.current === token && requestId.current === id) {
        setData(result);
        setAppliedPeriod(nextPeriod);
        setAppliedFilters(nextFilters);
        window.history.replaceState(null, "", `${window.location.pathname}?${nextQuery}`);
      }
    } catch (caught) {
      if (context.current === token && requestId.current === id) setError(
        caught instanceof ApiError ? caught.message : "Não foi possível carregar o relatório.",
      );
    } finally {
      if (context.current === token && requestId.current === id) setLoading(false);
    }
  }

  async function loadPage(url: string) {
    const token = context.current;
    const id = ++requestId.current;
    setLoading(true);
    try {
      const result = await http.get<ReportResponse<Row>>(reportPath(url));
      if (context.current === token && requestId.current === id) setData(result);
    } catch (caught) {
      if (context.current === token && requestId.current === id) setError(
        caught instanceof ApiError ? caught.message : "Não foi possível trocar a página.",
      );
    } finally {
      if (context.current === token && requestId.current === id) setLoading(false);
    }
  }

  useEffect(() => {
    const current = new URLSearchParams(window.location.search);
    const start = current.get("start_datetime");
    const end = current.get("end_datetime");
    const nextPeriod = start && end ? { start, end } : initialPeriod();
    const nextFilters = Object.fromEntries([...current.entries()].filter(([key]) => ![
      "start_datetime", "end_datetime", "branch", "export", "page", "page_size",
    ].includes(key)));
    if (kind === "payables" && !nextFilters.date_basis) nextFilters.date_basis = "due_date";
    setPeriod(nextPeriod);
    setAppliedPeriod(nextPeriod);
    setFilters(nextFilters);
    setAppliedFilters(nextFilters);
    setData(null);
    void load(nextPeriod, nextFilters, context.current);
    void loadOptions(nextPeriod, context.current);
  }, [currentBranch?.id, kind, allowed]);

  function apply(event: React.FormEvent) {
    event.preventDefault();
    const nextPeriod = { ...period };
    const nextFilters = { ...filters };
    void load(nextPeriod, nextFilters);
    void loadOptions(nextPeriod, context.current);
  }

  function clear() {
    const nextPeriod = initialPeriod();
    const nextFilters: Record<string, string> = kind === "payables"
      ? { date_basis: "due_date" }
      : {};
    setPeriod(nextPeriod);
    setFilters(nextFilters);
    void load(nextPeriod, nextFilters);
    void loadOptions(nextPeriod, context.current);
  }

  if (!allowed) return <div className="p-6"><Alert message="Você não possui permissão para este relatório." /></div>;

  const summary = data?.summary || {};
  const results = data?.results || [];
  const statusGroups = Array.isArray(summary.status_groups) ? summary.status_groups as Row[] : [];
  const itemDetails = Array.isArray(summary.item_details) ? summary.item_details as Row[] : [];
  return <>
    <PageHeader title={config.title} description={config.description} action={<div className="flex gap-2"><Link className="btn btn-secondary" href="/relatorios">Central</Link><ReportExportAction path={`reports/${config.endpoint}/`} query={query()} /></div>} />
    <div className="space-y-5 p-4 sm:p-6 lg:p-8">
      {error && <Alert message={error} />}
      <form className="card space-y-4 p-4" onSubmit={apply}>
        <div className="flex items-center gap-2 text-xs font-bold"><Filter className="size-4 text-primary" />Filtros</div>
        <PeriodFilter value={period} onChange={setPeriod} onApply={(nextPeriod) => {
          void load(nextPeriod, filters);
          void loadOptions(nextPeriod, context.current);
        }} />
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {kind !== "suppliers" && <Field label="Fornecedor"><Select value={filters.supplier || ""} onChange={(event) => setFilters((current) => ({ ...current, supplier: event.target.value }))}><option value="">Todos os fornecedores</option>{options.map((item) => <option key={item.id} value={item.id}>{supplierLabel(item)}</option>)}</Select></Field>}
          {kind === "purchases" && <><Field label="Tipo"><Select value={filters.order_type || ""} onChange={(event) => setFilters((current) => ({ ...current, order_type: event.target.value }))}><option value="">Todos os tipos</option>{Object.entries(purchaseTypeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select></Field><Field label="Status"><Select value={filters.status || ""} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}><option value="">Todos os status</option>{Object.entries(purchaseStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select></Field></>}
          {kind === "suppliers" && <><Field label="Status"><Select value={filters.status || ""} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}><option value="">Ativos e históricos</option><option value="active">Ativos</option><option value="inactive">Inativos</option></Select></Field><Field label="Fornecedor"><Select value={filters.supplier || ""} onChange={(event) => setFilters((current) => ({ ...current, supplier: event.target.value }))}><option value="">Todos os fornecedores</option>{options.map((item) => <option key={item.id} value={item.id}>{supplierLabel(item)}</option>)}</Select></Field></>}
          {kind === "payables" && <><Field label="Status"><Select value={filters.status || ""} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}><option value="">Todos os status</option>{Object.entries(payableStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select></Field><Field label="Período por"><Select value={filters.date_basis || "due_date"} onChange={(event) => setFilters((current) => ({ ...current, date_basis: event.target.value }))}><option value="due_date">Vencimento</option><option value="settlement_date">Baixa ou cancelamento</option></Select></Field></>}
          <Field label={kind === "suppliers" ? "Busca" : "Compra, documento ou fornecedor"}><Input value={filters.search || ""} onChange={(event) => setFilters((current) => ({ ...current, search: event.target.value }))} /></Field>
        </div>
        <div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={clear}>Limpar</Button><Button type="submit">Aplicar</Button></div>
      </form>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {kind === "purchases" && <><Kpi label="Compras" value={text(summary.count)} /><Kpi label="Itens" value={text(summary.items_count)} />{canViewCosts && <><Kpi label="Total pedido" value={money(summary.ordered_total)} /><Kpi label="Total recebido" value={money(summary.received_total)} /><Kpi label="Não recebido" value={money(summary.unreceived_total)} /></>}</>}
        {kind === "suppliers" && <><Kpi label="Fornecedores" value={text(summary.supplier_count)} /><Kpi label="Ativos" value={text(summary.active_count)} /><Kpi label="Compras no período" value={text(summary.purchase_count)} />{canViewCosts && <Kpi label="Total a pagar" value={money(summary.payable_total)} />}</>}
        {kind === "payables" && <><Kpi label="Pendentes" value={money(summary.pending_total)} /><Kpi label="Pagas" value={money(summary.paid_total)} /><Kpi label="Vencidas" value={money(summary.overdue_total)} /><Kpi label="Parcelas" value={text(summary.count)} /></>}
      </div>
      {statusGroups.length > 0 && <section className="card overflow-hidden"><div className="card-header"><div><h2 className="text-sm font-bold">Resumo por status</h2><p className="mt-1 text-[11px] text-muted">Totais do recorte aplicado.</p></div></div><div className="table-wrap"><table className="data-table"><thead><tr><th>Status</th><th>Registros</th>{kind === "purchases" ? <><th>Pedido</th><th>Recebido</th><th>Não recebido</th></> : kind === "payables" && <th>Valor</th>}</tr></thead><tbody>{statusGroups.map((group) => <tr key={String(group.status)}><td><StatusPill kind={kind === "suppliers" ? "suppliers" : kind} status={group.status} /></td><td>{text(group.count)}</td>{kind === "purchases" ? <><td>{money(group.ordered_total)}</td><td>{money(group.received_total)}</td><td>{money(group.unreceived_total)}</td></> : kind === "payables" && <td>{money(group.amount)}</td>}</tr>)}</tbody></table></div></section>}
      <section className="card overflow-hidden"><div className="card-header"><div><h2 className="text-sm font-bold">{kind === "purchases" ? "Compras detalhadas" : kind === "suppliers" ? "Fornecedores" : "Parcelas detalhadas"}</h2><p className="mt-1 text-[11px] text-muted">{data?.count || 0} registros no recorte.</p></div>{kind === "purchases" ? <ReceiptText className="size-5 text-muted" /> : kind === "suppliers" ? <Truck className="size-5 text-muted" /> : <WalletCards className="size-5 text-muted" />}</div>{loading ? <TableLoading columns={kind === "payables" ? 7 : 6} /> : results.length ? <><div className="table-wrap"><table className="data-table min-w-225"><thead>{kind === "purchases" ? <tr><th>Compra</th><th>Fornecedor</th><th>Documento</th><th>Tipo</th><th>Data</th>{canViewCosts && <th>Total</th>}<th>Status</th></tr> : kind === "suppliers" ? <tr><th>Fornecedor</th><th>Status</th><th>Produtos ativos</th><th>Compras</th><th>Recebidas</th>{canViewCosts && <th>Total a pagar</th>}</tr> : <tr><th>Compra</th><th>Fornecedor</th><th>Parcela</th><th>Vencimento</th><th>Valor</th><th>Status</th><th>Baixa</th></tr>}</thead><tbody>{results.map((row) => kind === "purchases" ? <tr key={String(row.id)}><td><Link className="font-bold text-link" href={`/compras/${row.id}`}>{text(row.order_number)}</Link></td><td><Link className="text-link" href={`/relatorios/fornecedores?supplier=${row.supplier_id}`}>{text(row.supplier_name)}</Link></td><td>{text(row.document_number)}</td><td>{purchaseTypeLabels[String(row.order_type) as keyof typeof purchaseTypeLabels] || text(row.order_type)}</td><td>{formatDate(String(row.created_at))}</td>{canViewCosts && <td className="font-bold">{money(row.payable_total)}</td>}<td><StatusPill kind="purchases" status={row.status} /></td></tr> : kind === "suppliers" ? <tr key={String(row.supplier_id)}><td><Link className="font-bold text-link" href={`/relatorios/compras?supplier=${row.supplier_id}`}>{text(row.supplier_name)}{row.historical ? " (Arquivado)" : ""}</Link></td><td><StatusPill kind="suppliers" status={row.status} /></td><td>{text(row.product_count)}</td><td>{text(row.purchase_count)}</td><td>{text(row.received_count)}</td>{canViewCosts && <td className="font-bold">{money(row.payable_total)}</td>}</tr> : <tr key={String(row.id)}><td><Link className="font-bold text-link" href={`/compras/${row.purchase_order_id}?origin=payables`}>{text(row.order_number)}</Link></td><td><Link className="text-link" href={`/relatorios/compras?supplier=${row.supplier_id}`}>{text(row.supplier_name)}</Link></td><td>{text(row.installment_number)}</td><td>{row.due_date ? new Date(`${String(row.due_date)}T12:00:00`).toLocaleDateString("pt-BR") : "-"}</td><td className="font-bold">{money(row.amount)}</td><td><StatusPill kind="payables" status={row.status} /></td><td>{row.paid_at ? formatDate(String(row.paid_at)) : row.cancelled_at ? formatDate(String(row.cancelled_at)) : "-"}</td></tr>)}</tbody></table></div><Pagination count={data?.count || 0} next={data?.next || null} previous={data?.previous || null} onPage={(url) => void loadPage(url)} /></> : <EmptyState title="Nenhum registro encontrado" description="Revise o período e os filtros aplicados." />}</section>
      {kind === "purchases" && canViewCosts && itemDetails.length > 0 && <section className="card overflow-hidden"><div className="card-header"><div><h2 className="text-sm font-bold">Pedido x recebimento por item</h2><p className="mt-1 text-[11px] text-muted">Valores efetivos das quantidades confirmadas no estoque.</p></div></div><div className="table-wrap"><table className="data-table min-w-250"><thead><tr><th>Compra</th><th>Item</th><th>Apresentação</th><th>Pedido</th><th>Recebido</th><th>Não recebido</th><th>Valor pedido</th><th>Valor recebido</th><th>Valor não recebido</th></tr></thead><tbody>{itemDetails.map((item) => <tr key={String(item.item_id)}><td><Link className="font-bold text-link" href={`/compras/${item.purchase_order_id}`}>{text(item.order_number)}</Link></td><td><strong>{text(item.product_name)}</strong><small className="block text-muted">{text(item.product_internal_code)}</small></td><td>{text(item.presentation)}</td><td>{text(item.ordered_quantity)}</td><td>{text(item.received_quantity)}</td><td>{text(item.unreceived_quantity)}</td><td>{money(item.ordered_total)}</td><td>{money(item.received_total)}</td><td>{money(item.unreceived_total)}</td></tr>)}</tbody></table></div></section>}
    </div>
  </>;
}
