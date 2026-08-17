"use client";

import { useEffect, useRef, useState } from "react";
import { Download, Filter, RefreshCw } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import { PeriodFilter, type PeriodValue } from "@/components/period-filter";
import {
  Alert,
  Button,
  EmptyState,
  Field,
  Pagination,
  Select,
  TableLoading,
} from "@/components/ui";
import { formatBRL, formatDate } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { ReportResponse, ReportsOptions } from "@/types";

const reports = [
  { key: "sales", label: "Vendas", permission: permissions.viewSalesReport },
  {
    key: "consumptions",
    label: "Consumação",
    permission: permissions.viewConsumptionsReport,
  },
  { key: "cash", label: "Caixa", permission: permissions.viewCashReport },
  {
    key: "operational-result",
    label: "Resultado estimado",
    permission: permissions.viewOperationalResult,
  },
  {
    key: "withdrawals",
    label: "Sangrias",
    permission: permissions.viewWithdrawalsReport,
  },
  {
    key: "inventory-movements",
    label: "Estoque",
    permission: permissions.viewInventoryReport,
  },
] as const;
function initialPeriod(): PeriodValue {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  const date = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-01`;
  const end = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T23:59`;
  return { start: `${date}T00:00`, end };
}
function scalar(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "object") return "Dados agrupados";
  return String(value);
}
const valueLabels: Record<string, string> = { finalized: "Finalizada", cancelled: "Cancelada", open: "Aberta", closed: "Fechada", manual_entry: "Entrada manual", withdrawal: "Sangria", entry: "Entrada", exit: "Saída", adjustment: "Ajuste", sale: "Venda", consumption: "Consumação" };
function displayValue(value: unknown) { const text = scalar(value); return valueLabels[text] || text; }
const summaryLabels: Record<string, string> = {
  gross: "Valor bruto a preço de tabela",
  effective_revenue: "Faturamento efetivo",
  revenue: "Faturamento efetivo",
  count: "Quantidade",
  average: "Ticket médio",
  manual_discount: "Desconto manual",
  promotion_discount: "Desconto promocional",
  total_discount: "Descontos totais",
  reference: "Valor de referência",
  charged: "Valor cobrado",
  subsidy: "Diferença / subsídio",
  quantity: "Quantidade consumida",
  historical_cost: "Custo histórico",
  opening: "Abertura",
  manual_entries: "Entradas manuais",
  cash_payments: "Dinheiro de vendas",
  withdrawals: "Sangrias",
  expected: "Esperado",
  informed: "Informado",
  difference: "Diferença",
  amount: "Total",
  by_category: "Sangrias por categoria",
  cancellations: "Cancelamentos",
  value: "Valor",
  product_ranking: "Ranking de produtos",
  category_ranking: "Ranking de categorias",
  payment_totals: "Totais por forma de pagamento",
  service_fee: "Taxa de serviço cobrada",
  commission: "Comissão",
  customer_total: "Total cobrado do cliente",
  operator_groups: "Vendas por operador",
  seller_groups: "Vendas por atendente",
  discounts: "Descontos totais",
  cogs: "CMV histórico",
  operating_expenses: "Despesas operacionais",
  fixed_cost: "Custo fixo rateado",
  result: "Resultado operacional estimado",
  margin: "Margem estimada",
  unclassified_withdrawals: "Sangrias não classificadas",
  cash_session: "Sessão de caixa",
  notice: "Observação",
};
const moneySummaryKeys = new Set(["gross", "effective_revenue", "revenue", "average", "manual_discount", "promotion_discount", "total_discount", "reference", "charged", "subsidy", "historical_cost", "opening", "manual_entries", "cash_payments", "withdrawals", "expected", "informed", "difference", "amount", "value", "service_fee", "commission", "customer_total", "discounts", "cogs", "operating_expenses", "fixed_cost", "result"]);
function Summary({ summary }: { summary: Record<string, unknown> }) {
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Object.entries(summary)
          .filter(([key, value]) => summaryLabels[key] && typeof value !== "object")
          .map(([key, value]) => (
            <div key={key} className="card p-4">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                {summaryLabels[key]}
              </span>
              <strong className="mt-2 block text-xl">
                {typeof value === "string" &&
                /^-?\d+\.\d+$/.test(value) && moneySummaryKeys.has(key)
                  ? formatBRL(value)
                  : key === "margin" && typeof value === "string"
                    ? `${value}%`
                  : scalar(value)}
              </strong>
            </div>
          ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        {Object.entries(summary)
          .filter(([key, value]) => summaryLabels[key] && !["operator_groups", "seller_groups"].includes(key) && value && typeof value === "object")
          .map(([key, value]) => {
            const rows = Array.isArray(value) ? value : [value];
            return (
              <section key={key} className="card overflow-hidden">
                <div className="card-header">
                  <h3 className="text-xs font-bold uppercase tracking-wider">
                    {summaryLabels[key]}
                  </h3>
                </div>
                <div className="divide-y divide-slate-100">
                  {rows.length ? (
                    rows.slice(0, 10).map((row, index) => {
                      const item = row as Record<string, unknown>;
                      const label =
                        item.name ||
                        item.product_name ||
                        item.category_name ||
                        item.category ||
                        item.payment_method_name ||
                        `Registro ${index + 1}`;
                      const amount =
                        item.amount ||
                        item.revenue ||
                        item.value ||
                        item.quantity ||
                        item.count;
                      return (
                        <div
                          key={index}
                          className="flex justify-between gap-4 px-5 py-3 text-xs"
                        >
                          <span>{scalar(label)}</span>
                          <strong>{scalar(amount)}</strong>
                        </div>
                      );
                    })
                  ) : (
                    <p className="p-5 text-xs text-slate-500">Sem dados.</p>
                  )}
                </div>
              </section>
            );
          })}
      </div>
    </>
  );
}

function UserGroups({ title, rows, filter, onSelect }: { title: string; rows: Array<Record<string, unknown>>; filter: "operator" | "seller"; onSelect: (filter: "operator" | "seller", id: string) => void }) {
  return <section className="card overflow-hidden"><div className="card-header"><h3 className="text-sm font-bold">{title}</h3></div>{rows.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Responsável</th><th>Vendas</th><th>Faturamento efetivo</th><th>Taxa</th><th>Comissão</th><th></th></tr></thead><tbody>{rows.map((row) => { const user = row.user as { id: number; name: string }; return <tr key={user.id}><td><strong>{user.name}</strong></td><td>{String(row.count)}</td><td>{formatBRL(String(row.effective_revenue))}</td><td>{formatBRL(String(row.service_fee))}</td><td>{formatBRL(String(row.commission))}</td><td className="text-right"><button className="text-xs font-bold text-primary" onClick={() => onSelect(filter, String(user.id))}>Ver vendas</button></td></tr>; })}</tbody></table></div> : <EmptyState title="Sem agrupamentos" description="Nenhuma venda finalizada no período." />}</section>;
}

function ReportsPage() {
  const { currentBranch, hasPermission } = useAuth();
  const available = reports.filter((item) => hasPermission(item.permission));
  const contextRef = useRef("");
  contextRef.current = String(currentBranch?.id || "");
  const [active, setActive] = useState<string>(available[0]?.key || "sales");
  const [period, setPeriod] = useState(initialPeriod);
  const [options, setOptions] = useState<ReportsOptions | null>(null);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [data, setData] = useState<ReportResponse<
    Record<string, unknown>
  > | null>(null);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState(false);
  function query(exportCsv = false, range = period, selected = filters) {
    const params = new URLSearchParams({
      start_datetime: range.start,
      end_datetime: range.end,
      ...Object.fromEntries(
        Object.entries(selected).filter(([, value]) => value),
      ),
    });
    if (exportCsv) params.set("export", "csv");
    return params;
  }
  async function load(
    path?: string,
    token = contextRef.current,
    range = period,
    selected = filters,
  ) {
    if (!currentBranch) return;
    setData(null);
    setError("");
    try {
      const result = await http.get<ReportResponse<Record<string, unknown>>>(
        path || `reports/${active}/?${query(false, range, selected)}`,
      );
      if (contextRef.current === token) setData(result);
    } catch (caught) {
      if (contextRef.current === token)
        setError(
          caught instanceof ApiError
            ? caught.message
            : "Não foi possível carregar o relatório.",
        );
    }
  }
  useEffect(() => {
    const first = available[0]?.key;
    if (first && !available.some((item) => item.key === active))
      setActive(first);
  }, [currentBranch?.id]);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const requestedReport = params.get("report");
    const targetReport = requestedReport && available.some((item) => item.key === requestedReport) ? requestedReport : active;
    if (targetReport !== active) setActive(targetReport);
    const start = params.get("start_datetime");
    const end = params.get("end_datetime");
    const targetPeriod = start && end ? { start, end } : period;
    if (start && end) setPeriod(targetPeriod);
    setFilters({});
    setData(null);
    if (!currentBranch) return;
    void load(`reports/${targetReport}/?${query(false, targetPeriod, {})}`, contextRef.current, targetPeriod, {});
    void http
      .get<ReportsOptions>("reports/options/")
      .then(setOptions)
      .catch(() => setOptions(null));
  }, [currentBranch?.id]);
  useEffect(() => {
    if (currentBranch && active) void load();
  }, [active, currentBranch?.id]);
  async function download() {
    if (!currentBranch) return;
    setDownloading(true);
    setError("");
    try {
      const base = (
        process.env.NEXT_PUBLIC_API_URL || "http://localhost:18000/api/v1"
      ).replace(/\/$/, "");
      const response = await fetch(
        `${base}/reports/${active}/?${query(true)}`,
        {
          credentials: "include",
          headers: { "X-Branch-ID": String(currentBranch.id) },
        },
      );
      if (!response.ok) throw new Error();
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${active}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("Não foi possível exportar o relatório com os filtros atuais.");
    } finally {
      setDownloading(false);
    }
  }
  const set = (key: string, value: string) =>
    setFilters((current) => ({ ...current, [key]: value }));
  function selectGroup(key: "operator" | "seller", value: string) {
    const selected = { ...filters, [key]: value };
    setFilters(selected);
    void load(undefined, contextRef.current, period, selected);
  }
  return (
    <>
      <PageHeader
        title="Relatórios"
        description={`Análises operacionais de ${currentBranch?.name || "sua filial"}.`}
        action={
          hasPermission(permissions.exportReports) ? (
            <Button
              variant="secondary"
              loading={downloading}
              onClick={() => void download()}
            >
              <Download className="size-4" />
              Exportar CSV
            </Button>
          ) : undefined
        }
      />
      <div className="space-y-5 p-4 sm:p-6 lg:p-8">
        {error && <Alert message={error} />}
        <section className="card p-4">
          <PeriodFilter
            value={period}
            onApply={(next) => {
              setPeriod(next);
              void load(undefined, contextRef.current, next);
            }}
          />
        </section>
        <div className="flex gap-2 overflow-x-auto">
          {available.map((item) => (
            <button
              key={item.key}
              onClick={() => { setFilters({}); setActive(item.key); }}
              className={`rounded-full px-4 py-2 text-xs font-bold ${active === item.key ? "bg-primary text-white" : "bg-white text-slate-600"}`}
            >
              {item.label}
            </button>
          ))}
        </div>
        <section className="card p-4">
          <div className="mb-3 flex items-center gap-2 text-xs font-bold">
            <Filter className="size-4 text-primary" />
            Filtros do relatório
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {(active === "sales" || active === "consumptions") && (
              <Field label="Status">
                <Select
                  value={filters.status || ""}
                  onChange={(e) => set("status", e.target.value)}
                >
                  <option value="">Todos</option>
                  {options?.sale_statuses.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </Select>
              </Field>
            )}
            {active === "sales" && (
              <>
                <Field label="Operador">
                  <Select
                    value={filters.operator || ""}
                    onChange={(e) => set("operator", e.target.value)}
                  >
                    <option value="">Todos</option>
                    {options?.operators.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Atendente">
                  <Select value={filters.seller || ""} onChange={(e) => set("seller", e.target.value)}>
                    <option value="">Todos</option>
                    {options?.sellers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                  </Select>
                </Field>
                <Field label="Pagamento">
                  <Select
                    value={filters.payment_method || ""}
                    onChange={(e) => set("payment_method", e.target.value)}
                  >
                    <option value="">Todos</option>
                    {options?.payment_methods.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </Select>
                </Field>
              </>
            )}
            {active === "consumptions" && (
              <>
                <Field label="Beneficiário">
                  <Select
                    value={filters.beneficiary || ""}
                    onChange={(e) => set("beneficiary", e.target.value)}
                  >
                    <option value="">Todos</option>
                    {options?.beneficiaries.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Tipo">
                  <Select
                    value={filters.user_type || ""}
                    onChange={(e) => set("user_type", e.target.value)}
                  >
                    <option value="">Todos</option>
                    {options?.user_types.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </Select>
                </Field>
              </>
            )}
            {(active === "sales" ||
              active === "consumptions" ||
              active === "inventory-movements") && (
              <>
                <Field label="Produto">
                  <Select
                    value={filters.product || ""}
                    onChange={(e) => set("product", e.target.value)}
                  >
                    <option value="">Todos</option>
                    {options?.products.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Categoria">
                  <Select
                    value={filters.category || ""}
                    onChange={(e) => set("category", e.target.value)}
                  >
                    <option value="">Todas</option>
                    {options?.categories.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </Select>
                </Field>
              </>
            )}
            {(active === "cash" || active === "withdrawals") && (
              <Field label="Caixa">
                <Select
                  value={filters.cash_register || ""}
                  onChange={(e) => set("cash_register", e.target.value)}
                >
                  <option value="">Todos</option>
                  {options?.cash_registers.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </Select>
              </Field>
            )}
            {active === "withdrawals" && (
              <Field label="Categoria">
                <Select
                  value={filters.category || ""}
                  onChange={(e) => set("category", e.target.value)}
                >
                  <option value="">Todas</option>
                  {options?.withdrawal_categories.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </Select>
              </Field>
            )}
            {active === "inventory-movements" && (
              <Field label="Movimento">
                <Select
                  value={filters.movement_type || ""}
                  onChange={(e) => set("movement_type", e.target.value)}
                >
                  <option value="">Todos</option>
                  {options?.movement_types.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </Select>
              </Field>
            )}
            {active === "operational-result" && (
              <Field label="Sessão de caixa">
                <Select value={filters.cash_session || ""} onChange={(e) => set("cash_session", e.target.value)}>
                  <option value="">Todas no período</option>
                  {options?.cash_sessions.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.status === "open" ? "aberta" : "fechada"}</option>)}
                </Select>
              </Field>
            )}
          </div>
          <div className="mt-4 flex gap-2">
            <Button onClick={() => void load()}>
              <RefreshCw className="size-4" />
              Aplicar
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setFilters({});
                void load(undefined, contextRef.current, period, {});
              }}
            >
              Limpar
            </Button>
          </div>
        </section>
        {!data ? (
          <section className="card">
            <TableLoading />
          </section>
        ) : (
          <>
            <Summary summary={data.summary} />
            {active === "sales" && <div className="grid gap-5 xl:grid-cols-2"><UserGroups title="Vendas por operador" rows={(data.summary.operator_groups as Array<Record<string, unknown>>) || []} filter="operator" onSelect={selectGroup} /><UserGroups title="Vendas por atendente" rows={(data.summary.seller_groups as Array<Record<string, unknown>>) || []} filter="seller" onSelect={selectGroup} /></div>}
            <section className="card overflow-hidden">
              {data.results.length ? (
                <div className="table-wrap">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Data</th>
                        <th>Registro</th>
                        <th>Status / tipo</th>
                        <th className="text-right">Valor</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.results.map((row, index) => (
                        <tr key={String(row.id || index)}>
                          <td>
                            {formatDate(
                              String(row.created_at || row.opened_at || ""),
                            )}
                          </td>
                          <td>
                            <strong>
                              {scalar(
                                row.sale_number ||
                                  (row.product as Record<string, unknown>)
                                    ?.name ||
                                  (row.register as Record<string, unknown>)
                                    ?.name ||
                                  row.id,
                              )}
                            </strong>
                            {Boolean(row.seller) && <span className="mt-1 block text-[10px] text-slate-400">Atendente: {(row.seller as { name: string }).name} · Operador: {(row.operator as { name: string }).name}</span>}
                          </td>
                          <td>
                            {displayValue(
                              row.status ||
                                row.movement_type ||
                                row.category_label,
                            )}
                          </td>
                          <td className="text-right font-bold">
                            {row.total || row.amount || row.expected
                              ? formatBRL(
                                  String(
                                    row.total || row.amount || row.expected,
                                  ),
                                )
                              : "-"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <EmptyState
                  title="Sem registros"
                  description="Nenhum dado encontrado para período e filtros."
                />
              )}
              <Pagination
                count={data.count}
                next={data.next}
                previous={data.previous}
                onPage={(url) => void load(url)}
              />
            </section>
          </>
        )}
      </div>
    </>
  );
}

export default function ReportsRoute() {
  return (
    <AdminGuard
      requiredPermissions={[
        permissions.viewSalesReport,
        permissions.viewConsumptionsReport,
        permissions.viewCashReport,
        permissions.viewWithdrawalsReport,
        permissions.viewInventoryReport,
        permissions.viewOperationalResult,
      ]}
    >
      <ReportsPage />
    </AdminGuard>
  );
}
