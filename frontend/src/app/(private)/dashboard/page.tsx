"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  Boxes,
  CalendarRange,
  ReceiptText,
  ShoppingBasket,
  TrendingDown,
  TrendingUp,
  Users,
} from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import {
  Alert,
  Button,
  EmptyState,
  Field,
  Select,
  TableLoading,
} from "@/components/ui";
import { domainLabel } from "@/lib/domain-labels";
import { formatBRL, formatDate, formatQuantity } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import {
  businessPeriod,
  toBusinessDateTimeLocal,
  type PeriodValue,
} from "@/lib/period";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { DashboardData, ReportUserGroup } from "@/types";

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
  icon: typeof TrendingUp;
  href?: string;
  tone?: "primary" | "danger" | "warning" | "success";
}) {
  const tones = {
    primary: "bg-primary/10 text-primary",
    danger: "bg-danger/10 text-danger-strong",
    warning: "bg-warning/10 text-warning-strong",
    success: "bg-success/10 text-success-strong",
  };
  const content = (
    <>
      <div className="flex justify-between gap-3">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[.14em] text-slate-500">
            {label}
          </p>
          <strong className="mt-3 block text-2xl text-dark">{value}</strong>
          <span className="mt-1 block text-[11px] text-slate-500">{note}</span>
        </div>
        <span
          className={`flex size-10 items-center justify-center rounded-lg ${tones[tone]}`}
        >
          <Icon className="size-5" />
        </span>
      </div>
    </>
  );
  const className = href
    ? "card group p-5 transition hover:-translate-y-0.5 hover:shadow-md focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/25"
    : "card p-5";
  return href ? (
    <Link href={href} className={className}>{content}</Link>
  ) : (
    <div className={className}>{content}</div>
  );
}

function HorizontalBars({
  title,
  rows,
  href,
}: {
  title: string;
  rows: Array<{
    label: string;
    value: number;
    display: string;
    note?: string;
    query?: string;
  }>;
  href?: string;
}) {
  const max = Math.max(...rows.map((row) => row.value), 0);
  return (
    <section className="card overflow-hidden">
      <div className="card-header">
        <h2 className="text-sm font-bold">{title}</h2>
        {href && (
          <Link className="text-xs font-bold text-link" href={href}>
            Ver relatório
          </Link>
        )}
      </div>
      {rows.length ? (
        <div className="space-y-4 p-5" aria-label={title}>
          {rows.map((row) => {
            const content = (
              <>
              <div className="mb-1.5 flex justify-between gap-3 text-xs">
                <span className="truncate font-semibold">
                  {row.label}
                  <small className="ml-1 font-normal text-slate-500">
                    {row.note}
                  </small>
                </span>
                <strong>{row.display}</strong>
              </div>
              <div className="h-2.5 overflow-hidden rounded-full bg-surface-muted">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-chart-1 to-chart-2"
                  style={{
                    width: `${max ? Math.max(3, (row.value / max) * 100) : 0}%`,
                  }}
                />
              </div>
              </>
            );
            return href ? (
              <Link
                href={`${href}${row.query || ""}`}
                key={row.label}
                title={`${row.label}: ${row.display}`}
                className="block rounded-md focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/25"
              >
                {content}
              </Link>
            ) : (
              <div key={row.label} title={`${row.label}: ${row.display}`}>
                {content}
              </div>
            );
          })}
        </div>
      ) : (
        <EmptyState
          title="Sem dados"
          description="Nenhum registro no período selecionado."
        />
      )}
    </section>
  );
}

function PaymentChart({
  rows,
  href,
  scope,
  totalReceived,
  reconciliationDelta,
}: {
  rows: NonNullable<DashboardData["sales"]>["payment_distribution"];
  href?: string;
  scope: NonNullable<DashboardData["sales"]>["payment_distribution_scope"];
  totalReceived: string;
  reconciliationDelta: string;
}) {
  const title = "Formas de pagamento";
  const subtitle = scope === "operational"
    ? "Inclui vendas comerciais, consumações cobradas e reversões no recorte."
    : "Escopo comercial: não inclui consumações sem permissão de visualização.";
  const colors = [
    "var(--chart-1)",
    "var(--chart-2)",
    "var(--chart-3)",
    "var(--chart-4)",
    "var(--chart-5)",
    "var(--chart-6)",
  ];
  const total = Number(totalReceived);
  const values = rows.map((row) => ({
    amount: Number(row.amount),
    paymentTotal: Number(row.payment_total),
    percentage: Number(row.percentage),
  }));
  const percentageTotal = values.reduce(
    (sum, row) => sum + row.percentage,
    0,
  );
  const roundedPercentageTotal = Number(percentageTotal.toFixed(6));
  const hasInvalidMethod = values.some(
    (row) =>
      !Number.isFinite(row.amount) ||
      !Number.isFinite(row.paymentTotal) ||
      !Number.isFinite(row.percentage) ||
      row.amount < 0 ||
      row.paymentTotal < 0 ||
      row.percentage < 0,
  );
  const hasInconsistentPercentage =
    total > 0 &&
    values.some(
      (row) =>
        Number.isFinite(row.paymentTotal) &&
        Number.isFinite(row.percentage) &&
        Math.abs(row.percentage - (row.paymentTotal * 100) / total) > 0.02,
    );
  const hasReconciliationDelta =
    Number.isFinite(Number(reconciliationDelta)) &&
    Math.abs(Number(reconciliationDelta)) >= 0.005;
  const canDrawDonut =
    total > 0 &&
    Number.isFinite(total) &&
    !hasInvalidMethod &&
    !hasInconsistentPercentage &&
    !hasReconciliationDelta &&
    roundedPercentageTotal > 0;
  const unavailableReason =
    total <= 0 || !Number.isFinite(total)
      ? "O Total recebido não é positivo neste recorte."
      : hasInvalidMethod
        ? "Há valores líquidos negativos ou inválidos por forma de pagamento após reversões."
        : hasInconsistentPercentage
          ? "Os percentuais por forma não reconciliam com o Total recebido."
          : hasReconciliationDelta
            ? "Os pagamentos não reconciliam com o Total recebido neste recorte."
        : roundedPercentageTotal <= 0
          ? "Não há participação positiva por forma de pagamento neste recorte."
          : "A distribuição excede 100% do Total recebido e não pode ser representada com segurança.";
  let cursor = 0;
  const visualScale = 100 / percentageTotal;
  const segments = values.map((row, index) => {
    const start = cursor;
    cursor = Number((cursor + row.percentage * visualScale).toFixed(6));
    return `${colors[index % colors.length]} ${start}% ${cursor}%`;
  });
  if (cursor < 100) segments.push(`var(--surface-muted) ${cursor}% 100%`);
  const donutTitle = rows
    .map(
      (row) =>
        `${row.name}: ${formatBRL(row.payment_total)} (${row.percentage}%)`,
    )
    .join(" · ");
  return (
    <section className="card overflow-hidden">
      <div className="card-header">
        <div>
          <h2 className="text-sm font-bold">{title}</h2>
          <p className="mt-1 text-[11px] text-slate-500">{subtitle}</p>
        </div>
        {href && (
          <Link className="text-xs font-bold text-link" href={href}>
            Ver relatório
          </Link>
        )}
      </div>
      {rows.length ? (
        <div className="grid items-center gap-6 p-5 sm:grid-cols-[minmax(180px,0.8fr)_minmax(0,1.2fr)]" aria-label="Distribuição por forma de pagamento">
          <div className="flex justify-center">
            {canDrawDonut ? (
              <div
                role="img"
                aria-label={`Total recebido: ${formatBRL(totalReceived)}. ${donutTitle}`}
                title={donutTitle}
                className="relative aspect-square w-full max-w-52 rounded-full shadow-inner"
                style={{
                  background: `conic-gradient(${segments.join(", ")})`,
                }}
              >
                <div className="absolute inset-[23%] flex flex-col items-center justify-center rounded-full bg-surface px-2 text-center shadow-sm">
                  <span className="text-[9px] font-bold uppercase tracking-[.12em] text-slate-500">
                    Total recebido
                  </span>
                  <strong className="mt-1 text-base text-dark sm:text-lg">
                    {formatBRL(totalReceived)}
                  </strong>
                </div>
              </div>
            ) : (
              <div
                role="img"
                aria-label={`Gráfico indisponível. ${unavailableReason}`}
                className="flex aspect-square w-full max-w-52 flex-col items-center justify-center rounded-full border-8 border-dashed border-subtle bg-surface-muted p-6 text-center"
              >
                <strong className="text-xs text-dark">Gráfico indisponível</strong>
                <span className="mt-1 text-[9px] font-bold uppercase tracking-[.1em] text-slate-500">
                  Total recebido: {formatBRL(totalReceived)}
                </span>
                <span className="mt-2 text-[10px] leading-relaxed text-slate-500">
                  {unavailableReason}
                </span>
              </div>
            )}
          </div>
          <div className="grid gap-2">
            {rows.map((row, index) => {
              const content = (
                <>
                <span className="flex min-w-0 items-center gap-2">
                  <i
                    className="size-2.5 shrink-0 rounded-full"
                    style={{ backgroundColor: colors[index % colors.length] }}
                  />
                  <span className="truncate">{row.name}</span>
                </span>
                <span className="flex shrink-0 items-baseline gap-2">
                  <strong>{formatBRL(row.payment_total)}</strong>
                  <small className="min-w-11 text-right text-slate-500">
                    {row.percentage}%
                  </small>
                </span>
                </>
              );
              return href ? (
                <Link
                  key={`${row.name}-${index}`}
                  href={`${href}&payment_method_code=${encodeURIComponent(row.code)}`}
                  title={`${row.name}: ${formatBRL(row.payment_total)} (${row.percentage}%)`}
                  className="flex items-center justify-between gap-3 rounded-md px-2 py-1.5 text-xs transition hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/25"
                >
                  {content}
                </Link>
              ) : (
                <div
                  key={`${row.name}-${index}`}
                  title={`${row.name}: ${formatBRL(row.payment_total)} (${row.percentage}%)`}
                  className="flex items-center justify-between gap-3 px-2 py-1.5 text-xs"
                >
                  {content}
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <EmptyState
          title="Sem recebimentos"
          description="Nenhum pagamento no período selecionado."
        />
      )}
      {hasReconciliationDelta && (
        <div className="flex items-center justify-between gap-3 border-t border-warning/30 bg-warning/10 px-5 py-3 text-xs text-warning-strong">
          <span>Delta de reconciliação</span>
          <strong>{formatBRL(reconciliationDelta)}</strong>
        </div>
      )}
    </section>
  );
}

function FinancialBridge({
  sales,
  href,
}: {
  sales: NonNullable<DashboardData["sales"]>;
  href?: string;
}) {
  const steps = [
    ["Faturamento de vendas", sales.sales_revenue, ""],
    ["Consumação cobrada", sales.consumption_charged, "+"],
    ["Faturamento efetivo", sales.effective_revenue, "="],
    ["Taxa de serviço", sales.service_fee, "+"],
    ["Total recebido", sales.total_received, "="],
  ] as const;
  return (
    <section className="card overflow-hidden">
      <div className="card-header">
        <div>
          <h2 className="text-sm font-bold">Composição do recebimento</h2>
          <p className="mt-1 text-[11px] text-slate-500">
            Faturamento efetivo e Total recebido no período aplicado.
          </p>
        </div>
        {href && (
          <Link className="text-xs font-bold text-link" href={href}>
            Ver recebimentos
          </Link>
        )}
      </div>
      <div className="grid gap-2 p-4 sm:grid-cols-2 xl:grid-cols-5">
        {steps.map(([label, value, operator], index) => {
          const content = (
            <>
            {operator && (
              <span className="absolute -left-2.5 top-1/2 z-10 flex size-5 -translate-y-1/2 items-center justify-center rounded-full border border-subtle bg-surface text-xs font-black text-primary">
                {operator}
              </span>
            )}
            <span className="text-[9px] font-bold uppercase tracking-[.12em] text-slate-500">
              {label}
            </span>
            <strong className="mt-2 block text-lg text-dark">
              {formatBRL(value)}
            </strong>
            </>
          );
          const className = `relative rounded-lg border p-4 ${href ? "transition hover:border-primary/40 hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/25" : ""} ${index === steps.length - 1 ? "border-primary/30 bg-primary/5" : "border-subtle"}`;
          return href ? (
            <Link key={label} href={href} className={className}>
              {content}
            </Link>
          ) : (
            <div key={label} className={className}>{content}</div>
          );
        })}
      </div>
    </section>
  );
}

function WeeklyComparison({
  comparison,
  href,
}: {
  comparison: NonNullable<DashboardData["sales"]>["weekly_comparison"];
  href?: string;
}) {
  const size = Math.max(comparison.current.length, comparison.previous.length);
  const points = Array.from({ length: size }, (_, index) => ({
    current: comparison.current[index],
    previous: comparison.previous[index],
  }));
  const max = Math.max(
    ...points.flatMap((point) => [
      Number(point.current?.sales_revenue || 0),
      Number(point.previous?.sales_revenue || 0),
    ]),
    0,
  );
  const hasData = points.some(
    (point) =>
      Number(point.current?.sales_revenue || 0) ||
      Number(point.previous?.sales_revenue || 0),
  );
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
          <h2 className="text-sm font-bold">Comparativo do período</h2>
          <p className="mt-1 text-[11px] text-slate-500">
            Atual × período anterior equivalente
          </p>
        </div>
        {href && (
          <Link className="text-xs font-bold text-link" href={href}>
            Ver vendas
          </Link>
        )}
      </div>
      {hasData ? (
        <div className="p-5">
          <div className="mb-4 flex gap-4 text-[10px] font-semibold text-slate-500">
            <span className="flex items-center gap-1.5">
              <i className="size-2.5 rounded-sm bg-chart-1" />
              Atual
            </span>
            <span className="flex items-center gap-1.5">
              <i className="size-2.5 rounded-sm bg-chart-previous" />
              Anterior
            </span>
          </div>
          <div
            className="flex h-52 items-end gap-2 overflow-x-auto"
            aria-label="Faturamento de vendas atual comparado ao período anterior"
          >
            {points.map((point, index) => (
              <div
                key={index}
                className="flex h-full min-w-12 flex-1 flex-col justify-end"
              >
                <div className="flex h-42 items-end justify-center gap-1">
                  {(
                    [
                      {
                        label: "Atual",
                        row: point.current,
                        tone: "bg-chart-1",
                      },
                      {
                        label: "Anterior",
                        row: point.previous,
                        tone: "bg-chart-previous",
                      },
                    ] as const
                  ).map((series) =>
                    series.row ? (() => {
                      const label = `${series.label}, ${series.row.date}: ${formatBRL(series.row.sales_revenue)}`;
                      const className = `group relative w-3 rounded-t ${series.tone} ${href ? "transition hover:brightness-110 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus" : ""}`;
                      const style = {
                        height: `${max ? Math.max(2, (Number(series.row.sales_revenue) * 100) / max) : 0}%`,
                      };
                      const content = (
                        <span className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 w-max -translate-x-1/2 rounded bg-chart-tooltip px-2 py-1 text-[10px] text-chart-tooltip-fg opacity-0 shadow-lg transition group-hover:opacity-100 group-focus-visible:opacity-100">
                          {series.label}: {formatBRL(series.row.sales_revenue)}
                        </span>
                      );
                      return href ? (
                        <Link key={series.label} href={dayHref(series.row.date)} aria-label={label} className={className} style={style}>
                          {content}
                        </Link>
                      ) : (
                        <span key={series.label} aria-label={label} className={className} style={style}>
                          {content}
                        </span>
                      );
                    })() : (
                      <span key={series.label} className="w-3" />
                    ),
                  )}
                </div>
                <span className="mt-2 truncate text-center text-[9px] text-slate-500">
                  {point.current || point.previous
                    ? `${(point.current || point.previous)!.date.slice(8, 10)}/${(point.current || point.previous)!.date.slice(5, 7)}`
                    : index + 1}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <EmptyState
          title="Sem comparação"
          description="Os dois períodos não possuem faturamento."
        />
      )}
    </section>
  );
}

function SellerRanking({
  rows,
  href,
}: {
  rows: ReportUserGroup[];
  href?: string;
}) {
  const rankedRows = rows.filter(
    (row): row is ReportUserGroup & { user: NonNullable<ReportUserGroup["user"]> } =>
      row.user !== null,
  );
  const showCommission = rankedRows.some(
    (row) => row.commission !== undefined,
  );
  return (
    <section className="card overflow-hidden">
      <div className="card-header">
        <div>
          <h2 className="text-sm font-bold">Ranking de atendentes</h2>
          <p className="mt-1 text-[11px] text-slate-500">
            Desempenho por seller_user nas vendas comerciais.
          </p>
        </div>
        {href && (
          <Link className="text-xs font-bold text-primary" href={href}>
            Ver relatório
          </Link>
        )}
      </div>
      {rankedRows.length ? (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Pessoa</th>
                <th>Faturamento de vendas</th>
                <th>Vendas</th>
                <th>Ticket</th>
                {showCommission && <th>Comissão</th>}
              </tr>
            </thead>
            <tbody>
              {rankedRows.map((row, index) => (
                <tr key={row.user.id}>
                  <td className="font-black text-slate-400">{index + 1}º</td>
                  <td>
                    {href ? (
                      <Link
                        className="font-bold text-primary"
                        href={`${href}&seller=${row.user.id}`}
                      >
                        {row.user.name}
                      </Link>
                    ) : (
                      <strong>{row.user.name}</strong>
                    )}
                  </td>
                  <td>{formatBRL(row.sales_revenue)}</td>
                  <td>{row.count}</td>
                  <td>{formatBRL(row.average)}</td>
                  {showCommission && (
                    <td>
                      {row.commission === undefined
                        ? "-"
                        : formatBRL(row.commission)}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title="Sem desempenho"
          description="Nenhuma venda atribuída no período."
        />
      )}
    </section>
  );
}

function OperatorTable({
  rows,
  href,
}: {
  rows: ReportUserGroup[];
  href?: string;
}) {
  const operatorRows = rows.filter(
    (row): row is ReportUserGroup & { user: NonNullable<ReportUserGroup["user"]> } =>
      row.user !== null,
  );
  return (
    <section className="card overflow-hidden">
      <div className="card-header">
        <div>
          <h2 className="text-sm font-bold">Operadores de caixa</h2>
          <p className="mt-1 text-[11px] text-slate-500">
            Vendas processadas por created_by, sem atribuição de comissão.
          </p>
        </div>
        {href && (
          <Link className="text-xs font-bold text-primary" href={href}>
            Ver relatório
          </Link>
        )}
      </div>
      {operatorRows.length ? (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Operador</th>
                <th>Faturamento de vendas</th>
                <th>Vendas</th>
                <th>Ticket</th>
              </tr>
            </thead>
            <tbody>
              {operatorRows.slice(0, 6).map((row) => (
                <tr key={row.user.id}>
                  <td>
                    {href ? (
                      <Link
                        className="font-bold text-primary"
                        href={`${href}&operator=${row.user.id}`}
                      >
                        {row.user.name}
                      </Link>
                    ) : (
                      <strong>{row.user.name}</strong>
                    )}
                  </td>
                  <td>{formatBRL(row.sales_revenue)}</td>
                  <td>{row.count}</td>
                  <td>{formatBRL(row.average)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title="Sem desempenho"
          description="Nenhuma venda processada no período."
        />
      )}
    </section>
  );
}

function DashboardPage() {
  const { currentBranch, hasAnyPermission, hasPermission } = useAuth();
  const context = useRef(currentBranch?.id || 0);
  context.current = currentBranch?.id || 0;
  const [period, setPeriod] = useState<PeriodValue>(() => businessPeriod());
  const [draftPeriod, setDraftPeriod] = useState<PeriodValue>(() =>
    businessPeriod(),
  );
  const [category, setCategory] = useState("");
  const [draftCategory, setDraftCategory] = useState("");
  const [categories, setCategories] = useState<
    Array<{ id: number; name: string }>
  >([]);
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const requestSequence = useRef(0);

  function updateDashboardUrl(
    next: PeriodValue,
    nextCategory: string,
    nextPage: number,
  ) {
    const params = new URLSearchParams({
      start_datetime: next.start,
      end_datetime: next.end,
      latest_sales_page: String(nextPage),
    });
    if (nextCategory) params.set("category", nextCategory);
    window.history.replaceState(
      window.history.state,
      "",
      `${window.location.pathname}?${params}`,
    );
  }

  async function load(
    next: PeriodValue,
    nextCategory: string,
    nextPage: number,
    token = context.current,
  ) {
    if (!currentBranch) {
      setLoading(false);
      return;
    }
    const request = ++requestSequence.current;
    setLoading(true);
    setData(null);
    setError("");
    const params = new URLSearchParams({
      start_datetime: next.start,
      end_datetime: next.end,
      latest_sales_page: String(nextPage),
    });
    if (nextCategory) params.set("category", nextCategory);
    try {
      const result = await http.get<DashboardData>(`dashboard/?${params}`);
      if (context.current === token && requestSequence.current === request) {
        setData(result);
        const canonicalPage = result.sales?.latest_sales.page ?? nextPage;
        if (canonicalPage !== nextPage)
          updateDashboardUrl(next, nextCategory, canonicalPage);
        if (result.filters?.categories)
          setCategories(result.filters.categories);
      }
    } catch (caught) {
      if (context.current !== token || requestSequence.current !== request) return;
      if (
        nextCategory &&
        caught instanceof ApiError &&
        caught.fields.category
      ) {
        setCategory("");
        setDraftCategory("");
        updateDashboardUrl(next, "", nextPage);
        void load(next, "", nextPage, token);
        return;
      }
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

  function apply(
    next: PeriodValue,
    nextCategory: string,
    nextPage = 1,
  ) {
    setPeriod(next);
    setCategory(nextCategory);
    updateDashboardUrl(next, nextCategory, nextPage);
    void load(next, nextCategory, nextPage, context.current);
  }

  useEffect(() => {
    requestSequence.current += 1;
    setData(null);
    setError("");
    setCategories([]);
    if (!currentBranch) {
      setLoading(false);
      return;
    }
    const params = new URLSearchParams(window.location.search);
    const defaultPeriod = businessPeriod();
    const requestedPeriod = {
      start: params.get("start_datetime") || "",
      end: params.get("end_datetime") || "",
    };
    const dateTimePattern = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$/;
    const next =
      dateTimePattern.test(requestedPeriod.start) &&
      dateTimePattern.test(requestedPeriod.end) &&
      requestedPeriod.start <= requestedPeriod.end
        ? requestedPeriod
        : defaultPeriod;
    const requestedCategory = params.get("category") || "";
    const nextCategory = /^\d+$/.test(requestedCategory)
      ? requestedCategory
      : "";
    const requestedPage = Number(params.get("latest_sales_page"));
    const nextPage = Number.isInteger(requestedPage) && requestedPage > 0
      ? requestedPage
      : 1;
    setDraftPeriod(next);
    setDraftCategory(nextCategory);
    apply(next, nextCategory, nextPage);
  }, [currentBranch?.id]);

  const query = new URLSearchParams({
    start_datetime: period.start,
    end_datetime: period.end,
    ...(category ? { category } : {}),
    ...(currentBranch ? { branch: String(currentBranch.id) } : {}),
  }).toString();
  const report = (slug: string, extra = "") =>
    `/relatorios/${slug}?${query}${extra}`;
  const canViewSalesReport = hasPermission(permissions.viewSalesReport);
  const canViewReceiptsReport = hasPermission(permissions.viewReceiptsReport);
  const canViewProductsReport = hasPermission(permissions.viewProductsReport);
  const canViewTeamReport = hasPermission(permissions.viewTeamReport);
  const canViewCancellationsReport = hasPermission(
    permissions.viewCancellationsReport,
  );
  const canViewDiscountsReport = hasPermission(
    permissions.viewDiscountsReport,
  );
  const canViewConsumptionsReport = hasPermission(
    permissions.viewConsumptionsReport,
  );
  const canViewCommissionReport = hasPermission(permissions.viewCommission);
  const canViewResultReport = hasPermission(
    permissions.viewOperationalResult,
  );
  const canViewInventory = hasPermission(permissions.viewInventory);
  const canViewCash = hasPermission(permissions.viewCashRegister);
  const canViewSaleDetail = hasAnyPermission([
    permissions.viewSale,
    permissions.cancelSale,
  ]);
  const sales = data?.sales;
  const weekdays = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];
  const heatMax = Math.max(
    ...(sales?.heatmap || []).map((row) => Number(row.sales_revenue)),
    0,
  );
  const resultDetails: Array<[string, string | undefined]> = data?.operational_result
    ? [
        ["CMV de vendas", data.operational_result.historical_sales_cogs],
        [
          "Custo de consumação",
          data.operational_result.historical_consumption_cogs,
        ],
        ["Comissão", data.operational_result.commission],
        ["Despesas operacionais", data.operational_result.operating_expenses],
        ["Custo fixo rateado", data.operational_result.fixed_cost],
      ]
    : [];

  return (
    <>
      <PageHeader
        title="Dashboard Executivo"
        description={`Visão gerencial organizada de ${currentBranch?.name || "sua filial"}.`}
      />
      <div className="space-y-5 p-4 sm:p-6 lg:p-8">
        <section className="card p-4">
          <div className="mb-3 flex items-center gap-2 text-xs font-bold">
            <CalendarRange className="size-4 text-primary" />
            Filtros globais
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <Field label="Filial">
              <Select value={currentBranch?.id || ""} disabled>
                <option value={currentBranch?.id || ""}>
                  {currentBranch?.name || "Selecione uma filial"}
                </option>
              </Select>
            </Field>
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
            <Field label="Categoria">
              <Select
                value={draftCategory}
                onChange={(event) => setDraftCategory(event.target.value)}
              >
                <option value="">Todas</option>
                {categories.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {[
              ["Hoje", businessPeriod()],
              ["Ontem", businessPeriod(0, -1)],
              ["Últimos 7 dias", businessPeriod(6)],
              ["Últimos 15 dias", businessPeriod(14)],
              ["Últimos 30 dias", businessPeriod(29)],
            ].map(([label, value]) => (
              <button
                type="button"
                key={String(label)}
                className="rounded-full bg-surface-muted px-3 py-1.5 text-[11px] font-bold text-muted hover:bg-primary/10 hover:text-link focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/20"
                onClick={() => {
                  const next = value as PeriodValue;
                  setDraftPeriod(next);
                  setDraftCategory(category);
                  apply(next, category);
                }}
              >
                {String(label)}
              </button>
            ))}
            {data?.current_cash?.[0] && (
              <button
                type="button"
                className="rounded-full bg-success/10 px-3 py-1.5 text-[11px] font-bold text-success-strong focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/20"
                onClick={() => {
                  const next = {
                    start: toBusinessDateTimeLocal(
                      data.current_cash![0].opened_at,
                    ),
                    end: toBusinessDateTimeLocal(new Date()),
                  };
                  setDraftPeriod(next);
                  setDraftCategory(category);
                  apply(next, category);
                }}
              >
                Sessão atual
              </button>
            )}
            <button
              type="button"
              className="rounded-full border border-subtle px-3 py-1.5 text-[11px] font-bold text-muted focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/20"
            >
              Personalizado
            </button>
            <Button
              className="ml-auto"
              onClick={() => apply(draftPeriod, draftCategory)}
            >
              Aplicar
            </Button>
          </div>
        </section>
        {error && <Alert message={error} />}
        {loading ? (
          <section className="card">
            <TableLoading />
          </section>
        ) : data ? (
          <>
            {sales && (
              <FinancialBridge
                sales={sales}
                href={canViewReceiptsReport ? report("recebimentos") : undefined}
              />
            )}
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {sales && (
                <>
                  <Kpi
                    label="Ticket médio"
                    value={formatBRL(sales.average)}
                    note={`${sales.count} vendas · somente faturamento de vendas`}
                    icon={ReceiptText}
                    href={canViewSalesReport ? report("vendas") : undefined}
                  />
                  <Kpi
                    label="Cancelamentos / Estornos"
                    value={formatBRL(sales.cancellations.value)}
                    note={`${sales.cancellations.count} operações`}
                    icon={TrendingDown}
                    tone="danger"
                    href={canViewCancellationsReport ? report("cancelamentos") : undefined}
                  />
                  <Kpi
                    label="Descontos manuais"
                    value={formatBRL(sales.manual_discount)}
                    note={`${sales.manual_discount_count} vendas · item + conta`}
                    icon={ReceiptText}
                    tone="warning"
                    href={canViewDiscountsReport ? report("descontos") : undefined}
                  />
                </>
              )}
              {data.consumptions && (
                <Kpi
                  label="Pedidos de consumação"
                  value={String(data.consumptions.count)}
                  note={`Referência ${formatBRL(data.consumptions.reference)} · benefício ${formatBRL(data.consumptions.subsidy)}`}
                  icon={ShoppingBasket}
                  href={canViewConsumptionsReport ? report("consumacoes") : undefined}
                />
              )}
              {sales?.commission !== undefined && (
                <Kpi
                  label="Comissão"
                  value={formatBRL(sales.commission)}
                  note="Custo separado do faturamento"
                  icon={Users}
                  href={canViewCommissionReport ? report("comissoes") : undefined}
                />
              )}
            </div>
            <div className="grid gap-5 xl:grid-cols-2">
              {data.inventory && (
                <section className="card p-5">
                  <div className="mb-4 flex justify-between">
                    <h2 className="text-sm font-bold">Estoque físico</h2>
                    {canViewInventory && (
                      <Link
                        className="text-xs font-bold text-primary"
                        href="/estoque"
                      >
                        Abrir estoque
                      </Link>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    {data.inventory.inventory_value !== undefined && (
                      <Kpi
                        label="Valor em estoque"
                        value={formatBRL(data.inventory.inventory_value)}
                        note="Saldos positivos no recorte"
                        icon={Boxes}
                        href={canViewInventory ? "/estoque" : undefined}
                      />
                    )}
                    <Kpi
                      label="Negativos"
                      value={String(data.inventory.negative_count)}
                      note="Produtos físicos"
                      icon={Boxes}
                      tone="danger"
                      href={canViewInventory ? "/estoque?state=negative" : undefined}
                    />
                    <Kpi
                      label="Abaixo do mínimo"
                      value={String(data.inventory.below_minimum_count)}
                      note="Exigem atenção"
                      icon={Boxes}
                      tone="warning"
                      href={canViewInventory ? "/estoque?state=below_minimum" : undefined}
                    />
                    <Kpi
                      label="Produtos físicos"
                      value={String(data.inventory.physical_products)}
                      note="Somente estoque direto"
                      icon={Boxes}
                      href={canViewInventory ? "/estoque" : undefined}
                    />
                  </div>
                </section>
              )}
              <section className="card p-5">
                <div className="mb-4 flex justify-between">
                  <h2 className="text-sm font-bold">Caixa e resultado</h2>
                  {canViewResultReport &&
                    (data.operational_result?.result ??
                      data.operational_result?.estimated_result) !== undefined && (
                    <Link
                      className="text-xs font-bold text-primary"
                      href={report("resultado")}
                    >
                      Ver resultado
                    </Link>
                  )}
                </div>
                {data.operational_result &&
                  (data.operational_result.result ??
                    data.operational_result.estimated_result) !== undefined && (
                    <div className="mb-4 rounded-lg border border-dashed border-primary/30 p-4">
                      <div className="space-y-2 text-xs">
                        <p className="flex items-center justify-between gap-3">
                          <span>Total recebido</span>
                          <strong>
                            {formatBRL(data.operational_result.total_received)}
                          </strong>
                        </p>
                        <p className="flex items-center justify-between gap-3 text-slate-500">
                          <span>(-) Custos e despesas</span>
                          <strong>
                            {formatBRL(
                              data.operational_result.costs_and_expenses,
                            )}
                          </strong>
                        </p>
                        <p className="flex items-center justify-between gap-3 border-t border-subtle pt-3">
                          <span className="font-bold">Resultado estimado</span>
                          <strong className="text-xl text-dark">
                            {formatBRL(
                              data.operational_result.result ??
                                data.operational_result.estimated_result,
                            )}
                          </strong>
                        </p>
                      </div>
                      {data.operational_result.margin != null && (
                        <small className="mt-2 block text-slate-500">
                          Margem sobre Total recebido: {data.operational_result.margin}%
                        </small>
                      )}
                      {resultDetails.some(([, value]) => value !== undefined) && (
                        <div className="mt-3 grid gap-1 border-t border-subtle pt-3 text-[11px] text-slate-500 sm:grid-cols-2">
                          {resultDetails.map(([label, value]) =>
                            value !== undefined ? (
                              <span key={label} className="flex justify-between gap-2">
                                <span>{label}</span>
                                <strong>{formatBRL(value)}</strong>
                              </span>
                            ) : null,
                          )}
                        </div>
                      )}
                    </div>
                  )}
                {data.current_cash?.length ? (
                  data.current_cash.map((item) => {
                    const content = (
                      <>
                        <span>{item.register.name}</span>
                        <strong>{formatBRL(item.expected)} em dinheiro</strong>
                      </>
                    );
                    return canViewCash ? (
                      <Link
                        key={item.id}
                        href={`/caixas/sessoes/${item.id}`}
                        className="flex justify-between border-t border-slate-100 py-3 text-sm"
                      >
                        {content}
                      </Link>
                    ) : (
                      <div
                        key={item.id}
                        className="flex justify-between border-t border-slate-100 py-3 text-sm"
                      >
                        {content}
                      </div>
                    );
                  })
                ) : (
                  <p className="text-xs text-slate-500">Nenhum caixa aberto.</p>
                )}
              </section>
            </div>
            {sales && (
              <>
                <div className="grid gap-5 xl:grid-cols-2">
                  <HorizontalBars
                    title="Produtos mais vendidos"
                    href={canViewProductsReport ? report("produtos") : undefined}
                    rows={sales.top_products.slice(0, 8).map((row) => ({
                      label: row.product_name,
                      value: Number(row.sales_revenue),
                      display: formatBRL(row.sales_revenue),
                      note: formatQuantity(row.quantity),
                      query: row.product_id ? `&product=${row.product_id}` : "",
                    }))}
                  />
                  <PaymentChart
                    rows={sales.payment_distribution}
                    href={canViewReceiptsReport ? report("recebimentos") : undefined}
                    scope={sales.payment_distribution_scope}
                    totalReceived={sales.total_received}
                    reconciliationDelta={sales.reconciliation_delta}
                  />
                  <WeeklyComparison
                    comparison={sales.weekly_comparison}
                    href={canViewSalesReport ? report("vendas") : undefined}
                  />
                </div>
                <SellerRanking
                  rows={sales.top_sellers}
                  href={canViewTeamReport ? report("atendentes") : undefined}
                />
                <OperatorTable
                  rows={sales.top_operators}
                  href={canViewTeamReport ? report("operadores") : undefined}
                />
                <section className="card overflow-hidden">
                  <div className="card-header">
                    <div>
                      <h2 className="text-sm font-bold">
                        Mapa de calor · dia × hora
                      </h2>
                      <p className="mt-1 text-[11px] text-slate-500">
                        Faturamento de vendas, quantidade e ticket no tooltip.
                      </p>
                    </div>
                  </div>
                  {sales.heatmap.length ? (
                    <div className="overflow-x-auto p-5">
                      <div className="grid min-w-240 grid-cols-[42px_repeat(24,minmax(28px,1fr))] gap-1">
                        <span />
                        {Array.from({ length: 24 }, (_, hour) => (
                          <span
                            key={hour}
                            className="text-center text-[9px] text-slate-500"
                          >
                            {hour}
                          </span>
                        ))}
                        {weekdays.map((day, weekday) => (
                          <div key={day} className="contents">
                            <span className="self-center text-[10px] font-bold">
                              {day}
                            </span>
                            {Array.from({ length: 24 }, (_, hour) => {
                              const cell = sales.heatmap.find(
                                (row) =>
                                  row.weekday === weekday && row.hour === hour,
                              );
                              const strength =
                                cell && heatMax
                                  ? Math.max(
                                      0.08,
                                      Number(cell.sales_revenue) / heatMax,
                                    )
                                  : 0.03;
                              const title = cell
                                ? `${formatBRL(cell.sales_revenue)} · ${cell.count} vendas · ticket ${formatBRL(cell.average)}`
                                : "Sem vendas";
                              const ariaLabel = cell
                                ? `${day}, ${hour} horas: ${formatBRL(cell.sales_revenue)}, ${cell.count} vendas`
                                : `${day}, ${hour} horas: sem vendas`;
                              const className = `group relative aspect-square rounded-sm border border-chart-1/20 ${canViewSalesReport ? "focus-visible:z-10 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus" : ""}`;
                              const style = {
                                backgroundColor: `color-mix(in srgb, var(--chart-1) ${Math.round(strength * 100)}%, transparent)`,
                              };
                              const content = (
                                <span className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 w-max -translate-x-1/2 rounded bg-chart-tooltip px-2 py-1 text-[10px] text-chart-tooltip-fg opacity-0 shadow-lg transition group-hover:opacity-100 group-focus-visible:opacity-100">
                                  {title}
                                </span>
                              );
                              return canViewSalesReport ? (
                                <Link
                                  key={hour}
                                  href={report(
                                    "vendas",
                                    `&hour=${hour}&weekday=${weekday}`,
                                  )}
                                  title={title}
                                  aria-label={ariaLabel}
                                  className={className}
                                  style={style}
                                >
                                  {content}
                                </Link>
                              ) : (
                                <div
                                  key={hour}
                                  title={title}
                                  aria-label={ariaLabel}
                                  className={className}
                                  style={style}
                                >
                                  {content}
                                </div>
                              );
                            })}
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <EmptyState
                      title="Sem mapa de calor"
                      description="Nenhuma venda no período selecionado."
                    />
                  )}
                </section>
                <section className="card overflow-hidden">
                  <div className="card-header">
                    <h2 className="text-sm font-bold">
                      Últimas vendas do recorte
                    </h2>
                    <div className="flex items-center gap-3">
                      <span className="text-[11px] text-slate-500">
                        {sales.latest_sales.count} vendas
                      </span>
                      {canViewSalesReport && (
                        <Link
                          className="text-xs font-bold text-primary"
                          href={report("vendas")}
                        >
                          Ver todas
                        </Link>
                      )}
                    </div>
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
                          {sales.latest_sales.results.map((sale) => (
                            <tr key={sale.id}>
                              <td>
                                {canViewSaleDetail ? (
                                  <Link
                                    className="font-bold text-primary"
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
                  {sales.latest_sales.count > 0 && (
                    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-subtle px-4 py-3 sm:px-5">
                      <span className="text-[11px] text-slate-500">
                        Página {sales.latest_sales.page} de {Math.max(1, sales.latest_sales.total_pages)} · {sales.latest_sales.page_size} por página
                      </span>
                      <div className="flex gap-2">
                        <button
                          type="button"
                          className="btn btn-secondary h-8 px-3 text-xs"
                          disabled={sales.latest_sales.previous_page === null}
                          onClick={() => {
                            const page = sales.latest_sales.previous_page;
                            if (page !== null) apply(period, category, page);
                          }}
                        >
                          Anterior
                        </button>
                        <button
                          type="button"
                          className="btn btn-secondary h-8 px-3 text-xs"
                          disabled={sales.latest_sales.next_page === null}
                          onClick={() => {
                            const page = sales.latest_sales.next_page;
                            if (page !== null) apply(period, category, page);
                          }}
                        >
                          Próxima
                        </button>
                      </div>
                    </div>
                  )}
                </section>
              </>
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
