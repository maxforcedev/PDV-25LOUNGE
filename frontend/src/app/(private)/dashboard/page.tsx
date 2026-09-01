"use client";

import Link from "next/link";
import { useEffect, useEffectEvent, useRef, useState } from "react";
import {
  CalendarRange,
  CircleAlert,
  CircleDollarSign,
  ReceiptText,
  ShoppingBasket,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import {
  Alert,
  Button,
  EmptyState,
  Field,
  TableLoading,
} from "@/components/ui";
import { domainLabel } from "@/lib/domain-labels";
import {
  decimalIsZero,
  formatDate,
  formatDecimalBRL as formatBRL,
  formatPercent,
  formatQuantity,
} from "@/lib/format";
import { signedMoneyToCents } from "@/lib/cash";
import { ApiError, http } from "@/lib/http";
import {
  businessPeriod,
  dashboardPeriods,
  dashboardQuery,
  validDashboardPeriod,
  type PeriodValue,
} from "@/lib/period";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { DashboardData } from "@/types";

function positiveMoneyCents(value: unknown) {
  const cents = signedMoneyToCents(value);
  return cents !== null && cents > BigInt(0) ? cents : BigInt(0);
}

function ratioPercent(value: bigint, total: bigint) {
  if (value <= BigInt(0) || total <= BigInt(0)) return 0;
  return Number((value * BigInt(10_000)) / total) / 100;
}

function samePeriod(left: PeriodValue, right: PeriodValue) {
  return left.start === right.start && left.end === right.end;
}

function Kpi({
  label,
  value,
  note,
  icon: Icon,
  href,
  tone = "primary",
}: {
  label: string;
  value: string;
  note: string;
  icon: LucideIcon;
  href?: string;
  tone?: "primary" | "success" | "warning";
}) {
  const tones = {
    primary: "bg-primary/10 text-primary",
    success: "bg-success/10 text-success-strong",
    warning: "bg-warning/10 text-warning-strong",
  };
  const content = (
    <div className="flex justify-between gap-4">
      <div className="min-w-0">
        <p className="text-[10px] font-bold uppercase tracking-[.14em] text-muted">
          {label}
        </p>
        <strong className="mt-3 block truncate text-2xl text-dark">
          {value}
        </strong>
        <span className="mt-1 block text-[11px] text-muted">{note}</span>
      </div>
      <span
        className={`flex size-10 shrink-0 items-center justify-center rounded-lg ${tones[tone]}`}
      >
        <Icon className="size-5" />
      </span>
    </div>
  );
  const className = href
    ? "card p-5 transition hover:-translate-y-0.5 hover:shadow-md focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/25"
    : "card p-5";
  return href ? (
    <Link href={href} className={className}>
      {content}
    </Link>
  ) : (
    <div className={className}>{content}</div>
  );
}

function DailyRevenueChart({
  rows,
  href,
}: {
  rows: NonNullable<DashboardData["sales"]>["weekly_comparison"]["current"];
  href?: string;
}) {
  const max = rows.reduce((largest, row) => {
    const value = positiveMoneyCents(row.sales_revenue);
    return value > largest ? value : largest;
  }, BigInt(0));
  const hasRevenue = rows.some((row) => !decimalIsZero(row.sales_revenue));

  function dayHref(date: string) {
    if (!href) return "";
    const [pathname, query = ""] = href.split("?");
    const params = new URLSearchParams(query);
    params.set("start_datetime", `${date}T00:00:00`);
    params.set("end_datetime", `${date}T23:59:59`);
    return `${pathname}?${params}`;
  }

  return (
    <section className="card overflow-hidden">
      <div className="card-header">
        <div>
          <h2 className="text-sm font-bold">Vendas no período</h2>
          <p className="mt-1 text-[11px] text-muted">
            Faturamento comercial por dia
          </p>
        </div>
        {href && (
          <Link className="text-xs font-bold text-link" href={href}>
            Ver detalhes
          </Link>
        )}
      </div>
      {hasRevenue ? (
        <div className="overflow-x-auto p-5">
          <div
            className="flex h-64 min-w-full items-end gap-2"
            aria-label="Faturamento diário no período"
          >
            {rows.map((row) => {
              const label = `${row.date}: ${formatBRL(row.sales_revenue)}`;
              const style = {
                height: `${Math.max(
                  4,
                  ratioPercent(positiveMoneyCents(row.sales_revenue), max),
                )}%`,
              };
              const bar = (
                <span
                  className="group relative block w-full rounded-t-md bg-chart-1 transition hover:brightness-110"
                  style={style}
                >
                  <span className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 w-max -translate-x-1/2 rounded bg-chart-tooltip px-2 py-1 text-[10px] text-chart-tooltip-fg opacity-0 shadow-lg transition group-hover:opacity-100 group-focus-visible:opacity-100">
                    {formatBRL(row.sales_revenue)} · {row.count} vendas
                  </span>
                </span>
              );
              return (
                <div
                  key={row.date}
                  className="flex h-full min-w-12 flex-1 flex-col justify-end"
                >
                  {href ? (
                    <Link
                      href={dayHref(row.date)}
                      aria-label={label}
                      className="flex h-52 items-end focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus"
                    >
                      {bar}
                    </Link>
                  ) : (
                    <div aria-label={label} className="flex h-52 items-end">
                      {bar}
                    </div>
                  )}
                  <span className="mt-2 text-center text-[9px] text-muted">
                    {row.date.slice(8, 10)}/{row.date.slice(5, 7)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <EmptyState
          title="Sem vendas"
          description="Nenhum faturamento foi registrado no período."
        />
      )}
    </section>
  );
}

function DashboardPage() {
  const { currentBranch, hasAnyPermission, hasFeature, hasPermission } = useAuth();
  const context = useRef(currentBranch?.id || 0);
  context.current = currentBranch?.id || 0;
  const [period, setPeriod] = useState<PeriodValue>(() => businessPeriod());
  const [draftPeriod, setDraftPeriod] = useState<PeriodValue>(() =>
    businessPeriod(),
  );
  const [customOpen, setCustomOpen] = useState(false);
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const requestSequence = useRef(0);

  function updateUrl(next: PeriodValue) {
    const params = new URLSearchParams({
      start_datetime: next.start,
      end_datetime: next.end,
    });
    window.history.replaceState(
      window.history.state,
      "",
      `${window.location.pathname}?${params}`,
    );
  }

  async function load(next: PeriodValue, token = context.current) {
    if (!currentBranch) {
      setLoading(false);
      return;
    }
    const request = ++requestSequence.current;
    setLoading(true);
    setData(null);
    setError("");
    const params = dashboardQuery(next);
    try {
      const result = await http.get<DashboardData>(`dashboard/?${params}`);
      if (context.current === token && requestSequence.current === request) {
        setData(result);
      }
    } catch (caught) {
      if (context.current !== token || requestSequence.current !== request)
        return;
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível carregar o Dashboard.",
      );
    } finally {
      if (context.current === token && requestSequence.current === request) {
        setLoading(false);
      }
    }
  }

  const loadDashboard = useEffectEvent(load);

  function apply(next: PeriodValue) {
    if (!validDashboardPeriod(next)) {
      setError("Informe um período personalizado válido.");
      return;
    }
    setPeriod(next);
    setDraftPeriod(next);
    setCustomOpen(false);
    updateUrl(next);
    void load(next, context.current);
  }

  useEffect(() => {
    requestSequence.current += 1;
    setData(null);
    setError("");
    if (!currentBranch) {
      setLoading(false);
      return;
    }
    const params = new URLSearchParams(window.location.search);
    const requested = {
      start: params.get("start_datetime") || "",
      end: params.get("end_datetime") || "",
    };
    const dateTimePattern = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$/;
    const next =
      dateTimePattern.test(requested.start) &&
      dateTimePattern.test(requested.end) &&
      requested.start <= requested.end
        ? requested
        : businessPeriod();
    setPeriod(next);
    setDraftPeriod(next);
    updateUrl(next);
    void loadDashboard(next, currentBranch.id);
  }, [currentBranch]);

  const query = new URLSearchParams({
    start_datetime: period.start,
    end_datetime: period.end,
  }).toString();
  const report = (slug: string, extra = "") =>
    `/relatorios/${slug}?${query}${extra}`;
  const canViewSalesReport = hasPermission(permissions.viewSalesReport);
  const canViewReceiptsReport = hasPermission(permissions.viewReceiptsReport);
  const canViewProductsReport = hasPermission(permissions.viewProductsReport);
  const canViewResultReport = hasPermission(permissions.viewOperationalResult);
  const canViewInventory = hasPermission(permissions.viewInventory);
  const canViewCash = hasPermission(permissions.viewCashRegister);
  const canViewCommands = hasPermission(permissions.viewCommands);
  const canViewSaleDetail = hasAnyPermission([
    permissions.viewSale,
    permissions.cancelSale,
  ]);
  const sales = data?.sales;
  const result =
    data?.operational_result?.result ??
    data?.operational_result?.estimated_result;
  const presets = dashboardPeriods();
  const operationalAlerts: Array<{
    key: string;
    title: string;
    detail: string;
    href?: string;
    tone: "danger" | "warning" | "info";
  }> = [];
  if (data?.inventory?.negative_count) {
    operationalAlerts.push({
      key: "negative-stock",
      title: `${data.inventory.negative_count} produto(s) com estoque negativo`,
      detail: "Revise as movimentações e faça o ajuste necessário.",
      href: canViewInventory ? "/estoque?state=negative" : undefined,
      tone: "danger",
    });
  }
  if (sales && !decimalIsZero(sales.reconciliation_delta)) {
    operationalAlerts.push({
      key: "reconciliation",
      title: `${formatBRL(sales.reconciliation_delta.replace(/^-/, ""))} de divergência de pagamentos`,
      detail: "Revise a reconciliação do período.",
      href: canViewReceiptsReport ? report("recebimentos") : undefined,
      tone: "danger",
    });
  }
  if (data?.inventory?.zero_count) {
    operationalAlerts.push({
      key: "zero-stock",
      title: `${data.inventory.zero_count} produto(s) com estoque zerado`,
      detail: "Avalie a necessidade de reposição.",
      href: canViewInventory ? "/estoque?state=zero" : undefined,
      tone: "warning",
    });
  }
  if (data?.inventory?.below_minimum_count) {
    operationalAlerts.push({
      key: "minimum-stock",
      title: `${data.inventory.below_minimum_count} produto(s) abaixo do mínimo`,
      detail: "Avalie a necessidade de reposição.",
      href: canViewInventory ? "/estoque?state=below_minimum" : undefined,
      tone: "warning",
    });
  }
  if (
    data?.commands?.open_table_count &&
    hasFeature("tables")
  ) {
    operationalAlerts.push({
      key: "open-tables",
      title: `${data.commands.open_table_count} mesa(s) aberta(s)`,
      detail: "Mesas com comandas em andamento.",
      href: canViewCommands ? "/mesas" : undefined,
      tone: "info",
    });
  }
  if (data?.commands?.open_count && hasFeature("commands")) {
    operationalAlerts.push({
      key: "open-commands",
      title: `${data.commands.open_count} comanda(s) aberta(s)`,
      detail: "Comandas em andamento na filial.",
      href: canViewCommands ? "/comandas" : undefined,
      tone: "info",
    });
  }
  if (data?.current_cash?.length && hasFeature("cash_register")) {
    operationalAlerts.push({
      key: "open-cash",
      title: `${data.current_cash.length} caixa(s) aberto(s)`,
      detail: "Sessões de caixa em andamento.",
      href: canViewCash
        ? `/caixas/sessoes/${data.current_cash[0].id}`
        : undefined,
      tone: "info",
    });
  }

  return (
    <>
      <PageHeader
        title="Dashboard"
        description={`Visão rápida da operação de ${currentBranch?.name || "sua filial"}.`}
      />
      <div className="space-y-5 p-4 sm:p-6 lg:p-8">
        <section className="card p-4">
          <div className="flex flex-wrap items-center gap-2">
            <CalendarRange className="mr-1 size-4 text-primary" />
            {presets.map(([label, value]) => (
              <button
                key={label}
                type="button"
                className={`rounded-full px-4 py-2 text-xs font-bold transition focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/20 ${
                  samePeriod(period, value)
                    ? "bg-primary text-white"
                    : "bg-surface-muted text-muted hover:bg-primary/10 hover:text-link"
                }`}
                onClick={() => apply(value)}
              >
                {label}
              </button>
            ))}
            <button
              type="button"
              className={`rounded-full px-4 py-2 text-xs font-bold transition focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/20 ${
                customOpen ||
                !presets.some(([, value]) => samePeriod(period, value))
                  ? "bg-primary text-white"
                  : "border border-subtle text-muted hover:bg-primary/10 hover:text-link"
              }`}
              onClick={() => setCustomOpen((open) => !open)}
              aria-expanded={customOpen}
            >
              Personalizado
            </button>
          </div>
          {customOpen && (
            <div className="mt-4 grid gap-3 border-t border-subtle pt-4 md:grid-cols-[1fr_1fr_auto] md:items-end">
              <Field label="Data/hora inicial">
                <input
                  className="input"
                  step="1"
                  type="datetime-local"
                  value={draftPeriod.start}
                  onChange={(event) =>
                    setDraftPeriod((value) => ({
                      ...value,
                      start: event.target.value,
                    }))
                  }
                />
              </Field>
              <Field label="Data/hora final">
                <input
                  className="input"
                  step="1"
                  type="datetime-local"
                  value={draftPeriod.end}
                  onChange={(event) =>
                    setDraftPeriod((value) => ({
                      ...value,
                      end: event.target.value,
                    }))
                  }
                />
              </Field>
              <Button onClick={() => apply(draftPeriod)}>
                Aplicar período
              </Button>
            </div>
          )}
        </section>

        {error && <Alert message={error} />}
        {loading ? (
          <section className="card">
            <TableLoading />
          </section>
        ) : data ? (
          <>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <Kpi
                label="Faturamento"
                value={sales ? formatBRL(sales.sales_revenue) : "Sem permissão"}
                note="Faturamento comercial no período"
                icon={TrendingUp}
                href={
                  sales && canViewSalesReport ? report("vendas") : undefined
                }
              />
              <Kpi
                label="Vendas"
                value={sales ? String(sales.count) : "Sem permissão"}
                note="Quantidade líquida de vendas"
                icon={ShoppingBasket}
                href={
                  sales && canViewSalesReport ? report("vendas") : undefined
                }
              />
              <Kpi
                label="Ticket médio"
                value={
                  sales ? formatBRL(sales.ticket_average) : "Sem permissão"
                }
                note="Faturamento dividido pelas vendas"
                icon={ReceiptText}
                href={
                  sales && canViewSalesReport ? report("vendas") : undefined
                }
              />
              <Kpi
                label="Resultado estimado"
                value={
                  result !== undefined ? formatBRL(result) : "Sem permissão"
                }
                note="Estimativa operacional, não contábil"
                icon={CircleDollarSign}
                tone={result !== undefined ? "success" : "warning"}
                href={
                  result !== undefined && canViewResultReport
                    ? report("resultado")
                    : undefined
                }
              />
            </div>

            <section className="card overflow-hidden">
              <div className="card-header">
                <div>
                  <h2 className="text-sm font-bold">Atenção operacional</h2>
                  <p className="mt-1 text-[11px] text-muted">
                    Exceções acionáveis conforme suas permissões
                  </p>
                </div>
              </div>
              {operationalAlerts.length ? (
                <div className="grid gap-3 p-4 md:grid-cols-2">
                  {operationalAlerts.map((item) => {
                    const content = (
                      <>
                        <CircleAlert className="mt-0.5 size-5 shrink-0" />
                        <span>
                          <strong className="block text-sm">
                            {item.title}
                          </strong>
                          <small className="mt-1 block text-[11px] opacity-80">
                            {item.detail}
                          </small>
                        </span>
                      </>
                    );
                    const className = `flex gap-3 rounded-lg border p-4 ${
                      item.tone === "danger"
                        ? "border-danger/30 bg-danger/10 text-danger-strong"
                        : item.tone === "warning"
                          ? "border-warning/30 bg-warning/10 text-warning-strong"
                          : "border-primary/25 bg-primary/5 text-primary"
                    }`;
                    return item.href ? (
                      <Link
                        key={item.key}
                        href={item.href}
                        className={className}
                      >
                        {content}
                      </Link>
                    ) : (
                      <div key={item.key} className={className}>
                        {content}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="p-5 text-sm text-muted">
                  Nenhuma exceção operacional detectada no momento.
                </div>
              )}
            </section>

            {sales ? (
              <>
                <DailyRevenueChart
                  rows={sales.weekly_comparison.current}
                  href={canViewSalesReport ? report("vendas") : undefined}
                />

                <div className="grid gap-5 xl:grid-cols-2">
                  <section className="card overflow-hidden">
                    <div className="card-header">
                      <div>
                        <h2 className="text-sm font-bold">Top 5 produtos</h2>
                        <p className="mt-1 text-[11px] text-muted">
                          Maior faturamento no período
                        </p>
                      </div>
                      {canViewProductsReport && (
                        <Link
                          className="text-xs font-bold text-link"
                          href={report("produtos")}
                        >
                          Ver relatório
                        </Link>
                      )}
                    </div>
                    {sales.top_products.length ? (
                      <ol className="divide-y divide-subtle px-5">
                        {sales.top_products.slice(0, 5).map((row, index) => {
                          const content = (
                            <>
                              <span className="flex min-w-0 items-center gap-3">
                                <b className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs text-primary">
                                  {index + 1}
                                </b>
                                <span className="truncate text-sm font-semibold">
                                  {row.product_name}
                                </span>
                              </span>
                              <span className="shrink-0 text-right">
                                <strong className="block text-sm">
                                  {formatBRL(row.sales_revenue)}
                                </strong>
                                <small className="text-[10px] text-muted">
                                  {formatQuantity(row.quantity)} vendidos
                                </small>
                              </span>
                            </>
                          );
                          return (
                            <li key={row.product_id || row.product_name}>
                              {canViewProductsReport && row.product_id ? (
                                <Link
                                  className="flex items-center justify-between gap-4 py-3"
                                  href={report(
                                    "produtos",
                                    `&product=${row.product_id}`,
                                  )}
                                >
                                  {content}
                                </Link>
                              ) : (
                                <div className="flex items-center justify-between gap-4 py-3">
                                  {content}
                                </div>
                              )}
                            </li>
                          );
                        })}
                      </ol>
                    ) : (
                      <EmptyState
                        title="Sem produtos vendidos"
                        description="Nenhum produto compõe o faturamento do período."
                      />
                    )}
                  </section>

                  <section className="card overflow-hidden">
                    <div className="card-header">
                      <div>
                        <h2 className="text-sm font-bold">
                          Formas de pagamento
                        </h2>
                        <p className="mt-1 text-[11px] text-muted">
                          Distribuição do total recebido
                        </p>
                      </div>
                      {canViewReceiptsReport && (
                        <Link
                          className="text-xs font-bold text-link"
                          href={report("recebimentos")}
                        >
                          Ver relatório
                        </Link>
                      )}
                    </div>
                    {sales.payment_distribution.length ? (
                      <div className="divide-y divide-subtle px-5">
                        {sales.payment_distribution.map((row) => {
                          const content = (
                            <>
                              <span className="text-sm font-semibold">
                                {row.name}
                              </span>
                              <span className="text-right">
                                <strong className="block text-sm">
                                  {formatBRL(row.payment_total)}
                                </strong>
                                <small className="text-[10px] text-muted">
                                  {formatPercent(row.percentage)}
                                </small>
                              </span>
                            </>
                          );
                          return canViewReceiptsReport ? (
                            <Link
                              key={row.code}
                              href={report(
                                "recebimentos",
                                `&payment_method_code=${encodeURIComponent(row.code)}`,
                              )}
                              className="flex items-center justify-between gap-4 py-3"
                            >
                              {content}
                            </Link>
                          ) : (
                            <div
                              key={row.code}
                              className="flex items-center justify-between gap-4 py-3"
                            >
                              {content}
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <EmptyState
                        title="Sem recebimentos"
                        description="Nenhuma forma de pagamento no período."
                      />
                    )}
                  </section>
                </div>

                <section className="card overflow-hidden">
                  <div className="card-header">
                    <h2 className="text-sm font-bold">Últimas 5 vendas</h2>
                    {canViewSalesReport && (
                      <Link
                        className="text-xs font-bold text-link"
                        href={report("vendas")}
                      >
                        Ver todas
                      </Link>
                    )}
                  </div>
                  {sales.latest_sales.results.length ? (
                    <div className="table-wrap">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Venda</th>
                            <th>Data</th>
                            <th>Atendente</th>
                            <th>Pagamento</th>
                            <th>Status</th>
                            <th>Total</th>
                          </tr>
                        </thead>
                        <tbody>
                          {sales.latest_sales.results
                            .slice(0, 5)
                            .map((sale) => (
                              <tr key={sale.id}>
                                <td>
                                  {canViewSaleDetail ? (
                                    <Link
                                      className="font-bold text-link"
                                      href={`/vendas/${sale.id}`}
                                    >
                                      {sale.sale_number}
                                    </Link>
                                  ) : (
                                    <strong>{sale.sale_number}</strong>
                                  )}
                                </td>
                                <td>{formatDate(sale.created_at)}</td>
                                <td>{sale.seller?.name || "-"}</td>
                                <td>
                                  {sale.payments
                                    .map((payment) =>
                                      String(payment.payment_method_name || ""),
                                    )
                                    .filter(Boolean)
                                    .join(", ") || "-"}
                                </td>
                                <td>{domainLabel(sale.status)}</td>
                                <td>{formatBRL(sale.total_received)}</td>
                              </tr>
                            ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <EmptyState
                      title="Sem vendas recentes"
                      description="Nenhuma venda no período."
                    />
                  )}
                </section>
              </>
            ) : (
              <section className="card">
                <EmptyState
                  title="Vendas sem permissão"
                  description="Os indicadores comerciais permanecem ocultos para este perfil."
                />
              </section>
            )}
          </>
        ) : !error ? (
          <section className="card">
            <EmptyState
              title="Dashboard indisponível"
              description="Selecione uma filial para carregar os indicadores."
            />
          </section>
        ) : null}
      </div>
    </>
  );
}

export default function DashboardRoute() {
  return (
    <AdminGuard requiredPermissions={[permissions.viewDashboard]}>
      <DashboardPage />
    </AdminGuard>
  );
}
