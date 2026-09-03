"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowRightLeft, Ban, CreditCard, Filter, ListOrdered } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { PeriodFilter, type PeriodValue } from "@/components/period-filter";
import { ReportExportAction } from "@/components/report-export-action";
import { Alert, Button, EmptyState, Field, Input, Modal, Pagination, Select, TableLoading } from "@/components/ui";
import { formatBRL, formatDate } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { businessMonthToDate } from "@/lib/period";
import { useAuth } from "@/providers/auth-provider";
import type { ReportResponse } from "@/types";

type Section = "commands" | "items" | "payments" | "cancellations" | "operations";
type Row = Record<string, unknown>;
type Option = { id: number; name: string; historical?: boolean };
type Options = { tables: Option[]; customers: Option[]; operators: Option[]; payment_methods: Option[] };

const labels: Record<Section, string> = {
  commands: "Comandas", items: "Itens", payments: "Pagamentos", cancellations: "Cancelamentos", operations: "Transferências",
};

function initialPeriod(): PeriodValue { return businessMonthToDate(); }
function text(value: unknown) { return value == null || value === "" ? "-" : String(value); }
function money(value: unknown) { return formatBRL(typeof value === "string" ? value : "0"); }
function date(value: unknown) { return value ? formatDate(String(value)) : "-"; }
function commandStatus(value: unknown) { return value === "open" ? "Aberta" : value === "closed" ? "Encerrada" : text(value); }
function paymentStatus(value: unknown) { return value === "applied" ? "Aplicado" : value === "reversed" ? "Estornado" : text(value); }
function reportPath(url: string) { const parsed = new URL(url); const marker = "/api/v1/"; const index = parsed.pathname.indexOf(marker); return `${index >= 0 ? parsed.pathname.slice(index + marker.length) : parsed.pathname.replace(/^\//, "")}${parsed.search}`; }
function optionLabel(option: Option) { return `${option.name}${option.historical ? " (Histórico)" : ""}`; }

function Kpi({ label, value }: { label: string; value: string }) {
  return <section className="card p-4"><span className="text-[11px] font-semibold uppercase tracking-wide text-muted">{label}</span><strong className="mt-1 block text-xl">{value}</strong></section>;
}

export function CommandsReport() {
  const { currentBranch, hasPermission } = useAuth();
  const allowed = hasPermission(permissions.viewCommands);
  const canViewPayments = hasPermission(permissions.viewCommandPayments);
  const context = useRef(0);
  const requestId = useRef(0);
  context.current = currentBranch?.id || 0;
  const [section, setSection] = useState<Section>("commands");
  const [period, setPeriod] = useState(initialPeriod);
  const [appliedPeriod, setAppliedPeriod] = useState(initialPeriod);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [appliedFilters, setAppliedFilters] = useState<Record<string, string>>({});
  const [options, setOptions] = useState<Options>({ tables: [], customers: [], operators: [], payment_methods: [] });
  const [data, setData] = useState<ReportResponse<Row> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reason, setReason] = useState("");

  function query(nextPeriod = appliedPeriod, nextFilters = appliedFilters, nextSection = section) {
    return new URLSearchParams({ start_datetime: nextPeriod.start, end_datetime: nextPeriod.end, section: nextSection, ...Object.fromEntries(Object.entries(nextFilters).filter(([, value]) => value)) });
  }

  async function loadOptions(nextPeriod: PeriodValue, token: number) {
    try {
      const result = await http.get<Options>(`reports/command-options/?${new URLSearchParams({ start_datetime: nextPeriod.start, end_datetime: nextPeriod.end })}`);
      if (context.current === token) setOptions(result);
    } catch { if (context.current === token) setOptions({ tables: [], customers: [], operators: [], payment_methods: [] }); }
  }

  async function load(nextPeriod = period, nextFilters = filters, nextSection = section, token = context.current) {
    if (!currentBranch || !allowed) return;
    const id = ++requestId.current;
    setLoading(true); setError("");
    const nextQuery = query(nextPeriod, nextFilters, nextSection);
    try {
      const result = await http.get<ReportResponse<Row>>(`reports/commands/?${nextQuery}`);
      if (context.current === token && requestId.current === id) {
        setData(result); setAppliedPeriod(nextPeriod); setAppliedFilters(nextFilters);
        window.history.replaceState(null, "", `${window.location.pathname}?${nextQuery}`);
      }
    } catch (caught) {
      if (context.current === token && requestId.current === id) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar o relatório.");
    } finally { if (context.current === token && requestId.current === id) setLoading(false); }
  }

  useEffect(() => {
    const current = new URLSearchParams(window.location.search);
    const start = current.get("start_datetime"); const end = current.get("end_datetime");
    const nextPeriod = start && end ? { start, end } : initialPeriod();
    const nextSection = current.get("section") as Section;
    const resolvedSection = Object.prototype.hasOwnProperty.call(labels, nextSection) && (nextSection !== "payments" || canViewPayments) ? nextSection : "commands";
    const nextFilters = Object.fromEntries([...current.entries()].filter(([key]) => !["start_datetime", "end_datetime", "section", "branch", "export", "page", "page_size"].includes(key)));
    setSection(resolvedSection); setPeriod(nextPeriod); setAppliedPeriod(nextPeriod); setFilters(nextFilters); setAppliedFilters(nextFilters); setData(null);
    void load(nextPeriod, nextFilters, resolvedSection, context.current); void loadOptions(nextPeriod, context.current);
  }, [currentBranch?.id, allowed, canViewPayments]);

  function apply(event: React.FormEvent) { event.preventDefault(); void load({ ...period }, { ...filters }); }
  function clear() { const nextPeriod = initialPeriod(); setPeriod(nextPeriod); setFilters({}); void load(nextPeriod, {}); void loadOptions(nextPeriod, context.current); }
  function selectSection(next: Section) { setSection(next); void load(period, filters, next); }
  async function loadPage(url: string) {
    const id = ++requestId.current; const token = context.current; setLoading(true);
    try { const result = await http.get<ReportResponse<Row>>(reportPath(url)); if (context.current === token && requestId.current === id) setData(result); }
    catch (caught) { if (context.current === token && requestId.current === id) setError(caught instanceof ApiError ? caught.message : "Não foi possível trocar a página."); }
    finally { if (context.current === token && requestId.current === id) setLoading(false); }
  }

  if (!allowed) return <div className="p-6"><Alert message="Você não possui permissão para este relatório." /></div>;
  const summary = data?.summary || {}; const results = data?.results || [];
  const tabs = (Object.keys(labels) as Section[]).filter((item) => item !== "payments" || canViewPayments);
  return <>
    <PageHeader title="Mesas e Comandas" description="Acompanhamento operacional, financeiro e histórico de comandas da filial." action={<div className="flex gap-2"><Link className="btn btn-secondary" href="/relatorios">Central</Link><ReportExportAction path="reports/commands/" query={query()} /></div>} />
    <div className="space-y-5 p-4 sm:p-6 lg:p-8">
      {error && <Alert message={error} />}
      <form className="card space-y-4 p-4" onSubmit={apply}>
        <div className="flex items-center gap-2 text-xs font-bold"><Filter className="size-4 text-primary" />Filtros</div>
        <PeriodFilter value={period} onChange={setPeriod} onApply={(next) => { void load(next, filters); void loadOptions(next, context.current); }} />
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <Field label="Status"><Select value={filters.status || ""} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}><option value="">Todos</option><option value="open">Aberta</option><option value="closed">Encerrada</option></Select></Field>
          <Field label="Mesa"><Select value={filters.table || ""} onChange={(event) => setFilters((current) => ({ ...current, table: event.target.value }))}><option value="">Todas as mesas</option>{options.tables.map((item) => <option key={item.id} value={item.id}>{optionLabel(item)}</option>)}</Select></Field>
          <Field label="Cliente"><Select value={filters.customer || ""} onChange={(event) => setFilters((current) => ({ ...current, customer: event.target.value }))}><option value="">Todos os clientes</option>{options.customers.map((item) => <option key={item.id} value={item.id}>{optionLabel(item)}</option>)}</Select></Field>
          <Field label="Atendente ou operador"><Select value={filters.operator || ""} onChange={(event) => setFilters((current) => ({ ...current, operator: event.target.value }))}><option value="">Todos</option>{options.operators.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>
          {canViewPayments && <Field label="Forma de pagamento"><Select value={filters.payment_method || ""} onChange={(event) => setFilters((current) => ({ ...current, payment_method: event.target.value }))}><option value="">Todas as formas</option>{options.payment_methods.map((item) => <option key={item.id} value={item.id}>{optionLabel(item)}</option>)}</Select></Field>}
          <Field label="Comanda ou identificador"><Input value={filters.command || ""} onChange={(event) => setFilters((current) => ({ ...current, command: event.target.value }))} /></Field>
        </div>
        <div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={clear}>Limpar</Button><Button type="submit">Aplicar</Button></div>
      </form>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Kpi label="Mesas abertas" value={text(summary.opened_tables)} /><Kpi label="Comandas abertas" value={text(summary.opened_commands)} /><Kpi label="Comandas encerradas" value={text(summary.closed_commands)} /><Kpi label="Faturamento associado" value={money(summary.associated_revenue)} /><Kpi label="Ticket médio" value={money(summary.average_ticket)} /><Kpi label="Permanência média" value={`${text(summary.average_stay_minutes)} min`} /><Kpi label="Cancelamentos" value={`${text(summary.cancelled_items)} · ${money(summary.cancelled_value)}`} /><Kpi label="Operações" value={text(summary.operations_count)} /></div>
      <div className="flex flex-wrap gap-2">{tabs.map((item) => <Button key={item} type="button" variant={section === item ? "primary" : "secondary"} onClick={() => selectSection(item)}>{labels[item]}</Button>)}</div>
      <section className="card overflow-hidden"><div className="card-header"><div><h2 className="text-sm font-bold">{labels[section]}</h2><p className="mt-1 text-[11px] text-muted">{data?.count || 0} registros no recorte aplicado.</p></div>{section === "operations" ? <ArrowRightLeft className="size-5 text-muted" /> : section === "cancellations" ? <Ban className="size-5 text-muted" /> : section === "payments" ? <CreditCard className="size-5 text-muted" /> : <ListOrdered className="size-5 text-muted" />}</div>
        {loading ? <TableLoading columns={7} /> : !results.length ? <EmptyState title="Nenhum registro encontrado" description="Ajuste o período ou os filtros para consultar este recorte." /> : <div className="table-wrap"><table className="data-table min-w-250"><thead>{section === "commands" ? <tr><th>Comanda</th><th>Mesa</th><th>Abertura</th><th>Encerramento</th><th>Atendente / operador</th><th>Cliente</th><th>Itens</th><th>Subtotal</th><th>Descontos</th><th>Taxa</th><th>Total</th><th>Status</th></tr> : section === "items" ? <tr><th>Comanda</th><th>Mesa</th><th>Produto histórico</th><th>Categoria histórica</th><th>Quantidade</th><th>Modificadores</th><th>Promoção</th><th>Desconto</th><th>Subtotal</th><th>Status</th></tr> : section === "payments" ? <tr><th>Comanda</th><th>Mesa</th><th>Forma</th><th>Valor</th><th>Parcial</th><th>Total</th><th>Situação</th><th>Operador</th><th>Venda</th><th>Data</th></tr> : section === "cancellations" ? <tr><th>Comanda</th><th>Mesa</th><th>Item</th><th>Quantidade</th><th>Valor</th><th>Responsável</th><th>Autorizador</th><th>Motivo</th><th>Data/hora</th></tr> : <tr><th>Operação</th><th>Origem</th><th>Destino</th><th>Itens</th><th>Responsável</th><th>Data/hora</th></tr>}</thead><tbody>{results.map((row) => section === "commands" ? <tr key={String(row.id)}><td><Link className="font-bold text-link" href={`/comandas/${row.id}`}>{text(row.command_number)}</Link><small className="block text-muted">{text(row.identifier)}</small></td><td>{text(row.table_name)}</td><td>{date(row.created_at)}</td><td>{date(row.closed_at)}</td><td>{text(row.attendant_name)}<small className="block text-muted">{text(row.opened_by_name)} / {text(row.closed_by_name)}</small></td><td>{text(row.customer_name)}</td><td>{text(row.items_count)}</td><td>{money(row.subtotal)}</td><td>{money(row.discount)}</td><td>{money(row.service_fee)}</td><td className="font-bold">{money(row.total)}</td><td>{commandStatus(row.status)}</td></tr> : section === "items" ? <tr key={String(row.id)}><td><Link className="font-bold text-link" href={`/comandas/${row.command_id}`}>{text(row.command_number)}</Link></td><td>{text(row.table_name)}</td><td><strong>{text(row.product_name)}</strong><small className="block text-muted">{text(row.internal_code)}</small></td><td>{text(row.category_name)}</td><td>{text(row.quantity)}</td><td>{text(row.modifiers)}</td><td>{text(row.promotion)}</td><td>{money(row.discount)}</td><td>{money(row.subtotal)}</td><td>{row.status === "cancelled" ? "Cancelado" : row.status === "confirmed" ? "Confirmado" : "Pendente"}</td></tr> : section === "payments" ? <tr key={String(row.id)}><td><Link className="font-bold text-link" href={`/comandas/${row.command_id}`}>{text(row.command_number)}</Link></td><td>{text(row.table_name)}</td><td>{text(row.payment_method)}</td><td>{money(row.amount)}</td><td>{row.is_partial ? "Sim" : "Não"}</td><td>{money(row.command_total)}</td><td>{paymentStatus(row.status)}<small className="block text-danger-strong">{text(row.reversal_reason)}</small></td><td>{text(row.operator_name)}</td><td>{text(row.sale_number)}</td><td>{date(row.created_at)}</td></tr> : section === "cancellations" ? <tr key={String(row.id)}><td><Link className="font-bold text-link" href={`/comandas/${row.command_id}`}>{text(row.command_number)}</Link></td><td>{text(row.table_name)}</td><td>{text(row.product_name)}</td><td>{text(row.quantity)}</td><td>{money(row.amount)}</td><td>{text(row.responsible_name)}</td><td>{text(row.authorized_by_name)}</td><td><Button type="button" variant="secondary" onClick={() => setReason(text(row.reason))}>Ver motivo</Button></td><td>{date(row.cancelled_at)}</td></tr> : <tr key={String(row.id)}><td>{text(row.operation_label)}</td><td>{text(row.source_command)}<small className="block text-muted">{text(row.source_table)}</small></td><td>{text(row.destination_command)}<small className="block text-muted">{text(row.destination_table)}</small></td><td>{Array.isArray(row.item_ids) ? row.item_ids.length : "-"}</td><td>{text(row.responsible_name)}</td><td>{date(row.created_at)}</td></tr>)}</tbody></table></div>}
        <Pagination count={data?.count || 0} next={data?.next || null} previous={data?.previous || null} onPage={loadPage} />
      </section>
    </div>
    <Modal open={!!reason} title="Motivo do cancelamento" onClose={() => setReason("")} size="md"><p className="p-5 text-sm leading-6 text-muted">{reason}</p></Modal>
  </>;
}
