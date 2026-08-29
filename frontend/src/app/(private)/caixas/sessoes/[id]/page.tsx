"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowUpFromLine,
  Banknote,
  History,
  LockKeyhole,
} from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { CashStatus, DifferenceBadge, MoneyKpi } from "@/components/cash-ui";
import { PageHeader } from "@/components/page-header";
import { PeriodFilter, type PeriodValue } from "@/components/period-filter";
import {
  Alert,
  Button,
  EmptyState,
  Field,
  Input,
  Modal,
  Pagination,
  Spinner,
  TableLoading,
  Textarea,
} from "@/components/ui";
import { moneyToCents, normalizeMoney } from "@/lib/cash";
import { formatBRL, formatDate } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type {
  CashBeneficiary,
  CashMovement,
  CashSession,
  CashSummary,
  Paginated,
  SessionTimeline,
  WithdrawalCategory,
} from "@/types";

type MovementAction = "entry" | "withdrawal";
const withdrawalCategories: Array<[WithdrawalCategory, string]> = [
  ["dj", "DJ"],
  ["artist", "Pagode/Artista"],
  ["advance", "Vale/Adiantamento"],
  ["promoter", "Promoter"],
  ["supplier", "Fornecedor"],
  ["other", "Outros"],
];
const beneficiaryRequired = new Set<WithdrawalCategory>([
  "dj",
  "artist",
  "advance",
  "promoter",
]);

type CanonicalCashSummary = CashSummary & {
  sales_revenue: string;
  consumption_charged: string;
  effective_revenue: string;
  service_fee: string;
  total_received: string;
  payment_total: string;
  reconciliation_delta: string;
  receipts?: { reversals?: string; reversal_payment_total?: string };
};

function CashFinancialBridge({ summary }: { summary: CashSummary }) {
  const financial = summary as CanonicalCashSummary;
  const lines: Array<[string, string, string, boolean?]> = [
    ["Faturamento de vendas", financial.sales_revenue, ""],
    ["Consumação cobrada", financial.consumption_charged, "+"],
    ["Faturamento efetivo", financial.effective_revenue, "=", true],
    ["Taxa de serviço", financial.service_fee, "+"],
    ["Total recebido", financial.total_received, "=", true],
  ];
  const reversals =
    financial.receipts?.reversal_payment_total ||
    financial.receipts?.reversals ||
    "0";
  const hasDelta = Math.abs(Number(financial.reconciliation_delta || 0)) >= 0.005;
  return (
    <section className="card overflow-hidden">
      <div className="card-header">
        <div>
          <h2 className="text-sm font-bold">Ponte financeira da sessão</h2>
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
            <strong className="mt-2 block text-base">{formatBRL(value)}</strong>
          </div>
        ))}
      </div>
      <div className="grid gap-3 border-t border-subtle p-4 text-xs sm:grid-cols-3">
        <p className="flex justify-between gap-3">
          <span>Reversões / estornos</span>
          <strong>{formatBRL(reversals)}</strong>
        </p>
        <p className="flex justify-between gap-3">
          <span>Total dos pagamentos</span>
          <strong>{formatBRL(financial.payment_total)}</strong>
        </p>
        <p
          className={`flex justify-between gap-3 ${hasDelta ? "text-warning-strong" : ""}`}
        >
          <span>Delta de reconciliação</span>
          <strong>{formatBRL(financial.reconciliation_delta)}</strong>
        </p>
      </div>
    </section>
  );
}

function SessionDetail() {
  const { id } = useParams<{ id: string }>();
  const { user, currentCompany, currentBranch, hasFeature, hasPermission } = useAuth();
  const cashEnabled = hasFeature("cash_register");
  const canEntry = cashEnabled && hasPermission(permissions.manualCashEntry);
  const canWithdraw = cashEnabled && hasPermission(permissions.withdrawCash);
  const canClose = hasPermission(permissions.closeCashRegister);
  const canAdministerOthers = hasPermission(permissions.administerOtherCash);
  const canViewSales = hasPermission(permissions.viewSale) || hasPermission(permissions.cancelSale);
  const canViewConsumptions = hasPermission(permissions.viewConsumption) || hasPermission(permissions.cancelConsumption);
  const contextRef = useRef("");
  const loadRequestRef = useRef(0);
  const movementsRequestRef = useRef(0);
  contextRef.current = `${currentCompany?.id || ""}:${currentBranch?.id || ""}:${id}`;
  const [session, setSession] = useState<CashSession | null>(null);
  const [summary, setSummary] = useState<CashSummary | null>(null);
  const [movements, setMovements] = useState<Paginated<CashMovement> | null>(
    null,
  );
  const [timeline, setTimeline] = useState<SessionTimeline | null>(null);
  const [loading, setLoading] = useState(true);
  const [movementsLoading, setMovementsLoading] = useState(true);
  const [timelineLoading, setTimelineLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [action, setAction] = useState<MovementAction | null>(null);
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [category, setCategory] = useState<WithdrawalCategory | "">("");
  const [resultEffect, setResultEffect] = useState<"operating_expense" | "neutral" | "">("");
  const [beneficiaryId, setBeneficiaryId] = useState("");
  const [beneficiaries, setBeneficiaries] = useState<CashBeneficiary[]>([]);
  const [beneficiariesLoading, setBeneficiariesLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancellationReason, setCancellationReason] = useState("");
  const [period, setPeriod] = useState<PeriodValue>({ start: "", end: "" });
  const movementIdempotencyKey = useRef("");

  function movementsPath(selectedPeriod = period) {
    const params = new URLSearchParams({ cash_session: id });
    if (selectedPeriod.start)
      params.set("start_datetime", selectedPeriod.start);
    if (selectedPeriod.end) params.set("end_datetime", selectedPeriod.end);
    return `cash-movements/?${params}`;
  }

  function syncMovementPeriodUrl(selectedPeriod: PeriodValue) {
    const params = new URLSearchParams(window.location.search);
    for (const key of ["start_datetime", "end_datetime", "page"]) {
      params.delete(key);
    }
    if (selectedPeriod.start)
      params.set("start_datetime", selectedPeriod.start);
    if (selectedPeriod.end) params.set("end_datetime", selectedPeriod.end);
    window.history.replaceState(
      window.history.state,
      "",
      `${window.location.pathname}${params.size ? `?${params}` : ""}`,
    );
  }

  async function load(context = contextRef.current, selectedPeriod = period) {
    const loadRequest = ++loadRequestRef.current;
    const movementsRequest = ++movementsRequestRef.current;
    if (!currentBranch || !id) {
      setLoading(false);
      setMovementsLoading(false);
      setTimelineLoading(false);
      return;
    }
    setLoading(true);
    setMovementsLoading(true);
    setTimelineLoading(true);
    setError("");
    try {
      const [
        sessionResponse,
        summaryResponse,
        movementResponse,
        timelineResponse,
      ] = await Promise.all([
        http.get<CashSession>(`cash-sessions/${id}/`),
        http.get<CashSummary>(`cash-sessions/${id}/summary/`),
        http.get<Paginated<CashMovement>>(movementsPath(selectedPeriod)),
        http.get<SessionTimeline>(`cash-sessions/${id}/timeline/`),
      ]);
      if (
        contextRef.current === context &&
        loadRequestRef.current === loadRequest
      ) {
        setSession(sessionResponse);
        setSummary(summaryResponse);
        setTimeline(timelineResponse);
      }
      if (
        contextRef.current === context &&
        movementsRequestRef.current === movementsRequest
      )
        setMovements(movementResponse);
    } catch (caught) {
      if (
        contextRef.current === context &&
        loadRequestRef.current === loadRequest
      )
        setError(
          caught instanceof ApiError
            ? caught.message
            : "Não foi possível carregar a sessão de caixa.",
        );
    } finally {
      if (
        contextRef.current === context &&
        loadRequestRef.current === loadRequest
      ) {
        setLoading(false);
        setTimelineLoading(false);
      }
      if (
        contextRef.current === context &&
        movementsRequestRef.current === movementsRequest
      )
        setMovementsLoading(false);
    }
  }

  async function loadMovements(
    path = movementsPath(),
    context = contextRef.current,
  ) {
    const requestId = ++movementsRequestRef.current;
    setMovementsLoading(true);
    setError("");
    setMovements(null);
    try {
      const response = await http.get<Paginated<CashMovement>>(path);
      if (
        contextRef.current === context &&
        movementsRequestRef.current === requestId
      )
        setMovements(response);
    } catch (caught) {
      if (
        contextRef.current === context &&
        movementsRequestRef.current === requestId
      )
        setError(
          caught instanceof ApiError
            ? caught.message
            : "Não foi possível carregar o histórico.",
        );
    } finally {
      if (
        contextRef.current === context &&
        movementsRequestRef.current === requestId
      )
        setMovementsLoading(false);
    }
  }

  useEffect(() => {
    const context = contextRef.current;
    setSession(null);
    setSummary(null);
    setMovements(null);
    setTimeline(null);
    setError("");
    setSuccess("");
    setAction(null);
    const query = new URLSearchParams(window.location.search);
    const nextPeriod = {
      start: query.get("start_datetime") || "",
      end: query.get("end_datetime") || "",
    };
    setPeriod(nextPeriod);
    void load(context, nextPeriod);
  }, [id, currentCompany?.id, currentBranch?.id]);

  function showAction(next: MovementAction) {
    setAction(next);
    setAmount("");
    setReason("");
    setCategory("");
    setResultEffect("");
    setBeneficiaryId("");
    setError("");
    movementIdempotencyKey.current = crypto.randomUUID();
    if (next === "withdrawal") {
      setBeneficiariesLoading(true);
      http
        .getAll<CashBeneficiary>("cash-beneficiaries/")
        .then(setBeneficiaries)
        .catch((caught) =>
          setError(
            caught instanceof ApiError
              ? caught.message
              : "Não foi possível carregar os beneficiários.",
          ),
        )
        .finally(() => setBeneficiariesLoading(false));
    }
  }

  async function submitMovement(event: React.FormEvent) {
    event.preventDefault();
    const allowed = action === "entry" ? canEntry : canWithdraw;
    if (
      !action ||
      !allowed ||
      moneyToCents(amount) === null ||
      moneyToCents(amount) === BigInt(0) ||
      !reason.trim()
    ) {
      setError(
        "Informe um valor maior que zero, com no máximo duas casas decimais, e o motivo.",
      );
      return;
    }
    if (
      action === "withdrawal" &&
      (!category || !resultEffect || (beneficiaryRequired.has(category) && !beneficiaryId))
    ) {
      setError(
        "Informe a categoria, o impacto no resultado e o beneficiário obrigatório desta sangria.",
      );
      return;
    }
    const context = contextRef.current;
    setSaving(true);
    setError("");
    try {
      await http.post(
        `cash-sessions/${id}/${action}/`,
        action === "entry"
          ? { amount: normalizeMoney(amount), reason: reason.trim(), idempotency_key: movementIdempotencyKey.current }
          : {
              amount: normalizeMoney(amount),
              reason: reason.trim(),
              idempotency_key: movementIdempotencyKey.current,
              category,
              result_effect: resultEffect,
              ...(beneficiaryId
                ? { beneficiary_user: Number(beneficiaryId) }
                : {}),
            },
      );
      if (contextRef.current !== context) return;
      setAction(null);
      setSuccess(
        action === "entry"
          ? "Entrada registrada com sucesso."
          : "Sangria registrada com sucesso.",
      );
      await load(context);
    } catch (caught) {
      if (contextRef.current === context)
        setError(
          caught instanceof ApiError
            ? caught.message
            : "Não foi possível registrar o movimento.",
        );
    } finally {
      if (contextRef.current === context) setSaving(false);
    }
  }

  async function cancelSession(event: React.FormEvent) {
    event.preventDefault();
    if (!cancellationReason.trim()) {
      setError("Informe o motivo da anulação.");
      return;
    }
    setSaving(true);
    try {
      await http.post(`cash-sessions/${id}/cancel/`, { reason: cancellationReason.trim() });
      setCancelOpen(false);
      setSuccess("Sessão anulada. O histórico foi preservado.");
      await load();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível anular a sessão.");
    } finally {
      setSaving(false);
    }
  }

  const isOpen = session?.status === "open";
  const canOperateSession = !!session && (session.opened_by === user?.id || canAdministerOthers);
  return (
    <>
      <PageHeader
        title={
          session
            ? `Sessão #${session.id} · ${session.register_name || session.cash_register_name}`
            : "Sessão de caixa"
        }
        description={`Filial atual: ${currentBranch?.name || "nenhuma filial selecionada"}${session ? ` · Aberta por ${session.opened_by_name} em ${formatDate(session.opened_at)}` : ""}.`}
        action={
          <div className="flex flex-wrap gap-2">
            <Link href="/caixas" className="btn btn-secondary">
              <ArrowLeft className="size-4" />
              Caixas
            </Link>
            {isOpen && canOperateSession && canEntry && (
              <Button variant="secondary" onClick={() => showAction("entry")}>
                <ArrowDownToLine className="size-4" />
                Entrada
              </Button>
            )}
            {isOpen && canOperateSession && canWithdraw && (
              <Button
                variant="secondary"
                onClick={() => showAction("withdrawal")}
              >
                <ArrowUpFromLine className="size-4" />
                Sangria
              </Button>
            )}
            {isOpen && canOperateSession && canClose && (
              <Link
                href={`/caixas/sessoes/${id}/fechar`}
                className="btn btn-danger"
              >
                <LockKeyhole className="size-4" />
                Fechar caixa
              </Link>
            )}
            {isOpen && canOperateSession && canClose && (
              <Button variant="secondary" onClick={() => { setCancellationReason(""); setCancelOpen(true); }}>
                Anular sessão
              </Button>
            )}
          </div>
        }
      />
      <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        {error && !action && <Alert message={error} />}
        {success && <Alert type="success" message={success} />}
        {loading ? (
          <div className="card flex min-h-64 items-center justify-center text-primary">
            <Spinner className="size-7" />
          </div>
        ) : session && summary ? (
          <>
            <section className="card p-5 sm:p-6">
              <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
                <div>
                  <div className="flex items-center gap-2">
                    <CashStatus status={session.status} />
                    <span className="text-xs text-slate-400">
                      Sessão #{session.id}
                    </span>
                  </div>
                  <h2 className="mt-3 text-lg font-bold">
                    {session.register_name || session.cash_register_name}
                  </h2>
                  <p className="mt-1 text-xs text-slate-500">
                    {session.branch_name} · {session.company_name}
                  </p>
                </div>
                <Banknote className="size-10 text-primary/25" />
              </div>
            </section>
            <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <MoneyKpi label="Abertura" value={summary.opening_amount} />
              <MoneyKpi
                label="Entradas manuais"
                value={summary.manual_entries}
                tone="success"
              />
              <MoneyKpi
                label="Sangrias"
                value={summary.withdrawals}
                tone="danger"
              />
              <MoneyKpi label="Vendas em dinheiro" value={summary.sale_cash} tone="success" />
              <MoneyKpi label="Consumações em dinheiro" value={summary.consumption_cash} tone="success" />
              <MoneyKpi label="Reversões em dinheiro" value={summary.cash_reversals} tone="danger" />
              <MoneyKpi
                label={isOpen ? "Esperado agora" : "Esperado no fechamento"}
                value={summary.expected_amount}
                tone="primary"
              />
            </section>
            <CashFinancialBridge summary={summary} />
            {!isOpen && (
              <section className="card overflow-hidden">
                <div className="card-header">
                  <div>
                    <h2 className="text-sm font-bold">Conferência encerrada</h2>
                    <p className="mt-1 text-[11px] text-slate-500">
                      Valores imutáveis gravados no fechamento.
                    </p>
                  </div>
                  {session.closing_difference !== null && (
                    <DifferenceBadge value={session.closing_difference} />
                  )}
                </div>
                <div className="grid gap-4 p-5 text-xs sm:grid-cols-3 sm:p-6">
                  <div>
                    <span className="text-slate-400">Esperado</span>
                    <strong className="mt-1 block text-base">
                      {formatBRL(
                        session.closing_expected_amount ||
                          session.expected_amount,
                      )}
                    </strong>
                  </div>
                  <div>
                    <span className="text-slate-400">Informado</span>
                    <strong className="mt-1 block text-base">
                      {formatBRL(session.closing_amount_informed || "0.00")}
                    </strong>
                  </div>
                  <div>
                    <span className="text-slate-400">Fechamento</span>
                    <strong className="mt-1 block">
                      {formatDate(session.closed_at || "")}
                    </strong>
                    <span className="mt-1 block text-[11px] text-slate-400">
                      por {session.closed_by_name || "-"}
                    </span>
                  </div>
                </div>
              </section>
            )}
            <div className="rounded-lg border border-primary/15 bg-primary/5 px-4 py-3 text-[11px] leading-5 text-slate-600">
              O esperado é calculado no servidor como abertura + entradas
              manuais + vendas em dinheiro + consumações em dinheiro - reversões
              em dinheiro - sangrias. Valores recebidos e troco não compõem esse cálculo.
            </div>
            <section className="card overflow-hidden">
              <div className="card-header"><div><h2 className="text-sm font-bold">Resumo operacional completo</h2><p className="mt-1 text-[11px] text-slate-500">Produção da sessão, benefícios e recebimentos por forma.</p></div><Banknote className="size-5 text-slate-300" /></div>
              <div className="grid gap-6 p-5 lg:grid-cols-4">
                <div className="space-y-2 text-xs"><h3 className="font-bold text-dark">Vendas ({summary.sales.count})</h3><p className="flex justify-between"><span>Bruto</span><strong>{formatBRL(summary.sales.gross)}</strong></p><p className="flex justify-between"><span>Descontos promocionais</span><strong className="text-danger">- {formatBRL(summary.sales.promotion_discount)}</strong></p><p className="flex justify-between"><span>Descontos manuais</span><strong className="text-danger">- {formatBRL(summary.sales.manual_discount)}</strong></p><p className="flex justify-between border-t border-slate-100 pt-2"><span>Faturamento de vendas</span><strong>{formatBRL((summary as CanonicalCashSummary).sales_revenue)}</strong></p><p className="flex justify-between"><span>Taxa de serviço</span><strong>{formatBRL(summary.sales.service_fee)}</strong></p><p className="flex justify-between"><span>Vendas com taxa de serviço</span><strong className="text-primary">{formatBRL(summary.sales.customer_total)}</strong></p>{summary.sales.commission !== undefined && <p className="flex justify-between"><span>Comissões atribuídas</span><strong>{formatBRL(summary.sales.commission)}</strong></p>}<p className="flex justify-between"><span>Cancelamentos</span><strong>{summary.sales.cancellations.count} · {formatBRL(summary.sales.cancellations.value)}</strong></p></div>
                <div className="space-y-2 text-xs"><h3 className="font-bold text-dark">Consumações ({summary.consumptions.count})</h3><p className="flex justify-between"><span>Valor de referência</span><strong>{formatBRL(summary.consumptions.reference)}</strong></p><p className="flex justify-between"><span>Consumação cobrada</span><strong>{formatBRL((summary as CanonicalCashSummary).consumption_charged)}</strong></p><p className="flex justify-between border-t border-slate-100 pt-2"><span>Benefício concedido</span><strong className="text-warning">{formatBRL(summary.consumptions.benefit)}</strong></p><p className="flex justify-between"><span>Cancelamentos</span><strong>{summary.consumptions.cancellations.count} · {formatBRL(summary.consumptions.cancellations.value)}</strong></p></div>
                <div className="space-y-2 text-xs"><h3 className="font-bold text-dark">Pagamentos</h3>{summary.payment_totals.length ? summary.payment_totals.map((payment) => <p key={`${payment.payment_method_code}:${payment.payment_method_name}`} className="flex justify-between"><span>{payment.payment_method_name}</span><strong>{formatBRL(payment.amount)}</strong></p>) : <p className="text-slate-500">Nenhum pagamento finalizado.</p>}<p className="flex justify-between border-t border-slate-100 pt-2"><span>Dinheiro líquido no caixa</span><strong className="text-primary">{formatBRL(summary.cash_payments)}</strong></p></div>
                <div className="space-y-2 text-xs"><h3 className="font-bold text-dark">Componentes da gaveta</h3><p className="flex justify-between"><span>Abertura</span><strong>{formatBRL(summary.opening_amount)}</strong></p><p className="flex justify-between"><span>Entradas manuais</span><strong>{formatBRL(summary.manual_entries)}</strong></p><p className="flex justify-between"><span>Vendas em dinheiro</span><strong>{formatBRL(summary.sale_cash)}</strong></p><p className="flex justify-between"><span>Consumações em dinheiro</span><strong>{formatBRL(summary.consumption_cash)}</strong></p><p className="flex justify-between text-danger"><span>Reversões ({summary.cash_cancellations})</span><strong>- {formatBRL(summary.cash_reversals)}</strong></p><p className="flex justify-between text-danger"><span>Sangrias</span><strong>- {formatBRL(summary.withdrawals)}</strong></p><p className="flex justify-between border-t border-slate-100 pt-2"><span>Esperado</span><strong>{formatBRL(summary.expected_amount)}</strong></p></div>
              </div>
            </section>
            <section className="card overflow-hidden">
              <div className="card-header">
                <div>
                  <h2 className="text-sm font-bold">Linha do tempo</h2>
                  <p className="mt-1 text-[11px] text-slate-500">
                    Abertura, entradas, sangrias, vendas em dinheiro,
                     consumações em dinheiro, reversões e fechamento.
                  </p>
                </div>
                <History className="size-5 text-slate-300" />
              </div>
              {timelineLoading ? (
                <TableLoading columns={3} />
              ) : timeline?.results.length ? (
                <ul className="divide-y divide-slate-100">
                  {timeline.results.map((event) => {
                    const displayedAmount = event.kind === "withdrawal" && !event.amount.startsWith("-") ? `-${event.amount}` : event.amount;
                    const canOpenSale = event.sale?.operation_type === "consumption" ? canViewConsumptions : canViewSales;
                    return (
                    <li
                      key={event.id}
                      className="flex items-start gap-3 px-5 py-4 text-sm"
                    >
                      <span
                        className={`mt-1 size-2.5 shrink-0 rounded-full ${event.kind === "open" || event.kind === "close" ? "bg-primary" : event.kind === "withdrawal" || event.kind === "cancellation" ? "bg-danger" : event.kind === "manual_entry" ? "bg-success" : "bg-slate-400"}`}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-baseline justify-between gap-2">
                          <strong className="text-dark">{event.label}</strong>
                          <span className="font-bold">
                            {formatBRL(displayedAmount)}
                          </span>
                        </div>
                        <p className="mt-0.5 text-[11px] text-slate-500">
                          <span className="whitespace-nowrap">
                            {formatDate(event.timestamp)}
                          </span>
                          {event.details && (
                            <span className="ml-1">· {event.details}</span>
                          )}
                        </p>
                        {(event.beneficiary_name || event.reason || event.registered_by_name) && <div className="mt-2 grid gap-1 text-[11px] text-slate-500 sm:grid-cols-3">{event.beneficiary_name && <p><strong className="text-dark">Beneficiário:</strong> {event.beneficiary_name}</p>}{event.reason && <p><strong className="text-dark">Motivo:</strong> {event.reason}</p>}{event.registered_by_name && <p><strong className="text-dark">Registrado por:</strong> {event.registered_by_name}</p>}</div>}
                        {event.sale && canOpenSale && (
                          <Link
                            className="mt-1 inline-block text-[11px] font-bold text-primary"
                            href={`${event.sale.operation_type === "consumption" ? "/consumacoes" : "/vendas"}/${event.sale.id}`}
                          >
                            Abrir {event.sale.number} →
                          </Link>
                        )}
                      </div>
                    </li>
                  );})}
                </ul>
              ) : (
                <EmptyState
                  title="Sem eventos na linha do tempo"
                  description="A atividade da sessão aparecerá aqui."
                />
              )}
            </section>
            <section className="card overflow-hidden">
              <div className="card-header">
                <div>
                  <h2 className="text-sm font-bold">Histórico da sessão</h2>
                  <p className="mt-1 text-[11px] text-slate-500">
                    Entradas e sangrias em ordem de registro.
                  </p>
                </div>
                <History className="size-5 text-slate-300" />
              </div>
              <PeriodFilter
                className="border-b border-slate-100 p-4"
                value={period}
                showActions
                onApply={(next) => {
                  setPeriod(next);
                  syncMovementPeriodUrl(next);
                  void loadMovements(movementsPath(next));
                }}
                onClear={() => {
                  const emptyPeriod = { start: "", end: "" };
                  setPeriod(emptyPeriod);
                  syncMovementPeriodUrl(emptyPeriod);
                  void loadMovements(movementsPath(emptyPeriod));
                }}
              />
              {movementsLoading ? (
                <TableLoading columns={7} />
              ) : movements?.results.length ? (
                <>
                  <div className="table-wrap">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Data</th>
                          <th>Tipo</th>
                          <th>Categoria</th>
                          <th>Beneficiário</th>
                          <th>Impacto no resultado</th>
                          <th>Valor</th>
                          <th>Motivo</th>
                          <th>Responsável</th>
                        </tr>
                      </thead>
                      <tbody>
                        {movements.results.map((movement) => (
                          <tr key={movement.id}>
                            <td className="whitespace-nowrap">
                              {formatDate(movement.created_at)}
                            </td>
                            <td>
                              <span
                                className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-semibold ${movement.movement_type === "manual_entry" ? "bg-success/10 text-emerald-700" : "bg-danger/10 text-red-700"}`}
                              >
                                {movement.movement_type === "manual_entry"
                                  ? "Entrada"
                                  : "Sangria"}
                              </span>
                            </td>
                            <td>{movement.category_label || "-"}</td>
                            <td>{movement.beneficiary?.name || "-"}</td>
                            <td>{movement.result_effect === "operating_expense" ? "Despesa operacional" : movement.result_effect === "neutral" ? "Não afeta" : "Não classificado"}</td>
                            <td className="font-bold">
                              {formatBRL(movement.amount)}
                            </td>
                            <td className="min-w-56">{movement.reason}</td>
                            <td>{movement.user_name}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <Pagination
                    count={movements.count}
                    next={movements.next}
                    previous={movements.previous}
                    onPage={loadMovements}
                  />
                </>
              ) : (
                <EmptyState
                  title="Sem movimentos manuais"
                  description="As entradas e sangrias desta sessão aparecerão aqui."
                />
              )}
            </section>
          </>
        ) : (
          !error && (
            <div className="card">
              <EmptyState
                title="Sessão não encontrada"
                description="A sessão não existe ou não pertence à filial atual."
              />
            </div>
          )
        )}
      </div>
      <Modal
        open={!!action}
        title={action === "entry" ? "Registrar entrada" : "Registrar sangria"}
        description="O movimento será associado a esta sessão e ao seu usuário."
        onClose={() => !saving && setAction(null)}
        size="md"
      >
        <form onSubmit={submitMovement}>
          <div className="space-y-4 p-5 sm:p-6">
            {error && <Alert message={error} />}
            <Field label="Valor">
              <div className="relative">
                <span className="absolute left-3 top-2.5 text-sm font-semibold text-slate-400">
                  R$
                </span>
                <Input
                  autoFocus
                  className="pl-10"
                  required
                  inputMode="decimal"
                  value={amount}
                  onChange={(event) => setAmount(event.target.value)}
                  placeholder="0,00"
                />
              </div>
            </Field>
            {action === "withdrawal" && (
              <>
                <Field label="Categoria">
                  <select
                    className="input"
                    required
                    value={category}
                    onChange={(event) => {
                      setCategory(event.target.value as WithdrawalCategory);
                      setBeneficiaryId("");
                    }}
                  >
                    <option value="">Selecione</option>
                    {withdrawalCategories.map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Impacto no resultado">
                  <select className="input" required value={resultEffect} onChange={(event) => setResultEffect(event.target.value as "operating_expense" | "neutral")}>
                    <option value="">Selecione</option>
                    <option value="operating_expense">Despesa operacional</option>
                    <option value="neutral">Não afeta · transferência/cofre</option>
                  </select>
                </Field>
                <Field
                  label="Beneficiário"
                  optional={!!category && !beneficiaryRequired.has(category)}
                >
                  <select
                    className="input"
                    required={!!category && beneficiaryRequired.has(category)}
                    value={beneficiaryId}
                    onChange={(event) => setBeneficiaryId(event.target.value)}
                    disabled={beneficiariesLoading}
                  >
                    <option value="">
                      {beneficiariesLoading ? "Carregando..." : "Selecione"}
                    </option>
                    {beneficiaries
                      .filter(
                        (item) =>
                          !category ||
                          category === "advance" ||
                          ["supplier", "other"].includes(category) ||
                          item.user_type === category,
                      )
                      .map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.name}
                        </option>
                      ))}
                  </select>
                </Field>
              </>
            )}
            <Field label="Motivo">
              <Textarea
                required
                maxLength={500}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder={
                  action === "entry"
                    ? "Ex.: Reforço de troco"
                    : "Ex.: Pagamento de fornecedor"
                }
              />
            </Field>
          </div>
          <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-4">
            <Button
              type="button"
              variant="secondary"
              disabled={saving}
              onClick={() => setAction(null)}
            >
              Cancelar
            </Button>
            <Button
              type="submit"
              variant={action === "withdrawal" ? "danger" : "primary"}
              loading={saving}
              disabled={action === "withdrawal" && beneficiariesLoading}
            >
              {action === "entry" ? "Confirmar entrada" : "Confirmar sangria"}
            </Button>
          </div>
        </form>
      </Modal>
      <Modal open={cancelOpen} title="Anular sessão" description="A sessão deixará a listagem padrão, mas seus movimentos e auditoria serão preservados." onClose={() => !saving && setCancelOpen(false)}>
        <form onSubmit={cancelSession}>
          <div className="space-y-4 p-5">
            <Field label="Motivo"><Textarea required value={cancellationReason} onChange={(event) => setCancellationReason(event.target.value)} disabled={saving} /></Field>
          </div>
          <div className="flex justify-end gap-2 border-t border-subtle px-5 py-4">
            <Button type="button" variant="secondary" onClick={() => setCancelOpen(false)} disabled={saving}>Cancelar</Button>
            <Button type="submit" variant="danger" loading={saving}>Anular sessão</Button>
          </div>
        </form>
      </Modal>
    </>
  );
}

export default function SessionPage() {
  return (
    <AdminGuard requiredPermissions={[permissions.viewCashRegister]}>
      <SessionDetail />
    </AdminGuard>
  );
}
