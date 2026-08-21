"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Calculator, LockKeyhole } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { DifferenceBadge, MoneyKpi } from "@/components/cash-ui";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, ConfirmDialog, EmptyState, Field, Input, Spinner } from "@/components/ui";
import { canonicalMoney, moneyToCents, normalizeMoney, subtractMoney } from "@/lib/cash";
import { formatBRL, formatDate } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { CashSession, CashSummary } from "@/types";

function CloseSession() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { currentCompany, currentBranch } = useAuth();
  const contextRef = useRef("");
  contextRef.current = `${currentCompany?.id || ""}:${currentBranch?.id || ""}:${id}`;
  const [session, setSession] = useState<CashSession | null>(null);
  const [summary, setSummary] = useState<CashSummary | null>(null);
  const [informed, setInformed] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState("");
  const [errorStatus, setErrorStatus] = useState(0);
  const difference = summary ? subtractMoney(informed, summary.expected_amount) : null;

  useEffect(() => {
    const context = contextRef.current;
    setSession(null);
    setSummary(null);
    setInformed("");
    setError("");
    setErrorStatus(0);
    setConfirming(false);
    if (!currentBranch || !id) {
      setLoading(false);
      return;
    }
    setLoading(true);
    Promise.all([http.get<CashSession>(`cash-sessions/${id}/`), http.get<CashSummary>(`cash-sessions/${id}/summary/`)])
      .then(([sessionResponse, summaryResponse]) => {
        if (contextRef.current === context) {
          setSession(sessionResponse);
          setSummary(summaryResponse);
        }
      })
      .catch((caught) => {
        if (contextRef.current === context) {
          const apiError = caught instanceof ApiError ? caught : null;
          setErrorStatus(apiError?.status || 0);
          setError(apiError?.status === 404 ? "A sessão não existe ou não pertence à filial atual." : apiError?.status === 403 ? "Você não possui permissão para fechar caixa nesta filial." : apiError?.message || "Não foi possível carregar a conferência do caixa.");
        }
      })
      .finally(() => {
        if (contextRef.current === context) setLoading(false);
      });
  }, [id, currentCompany?.id, currentBranch?.id]);

  function requestConfirmation(event: React.FormEvent) {
    event.preventDefault();
    if (moneyToCents(informed) === null) {
      setError("Informe um valor válido, maior ou igual a zero e com no máximo duas casas decimais.");
      return;
    }
    setError("");
    setConfirming(true);
  }

  async function close() {
    if (!summary || moneyToCents(informed) === null) return;
    const context = contextRef.current;
    setSaving(true);
    setError("");
    try {
      const closed = await http.post<CashSession>(`cash-sessions/${id}/close/`, { closing_amount_informed: normalizeMoney(informed) });
      if (contextRef.current === context) router.replace(`/caixas/sessoes/${closed.id}`);
    } catch (caught) {
      if (contextRef.current === context) {
        setConfirming(false);
        setError(caught instanceof ApiError ? caught.message : "Não foi possível fechar o caixa.");
      }
    } finally {
      if (contextRef.current === context) setSaving(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Fechar caixa"
        description={`Filial atual: ${currentBranch?.name || "nenhuma filial selecionada"}. O esperado é fornecido pelo servidor.`}
        action={
          <Link href={`/caixas/sessoes/${id}`} className="btn btn-secondary">
            <ArrowLeft className="size-4" />
            Voltar à sessão
          </Link>
        }
      />
      <div className="mx-auto max-w-5xl space-y-4 p-4 sm:p-6 lg:p-8">
        <nav aria-label="Etapas do fechamento" className="card flex items-center gap-2 overflow-x-auto px-4 py-3 text-xs">
          <Link href="/caixas" className="font-semibold text-primary">
            Operação
          </Link>
          <span className="text-slate-300">/</span>
          <span className="font-semibold text-primary">Fechar</span>
          <span className="text-slate-300">/</span>
          <strong>Conferir e confirmar</strong>
        </nav>
        {error && <Alert message={error} />}
        {loading ? (
          <div className="card flex min-h-64 items-center justify-center text-primary">
            <Spinner className="size-7" />
          </div>
        ) : session && summary ? (
          session.status === "closed" ? (
            <div className="card">
              <EmptyState title="Esta sessão já está fechada" description={`Fechada em ${formatDate(session.closed_at || "")} por ${session.closed_by_name || "outro usuário"}. Nenhum novo fechamento pode ser enviado.`} />
              <div className="flex justify-center pb-8">
                <Link href={`/caixas/sessoes/${id}`} className="btn btn-primary">
                  Ver fechamento
                </Link>
              </div>
            </div>
          ) : (
            <>
              <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <MoneyKpi label="Abertura" value={summary.opening_amount} />
                <MoneyKpi label="Entradas manuais" value={summary.manual_entries} tone="success" />
                <MoneyKpi label="Vendas em dinheiro" value={summary.sale_cash} tone="success" />
                <MoneyKpi label="Consumações em dinheiro" value={summary.consumption_cash} tone="success" />
                <MoneyKpi label="Reversões em dinheiro" value={summary.cash_reversals} tone="danger" />
                <MoneyKpi label="Sangrias" value={summary.withdrawals} tone="danger" />
                <MoneyKpi label="Esperado" value={summary.expected_amount} tone="primary" />
              </section>
              <section className="card overflow-hidden">
                <div className="card-header">
                  <div>
                    <h2 className="text-sm font-bold">Conferência operacional</h2>
                    <p className="mt-1 text-[11px] text-slate-500">Revise produção, recebimentos e componentes da gaveta antes de informar o numerário.</p>
                  </div>
                </div>
                <div className="grid gap-6 p-5 text-xs sm:grid-cols-2 lg:grid-cols-4">
                  <div className="space-y-2">
                    <h3 className="font-bold">Vendas ({summary.sales.count})</h3>
                    <p className="flex justify-between">
                      <span>Bruto</span>
                      <strong>{formatBRL(summary.sales.gross)}</strong>
                    </p>
                    <p className="flex justify-between">
                      <span>Descontos promocionais</span>
                      <strong>- {formatBRL(summary.sales.promotion_discount)}</strong>
                    </p>
                    <p className="flex justify-between">
                      <span>Descontos manuais</span>
                      <strong>- {formatBRL(summary.sales.manual_discount)}</strong>
                    </p>
                    <p className="flex justify-between">
                      <span>Faturamento de vendas</span>
                      <strong>{formatBRL(summary.sales.effective_revenue)}</strong>
                    </p>
                    <p className="flex justify-between">
                      <span>Taxa de serviço</span>
                      <strong>{formatBRL(summary.sales.service_fee)}</strong>
                    </p>
                    <p className="flex justify-between">
                      <span>Vendas com taxa de serviço</span>
                      <strong>{formatBRL(summary.sales.customer_total)}</strong>
                    </p>
                    {summary.sales.commission !== undefined && (
                      <p className="flex justify-between">
                        <span>Comissão autorizada</span>
                        <strong>{formatBRL(summary.sales.commission)}</strong>
                      </p>
                    )}
                    <p className="flex justify-between">
                      <span>Cancelamentos</span>
                      <strong>
                        {summary.sales.cancellations.count} · {formatBRL(summary.sales.cancellations.value)}
                      </strong>
                    </p>
                  </div>
                  <div className="space-y-2">
                    <h3 className="font-bold">Consumações ({summary.consumptions.count})</h3>
                    <p className="flex justify-between">
                      <span>Referência</span>
                      <strong>{formatBRL(summary.consumptions.reference)}</strong>
                    </p>
                    <p className="flex justify-between">
                      <span>Consumação cobrada</span>
                      <strong>{formatBRL(summary.consumptions.charged)}</strong>
                    </p>
                    <p className="flex justify-between">
                      <span>Benefício</span>
                      <strong>{formatBRL(summary.consumptions.benefit)}</strong>
                    </p>
                    <p className="flex justify-between">
                      <span>Cancelamentos</span>
                      <strong>
                        {summary.consumptions.cancellations.count} · {formatBRL(summary.consumptions.cancellations.value)}
                      </strong>
                    </p>
                  </div>
                  <div className="space-y-2">
                    <h3 className="font-bold">Pagamentos</h3>
                    {summary.payment_totals.length ? (
                      summary.payment_totals.map((payment) => (
                        <p key={`${payment.payment_method_code}:${payment.payment_method_name}`} className="flex justify-between">
                          <span>{payment.payment_method_name}</span>
                          <strong>{formatBRL(payment.amount)}</strong>
                        </p>
                      ))
                    ) : (
                      <p className="text-slate-500">Nenhum recebimento finalizado.</p>
                    )}
                    <p className="flex justify-between border-t border-slate-100 pt-2">
                      <span>Dinheiro líquido</span>
                      <strong>{formatBRL(summary.cash_payments)}</strong>
                    </p>
                  </div>
                  <div className="space-y-2">
                    <h3 className="font-bold">Componentes da gaveta</h3>
                    <p className="flex justify-between">
                      <span>Abertura</span>
                      <strong>{formatBRL(summary.opening_amount)}</strong>
                    </p>
                    <p className="flex justify-between">
                      <span>Entradas manuais</span>
                      <strong>{formatBRL(summary.manual_entries)}</strong>
                    </p>
                    <p className="flex justify-between">
                      <span>Vendas em dinheiro</span>
                      <strong>{formatBRL(summary.sale_cash)}</strong>
                    </p>
                    <p className="flex justify-between">
                      <span>Consumações em dinheiro</span>
                      <strong>{formatBRL(summary.consumption_cash)}</strong>
                    </p>
                    <p className="flex justify-between">
                      <span>Reversões ({summary.cash_cancellations})</span>
                      <strong>- {formatBRL(summary.cash_reversals)}</strong>
                    </p>
                    <p className="flex justify-between">
                      <span>Sangrias</span>
                      <strong>- {formatBRL(summary.withdrawals)}</strong>
                    </p>
                    <p className="flex justify-between border-t border-slate-100 pt-2">
                      <span>Esperado</span>
                      <strong>{formatBRL(summary.expected_amount)}</strong>
                    </p>
                  </div>
                </div>
              </section>
              <form className="card overflow-hidden" onSubmit={requestConfirmation}>
                <div className="card-header">
                  <div>
                    <h2 className="text-sm font-bold">Conferência de numerário</h2>
                    <p className="mt-1 text-[11px] text-slate-500">
                      {session.register_name || session.cash_register_name} · sessão #{session.id}
                    </p>
                  </div>
                  <Calculator className="size-5 text-slate-300" />
                </div>
                <div className="grid gap-6 p-5 sm:grid-cols-2 sm:p-6">
                  <Field label="Valor esperado (somente leitura)">
                    <Input readOnly value={formatBRL(summary.expected_amount)} className="font-bold text-primary" />
                  </Field>
                  <Field label="Valor contado e informado">
                    <div className="relative">
                      <span className="absolute left-3 top-2.5 text-sm font-semibold text-slate-400">R$</span>
                      <Input autoFocus className="pl-10" required inputMode="decimal" value={informed} onChange={(event) => setInformed(event.target.value)} placeholder="0,00" />
                    </div>
                  </Field>
                  <div className="sm:col-span-2 rounded-lg border border-slate-200 bg-slate-50 p-5">
                    <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">Prévia da diferença</p>
                    {difference === null ? (
                      <p className="mt-2 text-xs text-slate-500">Informe a contagem para comparar com o esperado.</p>
                    ) : (
                      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                        <DifferenceBadge value={difference} />
                        <span className="text-xs text-slate-500">
                          Informado {formatBRL(canonicalMoney(informed) || "0.00")} - esperado {formatBRL(summary.expected_amount)}
                        </span>
                      </div>
                    )}
                  </div>
                  <div className="sm:col-span-2 rounded-lg border border-warning/25 bg-warning/8 p-4 text-xs leading-5 text-amber-900">
                    <strong className="block">Como o valor esperado é composto</strong>
                    <span>Abertura + entradas manuais + vendas em dinheiro + consumações em dinheiro - reversões em dinheiro - sangrias. Valores recebidos e troco não compõem o cálculo. Ao confirmar, o backend recalcula o esperado e grava os valores do esperado, informado e diferença.</span>
                  </div>
                </div>
                <div className="flex flex-col-reverse gap-2 border-t border-slate-100 px-5 py-4 sm:flex-row sm:justify-end sm:px-6">
                  <Link href={`/caixas/sessoes/${id}`} className="btn btn-secondary">
                    Cancelar
                  </Link>
                  <Button type="submit" variant="danger">
                    <LockKeyhole className="size-4" />
                    Revisar e fechar
                  </Button>
                </div>
              </form>
            </>
          )
        ) : errorStatus === 404 || errorStatus === 403 ? (
          <div className="card">
            <EmptyState title={errorStatus === 404 ? "Sessão não encontrada" : "Acesso não autorizado"} description={error} />
            <div className="flex justify-center pb-8">
              <Link href="/caixas" className="btn btn-primary">
                Voltar à operação de caixa
              </Link>
            </div>
          </div>
        ) : (
          !error && (
            <div className="card">
              <EmptyState title="Sessão não encontrada" description="A sessão não existe ou não pertence à filial atual." />
            </div>
          )
        )}
      </div>
      <ConfirmDialog open={confirming} title="Confirmar fechamento" message={`O caixa será fechado com ${formatBRL(canonicalMoney(informed) || "0.00")} informado. O servidor recalculará o esperado; esta operação não poderá ser desfeita.`} confirmLabel="Fechar caixa" danger loading={saving} onClose={() => !saving && setConfirming(false)} onConfirm={close} />
    </>
  );
}

export default function CloseSessionPage() {
  return (
    <AdminGuard requiredPermissions={[permissions.closeCashRegister]}>
      <CloseSession />
    </AdminGuard>
  );
}
