"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Filter } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { PeriodFilter, type PeriodValue } from "@/components/period-filter";
import { ReportExportAction } from "@/components/report-export-action";
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
import { decimalIsZero, formatDate, formatDecimalBRL as formatBRL, formatPercent, formatQuantity } from "@/lib/format";
import { contentUnitLabel, divideInventoryDecimals, inventoryDecimalSign, physicalQuantityDisplay, subtractInventoryDecimals, sumInventoryDecimals } from "@/lib/inventory";
import { ApiError, http } from "@/lib/http";
import { businessMonthToDate } from "@/lib/period";
import { permissions } from "@/lib/permissions";
import { centsToDecimal } from "@/lib/sales";
import { signedMoneyToCents } from "@/lib/cash";
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
    title: "Produtos e desempenho",
    description: "Desempenho comercial por produto e categoria.",
    endpoint: "sales",
    permission: permissions.viewProductsReport,
  },
  receipts: {
    title: "Recebimentos",
    description: "Distribuição do total recebido por forma de pagamento.",
    endpoint: "sales",
    permission: permissions.viewReceiptsReport,
  },
  operators: {
    title: "Operadores",
    description: "Faturamento de vendas processado por operador de caixa.",
    endpoint: "sales",
    permission: permissions.viewTeamReport,
  },
  sellers: {
    title: "Atendentes",
    description: "Faturamento de vendas e ticket comercial por atendente.",
    endpoint: "sales",
    permission: permissions.viewTeamReport,
  },
  commissions: {
    title: "Comissões",
    description: "Valores históricos de comissão atribuídos aos atendentes.",
    endpoint: "sales",
    permission: permissions.viewCommission,
  },
  discounts: {
    title: "Descontos",
    description: "Descontos manuais por item, na conta e promoções.",
    endpoint: "sales",
    permission: permissions.viewDiscountsReport,
  },
  consumptions: {
    title: "Consumações e cortesias",
    description: "Referência, valor cobrado e benefício operacional.",
    endpoint: "consumptions",
    permission: permissions.viewConsumptionsReport,
  },
  cash: {
    title: "Caixa",
    description: "Sessões por interseção temporal e reconciliação completa.",
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
    title: "Cancelamentos e estornos",
    description: "Operações canceladas no período do cancelamento.",
    endpoint: "cancellations",
    permission: permissions.viewCancellationsReport,
  },
  prices: {
    title: "Preços por filial",
    description:
      "Comparação entre o preço padrão e os preços específicos por filial.",
    endpoint: "prices",
    permission: permissions.viewPricesReport,
  },
  result: {
    title: "Resultado estimado",
    description: "Total recebido, custos e despesas, resultado e margem.",
    endpoint: "operational-result",
    permission: permissions.viewOperationalResult,
  },
};

function initialPeriod(): PeriodValue {
  return businessMonthToDate();
}

function rows(value: unknown) {
  return Array.isArray(value) ? (value as Array<Record<string, unknown>>) : [];
}

function numberValue(value: unknown) {
  return Number(value || 0);
}

function sumReportMoney(values: unknown[]) {
  const total = values.reduce<bigint | null>((sum, value) => {
    const cents = signedMoneyToCents(value);
    return sum === null || cents === null ? null : sum + cents;
  }, BigInt(0));
  return total === null ? "0.00" : centsToDecimal(total);
}

function averageReportMoney(rows: Array<Record<string, unknown>>, amountKey: string) {
  const count = rows.reduce((total, row) => total + numberValue(row.count), 0);
  if (!count) return "0.00";
  const total = signedMoneyToCents(sumReportMoney(rows.map((row) => row[amountKey])));
  return total === null ? "0.00" : centsToDecimal(total / BigInt(count));
}

function firstValue(summary: Record<string, unknown>, ...keys: string[]) {
  const key = keys.find((candidate) => summary[candidate] !== undefined);
  return key ? summary[key] : "0";
}

function reportValue(record: Record<string, unknown>, ...keys: string[]) {
  const key = keys.find((candidate) => record[candidate] !== undefined && record[candidate] !== null);
  return key ? record[key] as string | number : undefined;
}

function reportPhysicalQuantity(row: Record<string, unknown>, quantityKey: string, prefix?: string) {
  const product = (row.product || {}) as Record<string, unknown>;
  const fraction = (product.fraction_config || {}) as Record<string, unknown>;
  const contentKeys = prefix ? [`${prefix}_content`, `${prefix}_content_quantity`] : ["content_quantity"];
  const completeKeys = prefix ? [`${prefix}_complete_packages`] : ["complete_packages", "movement_complete_packages"];
  const residualKeys = prefix ? [`${prefix}_residual_content`] : ["residual_content", "movement_residual_content"];
  return physicalQuantityDisplay({
    quantity: reportValue(row, quantityKey),
    unit: String(product.unit || row.unit || ""),
    content: reportValue(row, ...contentKeys),
    packageContent: reportValue(row, "package_content") ?? reportValue(product, "package_content") ?? reportValue(fraction, "package_content"),
    contentUnit: String(reportValue(row, "content_unit") ?? reportValue(product, "content_unit") ?? reportValue(fraction, "content_unit") ?? ""),
    completePackages: reportValue(row, ...completeKeys),
    residualContent: reportValue(row, ...residualKeys),
  });
}

function ConsumptionQuantity({ row, quantityKey, prefix }: { row: Record<string, unknown>; quantityKey: string; prefix?: string }) {
  const product = (row.product || {}) as Record<string, unknown>;
  const content = reportValue(row, ...(prefix ? [`${prefix}_content`, `${prefix}_content_quantity`] : ["content_quantity"]));
  const packageContent = reportValue(row, "package_content");
  const combined = reportValue(row, quantityKey) ?? 0;
  const unit = String(product.unit || "equiv.").toUpperCase();
  if (content == null || packageContent == null || inventoryDecimalSign(packageContent) !== 1) {
    return <span><strong>{formatQuantity(String(combined))} {unit}</strong><small className="block text-muted">Equivalente legado</small></span>;
  }
  const packageEquivalent = divideInventoryDecimals(content, packageContent);
  const legacy = packageEquivalent === null ? null : subtractInventoryDecimals(combined, packageEquivalent);
  return <span>
    <strong className="block">{reportPhysicalQuantity(row, quantityKey, prefix)}</strong>
    <small className="block text-muted">Equivalente legado: {formatQuantity(legacy ?? combined)} {unit}</small>
    <small className="block text-muted">Total combinado equivalente: {formatQuantity(String(combined))} {unit}</small>
  </span>;
}

function hasDelta(value: unknown) {
  const cents = signedMoneyToCents(value);
  return cents !== null ? cents !== BigInt(0) : !decimalIsZero(value);
}

function ReconciliationWarning({
  label,
  value,
}: {
  label: string;
  value: unknown;
}) {
  if (!hasDelta(value)) return null;
  return (
    <div
      role="alert"
      className="rounded-md border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-warning-strong"
    >
      <strong>{label}:</strong> {formatBRL(String(value))}. Os componentes
      retornados pelo backend não reconciliam neste recorte.
    </div>
  );
}

function Kpi({
  label,
  value,
  format = "money",
}: {
  label: string;
  value: unknown;
  format?: "money" | "number" | "quantity" | "percent";
}) {
  const display =
    format === "money"
      ? formatBRL(String(value || "0"))
      : format === "quantity"
        ? formatQuantity(String(value || "0"))
        : format === "percent"
          ? formatPercent(value)
          : String(value ?? "0");
  return (
    <div className="rounded-lg border border-dashed border-slate-200 p-4">
      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
        {label}
      </span>
      <strong className="mt-2 block text-xl text-dark">{display}</strong>
    </div>
  );
}

function reportKpis(kind: ReportKind, summary: Record<string, unknown>) {
  const productRows = rows(summary.product_ranking);
  const operatorRows = rows(summary.operator_groups);
  const sellerRows = rows(summary.seller_groups);
  const stockRows = rows(summary.products);
  const filteredMethod = summary.filtered_payment_method as
    Record<string, unknown> | undefined;
  const definitions: Partial<
    Record<
      ReportKind,
      Array<[string, unknown, "money" | "number" | "quantity" | "percent"]>
    >
  > = {
    overview: [
      ["Faturamento de vendas", summary.sales_revenue, "money"],
      ["Taxa de serviço", summary.service_fee, "money"],
      ["Total recebido", summary.total_received, "money"],
      ["Total dos pagamentos", summary.payment_total, "money"],
      ["Vendas", summary.count, "number"],
      ["Ticket médio comercial", summary.ticket_average, "money"],
    ],
    sales: [
      ["Faturamento de vendas", summary.sales_revenue, "money"],
      ["Taxa de serviço", summary.service_fee, "money"],
      ["Total recebido", summary.total_received, "money"],
      ["Total dos pagamentos", summary.payment_total, "money"],
      ["Vendas", summary.count, "number"],
      ["Ticket médio comercial", summary.ticket_average, "money"],
    ],
    products: [
      [
        "Faturamento de vendas",
        sumReportMoney(productRows.map((row) => row.revenue)),
        "money",
      ],
      [
        "Unidades vendidas",
        sumInventoryDecimals(productRows.map((row) => row.quantity)) || "0",
        "quantity",
      ],
      ["Produtos vendidos", productRows.length, "number"],
      ["Categorias", rows(summary.category_ranking).length, "number"],
    ],
    receipts: [
      ...(filteredMethod
        ? [
            [
              `Subtotal via ${String(filteredMethod.name || filteredMethod.code)}`,
              filteredMethod.subtotal,
              "money",
            ] as [string, unknown, "money"],
          ]
        : []),
      ["Faturamento de vendas", summary.sales_revenue, "money"],
      ["Consumação cobrada", summary.consumption_charged, "money"],
      ["Faturamento efetivo", summary.effective_revenue, "money"],
      ["Taxa de serviço", summary.service_fee, "money"],
      ["Total recebido", summary.total_received, "money"],
      ["Total dos pagamentos", summary.payment_total, "money"],
      ["Reversões / estornos", summary.reversals, "money"],
    ],
    operators: [
      [
        "Faturamento de vendas",
        sumReportMoney(operatorRows.map((row) => row.sales_revenue)),
        "money",
      ],
      [
        "Taxa de serviço",
        sumReportMoney(operatorRows.map((row) => row.service_fee)),
        "money",
      ],
      [
        "Total recebido",
        sumReportMoney(operatorRows.map((row) => row.total_received)),
        "money",
      ],
      [
        "Vendas",
        operatorRows.reduce((total, row) => total + numberValue(row.count), 0),
        "number",
      ],
      [
        "Ticket médio comercial",
        averageReportMoney(operatorRows, "sales_revenue"),
        "money",
      ],
    ],
    sellers: [
      [
        "Faturamento de vendas",
        sumReportMoney(sellerRows.map((row) => row.sales_revenue)),
        "money",
      ],
      [
        "Taxa de serviço",
        sumReportMoney(sellerRows.map((row) => row.service_fee)),
        "money",
      ],
      [
        "Total recebido",
        sumReportMoney(sellerRows.map((row) => row.total_received)),
        "money",
      ],
      [
        "Vendas",
        sellerRows.reduce((total, row) => total + numberValue(row.count), 0),
        "number",
      ],
      [
        "Ticket médio comercial",
        averageReportMoney(sellerRows, "sales_revenue"),
        "money",
      ],
    ],
    commissions: [
      ["Faturamento de vendas", summary.sales_revenue, "money"],
      ["Taxa de serviço", summary.service_fee, "money"],
      ["Total recebido", summary.total_received, "money"],
      ...(summary.commission !== undefined
        ? [
            ["Comissão gerada", summary.commission, "money"] as [
              string,
              unknown,
              "money",
            ],
          ]
        : []),
      ["Vendas com comissão", summary.commission_sale_count, "number"],
      ["Atendentes", summary.commission_attendant_count, "number"],
    ],
    discounts: [
      ["Desconto na conta", summary.account_discount, "money"],
      ["Desconto por item", summary.item_discount, "money"],
      ["Promoções", summary.promotion_discount, "money"],
      ["Vendas afetadas", summary.count, "number"],
    ],
    consumptions: [
      ["Valor de referência", summary.reference, "money"],
      ["Valor cobrado", summary.charged, "money"],
      ["Benefício concedido", summary.benefit, "money"],
      ["Operações", summary.count, "number"],
      ...(summary.historical_cost !== undefined
        ? [
            ["Custo histórico", summary.historical_cost, "money"] as [
              string,
              unknown,
              "money",
            ],
          ]
        : []),
    ],
    cash: [
      ["Faturamento de vendas", summary.sales_revenue, "money"],
      ["Consumação cobrada", summary.consumption_charged, "money"],
      ["Faturamento efetivo", summary.effective_revenue, "money"],
      ["Taxa de serviço", summary.service_fee, "money"],
      ["Total recebido", summary.total_received, "money"],
      ["Total dos pagamentos", summary.payment_total, "money"],
      ["Reversões no período", summary.reversals, "money"],
    ],
    withdrawals: [
      ["Total de sangrias", summary.amount, "money"],
      ["Movimentos", summary.count, "number"],
    ],
    "stock-consumption": [
      ["Consumo bruto · total equivalente", summary.gross_quantity, "quantity"],
      ["Devoluções · total equivalente", summary.returned_quantity, "quantity"],
      ["Consumo líquido · total equivalente", summary.net_quantity, "quantity"],
      ...(summary.estimated_cost !== undefined
        ? [
            [
              "Custo estimado pelo custo atual",
              summary.estimated_cost,
              "money",
            ] as [string, unknown, "money"],
          ]
        : [
            ["Produtos físicos", stockRows.length, "number"] as [
              string,
              unknown,
              "number",
            ],
          ]),
    ],
    cancellations: [
      [
        "Faturamento de vendas revertido",
        summary.reversed_sales_revenue,
        "money",
      ],
      ["Taxa de serviço revertida", summary.reversed_service_fee, "money"],
      ["Total revertido", summary.reversed_total_received, "money"],
      ["Cancelamentos", summary.count, "number"],
    ],
    result: [
      ["Total recebido", summary.total_received, "money"],
      ["Custos e despesas", summary.costs_and_expenses, "money"],
      ["Resultado estimado", summary.result, "money"],
      ...(summary.margin !== null && summary.margin !== undefined
        ? [
            ["Margem sobre o total recebido", summary.margin, "percent"] as [
              string,
              unknown,
              "percent",
            ],
          ]
        : []),
      ["Total dos pagamentos", summary.payment_total, "money"],
    ],
  };
  return definitions[kind] || [];
}

function StatusBadge({ value }: { value: unknown }) {
  const status = String(value || "");
  const tone =
    status === "finalized" || status === "open"
      ? "bg-success/10 text-emerald-700"
      : status === "cancelled"
        ? "bg-danger/10 text-red-700"
        : "bg-slate-100 text-slate-700";
  return (
    <span
      className={`inline-flex rounded-full px-2 py-1 text-[10px] font-bold ${tone}`}
    >
      {domainLabel(status)}
    </span>
  );
}

function SalesTable({
  kind,
  data,
  canViewSales,
  canViewConsumptions,
}: {
  kind: ReportKind;
  data: ReportResponse<Record<string, unknown>>;
  canViewSales: boolean;
  canViewConsumptions: boolean;
}) {
  if (!data.results.length)
    return (
      <EmptyState
        title="Sem registros"
        description="Nenhuma operação encontrada no período."
      />
    );
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Operação</th>
            <th>{kind === "cancellations" ? "Cancelada em" : "Data"}</th>
            <th>Responsáveis</th>
            <th>Status</th>
            {kind === "discounts" ? (
              <>
                <th>Por item</th>
                <th>Na conta</th>
                <th>Promoções</th>
                <th>Faturamento de vendas</th>
                <th>Taxa</th>
                <th>Total recebido</th>
              </>
            ) : kind === "cancellations" ? (
              <>
                <th>Faturamento de vendas revertido</th>
                <th>Taxa revertida</th>
                <th>Total revertido</th>
              </>
            ) : (
              <th>
                {kind === "consumptions" ? "Valor cobrado" : "Total cobrado"}
              </th>
            )}
            <th />
          </tr>
        </thead>
        <tbody>
          {data.results.map((row) => {
            const seller = row.seller as { name?: string } | null;
            const operator = row.operator as { name?: string } | null;
            const beneficiary = row.beneficiary as { name?: string } | null;
            const isConsumption =
              row.operation_type === "consumption" || kind === "consumptions";
            const canOpen = isConsumption ? canViewConsumptions : canViewSales;
            return (
              <tr key={String(row.operation_key)}>
                <td>
                  <strong>{String(row.sale_number)}</strong>
                </td>
                <td>
                  {formatDate(
                    String(
                      kind === "cancellations"
                        ? row.cancelled_at
                        : row.created_at,
                    ),
                  )}
                </td>
                <td>
                  {kind === "consumptions" ? (
                    <span>Beneficiário: {beneficiary?.name || "-"}</span>
                  ) : (
                    <>
                      <span className="block">
                        Atendente: {seller?.name || "-"}
                      </span>
                      <small className="text-slate-500">
                        Operador: {operator?.name || "-"}
                      </small>
                    </>
                  )}
                </td>
                <td>
                  <StatusBadge value={row.status} />
                </td>
                {kind === "discounts" ? (
                  <>
                    <td>{formatBRL(String(row.item_discount_total || "0"))}</td>
                    <td>{formatBRL(String(row.discount || "0"))}</td>
                    <td>
                      {formatBRL(String(row.promotion_discount_total || "0"))}
                    </td>
                    <td>{formatBRL(String(row.sales_revenue || "0"))}</td>
                    <td>{formatBRL(String(row.service_fee_amount || "0"))}</td>
                    <td>
                      {formatBRL(String(row.total_received || "0"))}
                    </td>
                  </>
                ) : kind === "cancellations" ? (
                  <>
                    <td>{formatBRL(String(row.sales_revenue || "0"))}</td>
                    <td>{formatBRL(String(row.service_fee_amount || "0"))}</td>
                    <td>
                      {formatBRL(String(row.total_received || "0"))}
                    </td>
                  </>
                ) : (
                  <td>{formatBRL(String(row.total || "0"))}</td>
                )}
                <td className="text-right">
                  {canOpen ? (
                    <Link
                      className="text-xs font-bold text-primary"
                      href={`${isConsumption ? "/consumacoes" : "/vendas"}/${row.id}`}
                    >
                      Detalhes
                    </Link>
                  ) : (
                    <span className="text-[11px] text-slate-400">
                      Sem acesso operacional
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RankingTable({
  kind,
  summary,
}: {
  kind: ReportKind;
  summary: Record<string, unknown>;
}) {
  const key =
    kind === "products"
      ? "product_ranking"
      : kind === "receipts"
        ? "payment_totals"
        : kind === "operators"
          ? "operator_groups"
          : "seller_groups";
  const list = rows(summary[key]);
  if (!list.length)
    return (
      <EmptyState
        title="Sem dados"
        description="Nenhum resultado no período selecionado."
      />
    );
  const isTeam = ["operators", "sellers", "commissions"].includes(kind);
  const showCommission =
    isTeam && list.some((row) => row.commission !== undefined);
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>
              {kind === "products"
                ? "Produto"
                : kind === "receipts"
                  ? "Forma de pagamento"
                  : "Pessoa"}
            </th>
            {kind === "products" && <th>Unidades</th>}
            {isTeam && <th>Vendas</th>}
            <th>
              {kind === "receipts"
                ? "Pagamentos de vendas"
                : "Faturamento de vendas"}
            </th>
            {kind === "receipts" && (
              <>
                <th>Pagamentos de consumações</th>
                <th>Pagamentos antes de reversões</th>
                <th>Reversões</th>
                <th>Total dos pagamentos</th>
              </>
            )}
            {isTeam && (
              <>
                <th>Taxa de serviço</th>
                <th>Total recebido</th>
                <th>Ticket médio comercial</th>
                <th>Cancelamentos</th>
              </>
            )}
            {showCommission && <th>Comissão histórica</th>}
          </tr>
        </thead>
        <tbody>
          {list.map((row) => {
            const user = row.user as { id?: number; name?: string } | undefined;
            const label = row.product_name || row.name || user?.name || "-";
            const amount = row.revenue || row.sales_revenue || "0";
            return (
              <tr
                key={String(row.product_id ? `product:${row.product_id}` : row.code ? `payment:${row.code}` : `user:${user?.id}`)}
              >
                <td>
                  <strong>{String(label)}</strong>
                  {kind === "products" && (
                    <small className="block text-slate-500">
                      {String(row.internal_code || "")}
                    </small>
                  )}
                </td>
                {kind === "products" && (
                  <td>{formatQuantity(String(row.quantity || "0"))}</td>
                )}
                {isTeam && <td>{String(row.count || 0)}</td>}
                <td>
                  {formatBRL(
                    String(
                      kind === "receipts" ? row.sales_payment_total : amount,
                    ),
                  )}
                </td>
                {kind === "receipts" && (
                  <>
                    <td>
                      {formatBRL(String(row.consumption_payment_total || "0"))}
                    </td>
                    <td>
                      {formatBRL(
                        String(row.payment_total_before_reversals || "0"),
                      )}
                    </td>
                    <td className="text-danger">
                      {formatBRL(String(row.reversal_payment_total || "0"))}
                    </td>
                    <td>
                      <strong>
                        {formatBRL(String(row.payment_total || "0"))}
                      </strong>
                    </td>
                  </>
                )}
                {isTeam && (
                  <>
                    <td>{formatBRL(String(row.service_fee || "0"))}</td>
                    <td>{formatBRL(String(row.total_received || "0"))}</td>
                    <td>{formatBRL(String(row.average || "0"))}</td>
                    <td>
                      {String(row.cancellation_count || 0)}
                      <small className="block text-slate-500">
                        {formatBRL(String(row.cancellation_value || "0"))}
                      </small>
                    </td>
                  </>
                )}
                {showCommission && (
                  <td>
                    <strong>{formatBRL(String(row.commission || "0"))}</strong>
                    {row.commission_sale_count !== undefined && (
                      <small className="block text-slate-500">
                        {String(row.commission_sale_count)} vendas
                      </small>
                    )}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function CategoryRanking({ summary }: { summary: Record<string, unknown> }) {
  const categories = rows(summary.category_ranking);
  return (
    <section className="card overflow-hidden">
      <div className="card-header">
        <h2 className="text-sm font-bold">Classificação por categoria</h2>
      </div>
      {categories.length ? (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Categoria</th>
                <th>Unidades</th>
                <th>Faturamento de vendas</th>
              </tr>
            </thead>
            <tbody>
              {categories.map((row) => (
                <tr key={`category:${String(row.category_id || "unassigned")}`}>
                  <td>
                    <strong>
                      {String(row.category_name || "Sem categoria")}
                    </strong>
                  </td>
                  <td>{formatQuantity(String(row.quantity || "0"))}</td>
                  <td>{formatBRL(String(row.revenue || "0"))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title="Sem categorias"
          description="Nenhuma categoria teve venda no período."
        />
      )}
    </section>
  );
}

function SalesSections({ summary }: { summary: Record<string, unknown> }) {
  const products = rows(summary.product_ranking);
  const categories = rows(summary.category_ranking);
  const payments = rows(summary.payment_totals);
  const cancellations = (summary.cancellations || {}) as Record<
    string,
    unknown
  >;
  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <section className="card overflow-hidden">
        <div className="card-header">
          <h2 className="text-sm font-bold">Produtos mais vendidos</h2>
        </div>
        {products.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Produto</th>
                  <th>Quantidade</th>
                  <th>Faturamento de vendas</th>
                </tr>
              </thead>
              <tbody>
                {products.map((row) => (
                  <tr key={`product:${String(row.product_id)}`}>
                    <td>
                      <strong>{String(row.product_name)}</strong>
                      <small className="block text-slate-500">
                        {String(row.internal_code || "")}
                      </small>
                    </td>
                    <td>{formatQuantity(String(row.quantity))}</td>
                    <td>{formatBRL(String(row.revenue))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="Sem produtos vendidos"
            description="Nenhuma venda finalizada no período."
          />
        )}
      </section>
      <section className="card overflow-hidden">
        <div className="card-header">
          <h2 className="text-sm font-bold">Categorias vendidas</h2>
        </div>
        {categories.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Categoria</th>
                  <th>Quantidade</th>
                  <th>Faturamento de vendas</th>
                </tr>
              </thead>
              <tbody>
                {categories.map((row) => (
                  <tr key={`category:${String(row.category_id || "unassigned")}`}>
                    <td>
                      <strong>{String(row.category_name)}</strong>
                    </td>
                    <td>{formatQuantity(String(row.quantity))}</td>
                    <td>{formatBRL(String(row.revenue))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="Sem categorias vendidas"
            description="Nenhuma categoria teve venda no período."
          />
        )}
      </section>
      <section className="card overflow-hidden">
        <div className="card-header">
          <h2 className="text-sm font-bold">Recebimentos por forma</h2>
        </div>
        {payments.length ? (
          <div className="divide-y divide-slate-100">
            {payments.map((row) => (
              <div
                key={`payment:${String(row.code)}`}
                className="flex items-center justify-between px-5 py-3 text-sm"
              >
                <span>{String(row.name)}</span>
                <strong>{formatBRL(String(row.amount))}</strong>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            title="Sem recebimentos"
            description="Nenhum recebimento finalizado no período."
          />
        )}
      </section>
      <section className="card p-5">
        <h2 className="text-sm font-bold">Cancelamentos</h2>
        <div className="mt-4 flex items-end justify-between gap-4">
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
              Operações
            </span>
            <strong className="mt-1 block text-xl">
              {String(cancellations.count || 0)}
            </strong>
          </div>
          <div className="text-right">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
              Valor estornado
            </span>
            <strong className="mt-1 block text-xl text-danger">
              {formatBRL(String(cancellations.value || "0"))}
            </strong>
          </div>
        </div>
      </section>
    </div>
  );
}

function SalesPaymentTotal({ summary }: { summary: Record<string, unknown> }) {
  return (
    <section className="card p-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-sm font-bold">
            Total dos recebimentos por forma
          </h2>
          <p className="mt-1 text-[11px] text-slate-500">
            Soma dos pagamentos das vendas consideradas. O delta abaixo compara
            pagamentos e Total recebido.
          </p>
        </div>
        <div className="text-right">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
            Total dos pagamentos
          </span>
          <strong className="mt-1 block text-xl text-dark">
            {formatBRL(String(summary.payment_total || "0"))}
          </strong>
        </div>
      </div>
      <ReconciliationWarning
        label="Delta entre pagamentos e Total recebido"
        value={summary.reconciliation_delta}
      />
    </section>
  );
}

function FinancialBridge({
  summary,
  title = "Ponte do Total recebido",
}: {
  summary: Record<string, unknown>;
  title?: string;
}) {
  const lines: Array<[string, unknown, string, boolean?]> = [
    ["Faturamento de vendas", summary.sales_revenue, ""],
    [
      "Consumação cobrada",
      firstValue(summary, "consumption_charged", "charged_consumption"),
      "+",
    ],
    ["Faturamento efetivo", summary.effective_revenue, "=", true],
    ["Taxa de serviço", summary.service_fee, "+"],
    ["Total recebido", summary.total_received, "=", true],
  ];
  return (
    <section className="card overflow-hidden">
      <div className="card-header">
        <div>
          <h2 className="text-sm font-bold">{title}</h2>
          <p className="mt-1 text-[11px] text-slate-500">
            Faturamento de vendas + consumação cobrada = faturamento efetivo; +
            taxa de serviço = Total recebido.
          </p>
        </div>
      </div>
      <div className="grid gap-px bg-surface-muted sm:grid-cols-2 xl:grid-cols-5">
        {lines.map(([label, value, operator, strong]) => (
          <div
            key={label}
            className={`bg-surface p-4 ${strong ? "text-primary" : ""}`}
          >
            <span className="text-[10px] font-bold uppercase tracking-wide text-slate-500">
              {operator} {label}
            </span>
            <strong className="mt-2 block text-base">
              {formatBRL(String(value || "0"))}
            </strong>
          </div>
        ))}
      </div>
    </section>
  );
}

function ReceiptEquations({ summary }: { summary: Record<string, unknown> }) {
  const lines: Array<[string, unknown, string]> = [
    [
      "Pagamentos de vendas antes de reversões",
      summary.sales_received_before_reversals,
      "",
    ],
    [
      "Pagamentos de consumações antes de reversões",
      summary.consumption_received_before_reversals,
      "+",
    ],
    ["Reversões / estornos", summary.reversal_payment_total, "-"],
    ["Total dos pagamentos", summary.payment_total, "="],
  ];
  return (
    <div className="space-y-5">
      <FinancialBridge summary={summary} />
      <section className="card overflow-hidden">
        <div className="card-header">
          <div>
            <h2 className="text-sm font-bold">Reconciliação dos pagamentos</h2>
            <p className="mt-1 text-[11px] text-slate-500">
              As reversões são deduzidas uma única vez dos pagamentos anteriores
              ao estorno.
            </p>
          </div>
        </div>
        <div className="p-5">
          <div className="overflow-hidden rounded-lg border border-subtle">
            <div className="divide-y divide-subtle">
              {lines.map(([label, value, operator]) => (
                <div
                  key={label}
                  className="flex items-center justify-between gap-4 px-4 py-3 text-sm"
                >
                  <span>
                    <b className="mr-2 text-primary">{operator}</b>
                    {label}
                  </span>
                  <strong>{formatBRL(String(value || "0"))}</strong>
                </div>
              ))}
            </div>
          </div>
          <ReconciliationWarning
            label="Delta entre pagamentos e Total recebido"
            value={summary.reconciliation_delta}
          />
        </div>
      </section>
    </div>
  );
}

function SummaryWarnings({
  kind,
  summary,
}: {
  kind: ReportKind;
  summary: Record<string, unknown>;
}) {
  const warnings: Array<[string, unknown]> = [];
  if (["overview", "sales"].includes(kind))
    warnings.push([
      "Delta de pagamentos das vendas",
      summary.reconciliation_delta,
    ]);
  if (kind === "receipts")
    warnings.push([
      "Delta de reconciliação operacional",
      summary.reconciliation_delta,
    ]);
  if (kind === "discounts")
    warnings.push(
      [
        "Delta da reconstrução dos descontos",
        summary.discount_reconstruction_delta,
      ],
      [
        "Delta da reconstrução do total recebido",
        summary.received_reconstruction_delta,
      ],
    );
  if (kind === "consumptions")
    warnings.push([
      "Delta de pagamentos das consumações",
      summary.reconciliation_delta,
    ]);
  if (kind === "cancellations")
    warnings.push([
      "Delta dos valores revertidos",
      summary.reconciliation_delta,
    ]);
  if (kind === "cash")
    warnings.push([
      "Delta de reconciliação operacional do período",
      summary.reconciliation_delta,
    ]);
  if (kind === "result")
    warnings.push([
      "Delta entre pagamentos e Total recebido",
      summary.reconciliation_delta,
    ]);
  const visible = warnings.filter(([, value]) => hasDelta(value));
  if (!visible.length) return null;
  return (
    <div className="space-y-2">
      {visible.map(([label, value]) => (
        <ReconciliationWarning key={label} label={label} value={value} />
      ))}
    </div>
  );
}

function DiscountReconstruction({
  summary,
}: {
  summary: Record<string, unknown>;
}) {
  const parts: Array<[string, unknown, string]> = [
    ["Bruto", summary.gross, ""],
    ["Promoções", summary.promotion_discount, "-"],
    ["Desconto por item", summary.item_discount, "-"],
    ["Desconto na conta", summary.account_discount, "-"],
    ["Faturamento de vendas", summary.sales_revenue, "="],
    ["Taxa de serviço", summary.service_fee, "+"],
    ["Total recebido", summary.total_received, "="],
  ];
  return (
    <section className="card overflow-hidden">
      <div className="card-header">
        <div>
          <h2 className="text-sm font-bold">Reconstrução financeira</h2>
          <p className="mt-1 text-[11px] text-slate-500">
            Bruto - promoção - item - conta = faturamento de vendas; + taxa =
            total recebido.
          </p>
        </div>
      </div>
      <div className="grid gap-px bg-slate-100 sm:grid-cols-2 xl:grid-cols-7">
        {parts.map(([label, value, operator]) => (
          <div key={label} className="bg-white p-4">
            <span className="text-[10px] font-bold uppercase tracking-wide text-slate-500">
              {operator} {label}
            </span>
            <strong className="mt-2 block text-base">
              {formatBRL(String(value || "0"))}
            </strong>
          </div>
        ))}
      </div>
    </section>
  );
}

function ConsumptionFinancials({
  summary,
}: {
  summary: Record<string, unknown>;
}) {
  const payments = rows(summary.payment_totals);
  return (
    <section className="card overflow-hidden">
      <div className="card-header">
        <div>
          <h2 className="text-sm font-bold">Pagamentos das consumações</h2>
          <p className="mt-1 text-[11px] text-slate-500">
            Valores cobrados distribuídos por forma de pagamento.
          </p>
        </div>
      </div>
      {payments.length ? (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Forma</th>
                <th>Valor recebido</th>
              </tr>
            </thead>
            <tbody>
              {payments.map((row) => (
                <tr key={`payment:${String(row.code)}`}>
                  <td>
                    <strong>{String(row.name || row.code)}</strong>
                  </td>
                  <td>{formatBRL(String(row.amount || "0"))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title="Sem pagamentos"
          description="Nenhuma consumação cobrada por forma de pagamento."
        />
      )}
    </section>
  );
}

function FilteredMethodNotice({
  summary,
}: {
  summary: Record<string, unknown>;
}) {
  const method = summary.filtered_payment_method as
    Record<string, unknown> | undefined;
  if (!method) return null;
  return (
    <div className="rounded-md border border-info/30 bg-info-surface px-4 py-3 text-sm text-info-strong">
      <strong>
        Subtotal específico de {String(method.name || method.code)}:{" "}
        {formatBRL(String(method.subtotal || "0"))}.
      </strong>{" "}
      Este subtotal filtra a forma de pagamento e não representa faturamento
      integral.
    </div>
  );
}

const userTypeLabels: Record<string, string> = {
  employee: "Funcionário",
  promoter: "Promoter",
  dj: "DJ",
  artist: "Artista",
  other: "Outro",
  not_informed: "Não informado",
};

function ConsumptionGroups({ summary }: { summary: Record<string, unknown> }) {
  const groups: Array<
    [
      string,
      Array<Record<string, unknown>>,
      (row: Record<string, unknown>) => string,
    ]
  > = [
    [
      "Por beneficiário",
      rows(summary.beneficiary_groups),
      (row) =>
        String((row.beneficiary as { name?: string })?.name || "Não informado"),
    ],
    [
      "Por tipo de beneficiário",
      rows(summary.user_type_groups),
      (row) => userTypeLabels[String(row.user_type)] || String(row.user_type),
    ],
  ];
  return (
    <div className="grid gap-5 xl:grid-cols-2">
      {groups.map(([title, list, label]) => (
        <section key={title} className="card overflow-hidden">
          <div className="card-header">
            <h2 className="text-sm font-bold">{title}</h2>
          </div>
          {list.length ? (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{title.replace("Por ", "")}</th>
                    <th>Operações</th>
                    <th>Referência</th>
                    <th>Cobrado</th>
                    <th>Benefício</th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((row) => (
                    <tr key={`${title}:${String((row.beneficiary as { id?: number } | undefined)?.id || row.user_type || "unassigned")}`}>
                      <td>
                        <strong>{label(row)}</strong>
                      </td>
                      <td>{String(row.count)}</td>
                      <td>{formatBRL(String(row.reference))}</td>
                      <td>{formatBRL(String(row.charged))}</td>
                      <td>{formatBRL(String(row.benefit))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="Sem agrupamentos"
              description="Nenhuma consumação finalizada no período."
            />
          )}
        </section>
      ))}
    </div>
  );
}

function WithdrawalCategories({
  summary,
}: {
  summary: Record<string, unknown>;
}) {
  const categories = rows(summary.by_category);
  if (!categories.length) return null;
  return (
    <section className="card overflow-hidden">
      <div className="card-header">
        <h2 className="text-sm font-bold">Resumo por categoria</h2>
      </div>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Categoria</th>
              <th>Movimentos</th>
              <th>Valor</th>
            </tr>
          </thead>
          <tbody>
            {categories.map((row) => (
              <tr key={`withdrawal-category:${String(row.category)}`}>
                <td>
                  <strong>{String(row.category_label || row.category)}</strong>
                </td>
                <td>{String(row.count)}</td>
                <td>{formatBRL(String(row.amount))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function CashSummarySections({
  summary,
}: {
  summary: Record<string, unknown>;
}) {
  const payments = rows(summary.payment_totals);
  return (
    <div className="space-y-5">
      <FinancialBridge
        summary={summary}
        title="Ponte financeira do período solicitado"
      />
      <div className="grid gap-5 lg:grid-cols-3">
        <section className="card p-5 text-sm">
          <h2 className="font-bold">Vendas no período solicitado</h2>
          <div className="mt-4 space-y-2">
            <p className="flex justify-between">
              <span>Operações</span>
              <strong>{String(summary.sales_count || 0)}</strong>
            </p>
            <p className="flex justify-between">
              <span>Faturamento de vendas</span>
              <strong>
                {formatBRL(String(summary.sales_revenue || "0"))}
              </strong>
            </p>
            <p className="flex justify-between">
              <span>Taxa de serviço</span>
              <strong>{formatBRL(String(summary.service_fee || "0"))}</strong>
            </p>
            <p className="flex justify-between border-t border-slate-100 pt-2">
              <span>Vendas com taxa de serviço</span>
              <strong>
                {formatBRL(
                  String(
                    sumReportMoney([summary.sales_revenue, summary.service_fee]),
                  ),
                )}
              </strong>
            </p>
            {summary.commission !== undefined && (
              <p className="flex justify-between text-danger">
                <span>Comissão histórica (custo)</span>
                <strong>{formatBRL(String(summary.commission))}</strong>
              </p>
            )}
          </div>
        </section>
        <section className="card p-5 text-sm">
          <h2 className="font-bold">Consumações no período solicitado</h2>
          <div className="mt-4 space-y-2">
            <p className="flex justify-between">
              <span>Operações</span>
              <strong>{String(summary.consumption_count || 0)}</strong>
            </p>
            <p className="flex justify-between">
              <span>Consumação cobrada</span>
              <strong>
                {formatBRL(String(summary.consumption_charged || "0"))}
              </strong>
            </p>
          </div>
        </section>
        <section className="card p-5 text-sm">
          <h2 className="font-bold">Reconciliação e movimentos do período</h2>
          <div className="mt-4 space-y-2">
            <p className="flex justify-between">
              <span>Pagamentos antes de reversões</span>
              <strong>
                {formatBRL(
                  String(
                    summary.payment_totals
                        ? sumReportMoney(rows(summary.payment_totals).map((row) => row.gross_received))
                        : "0.00",
                  ),
                )}
              </strong>
            </p>
            <p className="flex justify-between text-danger">
              <span>Reversões</span>
              <strong>- {formatBRL(String(summary.reversals || "0"))}</strong>
            </p>
            <p className="flex justify-between border-t border-slate-100 pt-2">
              <span>Total dos pagamentos</span>
              <strong>
                {formatBRL(String(summary.payment_total || "0"))}
              </strong>
            </p>
            <p className="flex justify-between">
              <span>Entradas manuais</span>
              <strong>
                {formatBRL(String(summary.manual_entries || "0"))}
              </strong>
            </p>
            <p className="flex justify-between text-danger">
              <span>Sangrias</span>
              <strong>- {formatBRL(String(summary.withdrawals || "0"))}</strong>
            </p>
          </div>
        </section>
      </div>
      <section className="card overflow-hidden">
        <div className="card-header">
          <div>
            <h2 className="text-sm font-bold">
              Fontes de recebimento no período solicitado
            </h2>
            <p className="mt-1 text-[11px] text-slate-500">
              Pagamentos de vendas + pagamentos de consumações - reversões =
              total dos pagamentos.
            </p>
          </div>
        </div>
        {payments.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Forma</th>
                  <th>Pagamentos de vendas</th>
                  <th>Pagamentos de consumações</th>
                  <th>Antes de reversões</th>
                  <th>Reversões</th>
                  <th>Total dos pagamentos</th>
                </tr>
              </thead>
              <tbody>
                {payments.map((row) => (
                  <tr key={`payment:${String(row.code)}`}>
                    <td>
                      <strong>{String(row.name)}</strong>
                    </td>
                    <td>{formatBRL(String(row.sales_payment_total || "0"))}</td>
                    <td>
                      {formatBRL(String(row.consumption_payment_total || "0"))}
                    </td>
                    <td>
                      {formatBRL(
                        String(row.payment_total_before_reversals || "0"),
                      )}
                    </td>
                    <td className="text-danger">
                      {formatBRL(String(row.reversal_payment_total || "0"))}
                    </td>
                    <td>
                      <strong>
                        {formatBRL(String(row.payment_total || "0"))}
                      </strong>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="Sem recebimentos"
            description="Nenhum evento de pagamento no período solicitado."
          />
        )}
      </section>
    </div>
  );
}

function CashTable({
  data,
  canViewCash,
}: {
  data: ReportResponse<Record<string, unknown>>;
  canViewCash: boolean;
}) {
  if (!data.results.length)
    return (
      <EmptyState
        title="Sem sessões"
        description="Nenhuma sessão intersecta o período."
      />
    );
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Sessão</th>
            <th>Status</th>
            <th>Período</th>
            <th>Vendas</th>
            <th>Consumações</th>
            <th>Gaveta da sessão completa</th>
            <th>Informado</th>
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
            const sales = (operational?.sales || {}) as Record<string, unknown>;
            const consumptions = (operational?.consumptions || {}) as Record<
              string,
              unknown
            >;
            return (
              <tr key={`cash-session:${String(row.id)}`}>
                <td>
                  {canViewCash ? (
                    <Link
                      className="font-bold text-primary"
                      href={`/caixas/sessoes/${row.id}`}
                    >
                      {register.name} #{String(row.id)}
                    </Link>
                  ) : (
                    <strong>
                      {register.name} #{String(row.id)}
                    </strong>
                  )}
                </td>
                <td>
                  <StatusBadge value={row.status} />
                </td>
                <td>
                  {formatDate(String(row.opened_at))}
                  <small className="block text-slate-500">
                    {row.closed_at
                      ? `até ${formatDate(String(row.closed_at))}`
                      : "Em andamento"}
                  </small>
                </td>
                <td>
                  {String(sales.count || 0)}
                  <small className="block text-slate-500">
                    {formatBRL(String(sales.sales_revenue || "0"))} +{" "}
                    {formatBRL(String(sales.service_fee || "0"))} de taxa
                  </small>
                </td>
                <td>
                  {String(consumptions.count || 0)}
                  <small className="block text-slate-500">
                    {formatBRL(String(consumptions.charged || "0"))} cobrados
                  </small>
                </td>
                <td>
                  <strong>{formatBRL(String(row.expected || "0"))}</strong>
                  <small className="block text-slate-500">
                    Vendas {formatBRL(String(row.sale_cash || "0"))} ·
                    Consumações {formatBRL(String(row.consumption_cash || "0"))}{" "}
                    · Reversões {formatBRL(String(row.cash_reversals || "0"))}
                  </small>
                </td>
                <td>
                  {row.informed == null ? "-" : formatBRL(String(row.informed))}
                </td>
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
  );
}

function StockConsumption({
  data,
}: {
  data: ReportResponse<Record<string, unknown>>;
}) {
  const products = rows(data.summary.products);
  const showCost = products.some((row) => row.estimated_cost !== undefined);
  const contentByUnit = Object.entries((data.summary.content_by_unit || {}) as Record<string, Record<string, unknown>>);
  return (
    <div className="space-y-5">
      {contentByUnit.length > 0 && <section className="card p-5">
        <h2 className="text-sm font-bold">Conteúdo exato rastreado</h2>
        <p className="mt-1 text-[11px] text-muted">Parcela canônica rastreada dentro dos totais equivalentes combinados do relatório.</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          {contentByUnit.flatMap(([unit, values]) => ([
            ["Consumo bruto", values.gross_content],
            ["Devoluções", values.returned_content],
            ["Consumo líquido", values.net_content],
          ] as Array<[string, unknown]>).map(([label, value]) => <div key={`${unit}-${label}`} className="rounded-lg bg-surface-muted p-3"><small className="block text-[10px] font-semibold text-muted">{label} rastreado</small><strong className="mt-1 block text-sm">{formatQuantity(String(value || "0"))} {contentUnitLabel(unit)}</strong></div>))}
        </div>
      </section>}
      <section className="card overflow-hidden">
        <div className="card-header">
          <h2 className="text-sm font-bold">Resumo por produto físico</h2>
        </div>
        {products.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Produto</th>
                  <th>Consumo bruto</th>
                  <th>Devoluções</th>
                  <th>Consumo líquido</th>
                  {showCost && <th>Custo estimado pelo custo atual</th>}
                </tr>
              </thead>
              <tbody>
                {products.map((row) => {
                  const product = row.product as {
                    id?: number;
                    name?: string;
                    unit?: string;
                  };
                  return (
                    <tr key={`product:${String(product.id)}`}>
                      <td>
                        <strong>{product.name}</strong>
                      </td>
                      <td>
                        <ConsumptionQuantity row={row} quantityKey="gross_quantity" prefix="gross" />
                      </td>
                      <td><ConsumptionQuantity row={row} quantityKey="returned_quantity" prefix="returned" /></td>
                      <td><ConsumptionQuantity row={row} quantityKey="net_quantity" prefix="net" /></td>
                      {showCost && (
                        <td>{formatBRL(String(row.estimated_cost || "0"))}</td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="Sem consumo físico"
            description="Nenhum movimento de consumo no período."
          />
        )}
      </section>
      <section className="card overflow-hidden">
        <div className="card-header">
          <h2 className="text-sm font-bold">Movimentações detalhadas</h2>
        </div>
        {data.results.length ? (
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
                {data.results.map((row) => {
                  const product = row.product as { name?: string };
                  return (
                    <tr key={`stock-movement:${String(row.id)}`}>
                      <td>{formatDate(String(row.created_at))}</td>
                      <td>{product.name}</td>
                      <td>{domainLabel(row.origin)}</td>
                      <td>{domainLabel(row.nature)}</td>
                      <td><ConsumptionQuantity row={row} quantityKey="equivalent_quantity" /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="Sem movimentações"
            description="Nenhum detalhe no período."
          />
        )}
      </section>
    </div>
  );
}

function ResultStatement({ summary }: { summary: Record<string, unknown> }) {
  const lines: Array<[string, string, boolean?]> = [
    ["Valor bruto a preço de tabela", "gross"],
    ["(-) Descontos promocionais", "promotion_discount"],
    ["(-) Descontos manuais por item", "item_discount"],
    ["(-) Descontos manuais na conta", "account_discount"],
    ["= Faturamento de vendas", "sales_revenue", true],
    ["(+) Consumação cobrada", "consumption_charged"],
    ["= Faturamento efetivo", "effective_revenue", true],
    ["(+) Taxa de serviço", "service_fee"],
    ["= Total recebido", "total_received", true],
    ["(-) Custos e despesas", "costs_and_expenses"],
    ["= Resultado estimado", "result", true],
  ];
  const costDetails: Array<[string, string]> = [
    ["CMV histórico de vendas", "historical_sales_cogs"],
    ["CMV histórico de consumações", "historical_consumption_cogs"],
    ["Comissão", "commission"],
    ["Despesas operacionais", "operating_expenses"],
    ["Custo fixo rateado", "fixed_cost"],
  ];
  const visibleCostDetails = costDetails.filter(
    ([, key]) => summary[key] !== undefined,
  );
  return (
    <div className="p-5">
      <div className="mx-auto max-w-2xl space-y-1">
        {lines
          .filter(([, key]) => summary[key] !== undefined)
          .map(([label, key, strong]) => (
            <div
              key={key}
              className={`flex items-center justify-between gap-4 rounded-md px-4 py-3 ${strong ? "mt-2 bg-primary/10 text-dark" : "border-b border-slate-100"}`}
            >
              <span className={strong ? "font-bold" : "text-sm"}>{label}</span>
              <strong>{formatBRL(String(summary[key] || "0"))}</strong>
            </div>
          ))}
        {summary.margin !== undefined && summary.margin !== null && (
          <div className="flex justify-between px-4 py-3">
            <span className="text-sm">Margem sobre o Total recebido</span>
            <strong>{formatPercent(summary.margin)}</strong>
          </div>
        )}
        {visibleCostDetails.length > 0 && (
          <div className="mt-5 rounded-lg border border-subtle p-4">
            <h3 className="text-xs font-bold">Composição autorizada de custos e despesas</h3>
            <div className="mt-3 space-y-2">
              {visibleCostDetails.map(([label, key]) => (
                <div key={key} className="flex justify-between gap-4 text-sm">
                  <span>{label}</span>
                  <strong>{formatBRL(String(summary[key] || "0"))}</strong>
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="mt-5 rounded-lg border border-subtle px-4 py-3 text-sm">
          <span>Total dos pagamentos</span>
          <strong className="float-right">
            {formatBRL(String(summary.payment_total || "0"))}
          </strong>
        </div>
        <p className="px-4 pt-3 text-xs text-slate-500">
          {String(
            summary.notice ||
              "Estimativa operacional; não constitui DRE contábil.",
          )}
        </p>
      </div>
    </div>
  );
}

function ReportBody({
  kind,
  data,
  canViewSales,
  canViewConsumptions,
  canViewCash,
}: {
  kind: ReportKind;
  data: ReportResponse<Record<string, unknown>>;
  canViewSales: boolean;
  canViewConsumptions: boolean;
  canViewCash: boolean;
}) {
  if (kind === "products")
    return (
      <div className="grid gap-5 xl:grid-cols-2">
        <section className="card overflow-hidden">
          <div className="card-header">
            <h2 className="text-sm font-bold">Classificação por produto</h2>
          </div>
          <RankingTable kind={kind} summary={data.summary} />
        </section>
        <CategoryRanking summary={data.summary} />
      </div>
    );
  if (kind === "receipts")
    return (
      <div className="space-y-5">
        <FilteredMethodNotice summary={data.summary} />
        <ReceiptEquations summary={data.summary} />
        <section className="card overflow-hidden">
          <div className="card-header">
            <div>
              <h2 className="text-sm font-bold">Recebimentos por forma</h2>
              <p className="mt-1 text-[11px] text-slate-500">
                Vendas, consumações, reversões e recebimento líquido no mesmo
                recorte.
              </p>
            </div>
          </div>
          <RankingTable kind={kind} summary={data.summary} />
        </section>
      </div>
    );
  if (["operators", "sellers", "commissions"].includes(kind))
    return (
      <section className="card overflow-hidden">
        <div className="card-header">
          <h2 className="text-sm font-bold">Detalhamento</h2>
        </div>
        <RankingTable kind={kind} summary={data.summary} />
      </section>
    );
  if (kind === "stock-consumption") return <StockConsumption data={data} />;
  if (kind === "cash")
    return (
      <div className="space-y-5">
        <CashSummarySections summary={data.summary} />
        <section className="card overflow-hidden">
          <div className="card-header">
            <div>
              <h2 className="text-sm font-bold">Sessões de caixa</h2>
              <p className="mt-1 text-[11px] text-slate-500">
                Resumo superior usa eventos do período solicitado; cada linha
                abaixo mostra valores da sessão completa.
              </p>
            </div>
          </div>
          <CashTable data={data} canViewCash={canViewCash} />
        </section>
      </div>
    );
  if (kind === "result")
    return (
      <div className="space-y-5">
        <FinancialBridge summary={data.summary} title="Ponte do resultado" />
        <section className="card overflow-hidden">
          <div className="card-header">
            <h2 className="text-sm font-bold">Demonstrativo de resultado</h2>
          </div>
          <ResultStatement summary={data.summary} />
        </section>
      </div>
    );
  if (kind === "withdrawals")
    return (
      <div className="space-y-5">
        <WithdrawalCategories summary={data.summary} />
        <section className="card overflow-hidden">
          <div className="card-header">
            <h2 className="text-sm font-bold">Sangrias detalhadas</h2>
          </div>
          {data.results.length ? (
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
                    const beneficiary = row.beneficiary as {
                      name?: string;
                    } | null;
                    const operator = row.operator as { name?: string };
                    return (
                      <tr key={`withdrawal:${String(row.id)}`}>
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
          ) : (
            <EmptyState
              title="Sem sangrias"
              description="Nenhuma sangria no período."
            />
          )}
        </section>
      </div>
    );
  const operations = (
    <section className="card overflow-hidden">
      <div className="card-header">
        <h2 className="text-sm font-bold">Operações</h2>
      </div>
      <SalesTable
        kind={kind}
        data={data}
        canViewSales={canViewSales}
        canViewConsumptions={canViewConsumptions}
      />
    </section>
  );
  if (["sales", "overview"].includes(kind))
    return (
      <div className="space-y-5">
        <SalesSections summary={data.summary} />
        <SalesPaymentTotal summary={data.summary} />
        {operations}
      </div>
    );
  if (kind === "discounts")
    return (
      <div className="space-y-5">
        <DiscountReconstruction summary={data.summary} />
        {operations}
      </div>
    );
  if (kind === "consumptions")
    return (
      <div className="space-y-5">
        <ConsumptionFinancials summary={data.summary} />
        <ConsumptionGroups summary={data.summary} />
        {operations}
      </div>
    );
  return operations;
}

export function DedicatedReport({ kind }: { kind: ReportKind }) {
  const config = configs[kind];
  const { currentBranch, hasPermission } = useAuth();
  const context = useRef(currentBranch?.id || 0);
  const requestId = useRef(0);
  const optionsRequestId = useRef(0);
  context.current = currentBranch?.id || 0;
  const [period, setPeriod] = useState(initialPeriod);
  const [appliedPeriod, setAppliedPeriod] = useState(initialPeriod);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [appliedFilters, setAppliedFilters] = useState<Record<string, string>>(
    {},
  );
  const [options, setOptions] = useState<ReportsOptions | null>(null);
  const [data, setData] = useState<ReportResponse<
    Record<string, unknown>
  > | null>(null);
  const [prices, setPrices] = useState<ProductPriceComparison | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const allowed = hasPermission(config.permission);

  function params(nextPeriod = appliedPeriod, nextFilters = appliedFilters) {
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
    const currentRequest = ++requestId.current;
    setLoading(true);
    setError("");
    try {
      if (kind === "prices") {
        const query = new URLSearchParams(
          Object.entries(nextFilters).filter(([, value]) => value),
        );
        setPrices(null);
        setAppliedFilters(nextFilters);
        window.history.replaceState(
          null,
          "",
          `${window.location.pathname}${query.size ? `?${query}` : ""}`,
        );
        const result = await http.get<ProductPriceComparison>(
          `products/price-comparison/${query.size ? `?${query}` : ""}`,
        );
        if (context.current === token && requestId.current === currentRequest) {
          setPrices(result);
        }
        return;
      }
      const query = params(nextPeriod, nextFilters);
      setData(null);
      setAppliedPeriod(nextPeriod);
      setAppliedFilters(nextFilters);
      window.history.replaceState(
        null,
        "",
        `${window.location.pathname}?${query}`,
      );
      const result = await http.get<ReportResponse<Record<string, unknown>>>(
        `reports/${config.endpoint}/?${query}`,
      );
      if (context.current === token && requestId.current === currentRequest) {
        setData(result);
      }
    } catch (caught) {
      if (context.current === token && requestId.current === currentRequest)
        setError(
          caught instanceof ApiError
            ? caught.message
            : "Não foi possível carregar o relatório.",
        );
    } finally {
      if (context.current === token && requestId.current === currentRequest)
        setLoading(false);
    }
  }

  async function loadPage(path: string, token = context.current) {
    const currentRequest = ++requestId.current;
    setLoading(true);
    setData(null);
    setError("");
    try {
      const result =
        await http.get<ReportResponse<Record<string, unknown>>>(path);
      if (context.current === token && requestId.current === currentRequest)
        setData(result);
    } catch {
      if (context.current === token && requestId.current === currentRequest)
        setError("Não foi possível trocar a página.");
    } finally {
      if (context.current === token && requestId.current === currentRequest)
        setLoading(false);
    }
  }

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const start = query.get("start_datetime");
    const end = query.get("end_datetime");
    const nextPeriod = start && end ? { start, end } : initialPeriod();
    const nextFilters = Object.fromEntries(
      [...query.entries()].filter(
        ([key]) =>
          ![
            "start_datetime",
            "end_datetime",
            "branch",
            "scope",
            "export",
            "page",
            "page_size",
          ].includes(key),
      ),
    );
    setData(null);
    setPrices(null);
    setPeriod(nextPeriod);
    setFilters(nextFilters);
    setAppliedFilters(nextFilters);
    void load(nextPeriod, nextFilters, context.current);
    const token = context.current;
    const currentOptionsRequest = ++optionsRequestId.current;
    setOptions(null);
    void http
      .get<ReportsOptions>(`reports/options/?scope=${kind}`)
      .then((result) => {
        if (
          context.current === token &&
          optionsRequestId.current === currentOptionsRequest
        )
          setOptions(result);
      })
      .catch(() => {
        if (
          context.current === token &&
          optionsRequestId.current === currentOptionsRequest
        )
          setOptions(null);
      });
  }, [currentBranch?.id, kind, allowed]);

  function clearReportFilters() {
    const resetPeriod = initialPeriod();
    setPeriod(resetPeriod);
    setFilters({});
    void load(resetPeriod, {});
  }

  if (!allowed)
    return (
      <div className="p-6">
        <Alert message="Você não possui permissão para este relatório." />
      </div>
    );
  const productKinds = [
    "sales",
    "overview",
    "products",
    "receipts",
    "operators",
    "sellers",
    "commissions",
    "discounts",
    "consumptions",
    "stock-consumption",
    "cancellations",
  ];
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
            <ReportExportAction
              path={
                kind === "prices"
                  ? "products/price-comparison/"
                  : `reports/${config.endpoint}/`
              }
              query={
                kind === "prices"
                  ? new URLSearchParams(
                      Object.entries(appliedFilters).filter(([, value]) => value),
                    )
                  : params()
              }
            />
          </div>
        }
      />
      <div className="space-y-5 p-4 sm:p-6 lg:p-8">
        {error && <Alert message={error} />}
        {kind === "prices" ? (
          <section className="card p-4">
            <div className="mb-3 flex items-center gap-2 text-xs font-bold">
              <Filter className="size-4 text-primary" />
              Filtros
            </div>
            <div className="grid gap-3 md:grid-cols-3">
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
              <Field label="Produto">
                <Select
                  value={filters.product || ""}
                  onChange={(event) =>
                    setFilters((current) => ({
                      ...current,
                      product: event.target.value,
                    }))
                  }
                >
                  <option value="">Todos</option>
                  {options?.products.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Status do produto">
                <Select
                  value={filters.status || ""}
                  onChange={(event) =>
                    setFilters((current) => ({
                      ...current,
                      status: event.target.value,
                    }))
                  }
                >
                  <option value="">Todos</option>
                  <option value="active">Ativo</option>
                  <option value="inactive">Inativo</option>
                </Select>
              </Field>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <Button
                variant="secondary"
                onClick={() => {
                  setFilters({});
                  void load(period, {});
                }}
              >
                Limpar filtros
              </Button>
              <Button onClick={() => void load(period, filters)}>
                Aplicar filtros
              </Button>
            </div>
          </section>
        ) : (
          <section className="card p-4">
            <div className="mb-3 flex items-center gap-2 text-xs font-bold">
              <Filter className="size-4 text-primary" />
              Filtros
            </div>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <PeriodFilter
                className="md:col-span-2 xl:col-span-4"
                value={period}
                onChange={setPeriod}
                onApply={(next) => {
                  setPeriod(next);
                  void load(next, appliedFilters);
                }}
                showActions={false}
              />
              {productKinds.includes(kind) && (
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
              {productKinds.includes(kind) && (
                <Field label="Produto">
                  <Select
                    value={filters.product || ""}
                    onChange={(event) =>
                      setFilters((current) => ({
                        ...current,
                        product: event.target.value,
                      }))
                    }
                  >
                    <option value="">Todos</option>
                    {options?.products.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </Select>
                </Field>
              )}
              {[
                "sales",
                "overview",
                "operators",
                "discounts",
                "cancellations",
                "cash",
                "withdrawals",
              ].includes(kind) && (
                <Field label="Operador">
                  <Select
                    value={filters.operator || ""}
                    onChange={(event) =>
                      setFilters((current) => ({
                        ...current,
                        operator: event.target.value,
                      }))
                    }
                  >
                    <option value="">Todos</option>
                    {options?.operators.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </Select>
                </Field>
              )}
              {[
                "sales",
                "overview",
                "sellers",
                "commissions",
                "discounts",
                "cancellations",
              ].includes(kind) && (
                <Field label="Atendente">
                  <Select
                    value={filters.seller || ""}
                    onChange={(event) =>
                      setFilters((current) => ({
                        ...current,
                        seller: event.target.value,
                      }))
                    }
                  >
                    <option value="">Todos</option>
                    {options?.sellers.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </Select>
                </Field>
              )}
              {["sales", "overview", "receipts"].includes(kind) && (
                <Field label="Forma de pagamento">
                  <Select
                    value={
                      filters.payment_method ||
                      String(
                        options?.payment_methods.find(
                          (item) => item.code === filters.payment_method_code,
                        )?.id || "",
                      )
                    }
                    onChange={(event) =>
                      setFilters((current) => ({
                        ...current,
                        payment_method: event.target.value,
                        payment_method_code: "",
                      }))
                    }
                  >
                    <option value="">Todas</option>
                    {options?.payment_methods.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </Select>
                </Field>
              )}
              {["sales", "overview"].includes(kind) && (
                <Field label="Status">
                  <Select
                    value={filters.status || ""}
                    onChange={(event) =>
                      setFilters((current) => ({
                        ...current,
                        status: event.target.value,
                      }))
                    }
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
              {["sales", "overview"].includes(kind) && (
                <Field label="Dia da semana">
                  <Select
                    value={filters.weekday || ""}
                    onChange={(event) =>
                      setFilters((current) => ({
                        ...current,
                        weekday: event.target.value,
                      }))
                    }
                  >
                    <option value="">Todos</option>
                    {[
                      "Segunda",
                      "Terça",
                      "Quarta",
                      "Quinta",
                      "Sexta",
                      "Sábado",
                      "Domingo",
                    ].map((label, index) => (
                      <option key={label} value={index}>
                        {label}
                      </option>
                    ))}
                  </Select>
                </Field>
              )}
              {["sales", "overview"].includes(kind) && (
                <Field label="Hora">
                  <Select
                    value={filters.hour || ""}
                    onChange={(event) =>
                      setFilters((current) => ({
                        ...current,
                        hour: event.target.value,
                      }))
                    }
                  >
                    <option value="">Todas</option>
                    {Array.from({ length: 24 }, (_, hour) => (
                      <option key={hour} value={hour}>
                        {String(hour).padStart(2, "0")}:00
                      </option>
                    ))}
                  </Select>
                </Field>
              )}
              {kind === "consumptions" && (
                <Field label="Tipo de beneficiário">
                  <Select
                    value={filters.user_type || ""}
                    onChange={(event) =>
                      setFilters((current) => ({
                        ...current,
                        user_type: event.target.value,
                      }))
                    }
                  >
                    <option value="">Todos</option>
                    {options?.user_types.map((item) => (
                      <option key={item.value} value={item.value}>
                        {userTypeLabels[item.value] || item.label}
                      </option>
                    ))}
                  </Select>
                </Field>
              )}
              {["consumptions", "withdrawals"].includes(kind) && (
                <Field label="Beneficiário">
                  <Select
                    value={filters.beneficiary || ""}
                    onChange={(event) =>
                      setFilters((current) => ({
                        ...current,
                        beneficiary: event.target.value,
                      }))
                    }
                  >
                    <option value="">Todos</option>
                    {options?.beneficiaries.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </Select>
                </Field>
              )}
              {kind === "consumptions" && (
                <Field label="Status">
                  <Select
                    value={filters.status || ""}
                    onChange={(event) =>
                      setFilters((current) => ({
                        ...current,
                        status: event.target.value,
                      }))
                    }
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
              {kind === "stock-consumption" && (
                <Field label="Origem">
                  <Select
                    value={filters.origin || ""}
                    onChange={(event) =>
                      setFilters((current) => ({
                        ...current,
                        origin: event.target.value,
                      }))
                    }
                  >
                    <option value="">Todas</option>
                    <option value="sale">Venda</option>
                    <option value="consumption">Consumação</option>
                    <option value="manual_exit">Saída manual</option>
                    <option value="reversal">Reversão/cancelamento</option>
                  </Select>
                </Field>
              )}
              {["cash", "withdrawals"].includes(kind) && (
                <Field label="Caixa">
                  <Select
                    value={filters.cash_register || ""}
                    onChange={(event) =>
                      setFilters((current) => ({
                        ...current,
                        cash_register: event.target.value,
                      }))
                    }
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
              {kind === "withdrawals" && (
                <Field label="Categoria da sangria">
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
                    {options?.withdrawal_categories.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </Select>
                </Field>
              )}
              {kind === "cash" && (
                <Field label="Status da sessão">
                  <Select
                    value={filters.status || ""}
                    onChange={(event) =>
                      setFilters((current) => ({
                        ...current,
                        status: event.target.value,
                      }))
                    }
                  >
                    <option value="">Todos</option>
                    <option value="open">Aberta</option>
                    <option value="closed">Fechada</option>
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
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="secondary" onClick={clearReportFilters}>
                Limpar filtros
              </Button>
              <Button onClick={() => void load(period, filters)}>
                Aplicar filtros
              </Button>
            </div>
          </section>
        )}
        {kind === "prices" ? (
          <section className="card overflow-hidden">
            {loading ? (
              <TableLoading />
            ) : !prices ? (
              <EmptyState
                title="Relatório indisponível"
                description="Revise os filtros e tente novamente."
              />
            ) : prices.products.length ? (
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
            ) : (
              <EmptyState
                title="Sem produtos"
                description="Nenhum preço disponível para os filtros selecionados."
              />
            )}
          </section>
        ) : loading ? (
          <section className="card">
            <TableLoading />
          </section>
        ) : !data ? (
          <section className="card">
            <EmptyState
              title="Relatório indisponível"
              description="Revise os filtros e tente novamente."
            />
          </section>
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {reportKpis(kind, data.summary).map(([label, value, format]) => (
                <Kpi key={label} label={label} value={value} format={format} />
              ))}
            </div>
            <SummaryWarnings kind={kind} summary={data.summary} />
            <ReportBody
              kind={kind}
              data={data}
              canViewSales={
                hasPermission(permissions.viewSale) ||
                hasPermission(permissions.cancelSale)
              }
              canViewConsumptions={
                hasPermission(permissions.viewConsumption) ||
                hasPermission(permissions.cancelConsumption)
              }
              canViewCash={hasPermission(permissions.viewCashRegister)}
            />
            {data.count > data.results.length && (
              <Pagination
                count={data.count}
                next={data.next}
                previous={data.previous}
                onPage={(path) => void loadPage(path)}
              />
            )}
          </>
        )}
      </div>
    </>
  );
}
