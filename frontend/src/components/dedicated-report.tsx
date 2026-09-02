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
  Input,
  Pagination,
  Select,
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
import {
  contentUnitLabel,
  divideInventoryDecimals,
  inventoryDecimalSign,
  physicalQuantityDisplay,
  subtractInventoryDecimals,
  sumInventoryDecimals,
} from "@/lib/inventory";
import { ApiError, http } from "@/lib/http";
import { businessMonthToDate } from "@/lib/period";
import { permissions } from "@/lib/permissions";
import { branchPriceState } from "@/lib/report-presentation";
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
  | "inventory-movements"
  | "cancellations"
  | "prices"
  | "result";

const configs: Record<
  ReportKind,
  { title: string; description: string; endpoint: string; permission: string }
> = {
  overview: {
    title: "Visão geral",
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
    title: "Recebimentos / Formas de pagamento",
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
    title: "Descontos e autorizações",
    description: "Descontos, promoções e responsáveis pela autorização.",
    endpoint: "sales",
    permission: permissions.viewDiscountsReport,
  },
  consumptions: {
    title: "Consumação / Cortesias",
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
    title: "Consumo / Custos",
    description: "Resumo físico e movimentos reais de saída e reversão.",
    endpoint: "stock-consumption",
    permission: permissions.viewStockConsumptionReport,
  },
  "inventory-movements": {
    title: "Movimentações de estoque",
    description: "Entradas, saídas, ajustes, inventários e reversões da filial.",
    endpoint: "inventory-movements",
    permission: permissions.viewInventoryReport,
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

function averageReportMoney(
  rows: Array<Record<string, unknown>>,
  amountKey: string,
) {
  const count = rows.reduce((total, row) => total + numberValue(row.count), 0);
  if (!count) return "0.00";
  const total = signedMoneyToCents(
    sumReportMoney(rows.map((row) => row[amountKey])),
  );
  return total === null ? "0.00" : centsToDecimal(total / BigInt(count));
}

function firstValue(summary: Record<string, unknown>, ...keys: string[]) {
  const key = keys.find((candidate) => summary[candidate] !== undefined);
  return key ? summary[key] : "0";
}

function reportValue(record: Record<string, unknown>, ...keys: string[]) {
  const key = keys.find(
    (candidate) =>
      record[candidate] !== undefined && record[candidate] !== null,
  );
  return key ? (record[key] as string | number) : undefined;
}

function reportPhysicalQuantity(
  row: Record<string, unknown>,
  quantityKey: string,
  prefix?: string,
) {
  const product = (row.product || {}) as Record<string, unknown>;
  const fraction = (product.fraction_config || {}) as Record<string, unknown>;
  const contentKeys = prefix
    ? [`${prefix}_content`, `${prefix}_content_quantity`]
    : ["content_quantity"];
  const completeKeys = prefix
    ? [`${prefix}_complete_packages`]
    : ["complete_packages", "movement_complete_packages"];
  const residualKeys = prefix
    ? [`${prefix}_residual_content`]
    : ["residual_content", "movement_residual_content"];
  return physicalQuantityDisplay({
    quantity: reportValue(row, quantityKey),
    unit: String(product.unit || row.unit || ""),
    content: reportValue(row, ...contentKeys),
    packageContent:
      reportValue(row, "package_content") ??
      reportValue(product, "package_content") ??
      reportValue(fraction, "package_content"),
    contentUnit: String(
      reportValue(row, "content_unit") ??
        reportValue(product, "content_unit") ??
        reportValue(fraction, "content_unit") ??
        "",
    ),
    completePackages: reportValue(row, ...completeKeys),
    residualContent: reportValue(row, ...residualKeys),
  });
}

function ConsumptionQuantity({
  row,
  quantityKey,
  prefix,
}: {
  row: Record<string, unknown>;
  quantityKey: string;
  prefix?: string;
}) {
  const product = (row.product || {}) as Record<string, unknown>;
  const content = reportValue(
    row,
    ...(prefix
      ? [`${prefix}_content`, `${prefix}_content_quantity`]
      : ["content_quantity"]),
  );
  const packageContent = reportValue(row, "package_content");
  const combined = reportValue(row, quantityKey) ?? 0;
  const unit = String(product.unit || "equiv.").toUpperCase();
  if (
    content == null ||
    packageContent == null ||
    inventoryDecimalSign(packageContent) !== 1
  ) {
    return (
      <span>
        <strong>
          {formatQuantity(String(combined))} {unit}
        </strong>
        <small className="block text-muted">Equivalente legado</small>
      </span>
    );
  }
  const packageEquivalent = divideInventoryDecimals(content, packageContent);
  const legacy =
    packageEquivalent === null
      ? null
      : subtractInventoryDecimals(combined, packageEquivalent);
  return (
    <span>
      <strong className="block">
        {reportPhysicalQuantity(row, quantityKey, prefix)}
      </strong>
      <small className="block text-muted">
        Equivalente legado: {formatQuantity(legacy ?? combined)} {unit}
      </small>
      <small className="block text-muted">
        Total combinado equivalente: {formatQuantity(String(combined))} {unit}
      </small>
    </span>
  );
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

type ReportTab = { value: string; label: string };

function reportTabs(
  kind: ReportKind,
  summary: Record<string, unknown> | null,
  canViewCosts: boolean,
): ReportTab[] {
  if (kind === "sales")
    return [
      { value: "resumo", label: "Resumo" },
      { value: "vendas", label: "Vendas" },
      { value: "itens", label: "Itens" },
      { value: "pagamentos", label: "Pagamentos" },
      { value: "cancelamentos", label: "Cancelamentos" },
    ];
  if (kind === "products") {
    const tabs = [
      { value: "desempenho", label: "Desempenho" },
      { value: "categorias", label: "Categorias" },
      { value: "modificadores", label: "Modificadores" },
      { value: "promocoes", label: "Promoções" },
    ];
    const hasCosts = summary?.has_costs === true;
    if (canViewCosts && hasCosts)
      tabs.push({ value: "custos", label: "Margem e custos" });
    return tabs;
  }
  if (kind === "cash")
    return [
      { value: "resumo", label: "Resumo" },
      { value: "sessoes", label: "Sessões" },
      { value: "recebimentos", label: "Recebimentos" },
      { value: "movimentos", label: "Entradas e sangrias" },
      { value: "diferencas", label: "Diferenças" },
    ];
  return [];
}

function ReportTabs({
  tabs,
  active,
  onChange,
}: {
  tabs: ReportTab[];
  active: string;
  onChange: (tab: string) => void;
}) {
  if (!tabs.length) return null;
  return (
    <nav className="overflow-x-auto rounded-lg border border-subtle bg-surface p-1" aria-label="Seções do relatório">
      <div className="flex min-w-max gap-1">
        {tabs.map((tab) => (
          <button
            key={tab.value}
            type="button"
            className={`rounded-md px-4 py-2 text-xs font-bold transition ${active === tab.value ? "bg-primary text-white" : "text-muted hover:bg-surface-muted hover:text-fg"}`}
            aria-current={active === tab.value ? "page" : undefined}
            onClick={() => onChange(tab.value)}
          >
            {tab.label}
          </button>
        ))}
      </div>
    </nav>
  );
}

function reportKpis(
  kind: ReportKind,
  summary: Record<string, unknown>,
  canViewCosts: boolean,
  canViewCommission: boolean,
) {
  const productRows = rows(summary.product_ranking);
  const operatorRows = rows(summary.operator_groups);
  const sellerRows = rows(summary.seller_groups);
  const stockRows = rows(summary.products);
  const filteredMethod = summary.filtered_payment_method as
    Record<string, unknown> | undefined;
  const receiptMethods = rows(summary.payment_totals);
  const receiptAmount = (...codes: string[]) => sumReportMoney(
    receiptMethods.filter((row) => codes.includes(String(row.code))).map((row) => row.applied_total),
  );
  const knownReceiptCodes = ["cash", "pix", "credit_card", "debit_card", "card"];
  const overviewCurrent = ((summary.period_comparison as Record<string, unknown> | undefined)?.current || {}) as Record<string, unknown>;
  const definitions: Partial<
    Record<
      ReportKind,
      Array<[string, unknown, "money" | "number" | "quantity" | "percent"]>
    >
  > = {
    overview: [
      ["Faturamento bruto", overviewCurrent.gross_revenue ?? summary.gross, "money"],
      ["Faturamento líquido", overviewCurrent.net_revenue ?? summary.sales_revenue, "money"],
      ["Vendas", overviewCurrent.sales_count ?? summary.count, "number"],
      ["Ticket médio", overviewCurrent.ticket_average ?? summary.ticket_average, "money"],
      ["Total recebido", overviewCurrent.total_received ?? summary.total_received, "money"],
      ["Descontos", overviewCurrent.discounts ?? summary.total_discount, "money"],
      ["Taxa de serviço", overviewCurrent.service_fee ?? summary.service_fee, "money"],
      ["Cancelamentos", overviewCurrent.cancellations ?? (summary.cancellations as Record<string, unknown> | undefined)?.value, "money"],
      ...(overviewCurrent.consumptions_courtesies !== undefined ? [["Consumação / cortesias", overviewCurrent.consumptions_courtesies, "money"] as [string, unknown, "money"]] : []),
      ...(overviewCurrent.estimated_result !== undefined ? [["Resultado estimado", overviewCurrent.estimated_result, "money"] as [string, unknown, "money"]] : []),
      ...(overviewCurrent.estimated_margin !== undefined ? [["Margem estimada", overviewCurrent.estimated_margin, "percent"] as [string, unknown, "percent"]] : []),
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
        summary.sales_revenue ?? sumReportMoney(productRows.map((row) => row.revenue)),
        "money",
      ],
      [
        "Unidades vendidas",
        summary.quantity ?? (sumInventoryDecimals(productRows.map((row) => row.quantity)) || "0"),
        "quantity",
      ],
      ["Produtos vendidos", summary.product_count ?? productRows.length, "number"],
      ["Categorias", summary.category_count ?? rows(summary.category_ranking).length, "number"],
      ...(canViewCosts && summary.cost !== undefined
        ? [["Custo histórico", summary.cost, "money"] as [string, unknown, "money"]]
        : []),
      ...(canViewCosts && summary.margin !== undefined
        ? [["Margem", summary.margin, "money"] as [string, unknown, "money"]]
        : []),
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
      ["Total recebido", summary.total_received, "money"],
      ["Pagamentos", summary.payment_count, "number"],
      ["Ticket médio recebido", summary.ticket_average_received, "money"],
      ["Dinheiro", receiptAmount("cash"), "money"],
      ["PIX", receiptAmount("pix"), "money"],
      ["Cartão", receiptAmount("credit_card", "debit_card", "card"), "money"],
      ["Outros", sumReportMoney(receiptMethods.filter((row) => !knownReceiptCodes.includes(String(row.code))).map((row) => row.applied_total)), "money"],
      ["Troco total", summary.change_total, "money"],
      ["Estornos", summary.reversals, "money"],
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
      ...(canViewCommission && summary.commission !== undefined
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
      ["Desconto total", summary.total_discount, "money"],
      ["Desconto médio", summary.discount_average, "money"],
      ["Desconto na conta", summary.account_discount, "money"],
      ["Desconto por item", summary.item_discount, "money"],
      ["Promoções", summary.promotion_discount, "money"],
      ["Taxas removidas", summary.service_fee_waiver_count, "number"],
    ],
    consumptions: [
      ["Valor de referência", summary.reference, "money"],
      ["Valor cobrado", summary.charged, "money"],
      ["Benefício concedido", summary.benefit, "money"],
      ["Operações", summary.count, "number"],
      ...(canViewCosts && summary.historical_cost !== undefined
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
      ["Sessões abertas", summary.opened_count, "number"],
      ["Sessões fechadas", summary.closed_count, "number"],
      ["Diferença total", summary.difference, "money"],
      ["Sangrias", summary.withdrawals, "money"],
      ["Entradas manuais", summary.manual_entries, "money"],
    ],
    withdrawals: [
      ["Total de sangrias", summary.amount, "money"],
      ["Movimentos", summary.count, "number"],
    ],
    "stock-consumption": [
      ["Consumo bruto · total equivalente", summary.gross_quantity, "quantity"],
      ["Devoluções · total equivalente", summary.returned_quantity, "quantity"],
      ["Consumo líquido · total equivalente", summary.net_quantity, "quantity"],
      ...(canViewCosts && summary.estimated_cost !== undefined
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
    "inventory-movements": [
      ["Movimentações", summary.count, "number"],
      ["Entradas", summary.entries, "quantity"],
      ["Saídas", summary.exits, "quantity"],
      ["Saldo dos movimentos", summary.equivalent_quantity, "quantity"],
      ...(canViewCosts && summary.historical_cost_impact !== undefined ? [["Impacto em custo", summary.historical_cost_impact, "money"] as [string, unknown, "money"]] : []),
    ],
    cancellations: [
      ["Vendas canceladas", summary.sale_cancellation_count, "number"],
      ["Valor total cancelado", summary.financial_impact, "money"],
      ["% do faturamento cancelado", summary.cancellation_percentage, "percent"],
      ["Itens cancelados em comandas", summary.item_cancellation_count, "number"],
      ["Pagamentos estornados", summary.payment_reversal_count, "number"],
    ],
    result: [
      ["Total recebido", summary.total_received, "money"],
      ...(canViewCosts && canViewCommission
        ? [
            ["Custos e despesas", summary.costs_and_expenses, "money"],
            ["Resultado estimado", firstValue(summary, "result", "estimated_result"), "money"],
          ] as Array<[string, unknown, "money"]>
        : []),
      ...(canViewCosts &&
      canViewCommission &&
      summary.margin !== null &&
      summary.margin !== undefined
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
    <>
      <div className="divide-y divide-subtle md:hidden">
        {data.results.map((row) => {
          const seller = row.seller as { name?: string } | null;
          const operator = row.operator as { name?: string } | null;
          return (
            <article key={`mobile:${String(row.operation_key)}`} className="space-y-3 p-4 text-xs">
              <div className="flex items-start justify-between gap-3">
                <span><strong className="block text-sm">{String(row.sale_number)}</strong><small className="text-muted">{formatDate(String(row.event_at || row.created_at))}</small></span>
                <StatusBadge value={row.status} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <span><small className="block text-muted">Atendente</small>{seller?.name || "-"}</span>
                <span><small className="block text-muted">Operador</small>{operator?.name || "-"}</span>
                <span><small className="block text-muted">Desconto</small>{formatBRL(sumReportMoney([row.item_discount_total, row.discount, row.promotion_discount_total]))}</span>
                <span><small className="block text-muted">Total recebido</small><strong>{formatBRL(String(row.total_received || row.total || "0"))}</strong></span>
              </div>
            </article>
          );
        })}
      </div>
      <div className="table-wrap hidden md:block">
      <table className="data-table min-w-260">
        <thead>
          <tr>
            <th>Operação</th>
            <th>{kind === "cancellations" ? "Cancelada em" : "Data"}</th>
            {kind === "sales" && <th>Cliente</th>}
            <th>Atendente</th>
            <th>Operador</th>
            {kind === "sales" && <th>Caixa</th>}
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
            const customer = row.customer as { name?: string } | null;
            const cashSession = row.cash_session as { register?: { name?: string } } | null;
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
                {kind === "sales" && <td>{customer?.name || "-"}</td>}
                <td>{kind === "consumptions" ? beneficiary?.name || "-" : seller?.name || "-"}</td>
                <td>{operator?.name || "-"}</td>
                {kind === "sales" && <td>{cashSession?.register?.name || "-"}</td>}
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
                    <td>{formatBRL(String(row.total_received || "0"))}</td>
                  </>
                ) : kind === "cancellations" ? (
                  <>
                    <td>{formatBRL(String(row.sales_revenue || "0"))}</td>
                    <td>{formatBRL(String(row.service_fee_amount || "0"))}</td>
                    <td>{formatBRL(String(row.total_received || "0"))}</td>
                  </>
                ) : kind === "sales" ? (
                  <td>
                    <strong>{formatBRL(String(row.total_received || row.total || "0"))}</strong>
                    <small className="block text-muted">Subtotal {formatBRL(String(row.subtotal || "0"))} · desconto {formatBRL(sumReportMoney([row.item_discount_total, row.discount, row.promotion_discount_total]))} · taxa {formatBRL(String(row.service_fee_amount || "0"))} · pago {formatBRL(String(row.payment_total || "0"))}</small>
                  </td>
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
    </>
  );
}

function SalesItemsTable({ data, canViewCosts }: { data: ReportResponse<Record<string, unknown>>; canViewCosts: boolean }) {
  const items = data.results.flatMap((sale) =>
    rows(sale.items).map((item) => ({ sale, item })),
  );
  if (!items.length)
    return <EmptyState title="Sem itens" description="Nenhum item encontrado nas vendas desta página." />;
  return (
    <div className="table-wrap">
      <table className="data-table min-w-300">
        <thead><tr><th>Venda</th><th>Produto</th><th>Categoria histórica</th><th>Quantidade</th><th>Preço base</th><th>Modificadores</th><th>Promoção</th><th>Desconto do item</th><th>Subtotal</th><th>Total</th>{canViewCosts && <><th>Custo unitário</th><th>Custo total</th><th>Margem</th><th>Margem %</th></>}</tr></thead>
        <tbody>{items.map(({ sale, item }) => <tr key={`${String(sale.operation_key)}:${String(item.id)}`}>
          <td><strong>{String(sale.sale_number)}</strong><small className="block text-muted">{formatDate(String(sale.event_at || sale.created_at))}</small></td>
          <td><strong>{String(item.product_name || "-")}</strong><small className="block text-muted">{String(item.internal_code || "")}</small></td>
          <td>{String((item.category as Record<string, unknown> | undefined)?.name || "Sem categoria")}</td>
          <td>{formatQuantity(String(item.quantity || "0"))} {String(item.unit || "").toUpperCase()}</td>
          <td>{formatBRL(String(item.base_unit_price || item.unit_price || "0"))}</td>
          <td>{rows(item.modifier_snapshot).length ? rows(item.modifier_snapshot).map((modifier) => `${String(modifier.option_name)} × ${formatQuantity(String(modifier.selected_quantity || "0"))}`).join(", ") : "-"}</td>
          <td>{item.promotion_name ? <span>{String(item.promotion_name)}<small className="block text-muted">{formatBRL(String(item.promotion_benefit || "0"))}</small></span> : "-"}</td>
          <td>{formatBRL(String(item.manual_discount || "0"))}</td>
          <td>{formatBRL(String(item.subtotal || "0"))}</td>
          <td><strong>{formatBRL(String(item.net_subtotal || "0"))}</strong></td>
          {canViewCosts && <><td>{formatBRL(String(item.unit_cost || "0"))}</td><td>{formatBRL(String(item.cost_total || "0"))}</td><td>{formatBRL(String(item.margin_amount || "0"))}</td><td>{formatPercent(item.margin_percentage)}</td></>}
        </tr>)}</tbody>
      </table>
    </div>
  );
}

function SalesPaymentsTable({ data }: { data: ReportResponse<Record<string, unknown>> }) {
  const payments = data.results.flatMap((sale) =>
    rows(sale.payments).map((payment, index) => ({ sale, payment, index })),
  );
  if (!payments.length)
    return <EmptyState title="Sem pagamentos" description="Nenhum pagamento encontrado nas vendas desta página." />;
  return (
    <div className="table-wrap">
      <table className="data-table min-w-160">
        <thead><tr><th>Venda</th><th>Data/hora</th><th>Forma</th><th>Valor aplicado</th><th>Valor recebido</th><th>Troco</th><th>Origem</th><th>Operador</th><th>Status</th></tr></thead>
        <tbody>{payments.map(({ sale, payment, index }) => {
          const operator = sale.operator as { name?: string } | null;
          return <tr key={`${String(sale.operation_key)}:${String(payment.payment_method_code)}:${index}`}>
            <td><strong>{String(sale.sale_number)}</strong></td>
            <td>{formatDate(String(payment.occurred_at || sale.event_at || sale.created_at))}</td>
            <td>{String(payment.payment_method_name || payment.payment_method_code || "-")}</td>
            <td><strong>{formatBRL(String(payment.amount || "0"))}</strong></td>
            <td>{formatBRL(String(payment.received_amount || payment.amount || "0"))}</td>
            <td>{formatBRL(String(payment.change_amount || "0"))}</td>
            <td>{domainLabel(payment.origin)}</td>
            <td>{String((payment.operator as Record<string, unknown> | null)?.name || operator?.name || "-")}</td>
            <td><StatusBadge value={payment.status || sale.status} /></td>
          </tr>;
        })}</tbody>
      </table>
    </div>
  );
}

function ReceiptEventsTable({ data }: { data: ReportResponse<Record<string, unknown>> }) {
  if (!data.results.length)
    return <EmptyState title="Sem eventos" description="Nenhum recebimento ou estorno ocorreu no período." />;
  return (
    <div className="table-wrap">
      <table className="data-table min-w-260">
        <thead><tr><th>Data/hora</th><th>Venda / comanda</th><th>Forma</th><th>Aplicado</th><th>Recebido</th><th>Troco</th><th>Origem</th><th>Operador</th><th>Caixa</th><th>Status</th><th>Motivo do estorno</th></tr></thead>
        <tbody>{data.results.map((row) => {
          const sale = row.sale as Record<string, unknown> | null;
          const command = row.command as Record<string, unknown> | null;
          const method = row.payment_method as Record<string, unknown>;
          const operator = row.operator as Record<string, unknown>;
          const register = row.cash_register as Record<string, unknown> | null;
          return <tr key={String(row.event_id)}>
            <td className="whitespace-nowrap">{formatDate(String(row.occurred_at))}</td>
            <td><strong>{sale?.number ? `Venda ${String(sale.number)}` : command?.number ? `Comanda ${String(command.number)}` : "-"}</strong><small className="block text-muted">{String(row.event_id)}</small></td>
            <td>{String(method?.name || method?.code || "-")}</td>
            <td><strong>{formatBRL(String(row.applied_amount || "0"))}</strong></td>
            <td>{formatBRL(String(row.received_amount || "0"))}</td>
            <td>{formatBRL(String(row.change_amount || "0"))}</td>
            <td>{domainLabel(row.origin)}</td>
            <td>{String(operator?.name || "-")}</td>
            <td>{String(register?.name || "-")}</td>
            <td><StatusBadge value={row.status} /></td>
            <td className="max-w-64">{String(row.reversal_reason || "-")}</td>
          </tr>;
        })}</tbody>
      </table>
    </div>
  );
}

function ReceiptDistributionTable({ summary }: { summary: Record<string, unknown> }) {
  const methods = rows(summary.payment_totals);
  if (!methods.length) return <EmptyState title="Sem recebimentos" description="Nenhuma forma de pagamento foi utilizada no período." />;
  return <div className="table-wrap"><table className="data-table"><thead><tr><th>Forma</th><th>Quantidade</th><th>Valor aplicado líquido</th><th>Valor recebido</th><th>Troco</th><th>Estornos</th><th>%</th></tr></thead><tbody>{methods.map((row) => <tr key={String(row.code)}><td><strong>{String(row.name || row.code)}</strong></td><td>{String(row.count || 0)}</td><td>{formatBRL(String(row.applied_total || "0"))}</td><td>{formatBRL(String(row.received_total || "0"))}</td><td>{formatBRL(String(row.change_total || "0"))}</td><td className="text-danger">{formatBRL(String(row.reversals || "0"))}</td><td>{formatPercent(row.percentage)}</td></tr>)}</tbody></table></div>;
}

function CancellationEventsTable({ data }: { data: ReportResponse<Record<string, unknown>> }) {
  if (!data.results.length)
    return <EmptyState title="Sem cancelamentos" description="Nenhum cancelamento ou estorno ocorreu no período." />;
  return (
    <div className="table-wrap">
      <table className="data-table min-w-260">
        <thead><tr><th>Data/hora</th><th>Tipo</th><th>Operação</th><th>Produto</th><th>Quantidade</th><th>Responsável</th><th>Motivo</th><th>Impacto financeiro</th><th>Impacto no estoque</th></tr></thead>
        <tbody>{data.results.map((row) => {
          const product = row.product as Record<string, unknown> | null;
          const actor = row.cancellation_actor as Record<string, unknown> | null;
          return <tr key={String(row.event_id)}>
            <td className="whitespace-nowrap">{formatDate(String(row.cancelled_at))}</td>
            <td>{domainLabel(row.event_type)}</td>
            <td><strong>{String(row.operation_number || row.operation_id || "-")}</strong><small className="block text-muted">{domainLabel(row.operation_type)}</small></td>
            <td>{String(product?.name || "-")}</td>
            <td>{row.quantity == null ? "-" : formatQuantity(String(row.quantity))}</td>
            <td>{String(actor?.name || "-")}</td>
            <td className="max-w-72">{String(row.reason || "Não informado")}</td>
            <td className="text-danger">{formatBRL(String(row.financial_impact || "0"))}</td>
            <td>{String(row.stock_impact || "-")}</td>
          </tr>;
        })}</tbody>
      </table>
    </div>
  );
}

function DiscountEventsTable({ data }: { data: ReportResponse<Record<string, unknown>> }) {
  const events = data.results.flatMap((sale) => {
    const operator = sale.operator as Record<string, unknown> | null;
    const seller = sale.seller as Record<string, unknown> | null;
    const saleApprover = sale.discount_approved_by as Record<string, unknown> | null;
    const base = { sale, operator, seller };
    const itemEvents = rows(sale.items).flatMap((item) => {
      const approver = item.discount_approved_by as Record<string, unknown> | null;
      const itemRows: Array<Record<string, unknown>> = [];
      if (hasDelta(item.manual_discount)) itemRows.push({ ...base, id: `item:${String(item.id)}`, type: "item", value: item.manual_discount, approver, product: item.product_name });
      if (hasDelta(item.promotion_benefit)) itemRows.push({ ...base, id: `promotion:${String(item.id)}`, type: "promotion", value: item.promotion_benefit, approver: null, product: item.product_name });
      return itemRows;
    });
    if (hasDelta(sale.discount)) itemEvents.push({ ...base, id: `account:${String(sale.id)}`, type: "account", value: sale.discount, approver: saleApprover, product: null });
    if (sale.service_fee_waived) itemEvents.push({ ...base, id: `fee:${String(sale.id)}`, type: "service_fee_waiver", value: sale.service_fee_waived_value, approver: sale.service_fee_waived_by, product: null });
    return itemEvents;
  });
  if (!events.length) return <EmptyState title="Sem descontos" description="Nenhum desconto ou retirada de taxa foi encontrado nesta página." />;
  return <div className="table-wrap"><table className="data-table min-w-220"><thead><tr><th>Venda</th><th>Tipo</th><th>Produto</th><th>Valor</th><th>Aplicado por</th><th>Aprovado por</th><th>Atendente</th><th>Data/hora</th></tr></thead><tbody>{events.map((event) => {
    const sale = event.sale as Record<string, unknown>;
    const operator = event.operator as Record<string, unknown> | null;
    const seller = event.seller as Record<string, unknown> | null;
    const approver = event.approver as Record<string, unknown> | null;
    return <tr key={String(event.id)}><td><strong>{String(sale.sale_number)}</strong></td><td>{domainLabel(event.type)}</td><td>{String(event.product || "-")}</td><td>{formatBRL(String(event.value || "0"))}</td><td>{String(operator?.name || "-")}</td><td>{String(approver?.name || "Automático")}</td><td>{String(seller?.name || "-")}</td><td>{formatDate(String(sale.event_at || sale.created_at))}</td></tr>;
  })}</tbody></table></div>;
}

function ConsumptionDetailsTable({ data, canViewCosts }: { data: ReportResponse<Record<string, unknown>>; canViewCosts: boolean }) {
  const items = data.results.flatMap((sale) => rows(sale.items).map((item) => ({ sale, item })));
  if (!items.length) return <EmptyState title="Sem itens" description="Nenhuma consumação foi encontrada nesta página." />;
  return <div className="table-wrap"><table className="data-table min-w-260"><thead><tr><th>Data/hora</th><th>Beneficiário</th><th>Produto</th><th>Categoria</th><th>Quantidade</th><th>Valor comercial</th><th>Valor cobrado</th><th>Subsídio / cortesia</th>{canViewCosts && <th>Custo histórico</th>}<th>Responsável</th></tr></thead><tbody>{items.map(({ sale, item }) => { const beneficiary = sale.beneficiary as Record<string, unknown> | null; const operator = sale.operator as Record<string, unknown> | null; const category = item.category as Record<string, unknown> | null; return <tr key={`consumption:${String(sale.id)}:${String(item.id)}`}><td>{formatDate(String(sale.event_at || sale.created_at))}</td><td>{String(beneficiary?.name || "-")}</td><td><strong>{String(item.product_name || "-")}</strong></td><td>{String(category?.name || "Sem categoria")}</td><td>{formatQuantity(String(item.quantity || "0"))}</td><td>{formatBRL(String(item.commercial_value || item.subtotal || "0"))}</td><td>{formatBRL(String(item.charged_value || "0"))}</td><td>{formatBRL(String(item.subsidy_value || "0"))}</td>{canViewCosts && <td>{formatBRL(String(item.cost_total || "0"))}</td>}<td>{String(operator?.name || "-")}</td></tr>; })}</tbody></table></div>;
}

function CommissionDetailsTable({ data }: { data: ReportResponse<Record<string, unknown>> }) {
  const items = data.results.flatMap((sale) => rows(sale.items).filter((item) => hasDelta(item.commission_amount)).map((item) => ({ sale, item })));
  if (!items.length) return <EmptyState title="Sem comissões detalhadas" description="Nenhum item elegível foi encontrado nesta página." />;
  return <div className="table-wrap"><table className="data-table min-w-220"><thead><tr><th>Venda</th><th>Atendente</th><th>Produto</th><th>Quantidade</th><th>Base</th><th>Percentual</th><th>Comissão</th></tr></thead><tbody>{items.map(({ sale, item }) => { const seller = sale.seller as Record<string, unknown> | null; return <tr key={`commission:${String(sale.id)}:${String(item.id)}`}><td><strong>{String(sale.sale_number)}</strong><small className="block text-muted">{formatDate(String(sale.created_at))}</small></td><td>{String(seller?.name || "-")}</td><td>{String(item.product_name || "-")}</td><td>{formatQuantity(String(item.quantity || "0"))}</td><td>{formatBRL(String(item.net_subtotal || "0"))}</td><td>{formatPercent(sale.commission_rate)}</td><td><strong>{formatBRL(String(item.commission_amount || "0"))}</strong></td></tr>; })}</tbody></table></div>;
}

function ProductCommercialBreakdown({
  summary,
  kind,
}: {
  summary: Record<string, unknown>;
  kind: "modifiers" | "promotions";
}) {
  const list = rows(summary[kind === "modifiers" ? "modifier_ranking" : "promotion_ranking"]);
  if (!list.length)
    return <EmptyState title="Sem dados" description={`Nenhuma ocorrência de ${kind === "modifiers" ? "modificador" : "promoção"} no período.`} />;
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>{kind === "modifiers" ? <tr><th>Modificador</th><th>Quantidade</th><th>Produtos</th><th>Receita adicional</th><th>Ticket médio</th></tr> : <tr><th>Promoção</th><th>Usos</th><th>Desconto concedido</th><th>Receita líquida associada</th></tr>}</thead>
        <tbody>{list.map((row) => kind === "modifiers" ? <tr key={`modifier:${String(row.option_id || row.option_name)}`}><td><strong>{String(row.option_name)}</strong></td><td>{formatQuantity(String(row.quantity || "0"))}</td><td>{String(row.product_count || 0)}</td><td>{formatBRL(String(row.additional_revenue || "0"))}</td><td>{formatBRL(String(row.ticket_average || "0"))}</td></tr> : <tr key={`promotion:${String(row.promotion_id)}`}><td><strong>{String(row.promotion_name)}</strong></td><td>{String(row.uses || 0)}</td><td>{formatBRL(String(row.discount || "0"))}</td><td>{formatBRL(String(row.net_revenue || "0"))}</td></tr>)}</tbody>
      </table>
    </div>
  );
}

function RankingTable({
  kind,
  summary,
  canViewCosts = false,
  canViewCommission = false,
  dataRows,
}: {
  kind: ReportKind;
  summary: Record<string, unknown>;
  canViewCosts?: boolean;
  canViewCommission?: boolean;
  dataRows?: Array<Record<string, unknown>>;
}) {
  const key =
    kind === "products"
      ? "product_ranking"
      : kind === "receipts"
        ? "payment_totals"
        : kind === "operators"
          ? "operator_groups"
          : "seller_groups";
  const list = dataRows || rows(summary[key]);
  if (!list.length)
    return (
      <EmptyState
        title="Sem dados"
        description="Nenhum resultado no período selecionado."
      />
    );
  const isTeam = ["operators", "sellers", "commissions"].includes(kind);
  const showCommission =
    canViewCommission && isTeam && list.some((row) => row.commission !== undefined);
  const showProductCosts =
    canViewCosts &&
    kind === "products" &&
    list.some((row) => row.cost !== undefined || row.margin !== undefined);
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
            {kind === "products" && <><th>Vendas</th><th>Descontos</th><th>Ticket médio</th></>}
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
            {kind === "sellers" && <><th>Itens vendidos</th><th>Descontos</th><th>Taxas removidas</th></>}
            {kind === "operators" && <><th>Caixas operados</th><th>Descontos autorizados</th><th>Cancelados por</th><th>Estornos</th><th>Diferença de caixa</th></>}
            {kind === "commissions" && <><th>Base de cálculo</th><th>Percentual efetivo</th></>}
            {showCommission && <th>Comissão histórica</th>}
            {showProductCosts && <><th>Custo histórico</th><th>Margem</th><th>Margem %</th></>}
          </tr>
        </thead>
        <tbody>
          {list.map((row) => {
            const user = row.user as { id?: number; name?: string } | undefined;
            const label = row.product_name || row.name || user?.name || "-";
            const amount = row.revenue || row.sales_revenue || "0";
            return (
              <tr
                key={String(
                  row.product_id
                    ? `product:${row.product_id}`
                    : row.code
                      ? `payment:${row.code}`
                      : `user:${user?.id}`,
                )}
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
                {kind === "products" && <><td>{String(row.sale_count || 0)}</td><td>{formatBRL(String(row.discounts || "0"))}</td><td>{formatBRL(String(row.ticket_average || "0"))}</td></>}
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
                {kind === "sellers" && <><td>{formatQuantity(String(row.item_quantity || "0"))}</td><td>{formatBRL(String(row.discounts || "0"))}</td><td>{String(row.service_fee_waiver_count || 0)}</td></>}
                {kind === "operators" && <><td>{String(row.cash_session_count || 0)}</td><td>{String(row.authorized_discount_count || 0)}</td><td>{String(row.actor_cancellation_count || 0)}</td><td>{String(row.payment_reversal_count || 0)}</td><td>{formatBRL(String(row.cash_difference || "0"))}</td></>}
                {kind === "commissions" && <><td>{formatBRL(String(row.commission_base || "0"))}</td><td>{formatPercent(row.commission_rate)}</td></>}
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
                {showProductCosts && <>
                  <td>{formatBRL(String(row.cost || "0"))}</td>
                  <td>{formatBRL(String(row.margin || "0"))}</td>
                  <td>{formatPercent(row.margin_percent)}</td>
                </>}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function CategoryRanking({
  summary,
  canViewCosts = false,
}: {
  summary: Record<string, unknown>;
  canViewCosts?: boolean;
}) {
  const categories = rows(summary.category_ranking);
  const showCosts = canViewCosts && categories.some((row) => row.cost !== undefined);
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
                {showCosts && <><th>Custo histórico</th><th>Margem</th></>}
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
                   {showCosts && <><td>{formatBRL(String(row.cost || "0"))}</td><td>{formatBRL(String(row.margin || "0"))}</td></>}
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
                  <tr
                    key={`category:${String(row.category_id || "unassigned")}`}
                  >
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
    [
      "Por produto",
      rows(summary.product_groups),
      (row) => String(row.product_name || "Produto não informado"),
    ],
    [
      "Por categoria",
      rows(summary.category_groups),
      (row) => String(row.category_name || "Sem categoria"),
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
                    <th>{title === "Por produto" || title === "Por categoria" ? "Quantidade" : "Operações"}</th>
                    <th>Referência</th>
                    <th>Cobrado</th>
                    <th>Benefício</th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((row) => (
                    <tr
                      key={`${title}:${String((row.beneficiary as { id?: number } | undefined)?.id || row.user_type || row.product_id || row.category_id || "unassigned")}`}
                    >
                      <td>
                        <strong>{label(row)}</strong>
                      </td>
                      <td>{row.count === undefined ? formatQuantity(String(row.quantity || "0")) : String(row.count)}</td>
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
  const operators = rows(summary.by_operator);
  const beneficiaries = rows(summary.by_beneficiary);
  if (!categories.length && !operators.length && !beneficiaries.length) return null;
  return (
    <div className="grid gap-5 xl:grid-cols-3"><section className="card overflow-hidden">
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
    </section>{[["Por operador", operators, "operator"], ["Por beneficiário", beneficiaries, "beneficiary"]].map(([title, list, key]) => <section key={String(title)} className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">{String(title)}</h2></div>{(list as Array<Record<string, unknown>>).length ? <div className="divide-y divide-subtle">{(list as Array<Record<string, unknown>>).map((row) => { const user = row[String(key)] as Record<string, unknown> | null; return <div key={`${String(key)}:${String(user?.id || "none")}`} className="flex items-center justify-between gap-4 px-5 py-3 text-sm"><span>{String(user?.name || "Não informado")}<small className="block text-muted">{String(row.count || 0)} movimentos</small></span><strong>{formatBRL(String(row.amount || "0"))}</strong></div>; })}</div> : <EmptyState title="Sem agrupamento" description="Nenhum movimento no período." />}</section>)}</div>
  );
}

function CashSummarySections({
  summary,
  canViewCommission,
}: {
  summary: Record<string, unknown>;
  canViewCommission: boolean;
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
              <strong>{formatBRL(String(summary.sales_revenue || "0"))}</strong>
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
                    sumReportMoney([
                      summary.sales_revenue,
                      summary.service_fee,
                    ]),
                  ),
                )}
              </strong>
            </p>
            {canViewCommission && summary.commission !== undefined && (
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
                      ? sumReportMoney(
                          rows(summary.payment_totals).map(
                            (row) => row.gross_received,
                          ),
                        )
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
              <strong>{formatBRL(String(summary.payment_total || "0"))}</strong>
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
    <>
      <div className="divide-y divide-subtle md:hidden">
        {data.results.map((row) => {
          const register = row.register as { name?: string };
          const operator = row.operator as { name?: string };
          return <article key={`mobile-cash:${String(row.id)}`} className="space-y-3 p-4 text-xs">
            <div className="flex items-start justify-between gap-3"><span><strong className="block text-sm">{register.name} #{String(row.id)}</strong><small className="text-muted">{operator.name || "-"}</small></span><StatusBadge value={row.status} /></div>
            <p>{formatDate(String(row.opened_at))}{row.closed_at ? ` até ${formatDate(String(row.closed_at))}` : " · Em andamento"}</p>
            <div className="grid grid-cols-2 gap-3"><span><small className="block text-muted">Esperado</small><strong>{formatBRL(String(row.expected || "0"))}</strong></span><span><small className="block text-muted">Informado</small>{row.informed == null ? "-" : formatBRL(String(row.informed))}</span><span><small className="block text-muted">Entradas</small>{formatBRL(String(row.manual_entries || "0"))}</span><span><small className="block text-muted">Sangrias</small>{formatBRL(String(row.withdrawals || "0"))}</span></div>
          </article>;
        })}
      </div>
      <div className="table-wrap hidden md:block">
      <table className="data-table min-w-320">
        <thead>
          <tr>
            <th>Sessão</th>
            <th>Operador</th>
            <th>Aberto por</th>
            <th>Fechado por</th>
            <th>Status</th>
            <th>Período</th>
            <th>Duração</th>
            <th>Fundo</th>
            <th>Entradas</th>
            <th>Sangrias</th>
            <th>Esperado</th>
            <th>Informado</th>
            <th>Diferença</th>
          </tr>
        </thead>
        <tbody>
          {data.results.map((row) => {
            const register = row.register as { name?: string };
            const operator = row.operator as { name?: string };
            const openedBy = row.opened_by as { name?: string } | null;
            const closedBy = row.closed_by as { name?: string } | null;
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
                <td>{operator.name || "-"}</td>
                <td>{openedBy?.name || "-"}</td>
                <td>{closedBy?.name || "-"}</td>
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
                <td>{Math.floor(Number(row.duration_seconds || 0) / 3600)}h {Math.floor((Number(row.duration_seconds || 0) % 3600) / 60)}min</td>
                <td>{formatBRL(String(row.opening || "0"))}</td>
                <td>{formatBRL(String(row.manual_entries || "0"))}</td>
                <td>{formatBRL(String(row.withdrawals || "0"))}</td>
                <td><strong>{formatBRL(String(row.expected || "0"))}</strong><small className="block text-muted">Vendas {String(sales.count || 0)} · Consumações {String(consumptions.count || 0)}</small></td>
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
    </>
  );
}

function StockConsumption({
  data,
  canViewCosts,
}: {
  data: ReportResponse<Record<string, unknown>>;
  canViewCosts: boolean;
}) {
  const products = rows(data.summary.products);
  const showCost = canViewCosts && products.some((row) => row.estimated_cost !== undefined);
  const contentByUnit = Object.entries(
    (data.summary.content_by_unit || {}) as Record<
      string,
      Record<string, unknown>
    >,
  );
  return (
    <div className="space-y-5">
      {contentByUnit.length > 0 && (
        <section className="card p-5">
          <h2 className="text-sm font-bold">Conteúdo exato rastreado</h2>
          <p className="mt-1 text-[11px] text-muted">
            Parcela canônica rastreada dentro dos totais equivalentes combinados
            do relatório.
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            {contentByUnit.flatMap(([unit, values]) =>
              (
                [
                  ["Consumo bruto", values.gross_content],
                  ["Devoluções", values.returned_content],
                  ["Consumo líquido", values.net_content],
                ] as Array<[string, unknown]>
              ).map(([label, value]) => (
                <div
                  key={`${unit}-${label}`}
                  className="rounded-lg bg-surface-muted p-3"
                >
                  <small className="block text-[10px] font-semibold text-muted">
                    {label} rastreado
                  </small>
                  <strong className="mt-1 block text-sm">
                    {formatQuantity(String(value || "0"))}{" "}
                    {contentUnitLabel(unit)}
                  </strong>
                </div>
              )),
            )}
          </div>
        </section>
      )}
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
                        <ConsumptionQuantity
                          row={row}
                          quantityKey="gross_quantity"
                          prefix="gross"
                        />
                      </td>
                      <td>
                        <ConsumptionQuantity
                          row={row}
                          quantityKey="returned_quantity"
                          prefix="returned"
                        />
                      </td>
                      <td>
                        <ConsumptionQuantity
                          row={row}
                          quantityKey="net_quantity"
                          prefix="net"
                        />
                      </td>
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
                      <td>
                        <ConsumptionQuantity
                          row={row}
                          quantityKey="equivalent_quantity"
                        />
                      </td>
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

function InventoryMovementsTable({
  data,
  canViewCosts = false,
}: {
  data: ReportResponse<Record<string, unknown>>;
  canViewCosts?: boolean;
}) {
  if (!data.results.length)
    return <EmptyState title="Sem movimentações" description="Nenhuma movimentação encontrada no período." />;
  return (
    <>
      <div className="divide-y divide-subtle md:hidden">
        {data.results.map((row) => {
          const product = row.product as Record<string, unknown>;
          const user = row.user as Record<string, unknown>;
          return <article key={`mobile-movement:${String(row.id)}`} className="space-y-3 p-4 text-xs">
            <div className="flex items-start justify-between gap-3"><span><strong className="block text-sm">{String(product.name || "-")}</strong><small className="text-muted">{formatDate(String(row.created_at))}</small></span><span className="rounded-full bg-surface-muted px-2 py-1 font-bold">{domainLabel(row.movement_type)}</span></div>
            <div className="grid grid-cols-2 gap-3"><span><small className="block text-muted">Movimento</small><strong>{formatQuantity(String(row.quantity || "0"))}</strong></span><span><small className="block text-muted">Saldo</small>{formatQuantity(String(row.previous_quantity || "0"))} → {formatQuantity(String(row.final_quantity || "0"))}</span><span><small className="block text-muted">Responsável</small>{String(user.name || "-")}</span><span><small className="block text-muted">Categoria</small>{String((product.category as Record<string, unknown> | undefined)?.name || "-")}</span></div>
            {Boolean(row.reason) && <p className="text-muted">{String(row.reason)}</p>}
          </article>;
        })}
      </div>
      <div className="table-wrap hidden md:block">
        <table className="data-table min-w-300">
          <thead><tr><th>Data/hora</th><th>Produto</th><th>Categoria</th><th>Tipo</th><th>Origem</th><th>Saldo anterior</th><th>Movimento</th><th>Saldo final</th><th>Unidade</th>{canViewCosts && <><th>Custo snapshot</th><th>Impacto em custo</th></>}<th>Responsável</th><th>Motivo</th><th>Referência</th></tr></thead>
          <tbody>{data.results.map((row) => {
            const product = row.product as Record<string, unknown>;
            const category = product.category as Record<string, unknown> | undefined;
            const user = row.user as Record<string, unknown>;
            const sale = row.sale as Record<string, unknown> | null;
            const origin = row.origin as Record<string, unknown> | null;
            return <tr key={`inventory-movement:${String(row.id)}`}>
              <td className="whitespace-nowrap">{formatDate(String(row.created_at))}</td>
              <td><strong>{String(product.name || "-")}</strong><small className="block text-muted">{String(product.internal_code || "")}</small></td>
              <td>{String(category?.name || "-")}</td>
              <td>{domainLabel(row.movement_type)}</td>
              <td>{String(origin?.label || domainLabel(row.domain_origin || row.nature))}</td>
              <td>{formatQuantity(String(row.previous_quantity || "0"))}</td>
              <td className="font-bold">{formatQuantity(String(row.quantity || "0"))}<small className="block text-muted">Equiv. {formatQuantity(String(row.equivalent_quantity || "0"))}</small></td>
              <td>{formatQuantity(String(row.final_quantity || "0"))}</td>
              <td>{String(row.unit || "-").toUpperCase()}</td>
              {canViewCosts && <><td>{row.unit_cost_snapshot == null ? "-" : formatBRL(String(row.unit_cost_snapshot))}</td><td>{row.cost_impact == null ? "-" : formatBRL(String(row.cost_impact))}</td></>}
              <td>{String(user.name || "-")}</td>
              <td className="max-w-64">{String(row.reason || "-")}</td>
              <td className="max-w-64 break-all font-mono text-xs">{sale?.number ? `Venda ${String(sale.number)}` : String(row.operation_reference || "-")}</td>
            </tr>;
          })}</tbody>
        </table>
      </div>
    </>
  );
}

function ResultStatement({
  summary,
  canViewCosts,
  canViewCommission,
}: {
  summary: Record<string, unknown>;
  canViewCosts: boolean;
  canViewCommission: boolean;
}) {
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
  const visibleCostDetails = costDetails.filter(([, key]) =>
    key === "commission"
      ? canViewCommission && summary[key] !== undefined
      : canViewCosts && summary[key] !== undefined,
  );
  return (
    <div className="p-5">
      <div className="mx-auto max-w-2xl space-y-1">
        {lines
          .filter(([, key]) => {
            if (["costs_and_expenses", "result"].includes(key))
              return canViewCosts && canViewCommission && summary[key] !== undefined;
            return summary[key] !== undefined;
          })
          .map(([label, key, strong]) => (
            <div
              key={key}
              className={`flex items-center justify-between gap-4 rounded-md px-4 py-3 ${strong ? "mt-2 bg-primary/10 text-dark" : "border-b border-slate-100"}`}
            >
              <span className={strong ? "font-bold" : "text-sm"}>{label}</span>
              <strong>{formatBRL(String(summary[key] || "0"))}</strong>
            </div>
          ))}
        {canViewCosts && canViewCommission && summary.margin !== undefined && summary.margin !== null && (
          <div className="flex justify-between px-4 py-3">
            <span className="text-sm">Margem sobre o Total recebido</span>
            <strong>{formatPercent(summary.margin)}</strong>
          </div>
        )}
        {visibleCostDetails.length > 0 && (
          <div className="mt-5 rounded-lg border border-subtle p-4">
            <h3 className="text-xs font-bold">
              Composição autorizada de custos e despesas
            </h3>
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

type TimeAnalysisRow = {
  date: string;
  count: number;
  sales_revenue: string;
};

function positiveMoney(value: unknown) {
  const cents = signedMoneyToCents(value);
  return cents !== null && cents > BigInt(0) ? cents : BigInt(0);
}

function chartPercent(value: bigint, total: bigint, minimum = 0) {
  if (value <= BigInt(0) || total <= BigInt(0)) return minimum;
  return Math.max(minimum, Number((value * BigInt(10_000)) / total) / 100);
}

function OverviewAnalytics({ summary }: { summary: Record<string, unknown> }) {
  const comparison = (summary.weekly_comparison || {
    current: [],
    previous: [],
  }) as { current: TimeAnalysisRow[]; previous: TimeAnalysisRow[] };
  const payments = rows(summary.payment_totals);
  const points = Array.from(
    { length: Math.max(comparison.current.length, comparison.previous.length) },
    (_, index) => ({
      current: comparison.current[index],
      previous: comparison.previous[index],
    }),
  );
  const comparisonMax = points.reduce((largest, point) => {
    const current = positiveMoney(point.current?.sales_revenue);
    const previous = positiveMoney(point.previous?.sales_revenue);
    return current > largest
      ? current
      : previous > largest
        ? previous
        : largest;
  }, BigInt(0));
  const currentRevenue = signedMoneyToCents(sumReportMoney(comparison.current.map((row) => row.sales_revenue))) || BigInt(0);
  const previousRevenue = signedMoneyToCents(sumReportMoney(comparison.previous.map((row) => row.sales_revenue))) || BigInt(0);
  const revenueDelta = currentRevenue - previousRevenue;
  const revenueDeltaPercent = previousRevenue === BigInt(0)
    ? null
    : Number((revenueDelta * BigInt(10_000)) / (previousRevenue < 0 ? -previousRevenue : previousRevenue)) / 100;
  const currentCount = comparison.current.reduce((total, row) => total + row.count, 0);
  const previousCount = comparison.previous.reduce((total, row) => total + row.count, 0);
  const periodComparison = (summary.period_comparison || {}) as Record<string, unknown>;
  const currentPeriod = (periodComparison.current || {}) as Record<string, unknown>;
  const previousPeriod = (periodComparison.previous || {}) as Record<string, unknown>;
  const deltas = (periodComparison.deltas || {}) as Record<string, Record<string, unknown>>;
  const comparisonMetrics: Array<[string, string, "money" | "number" | "percent"]> = [
    ["Faturamento bruto", "gross_revenue", "money"],
    ["Faturamento líquido", "net_revenue", "money"],
    ["Vendas", "sales_count", "number"],
    ["Ticket médio", "ticket_average", "money"],
    ["Total recebido", "total_received", "money"],
    ["Descontos", "discounts", "money"],
    ["Taxa de serviço", "service_fee", "money"],
    ["Cancelamentos", "cancellations", "money"],
    ["Consumação / cortesias", "consumptions_courtesies", "money"],
    ["Resultado estimado", "estimated_result", "money"],
    ["Margem estimada", "estimated_margin", "percent"],
  ].filter(([, key]) => currentPeriod[key] !== undefined) as Array<[string, string, "money" | "number" | "percent"]>;

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <section className="card overflow-hidden">
        <div className="card-header">
          <div>
            <h2 className="text-sm font-bold">Comparativo do período</h2>
            <p className="mt-1 text-[11px] text-muted">
              Faturamento atual e período anterior equivalente
            </p>
          </div>
        </div>
        {comparison.current.length || comparison.previous.length ? (
          <div className="p-5">
            <div className="mb-5 grid grid-cols-2 gap-3">
              <div className="rounded-lg bg-surface-muted p-3"><small className="text-muted">Variação de faturamento</small><strong className={`mt-1 block ${revenueDelta < 0 ? "text-danger" : "text-success-strong"}`}>{revenueDelta < 0 ? "" : "+"}{formatBRL(centsToDecimal(revenueDelta))}</strong>{revenueDeltaPercent !== null && <small className="text-muted">{revenueDeltaPercent > 0 ? "+" : ""}{formatPercent(revenueDeltaPercent)}</small>}</div>
              <div className="rounded-lg bg-surface-muted p-3"><small className="text-muted">Variação de vendas</small><strong className={`mt-1 block ${currentCount - previousCount < 0 ? "text-danger" : "text-success-strong"}`}>{currentCount - previousCount > 0 ? "+" : ""}{currentCount - previousCount}</strong></div>
            </div>
            {comparisonMax > BigInt(0) && <div className="overflow-x-auto">
            <div className="mb-4 flex gap-4 text-[10px] font-semibold text-muted">
              <span className="flex items-center gap-1.5">
                <i className="size-2.5 rounded-sm bg-chart-1" /> Atual
              </span>
              <span className="flex items-center gap-1.5">
                <i className="size-2.5 rounded-sm bg-chart-previous" /> Anterior
              </span>
            </div>
            <div className="flex h-52 min-w-full items-end gap-2">
              {points.map((point, index) => (
                <div
                  key={point.current?.date || point.previous?.date || index}
                  className="flex h-full min-w-12 flex-1 flex-col justify-end"
                >
                  <div className="flex h-42 items-end justify-center gap-1">
                    {[
                      ["Atual", point.current, "bg-chart-1"],
                      ["Anterior", point.previous, "bg-chart-previous"],
                    ].map(([label, row, tone]) => {
                      const item = row as TimeAnalysisRow | undefined;
                      return item ? (
                        <span
                          key={String(label)}
                          className={`w-3 rounded-t ${tone}`}
                          style={{
                            height: `${chartPercent(
                              positiveMoney(item.sales_revenue),
                              comparisonMax,
                              2,
                            )}%`,
                          }}
                          title={`${label}: ${formatBRL(item.sales_revenue)}`}
                        />
                      ) : (
                        <span key={String(label)} className="w-3" />
                      );
                    })}
                  </div>
                  <span className="mt-2 text-center text-[9px] text-muted">
                    {(point.current || point.previous)?.date.slice(8, 10)}/
                    {(point.current || point.previous)?.date.slice(5, 7)}
                  </span>
                </div>
              ))}
            </div>
            </div>}
          </div>
        ) : (
          <EmptyState
            title="Sem comparação"
            description="Os períodos não possuem faturamento."
          />
        )}
      </section>

      <section className="card overflow-hidden">
        <div className="card-header">
          <div>
            <h2 className="text-sm font-bold">Recebimentos por forma</h2>
            <p className="mt-1 text-[11px] text-muted">
              Distribuição dos pagamentos do período
            </p>
          </div>
        </div>
        {payments.length ? (
          <div className="divide-y divide-subtle">
            {payments.map((row) => <div key={String(row.code)} className="flex items-center justify-between gap-4 px-5 py-4 text-sm"><span>{String(row.name || row.code)}</span><strong>{formatBRL(String(row.amount || row.payment_total || "0"))}</strong></div>)}
          </div>
        ) : (
          <EmptyState
            title="Sem recebimentos"
            description="Nenhum pagamento no período selecionado."
          />
        )}
      </section>
      {comparisonMetrics.length > 0 && <section className="card overflow-hidden lg:col-span-2"><div className="card-header"><div><h2 className="text-sm font-bold">Indicadores contra o período anterior</h2><p className="mt-1 text-[11px] text-muted">Variação absoluta e percentual para o mesmo intervalo imediatamente anterior.</p></div></div><div className="table-wrap"><table className="data-table"><thead><tr><th>Indicador</th><th>Atual</th><th>Anterior</th><th>Variação</th><th>Variação %</th></tr></thead><tbody>{comparisonMetrics.map(([label, key, format]) => {
        const delta = deltas[key] || {};
        const display = (value: unknown) => format === "number" ? String(value ?? 0) : format === "percent" ? formatPercent(value) : formatBRL(String(value || "0"));
        return <tr key={key}><td><strong>{label}</strong></td><td>{display(currentPeriod[key])}</td><td>{display(previousPeriod[key])}</td><td className={delta.direction === "down" ? "text-danger" : delta.direction === "up" ? "text-success-strong" : ""}>{display(delta.amount)}</td><td>{delta.percentage == null ? "Sem base" : formatPercent(delta.percentage)}</td></tr>;
      })}</tbody></table></div></section>}
    </div>
  );
}

function ReportBody({
  kind,
  data,
  activeTab,
  canViewSales,
  canViewConsumptions,
  canViewCash,
  canViewCosts,
  canViewCommission,
}: {
  kind: ReportKind;
  data: ReportResponse<Record<string, unknown>>;
  activeTab: string;
  canViewSales: boolean;
  canViewConsumptions: boolean;
  canViewCash: boolean;
  canViewCosts: boolean;
  canViewCommission: boolean;
}) {
  if (kind === "products") {
    if (activeTab === "categorias")
      return <CategoryRanking summary={data.summary} canViewCosts={canViewCosts} />;
    if (activeTab === "modificadores")
      return <section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Desempenho por modificador</h2></div><ProductCommercialBreakdown summary={data.summary} kind="modifiers" /></section>;
    if (activeTab === "promocoes")
      return <section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Desempenho por promoção</h2></div><ProductCommercialBreakdown summary={data.summary} kind="promotions" /></section>;
    return (
      <section className="card overflow-hidden">
        <div className="card-header"><h2 className="text-sm font-bold">Desempenho por produto</h2></div>
        <RankingTable kind={kind} summary={data.summary} canViewCosts={canViewCosts} dataRows={data.results} />
      </section>
    );
  }
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
          <ReceiptDistributionTable summary={data.summary} />
        </section>
        <section className="card overflow-hidden">
          <div className="card-header"><div><h2 className="text-sm font-bold">Eventos detalhados</h2><p className="mt-1 text-[11px] text-muted">Uma linha por recebimento ou estorno ocorrido no período.</p></div></div>
          <ReceiptEventsTable data={data} />
        </section>
      </div>
    );
  if (["operators", "sellers"].includes(kind))
    return (
      <div className="space-y-5"><section className="card overflow-hidden">
          <div className="card-header"><h2 className="text-sm font-bold">Desempenho consolidado</h2></div>
          <RankingTable kind={kind} summary={data.summary} canViewCommission={canViewCommission} />
        </section><section className="card overflow-hidden"><div className="card-header"><div><h2 className="text-sm font-bold">Vendas relacionadas</h2><p className="mt-1 text-[11px] text-muted">Use o filtro de {kind === "operators" ? "operador" : "atendente"} para o drill-down individual.</p></div></div><SalesTable kind="sales" data={data} canViewSales={canViewSales} canViewConsumptions={canViewConsumptions} /></section></div>
    );
  if (kind === "commissions")
    return <div className="space-y-5"><section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Comissão por atendente</h2></div><RankingTable kind={kind} summary={data.summary} canViewCommission={canViewCommission} /></section><section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Comissão por venda e produto</h2></div><CommissionDetailsTable data={data} /></section></div>;
  if (kind === "stock-consumption") return <StockConsumption data={data} canViewCosts={canViewCosts} />;
  if (kind === "inventory-movements")
    return <section className="card overflow-hidden"><div className="card-header"><div><h2 className="text-sm font-bold">Movimentações detalhadas</h2><p className="mt-1 text-[11px] text-muted">Transição de saldo e referência operacional.</p></div></div><InventoryMovementsTable data={data} canViewCosts={canViewCosts} /></section>;
  if (kind === "cash") {
    if (activeTab === "sessoes")
      return <section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Sessões de caixa</h2></div><CashTable data={data} canViewCash={canViewCash} /></section>;
    if (activeTab === "recebimentos")
      return <section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Recebimentos por forma</h2></div><RankingTable kind="receipts" summary={data.summary} /></section>;
    if (activeTab === "movimentos")
      return <section className="card overflow-hidden"><div className="card-header"><div><h2 className="text-sm font-bold">Entradas e sangrias no período</h2><p className="mt-1 text-[11px] text-muted">Movimentos manuais, motivos e responsáveis.</p></div></div>{data.results.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Data/hora</th><th>Tipo</th><th>Caixa</th><th>Sessão</th><th>Responsável</th><th>Motivo</th><th>Valor</th></tr></thead><tbody>{data.results.map((row) => { const register = row.cash_register as Record<string, unknown>; const operator = row.operator as Record<string, unknown>; return <tr key={`cash-movement:${String(row.id)}`}><td>{formatDate(String(row.created_at))}</td><td>{domainLabel(row.movement_type)}</td><td>{String(register?.name || "-")}</td><td>#{String(row.cash_session)}</td><td>{String(operator?.name || "-")}</td><td>{String(row.reason || "-")}</td><td>{formatBRL(String(row.amount || "0"))}</td></tr>; })}</tbody></table></div> : <EmptyState title="Sem movimentos" description="Nenhuma entrada manual ou sangria ocorreu no período." />}</section>;
    if (activeTab === "diferencas") {
      const differenceData = { ...data, results: data.results.filter((row) => row.difference != null && hasDelta(row.difference)) };
      return <section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Sessões com diferença</h2></div><CashTable data={differenceData} canViewCash={canViewCash} /></section>;
    }
    return (
      <div className="space-y-5">
        <CashSummarySections summary={data.summary} canViewCommission={canViewCommission} />
      </div>
    );
  }
  if (kind === "result")
    return (
      <div className="space-y-5">
        <FinancialBridge summary={data.summary} title="Ponte do resultado" />
        <section className="card overflow-hidden">
          <div className="card-header">
            <h2 className="text-sm font-bold">Demonstrativo de resultado</h2>
          </div>
          <ResultStatement summary={data.summary} canViewCosts={canViewCosts} canViewCommission={canViewCommission} />
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
                    <th>Caixa / sessão</th>
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
                    const register = row.cash_register as { name?: string };
                    const session = row.cash_session as { id?: number };
                    return (
                      <tr key={`withdrawal:${String(row.id)}`}>
                        <td>{formatDate(String(row.created_at))}</td>
                        <td>{register?.name || "-"}<small className="block text-muted">Sessão #{String(session?.id || "-")}</small></td>
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
  if (kind === "cancellations")
    return <section className="card overflow-hidden"><div className="card-header"><div><h2 className="text-sm font-bold">Eventos de cancelamento e estorno</h2><p className="mt-1 text-[11px] text-muted">Vendas canceladas, itens de comandas cancelados e pagamentos estornados.</p></div></div><CancellationEventsTable data={data} /></section>;
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
  if (kind === "overview")
    return (
      <div className="space-y-5">
        <OverviewAnalytics summary={data.summary} />
        <FinancialBridge summary={data.summary} title="Composição do total recebido" />
      </div>
    );
  if (kind === "sales") {
    if (activeTab === "itens") return <section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Itens vendidos</h2></div><SalesItemsTable data={data} canViewCosts={canViewCosts} /></section>;
    if (activeTab === "pagamentos") return <section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Pagamentos das vendas</h2></div><SalesPaymentsTable data={data} /></section>;
    if (activeTab === "vendas") return operations;
    if (activeTab === "cancelamentos") {
      const cancelledData = { ...data, results: data.results.filter((row) => row.event_type === "reversal" || row.status === "cancelled") };
      return <section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Cancelamentos no recorte carregado</h2></div><SalesTable kind="cancellations" data={cancelledData} canViewSales={canViewSales} canViewConsumptions={canViewConsumptions} /></section>;
    }
    return <div className="space-y-5"><FinancialBridge summary={data.summary} /><SalesPaymentTotal summary={data.summary} /></div>;
  }
  if (kind === "discounts")
    return (
      <div className="space-y-5">
        <DiscountReconstruction summary={data.summary} />
        <section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Descontos e autorizações detalhados</h2></div><DiscountEventsTable data={data} /></section>
      </div>
    );
  if (kind === "consumptions")
    return (
      <div className="space-y-5">
        <ConsumptionFinancials summary={data.summary} />
        <ConsumptionGroups summary={data.summary} />
        <section className="card overflow-hidden"><div className="card-header"><h2 className="text-sm font-bold">Consumação e cortesias detalhadas</h2></div><ConsumptionDetailsTable data={data} canViewCosts={canViewCosts} /></section>
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
  const [activeTab, setActiveTab] = useState("");
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
        const tab = new URLSearchParams(window.location.search).get("tab");
        if (tab) query.set("tab", tab);
        window.history.replaceState(
          null,
          "",
          `${window.location.pathname}${query.size ? `?${query}` : ""}`,
        );
        query.delete("tab");
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
      const urlQuery = new URLSearchParams(query);
      const tab = new URLSearchParams(window.location.search).get("tab");
      if (tab) urlQuery.set("tab", tab);
      window.history.replaceState(
        null,
        "",
        `${window.location.pathname}?${urlQuery}`,
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

  async function loadPricePage(path: string, token = context.current) {
    const currentRequest = ++requestId.current;
    setLoading(true);
    setPrices(null);
    setError("");
    try {
      const result = await http.get<ProductPriceComparison>(path);
      if (context.current === token && requestId.current === currentRequest)
        setPrices(result);
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
    setActiveTab(query.get("tab") || "");
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
            "tab",
          ].includes(key),
      ),
    );
    if (kind === "cash" && query.get("tab") === "movimentos") {
      nextFilters.section = "movements";
    }
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
    const resetFilters: Record<string, string> = kind === "cash" && activeTab === "movimentos"
      ? { section: "movements" }
      : {};
    setPeriod(resetPeriod);
    setFilters(resetFilters);
    void load(resetPeriod, resetFilters);
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
    "inventory-movements",
    "cancellations",
  ];
  const canViewCosts = hasPermission(permissions.viewStockCosts);
  const canViewCommission = hasPermission(permissions.viewCommission);
  const tabs = reportTabs(kind, data?.summary || null, canViewCosts);
  const selectedTab = tabs.some((tab) => tab.value === activeTab)
    ? activeTab
    : tabs[0]?.value || "";

  function changeTab(tab: string) {
    setActiveTab(tab);
    const query = new URLSearchParams(window.location.search);
    query.set("tab", tab);
    window.history.replaceState(null, "", `${window.location.pathname}?${query}`);
    if (kind === "cash") {
      const nextFilters = { ...filters };
      if (tab === "movimentos") nextFilters.section = "movements";
      else delete nextFilters.section;
      setFilters(nextFilters);
      void load(period, nextFilters);
    }
  }
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
                      Object.entries(appliedFilters).filter(
                        ([, value]) => value,
                      ),
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
              {kind === "sales" && (
                <Field label="Cliente">
                  <Select value={filters.customer || ""} onChange={(event) => setFilters((current) => ({ ...current, customer: event.target.value }))}>
                    <option value="">Todos</option>
                    {options?.customers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                  </Select>
                </Field>
              )}
              {kind === "sales" && <Field label="Valor mínimo"><Input type="number" min="0" step="0.01" value={filters.minimum_value || ""} onChange={(event) => setFilters((current) => ({ ...current, minimum_value: event.target.value }))} /></Field>}
              {kind === "sales" && <Field label="Valor máximo"><Input type="number" min="0" step="0.01" value={filters.maximum_value || ""} onChange={(event) => setFilters((current) => ({ ...current, maximum_value: event.target.value }))} /></Field>}
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
                            {(() => {
                              const key = String(branch.id);
                              const cell = product.cells?.[key];
                              const state = cell
                                ? {
                                    kind: cell.state,
                                    price: cell.effective_price,
                                    detail: cell.label,
                                  }
                                : branchPriceState(
                                    product.availability[key],
                                    product.prices[key],
                                    product.default_price,
                                  );
                              return state.price == null ? (
                                <strong className="text-muted">Não disponível</strong>
                              ) : (
                                <>
                                  {formatBRL(state.price)}
                                  <small className="block text-slate-500">{state.detail}</small>
                                </>
                              );
                            })()}
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
            {prices && (prices.count || 0) > prices.products.length && (
              <div className="border-t border-subtle p-4">
                <Pagination
                  count={prices.count || 0}
                  next={prices.next || null}
                  previous={prices.previous || null}
                  onPage={(path) => void loadPricePage(path)}
                />
              </div>
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
            <ReportTabs tabs={tabs} active={selectedTab} onChange={changeTab} />
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {reportKpis(kind, data.summary, canViewCosts, canViewCommission).map(([label, value, format]) => (
                <Kpi key={label} label={label} value={value} format={format} />
              ))}
            </div>
            <SummaryWarnings kind={kind} summary={data.summary} />
            <ReportBody
              kind={kind}
              data={data}
              activeTab={selectedTab}
              canViewSales={
                hasPermission(permissions.viewSale) ||
                hasPermission(permissions.cancelSale)
              }
              canViewConsumptions={
                hasPermission(permissions.viewConsumption) ||
                hasPermission(permissions.cancelConsumption)
              }
              canViewCash={hasPermission(permissions.viewCashRegister)}
              canViewCosts={canViewCosts}
              canViewCommission={canViewCommission}
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
