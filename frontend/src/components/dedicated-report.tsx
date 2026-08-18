"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Download, Filter, RefreshCw } from "lucide-react";
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
import { domainLabel } from "@/lib/domain-labels";
import { formatBRL, formatDate, formatQuantity } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type {
  ProductPriceComparison,
  ReportResponse,
  ReportsOptions,
} from "@/types";

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

const configs: Record<
  ReportKind,
  { title: string; description: string; endpoint: string; permission: string }
> = {
  overview: {
    title: "Visão gerencial",
    description: "Resumo comercial e financeiro da filial.",
    endpoint: "sales",
    permission: permissions.viewSalesReport,
  },
  sales: {
    title: "Vendas",
    description: "Vendas comerciais, responsáveis e valores históricos.",
    endpoint: "sales",
    permission: permissions.viewSalesReport,
  },
  products: {
    title: "Produtos & Performance",
    description: "Performance comercial por produto e categoria.",
    endpoint: "sales",
    permission: permissions.viewProductsReport,
  },
  receipts: {
    title: "Recebimentos",
    description: "Distribuição do faturamento por forma de pagamento.",
    endpoint: "sales",
    permission: permissions.viewReceiptsReport,
  },
  operators: {
    title: "Operadores",
    description: "Faturamento processado por operador de caixa.",
    endpoint: "sales",
    permission: permissions.viewTeamReport,
  },
  sellers: {
    title: "Atendentes",
    description: "Vendas e ticket por atendente responsável.",
    endpoint: "sales",
    permission: permissions.viewTeamReport,
  },
  commissions: {
    title: "Comissões",
    description: "Comissão histórica atribuída ao atendente da venda.",
    endpoint: "sales",
    permission: permissions.viewCommission,
  },
  discounts: {
    title: "Descontos",
    description: "Descontos manuais e benefícios promocionais.",
    endpoint: "sales",
    permission: permissions.viewDiscountsReport,
  },
  consumptions: {
    title: "Consumações & Cortesias",
    description: "Referência, valor cobrado e benefício operacional.",
    endpoint: "consumptions",
    permission: permissions.viewConsumptionsReport,
  },
  cash: {
    title: "Caixa",
    description: "Sessões por interseção temporal e resumo completo.",
    endpoint: "cash",
    permission: permissions.viewCashReport,
  },
  withdrawals: {
    title: "Sangrias",
    description: "Saídas de gaveta, beneficiários e impacto no resultado.",
    endpoint: "withdrawals",
    permission: permissions.viewWithdrawalsReport,
  },
  "stock-consumption": {
    title: "Consumo de estoque",
    description: "Resumo físico e movimentos reais de saída e reversão.",
    endpoint: "stock-consumption",
    permission: permissions.viewStockConsumptionReport,
  },
  cancellations: {
    title: "Cancelamentos & Estornos",
    description: "Operações canceladas no período do cancelamento.",
    endpoint: "cancellations",
    permission: permissions.viewCancellationsReport,
  },
  prices: {
    title: "Preços por filial",
    description: "Comparação entre preço padrão e overrides por filial.",
    endpoint: "prices",
    permission: permissions.viewPricesReport,
  },
  result: {
    title: "Resultado estimado",
    description: "Receita, CMV histórico, despesas e margem operacional.",
    endpoint: "operational-result",
    permission: permissions.viewOperationalResult,
  },
};

function initialPeriod(): PeriodValue {
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, "0");
  const start = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-01T00:00`;
  return {
    start,
    end: `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T23:59`,
  };
}

function Kpi({
  label,
  value,
  money = false,
}: {
  label: string;
  value: unknown;
  money?: boolean;
}) {
  return (
    <div className="rounded-lg border border-dashed border-slate-200 p-4">
      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
        {label}
      </span>
      <strong className="mt-2 block text-xl text-dark">
        {money ? formatBRL(String(value || "0")) : String(value ?? "-")}
      </strong>
    </div>
  );
}

function SalesRows({ rows }: { rows: Array<Record<string, unknown>> }) {
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Venda</th>
          <th>Data</th>
          <th>Responsáveis</th>
          <th>Status</th>
          <th>Total</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const seller = row.seller as { name?: string } | null;
          const operator = row.operator as { name?: string } | null;
          return (
            <tr key={String(row.id)}>
              <td>
                <strong>{String(row.sale_number)}</strong>
              </td>
              <td>{formatDate(String(row.cancelled_at || row.created_at))}</td>
              <td>
                <span className="block">Atendente: {seller?.name || "-"}</span>
                <small className="text-slate-500">
                  Operador: {operator?.name || "-"}
                </small>
              </td>
              <td>{domainLabel(row.status)}</td>
              <td>{formatBRL(String(row.total))}</td>
              <td className="text-right">
                <Link
                  className="text-xs font-bold text-primary"
                  href={`/vendas/${row.id}`}
                >
                  Detalhes
                </Link>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function DedicatedBody({
  kind,
  data,
}: {
  kind: ReportKind;
  data: ReportResponse<Record<string, unknown>>;
}) {
  const summary = data.summary;
  if (
    ["products", "receipts", "operators", "sellers", "commissions"].includes(
      kind,
    )
  ) {
    const key =
      kind === "products"
        ? "product_ranking"
        : kind === "receipts"
          ? "payment_totals"
          : kind === "operators"
            ? "operator_groups"
            : "seller_groups";
    const rows = (summary[key] as Array<Record<string, unknown>>) || [];
    return (
      <section className="card overflow-hidden">
        <div className="card-header">
          <h2 className="text-sm font-bold">Detalhamento</h2>
        </div>
        {rows.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>
                    {kind === "receipts"
                      ? "Forma de pagamento"
                      : kind === "products"
                        ? "Produto"
                        : "Pessoa"}
                  </th>
                  <th>Quantidade</th>
                  <th>Faturamento</th>
                  {kind === "commissions" && <th>Comissão</th>}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => {
                  const user = row.user as { name?: string } | undefined;
                  return (
                    <tr key={index}>
                      <td>
                        <strong>
                          {String(
                            row.product_name ||
                              row.name ||
                              row.payment_method_name ||
                              user?.name ||
                              "-",
                          )}
                        </strong>
                      </td>
                      <td>
                        {formatQuantity(
                          String(row.quantity || row.count || "0"),
                        )}
                      </td>
                      <td>
                        {formatBRL(
                          String(
                            row.revenue ||
                              row.amount ||
                              row.effective_revenue ||
                              "0",
                          ),
                        )}
                      </td>
                      {kind === "commissions" && (
                        <td>{formatBRL(String(row.commission || "0"))}</td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="Sem dados"
            description="Nenhum registro encontrado no período."
          />
        )}
      </section>
    );
  }
  if (kind === "stock-consumption") {
    const products = (summary.products as Array<Record<string, unknown>>) || [];
    return (
      <>
        <section className="card overflow-hidden">
          <div className="card-header">
            <h2 className="text-sm font-bold">Resumo por produto físico</h2>
          </div>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Produto</th>
                  <th>Bruta</th>
                  <th>Devoluções</th>
                  <th>Líquida</th>
                </tr>
              </thead>
              <tbody>
                {products.map((row, index) => {
                  const product = row.product as {
                    name?: string;
                    unit?: string;
                  };
                  return (
                    <tr key={index}>
                      <td>
                        <strong>{product.name}</strong>
                      </td>
                      <td>
                        {formatQuantity(String(row.gross_quantity))}{" "}
                        {product.unit?.toUpperCase()}
                      </td>
                      <td>{formatQuantity(String(row.returned_quantity))}</td>
                      <td>{formatQuantity(String(row.net_quantity))}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
        <section className="card overflow-hidden">
          <div className="card-header">
            <h2 className="text-sm font-bold">Movimentações detalhadas</h2>
          </div>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Data</th>
                  <th>Produto</th>
                  <th>Origem</th>
                  <th>Natureza</th>
                  <th>Quantidade</th>
                </tr>
              </thead>
              <tbody>
                {data.results.map((row, index) => {
                  const product = row.product as { name?: string };
                  return (
                    <tr key={index}>
                      <td>{formatDate(String(row.created_at))}</td>
                      <td>{product.name}</td>
                      <td>{domainLabel(row.origin)}</td>
                      <td>{domainLabel(row.nature)}</td>
                      <td>{formatQuantity(String(row.quantity))}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      </>
    );
  }
  if (kind === "cash")
    return (
      <section className="card overflow-hidden">
        <div className="card-header">
          <h2 className="text-sm font-bold">Sessões de caixa</h2>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Sessão</th>
                <th>Período</th>
                <th>Vendas</th>
                <th>Faturamento efetivo</th>
                <th>Esperado em dinheiro</th>
                <th>Diferença</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((row) => {
                const register = row.register as { name?: string };
                const operational = row.operational_summary as Record<
                  string,
                  unknown
                >;
                const sales = (operational?.sales || {}) as Record<
                  string,
                  unknown
                >;
                return (
                  <tr key={String(row.id)}>
                    <td>
                      <Link
                        className="font-bold text-primary"
                        href={`/caixas/sessoes/${row.id}`}
                      >
                        {register.name} #{String(row.id)}
                      </Link>
                    </td>
                    <td>{formatDate(String(row.opened_at))}</td>
                    <td>{String(sales.count || 0)}</td>
                    <td>{formatBRL(String(sales.effective_revenue || "0"))}</td>
                    <td>{formatBRL(String(row.expected))}</td>
                    <td>
                      {row.difference == null
                        ? "-"
                        : formatBRL(String(row.difference))}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    );
  if (kind === "withdrawals")
    return (
      <section className="card overflow-hidden">
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Data</th>
                <th>Categoria</th>
                <th>Beneficiário</th>
                <th>Motivo</th>
                <th>Registrado por</th>
                <th>Valor</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((row) => {
                const beneficiary = row.beneficiary as { name?: string } | null;
                const operator = row.operator as { name?: string };
                return (
                  <tr key={String(row.id)}>
                    <td>{formatDate(String(row.created_at))}</td>
                    <td>{String(row.category_label)}</td>
                    <td>{beneficiary?.name || "-"}</td>
                    <td>{String(row.reason)}</td>
                    <td>{operator?.name}</td>
                    <td>{formatBRL(String(row.amount))}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    );
  return (
    <section className="card overflow-hidden">
      <div className="card-header">
        <h2 className="text-sm font-bold">Operações</h2>
      </div>
      {data.results.length ? (
        <div className="table-wrap">
          <SalesRows rows={data.results} />
        </div>
      ) : (
        <EmptyState
          title="Sem registros"
          description="Nenhuma operação encontrada no período."
        />
      )}
    </section>
  );
}

export function DedicatedReport({ kind }: { kind: ReportKind }) {
  const config = configs[kind];
  const { currentBranch, hasPermission } = useAuth();
  const context = useRef(currentBranch?.id || 0);
  context.current = currentBranch?.id || 0;
  const [period, setPeriod] = useState(initialPeriod);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [options, setOptions] = useState<ReportsOptions | null>(null);
  const [data, setData] = useState<ReportResponse<
    Record<string, unknown>
  > | null>(null);
  const [prices, setPrices] = useState<ProductPriceComparison | null>(null);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState(false);
  const allowed = hasPermission(config.permission);

  function params(nextPeriod = period, nextFilters = filters) {
    return new URLSearchParams({
      start_datetime: nextPeriod.start,
      end_datetime: nextPeriod.end,
      ...(config.endpoint === "sales" ? { scope: kind } : {}),
      ...Object.fromEntries(
        Object.entries(nextFilters).filter(([, value]) => value),
      ),
    });
  }
  async function load(
    nextPeriod = period,
    nextFilters = filters,
    token = context.current,
  ) {
    if (!currentBranch || !allowed) return;
    setData(null);
    setError("");
    try {
      if (kind === "prices") {
        const result = await http.get<ProductPriceComparison>(
          "products/price-comparison/",
        );
        if (context.current === token) setPrices(result);
        return;
      }
      const result = await http.get<ReportResponse<Record<string, unknown>>>(
        `reports/${config.endpoint}/?${params(nextPeriod, nextFilters)}`,
      );
      if (context.current === token) setData(result);
    } catch (caught) {
      if (context.current === token)
        setError(
          caught instanceof ApiError
            ? caught.message
            : "Não foi possível carregar o relatório.",
        );
    }
  }
  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const start = query.get("start_datetime");
    const end = query.get("end_datetime");
    const nextPeriod = start && end ? { start, end } : initialPeriod();
    const nextFilters = Object.fromEntries(
      [...query.entries()].filter(
        ([key]) => !["start_datetime", "end_datetime", "branch", "scope"].includes(key),
      ),
    );
    setPeriod(nextPeriod);
    setFilters(nextFilters);
    void load(nextPeriod, nextFilters, context.current);
    void http
      .get<ReportsOptions>("reports/options/")
      .then(setOptions)
      .catch(() => setOptions(null));
  }, [currentBranch?.id, kind, allowed]);
  async function download() {
    if (!currentBranch || kind === "prices") return;
    setDownloading(true);
    try {
      const base = (
        process.env.NEXT_PUBLIC_API_URL || "http://localhost:18000/api/v1"
      ).replace(/\/$/, "");
      const query = params();
      query.set("export", "csv");
      const response = await fetch(
        `${base}/reports/${config.endpoint}/?${query}`,
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
      link.download = `${kind}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("Não foi possível exportar este relatório.");
    } finally {
      setDownloading(false);
    }
  }
  if (!allowed)
    return (
      <div className="p-6">
        <Alert message="Você não possui permissão para este relatório." />
      </div>
    );
  return (
    <>
      <PageHeader
        title={config.title}
        description={config.description}
        action={
          <div className="flex gap-2">
            <Link className="btn btn-secondary" href="/relatorios">
              Central
            </Link>
            {kind !== "prices" && hasPermission(permissions.exportReports) && (
              <Button
                variant="secondary"
                loading={downloading}
                onClick={() => void download()}
              >
                <Download className="size-4" />
                Exportar
              </Button>
            )}
          </div>
        }
      />
      <div className="space-y-5 p-4 sm:p-6 lg:p-8">
        {error && <Alert message={error} />}
        {kind !== "prices" && (
          <section className="card p-4">
            <div className="mb-3 flex items-center gap-2 text-xs font-bold">
              <Filter className="size-4 text-primary" />
              Filtros
            </div>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <PeriodFilter
                value={period}
                onApply={(next) => {
                  setPeriod(next);
                  void load(next);
                }}
              />
              {[
                "sales",
                "overview",
                "products",
                "discounts",
                "consumptions",
                "stock-consumption",
                "cancellations",
              ].includes(kind) && (
                <Field label="Categoria">
                  <Select
                    value={filters.category || ""}
                    onChange={(event) =>
                      setFilters((current) => ({
                        ...current,
                        category: event.target.value,
                      }))
                    }
                  >
                    <option value="">Todas</option>
                    {options?.categories.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </Select>
                </Field>
              )}
              {["sales", "overview", "products", "discounts", "consumptions", "stock-consumption", "cancellations"].includes(kind) && (
                <Field label="Produto">
                  <Select value={filters.product || ""} onChange={(event) => setFilters((current) => ({ ...current, product: event.target.value }))}>
                    <option value="">Todos</option>
                    {options?.products.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                  </Select>
                </Field>
              )}
              {["sales", "overview", "operators", "discounts", "cancellations", "cash", "withdrawals"].includes(kind) && (
                <Field label="Operador">
                  <Select value={filters.operator || ""} onChange={(event) => setFilters((current) => ({ ...current, operator: event.target.value }))}>
                    <option value="">Todos</option>
                    {options?.operators.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                  </Select>
                </Field>
              )}
              {["sales", "overview", "sellers", "commissions", "discounts", "cancellations"].includes(kind) && (
                <Field label="Atendente">
                  <Select value={filters.seller || ""} onChange={(event) => setFilters((current) => ({ ...current, seller: event.target.value }))}>
                    <option value="">Todos</option>
                    {options?.sellers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                  </Select>
                </Field>
              )}
              {["sales", "overview", "receipts"].includes(kind) && (
                <Field label="Forma de pagamento">
                  <Select value={filters.payment_method || String(options?.payment_methods.find((item) => item.code === filters.payment_method_code)?.id || "")} onChange={(event) => setFilters((current) => ({ ...current, payment_method: event.target.value, payment_method_code: "" }))}>
                    <option value="">Todas</option>
                    {options?.payment_methods.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                  </Select>
                </Field>
              )}
              {["sales", "overview"].includes(kind) && (
                <Field label="Dia da semana">
                  <Select value={filters.weekday || ""} onChange={(event) => setFilters((current) => ({ ...current, weekday: event.target.value }))}>
                    <option value="">Todos</option>{["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"].map((label, index) => <option key={label} value={index}>{label}</option>)}
                  </Select>
                </Field>
              )}
              {["sales", "overview"].includes(kind) && (
                <Field label="Hora">
                  <Select value={filters.hour || ""} onChange={(event) => setFilters((current) => ({ ...current, hour: event.target.value }))}>
                    <option value="">Todas</option>{Array.from({ length: 24 }, (_, hour) => <option key={hour} value={hour}>{String(hour).padStart(2, "0")}:00</option>)}
                  </Select>
                </Field>
              )}
              {["consumptions", "withdrawals"].includes(kind) && (
                <Field label="Beneficiário">
                  <Select value={filters.beneficiary || ""} onChange={(event) => setFilters((current) => ({ ...current, beneficiary: event.target.value }))}>
                    <option value="">Todos</option>
                    {options?.beneficiaries.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                  </Select>
                </Field>
              )}
              {["cash", "withdrawals"].includes(kind) && (
                <Field label="Caixa">
                  <Select value={filters.cash_register || ""} onChange={(event) => setFilters((current) => ({ ...current, cash_register: event.target.value }))}>
                    <option value="">Todos</option>
                    {options?.cash_registers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                  </Select>
                </Field>
              )}
              {kind === "withdrawals" && (
                <Field label="Categoria da sangria">
                  <Select value={filters.category || ""} onChange={(event) => setFilters((current) => ({ ...current, category: event.target.value }))}>
                    <option value="">Todas</option>
                    {options?.withdrawal_categories.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                  </Select>
                </Field>
              )}
              {kind === "cash" && (
                <Field label="Status da sessão">
                  <Select value={filters.status || ""} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}>
                    <option value="">Todos</option><option value="open">Aberta</option><option value="closed">Fechada</option>
                  </Select>
                </Field>
              )}
              {kind === "result" && (
                <Field label="Sessão de caixa">
                  <Select
                    value={filters.cash_session || ""}
                    onChange={(event) =>
                      setFilters((current) => ({
                        ...current,
                        cash_session: event.target.value,
                      }))
                    }
                  >
                    <option value="">Todas</option>
                    {options?.cash_sessions.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </Select>
                </Field>
              )}
              <div className="flex items-end">
                <Button onClick={() => void load()}>
                  <RefreshCw className="size-4" />
                  Aplicar
                </Button>
              </div>
            </div>
          </section>
        )}
        {kind === "prices" ? (
          <section className="card overflow-hidden">
            {!prices ? (
              <TableLoading />
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Produto</th>
                      <th>Preço padrão</th>
                      {prices.branches.map((branch) => (
                        <th key={branch.id}>{branch.name}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {prices.products.map((product) => (
                      <tr key={product.id}>
                        <td>
                          <strong>{product.name}</strong>
                          <small className="block text-slate-500">
                            {product.internal_code}
                          </small>
                        </td>
                        <td>{formatBRL(product.default_price)}</td>
                        {prices.branches.map((branch) => (
                          <td key={branch.id}>
                            {formatBRL(
                              product.prices[String(branch.id)] ||
                                product.default_price,
                            )}
                            <small className="block text-slate-500">
                              {product.prices[String(branch.id)]
                                ? "Preço da filial"
                                : "Preço padrão"}
                            </small>
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        ) : !data ? (
          <section className="card">
            <TableLoading />
          </section>
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <Kpi
                label="Quantidade"
                value={data.summary.count || data.count}
              />
              <Kpi
                label="Faturamento efetivo"
                value={
                  data.summary.effective_revenue ||
                  data.summary.charged ||
                  data.summary.value ||
                  data.summary.amount ||
                  data.summary.result ||
                  "0"
                }
                money
              />
              <Kpi
                label="Descontos"
                value={
                  data.summary.total_discount ||
                  data.summary.discounts ||
                  data.summary.subsidy ||
                  "0"
                }
                money
              />
              <Kpi
                label="Ticket / margem"
                value={data.summary.average || data.summary.margin || "0"}
                money={kind !== "result"}
              />
            </div>
            <DedicatedBody kind={kind} data={data} />
            {data.count > data.results.length && (
              <Pagination
                count={data.count}
                next={data.next}
                previous={data.previous}
                onPage={(path) =>
                  http
                    .get<ReportResponse<Record<string, unknown>>>(path)
                    .then(setData)
                    .catch(() => setError("Não foi possível trocar a página."))
                }
              />
            )}
          </>
        )}
      </div>
    </>
  );
}
