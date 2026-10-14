"use client";

import { useEffect, useEffectEvent, useRef, useState } from "react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import { Alert, EmptyState, TableLoading } from "@/components/ui";
import { decimalIsZero, formatDecimalBRL as formatBRL } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { businessPeriod, dashboardPeriods, dashboardQuery, validDashboardPeriod, type PeriodValue } from "@/lib/period";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { DashboardData } from "@/types";
import { CommercialOverview } from "./commercial-overview";
import { DashboardToolbar } from "./dashboard-toolbar";
import { OperationalAttention, type OperationalAlert } from "./operational-attention";

function updateDashboardUrl(next: PeriodValue, category: string) {
  const params = new URLSearchParams({ start_datetime: next.start, end_datetime: next.end });
  if (category) params.set("category", category);
  window.history.replaceState(window.history.state, "", `${window.location.pathname}?${params}`);
}

function requestedDashboardState(keepCategory: boolean) {
  const params = new URLSearchParams(window.location.search);
  const requested = { start: params.get("start_datetime") || "", end: params.get("end_datetime") || "" };
  const dateTimePattern = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$/;
  const period = dateTimePattern.test(requested.start) && dateTimePattern.test(requested.end) && requested.start <= requested.end
    ? requested
    : businessPeriod();
  const requestedCategory = params.get("category") || "";
  return { period, category: keepCategory && /^\d+$/.test(requestedCategory) ? requestedCategory : "" };
}

function DashboardPage() {
  const { currentBranch, hasAnyPermission, hasFeature, hasPermission } = useAuth();
  const branchId = currentBranch?.id || 0;
  const context = useRef(branchId);
  const loadedBranch = useRef<number | null>(null);
  const requestSequence = useRef(0);
  context.current = branchId;
  const [period, setPeriod] = useState<PeriodValue>(() => businessPeriod());
  const [draftPeriod, setDraftPeriod] = useState<PeriodValue>(() => businessPeriod());
  const [category, setCategory] = useState("");
  const [customOpen, setCustomOpen] = useState(false);
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<string>();

  async function load(next: PeriodValue, token = context.current, nextCategory = category) {
    if (!token) {
      setLoading(false);
      return;
    }
    const request = ++requestSequence.current;
    setLoading(true);
    setData(null);
    setError("");
    const params = dashboardQuery(next);
    if (nextCategory) params.set("category", nextCategory);
    try {
      const result = await http.get<DashboardData>(`dashboard/?${params}`);
      if (context.current === token && requestSequence.current === request) {
        setData(result);
        setUpdatedAt(new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short", timeZone: "America/Sao_Paulo" }).format(new Date()));
      }
    } catch (caught) {
      if (context.current !== token || requestSequence.current !== request) return;
      setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar o Dashboard.");
    } finally {
      if (context.current === token && requestSequence.current === request) setLoading(false);
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
    updateDashboardUrl(next, category);
    void load(next, context.current, category);
  }

  function applyCategory(nextCategory: string) {
    setCategory(nextCategory);
    updateDashboardUrl(period, nextCategory);
    void load(period, context.current, nextCategory);
  }

  useEffect(() => {
    requestSequence.current += 1;
    setData(null);
    setError("");
    setUpdatedAt(undefined);
    if (!branchId) {
      setLoading(false);
      loadedBranch.current = null;
      return;
    }
    const branchChanged = loadedBranch.current !== null && loadedBranch.current !== branchId;
    const next = requestedDashboardState(!branchChanged);
    loadedBranch.current = branchId;
    setPeriod(next.period);
    setDraftPeriod(next.period);
    setCategory(next.category);
    updateDashboardUrl(next.period, next.category);
    void loadDashboard(next.period, branchId, next.category);
  }, [branchId]);

  const query = new URLSearchParams({ start_datetime: period.start, end_datetime: period.end });
  if (category) query.set("category", category);
  const report = (slug: string) => `/relatorios/${slug}?${query}`;
  const canViewSalesReport = hasFeature("reports") && hasPermission(permissions.viewSalesReport);
  const canViewReceiptsReport = hasFeature("financial") && hasPermission(permissions.viewReceiptsReport);
  const canViewProductsReport = hasFeature("products") && hasPermission(permissions.viewProductsReport);
  const canViewResultReport = hasFeature("financial") && hasPermission(permissions.viewOperationalResult);
  const canViewInventory = hasFeature("inventory") && hasPermission(permissions.viewInventory);
  const canViewCash = hasFeature("cash_register") && hasPermission(permissions.viewCashRegister);
  const canViewCommands = hasFeature("commands") && hasPermission(permissions.viewCommands);
  const canViewSaleDetail = hasFeature("counter") && hasAnyPermission([permissions.viewSale, permissions.cancelSale]);
  const sales = data?.sales;
  const operationalAlerts: OperationalAlert[] = [];
  if (hasFeature("inventory") && data?.inventory?.negative_count) operationalAlerts.push({ key: "negative-stock", title: `${data.inventory.negative_count} produto(s) com estoque negativo`, detail: "Revise as movimentações e faça o ajuste necessário.", href: canViewInventory ? "/estoque?state=negative" : undefined, tone: "danger" });
  if (sales?.reconciliation_delta && !decimalIsZero(sales.reconciliation_delta)) operationalAlerts.push({ key: "reconciliation", title: `${formatBRL(sales.reconciliation_delta.replace(/^-/, ""))} de divergência de pagamentos`, detail: "Revise a reconciliação do período.", href: canViewReceiptsReport ? report("recebimentos") : undefined, tone: "danger", reference: "period" });
  if (hasFeature("inventory") && data?.inventory?.zero_count) operationalAlerts.push({ key: "zero-stock", title: `${data.inventory.zero_count} produto(s) com estoque zerado`, detail: "Avalie a necessidade de reposição.", href: canViewInventory ? "/estoque?state=zero" : undefined, tone: "warning" });
  if (hasFeature("inventory") && data?.inventory?.below_minimum_count) operationalAlerts.push({ key: "minimum-stock", title: `${data.inventory.below_minimum_count} produto(s) abaixo do mínimo`, detail: "Avalie a necessidade de reposição.", href: canViewInventory ? "/estoque?state=below_minimum" : undefined, tone: "warning" });
  if (data?.commands?.open_table_count && hasFeature("tables")) operationalAlerts.push({ key: "open-tables", title: `${data.commands.open_table_count} mesa(s) aberta(s)`, detail: "Mesas com atendimento em andamento.", href: canViewCommands ? "/mesas" : undefined, tone: "info" });
  if (data?.commands?.open_count && hasFeature("commands")) operationalAlerts.push({ key: "open-commands", title: `${data.commands.open_count} comanda(s) aberta(s)`, detail: "Comandas em andamento na filial.", href: canViewCommands ? "/comandas" : undefined, tone: "info" });
  if (data?.current_cash?.length && hasFeature("cash_register")) operationalAlerts.push({ key: "open-cash", title: `${data.current_cash.length} caixa(s) aberto(s)`, detail: "Sessões de caixa em andamento.", href: canViewCash ? `/caixas/sessoes/${data.current_cash[0].id}` : undefined, tone: "info" });

  return <><PageHeader title="Visão geral" description={currentBranch ? `Acompanhe a operação comercial da filial ${currentBranch.name}.` : "Acompanhe a operação comercial da sua filial."} /><main className="space-y-5 p-4 sm:p-6 lg:p-8"><DashboardToolbar period={period} draftPeriod={draftPeriod} presets={dashboardPeriods()} customOpen={customOpen} category={category} categories={data?.filters?.categories ?? []} showCategory={hasFeature("products") && Boolean(data?.filters?.categories.length)} loading={loading} updatedAt={updatedAt} onPreset={apply} onToggleCustom={() => setCustomOpen((open) => !open)} onDraftChange={setDraftPeriod} onApplyCustom={() => apply(draftPeriod)} onCategoryChange={applyCategory} onRefresh={() => void load(period, context.current, category)} />{error && <Alert message={error} />}{loading ? <section className="card"><TableLoading columns={4} /></section> : data ? <><CommercialOverview data={data} salesReportHref={canViewSalesReport ? report("vendas") : undefined} receiptsReportHref={canViewReceiptsReport ? report("recebimentos") : undefined} productsReportHref={canViewProductsReport ? report("produtos") : undefined} resultReportHref={canViewResultReport ? report("resultado") : undefined} canViewSaleDetail={canViewSaleDetail} /><OperationalAttention alerts={operationalAlerts} asOf={data.metadata.operational_state.as_of} /></> : !error ? <section className="card"><EmptyState title="Dashboard indisponível" description="Selecione uma filial para carregar os indicadores." /></section> : null}</main></>;
}

export default function DashboardRoute() {
  return <AdminGuard requiredPermissions={[permissions.viewDashboard]} requiredFeatures={["reports"]}><DashboardPage /></AdminGuard>;
}
