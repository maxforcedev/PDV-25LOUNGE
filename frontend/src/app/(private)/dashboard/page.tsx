"use client";

import { useEffect, useEffectEvent, useRef, useState } from "react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import { Button, EmptyState } from "@/components/ui";
import { decimalIsZero, formatDecimalBRL as formatBRL } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { businessPeriod, dashboardAnalysisPeriods, dashboardQuery, validDashboardPeriod, type PeriodValue } from "@/lib/period";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { DashboardData } from "@/types";
import { CommercialOverview } from "./commercial-overview";
import { DashboardToolbar } from "./dashboard-toolbar";
import { OperationalAttention, type OperationalAlert, type OperationalCoverage } from "./operational-attention";

function updateDashboardUrl(next: PeriodValue, category: string) {
  const params = new URLSearchParams({ start_datetime: next.start, end_datetime: next.end });
  if (category) params.set("category", category);
  window.history.replaceState(window.history.state, "", `${window.location.pathname}?${params}`);
}

function requestedDashboardState(keepCategory: boolean) {
  const params = new URLSearchParams(window.location.search);
  const requested = { start: params.get("start_datetime") || "", end: params.get("end_datetime") || "" };
  const period = validDashboardPeriod(requested) ? requested : businessPeriod();
  const requestedCategory = params.get("category") || "";
  return { period, category: keepCategory && /^\d+$/.test(requestedCategory) ? requestedCategory : "" };
}

type DashboardErrorState = {
  title: string;
  message: string;
  retryable: boolean;
};

function dashboardError(caught: unknown): DashboardErrorState {
  if (!(caught instanceof ApiError) || caught.status === 0)
    return { title: "Falha de rede", message: "Não foi possível conectar ao servidor. Verifique sua conexão e tente novamente.", retryable: true };
  if (caught.status === 401)
    return { title: "Sessão expirada", message: "Entre novamente para consultar o Dashboard.", retryable: false };
  if (caught.status === 403) {
    const unavailable = /plano|licen[çc]a|recurso|m[oó]dulo/i.test(caught.message);
    return unavailable
      ? { title: "Recurso indisponível", message: "O Dashboard não está disponível para o plano ou a configuração desta filial.", retryable: false }
      : { title: "Acesso restrito", message: "Seu perfil não possui acesso a esta consulta do Dashboard.", retryable: false };
  }
  if (caught.status === 400)
    return { title: "Filtro inválido", message: "O período ou filtro informado não é válido para esta filial. Revise os filtros e tente novamente.", retryable: true };
  if (caught.status === 404)
    return { title: "Filial indisponível", message: "A filial selecionada não está disponível. Escolha outra filial e tente novamente.", retryable: false };
  return { title: "Não foi possível carregar o Dashboard", message: caught.message || "Ocorreu um erro inesperado. Tente novamente.", retryable: true };
}

function categoryError(caught: unknown) {
  return caught instanceof ApiError && caught.status === 400 && (
    "category" in caught.fields || /categoria/i.test(caught.message)
  );
}

function DashboardLoading() {
  const block = "animate-pulse rounded bg-surface-muted";
  return (
    <div className="space-y-5" aria-busy="true" aria-label="Carregando indicadores do Dashboard">
      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((item) => <div key={item} className="card min-h-52 p-5"><div className={`${block} h-3 w-24`} /><div className={`${block} mt-5 h-8 w-3/4`} /><div className={`${block} mt-10 h-3 w-full`} /><div className={`${block} mt-2 h-3 w-2/3`} /></div>)}
      </section>
      <section className="grid gap-5 xl:grid-cols-3">
        <div className="card h-92 p-5 xl:col-span-2"><div className={`${block} h-4 w-48`} /><div className={`${block} mt-8 h-52 w-full`} /></div>
        <div className="card h-92 p-5"><div className={`${block} h-4 w-36`} /><div className="mt-8 space-y-5">{[0, 1, 2].map((item) => <div key={item}><div className={`${block} h-3 w-full`} /><div className={`${block} mt-2 h-2 w-full`} /></div>)}</div></div>
      </section>
      <section className="card h-64 p-5"><div className={`${block} h-4 w-48`} /><div className="mt-7 space-y-4">{[0, 1, 2].map((item) => <div key={item} className={`${block} h-8 w-full`} />)}</div></section>
    </div>
  );
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
  const [error, setError] = useState<DashboardErrorState | null>(null);
  const [filterNotice, setFilterNotice] = useState("");
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
    setError(null);
    const params = dashboardQuery(next);
    if (nextCategory) params.set("category", nextCategory);
    try {
      const result = await http.get<DashboardData>(`dashboard/?${params}`);
      if (context.current === token && requestSequence.current === request) {
        const selectedCategory = result.filters?.category;
        const categoryIsCurrent = result.filters?.categories.some((item) => String(item.id) === nextCategory);
        if (nextCategory && (selectedCategory !== Number(nextCategory) || !categoryIsCurrent)) {
          setCategory("");
          setFilterNotice("A categoria informada não está disponível para a filial atual. O filtro foi removido.");
          updateDashboardUrl(next, "");
          void load(next, token, "");
          return;
        }
        setData(result);
        setUpdatedAt(new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short", timeZone: "America/Sao_Paulo" }).format(new Date()));
      }
    } catch (caught) {
      if (context.current !== token || requestSequence.current !== request) return;
      if (nextCategory && categoryError(caught)) {
        setCategory("");
        setFilterNotice("A categoria informada não pertence à filial atual. O filtro foi removido.");
        updateDashboardUrl(next, "");
        void load(next, token, "");
        return;
      }
      setError(dashboardError(caught));
    } finally {
      if (context.current === token && requestSequence.current === request) setLoading(false);
    }
  }

  const loadDashboard = useEffectEvent(load);

  function apply(next: PeriodValue) {
    if (!validDashboardPeriod(next)) {
      setError({ title: "Período inválido", message: "Informe datas e horários existentes, com início anterior ou igual ao fim.", retryable: false });
      return;
    }
    setFilterNotice("");
    setPeriod(next);
    setDraftPeriod(next);
    setCustomOpen(false);
    updateDashboardUrl(next, category);
    void load(next, context.current, category);
  }

  function applyCategory(nextCategory: string) {
    if (nextCategory && !data?.filters?.categories.some((item) => String(item.id) === nextCategory)) {
      setCategory("");
      setFilterNotice("A categoria selecionada não está disponível para a filial atual.");
      updateDashboardUrl(period, "");
      return;
    }
    setFilterNotice("");
    setCategory(nextCategory);
    updateDashboardUrl(period, nextCategory);
    void load(period, context.current, nextCategory);
  }

  useEffect(() => {
    requestSequence.current += 1;
    setData(null);
    setError(null);
    setFilterNotice("");
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
  const appliedCategory = data?.filters?.category;
  if (appliedCategory) query.set("category", String(appliedCategory));
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
  const operationalSections = data?.metadata.operational_state.sections ?? [];
  const hasInventoryIndicator = hasFeature("inventory");
  const hasCommandsIndicator = hasFeature("commands") || hasFeature("tables");
  const hasCashIndicator = hasFeature("cash_register");
  const configuredOperationalIndicators = [hasInventoryIndicator, hasCommandsIndicator, hasCashIndicator].filter(Boolean).length;
  const availableOperationalIndicators = [
    hasInventoryIndicator && data?.availability.inventory === "available" && operationalSections.includes("inventory"),
    hasCommandsIndicator && operationalSections.includes("commands"),
    hasCashIndicator && operationalSections.includes("current_cash"),
  ].filter(Boolean).length;
  const operationalCoverage: OperationalCoverage =
    !availableOperationalIndicators
      ? "none"
      : availableOperationalIndicators === configuredOperationalIndicators
        ? "full"
        : "partial";
  const operationalAlerts: OperationalAlert[] = [];
  if (data?.availability.inventory === "available" && data.inventory?.negative_count) operationalAlerts.push({ key: "negative-stock", title: `${data.inventory.negative_count} produto(s) com estoque negativo`, detail: "Revise as movimentações e faça o ajuste necessário.", href: canViewInventory ? "/estoque?state=negative" : undefined, tone: "danger", reference: "current" });
  if (data?.availability.financial_receipts === "available" && sales?.reconciliation_delta && !decimalIsZero(sales.reconciliation_delta)) operationalAlerts.push({ key: "reconciliation", title: `${formatBRL(sales.reconciliation_delta.replace(/^-/, ""))} de divergência de pagamentos`, detail: "Revise a reconciliação do período.", href: canViewReceiptsReport ? report("recebimentos") : undefined, tone: "danger", reference: "period" });
  if (data?.availability.inventory === "available" && data.inventory?.zero_count) operationalAlerts.push({ key: "zero-stock", title: `${data.inventory.zero_count} produto(s) com estoque zerado`, detail: "Avalie a necessidade de reposição.", href: canViewInventory ? "/estoque?state=zero" : undefined, tone: "warning", reference: "current" });
  if (data?.availability.inventory === "available" && data.inventory?.below_minimum_count) operationalAlerts.push({ key: "minimum-stock", title: `${data.inventory.below_minimum_count} produto(s) abaixo do mínimo`, detail: "Avalie a necessidade de reposição.", href: canViewInventory ? "/estoque?state=below_minimum" : undefined, tone: "warning", reference: "current" });
  if (operationalSections.includes("commands") && data?.commands?.open_table_count && hasFeature("tables")) operationalAlerts.push({ key: "open-tables", title: `${data.commands.open_table_count} mesa(s) aberta(s)`, detail: "Mesas com atendimento em andamento.", href: canViewCommands ? "/mesas" : undefined, tone: "info", reference: "current" });
  if (operationalSections.includes("commands") && data?.commands?.open_count && hasFeature("commands")) operationalAlerts.push({ key: "open-commands", title: `${data.commands.open_count} comanda(s) aberta(s)`, detail: "Comandas em andamento na filial.", href: canViewCommands ? "/comandas" : undefined, tone: "info", reference: "current" });
  if (operationalSections.includes("current_cash") && data?.current_cash?.length && hasFeature("cash_register")) operationalAlerts.push({ key: "open-cash", title: `${data.current_cash.length} caixa(s) aberto(s)`, detail: "Sessões de caixa em andamento.", href: canViewCash ? `/caixas/sessoes/${data.current_cash[0].id}` : undefined, tone: "info", reference: "current" });
  const branchTransitioning = loadedBranch.current !== null && loadedBranch.current !== branchId;
  const visibleData = branchTransitioning ? null : data;

  return <><PageHeader title="Visão geral" description={currentBranch ? `Acompanhe a operação comercial da filial ${currentBranch.name}.` : "Acompanhe a operação comercial da sua filial."} /><main className="space-y-5 p-4 sm:p-6 lg:p-8"><DashboardToolbar period={period} draftPeriod={draftPeriod} presets={dashboardAnalysisPeriods()} customOpen={customOpen} category={category} categories={visibleData?.filters?.categories ?? []} showCategory={hasFeature("products") && Boolean(visibleData?.filters?.categories.length)} loading={loading || branchTransitioning} updatedAt={updatedAt} onPreset={apply} onToggleCustom={() => setCustomOpen((open) => !open)} onDraftChange={setDraftPeriod} onApplyCustom={() => apply(draftPeriod)} onCategoryChange={applyCategory} onRefresh={() => void load(period, context.current, category)} />{filterNotice && <p className="rounded-md border border-warning/30 bg-warning/10 px-3.5 py-3 text-sm text-warning-strong" role="status">{filterNotice}</p>}{error && <section className="card flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between" role="alert"><div><h2 className="text-sm font-bold text-fg">{error.title}</h2><p className="mt-1 text-sm text-muted">{error.message}</p></div>{error.retryable && <Button type="button" variant="secondary" onClick={() => void load(period, context.current, category)}>Tentar novamente</Button>}</section>}{loading || branchTransitioning ? <DashboardLoading /> : visibleData ? <><CommercialOverview data={visibleData} salesReportHref={canViewSalesReport ? report("vendas") : undefined} receiptsReportHref={canViewReceiptsReport ? report("recebimentos") : undefined} productsReportHref={canViewProductsReport ? report("produtos") : undefined} resultReportHref={canViewResultReport ? report("resultado") : undefined} canViewSaleDetail={canViewSaleDetail} /><OperationalAttention alerts={operationalAlerts} asOf={visibleData.metadata.operational_state.as_of} coverage={operationalCoverage} /></> : !error ? <section className="card"><EmptyState title="Dashboard indisponível" description="Selecione uma filial para carregar os indicadores." /></section> : null}</main></>;
}

export default function DashboardRoute() {
  return <AdminGuard requiredPermissions={[permissions.viewDashboard]} requiredFeatures={["reports"]}><DashboardPage /></AdminGuard>;
}
