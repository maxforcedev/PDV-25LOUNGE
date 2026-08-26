"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, ArrowRightLeft, CalendarClock, CreditCard, History, LifeBuoy, Users } from "lucide-react";
import { Alert, Button, EmptyState, Field, Modal, Select, Spinner, Textarea, Input } from "@/components/ui";
import { fieldError, formatBRL, formatDate } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { useAuth } from "@/providers/auth-provider";
import type { BillingRecord, OwnerSubscriptionContext, PublicPlan, SubscriptionChangeRequest, SupportSessionContext } from "@/types";

const STATUS_LABELS: Record<string, string> = {
  PENDING_APPROVAL: "Aguardando aprovação",
  TRIALING: "Período de teste",
  ACTIVE: "Ativa",
  PAST_DUE: "Pagamento pendente",
  RESTRICTED: "Acesso restrito",
  SUSPENDED_FINANCIAL: "Suspensa financeiramente",
  SUSPENDED_ADMIN: "Suspensa administrativamente",
  TRIAL_EXPIRED: "Período de teste encerrado",
  CANCELLED: "Cancelada",
  ARCHIVED: "Arquivada",
  PENDING: "Pendente",
  APPROVED: "Aprovada",
  REJECTED: "Rejeitada",
};

const BILLING_LABELS = { PAID: "Pago", FREE: "Gratuito", INTERNAL: "Interno" } as const;

function StatusPill({ status }: { status: string }) {
  const positive = ["ACTIVE", "APPROVED", "TRIALING"].includes(status);
  const warning = ["PENDING", "PENDING_APPROVAL", "PAST_DUE", "RESTRICTED"].includes(status);
  return <span className={`inline-flex rounded-full border px-2.5 py-1 text-[11px] font-bold ${positive ? "border-success/30 bg-success-surface text-success-strong" : warning ? "border-warning/30 bg-warning-surface text-warning-strong" : "border-danger/25 bg-danger-surface text-danger-strong"}`}>{STATUS_LABELS[status] || status}</span>;
}

function capabilityLabel(code: string) {
  return code === "users.max" ? "Usuários com login" : code === "branches.max" ? "Filiais ativas" : code;
}

type Action = "change" | "cancel" | null;

export function SubscriptionCenter() {
  const { currentCompany } = useAuth();
  const companyId = currentCompany?.id;
  const [context, setContext] = useState<OwnerSubscriptionContext | null>(null);
  const [payments, setPayments] = useState<BillingRecord[]>([]);
  const [requests, setRequests] = useState<SubscriptionChangeRequest[]>([]);
  const [supportHistory, setSupportHistory] = useState<SupportSessionContext[]>([]);
  const [plans, setPlans] = useState<PublicPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [reload, setReload] = useState(0);
  const [action, setAction] = useState<Action>(null);
  const [requestedPlan, setRequestedPlan] = useState("");
  const [reason, setReason] = useState("");
  const [password, setPassword] = useState("");
  const [actionError, setActionError] = useState("");
  const [actionFields, setActionFields] = useState<Record<string, string[]>>({});
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!companyId) return;
    let active = true;
    setLoading(true);
    setError("");
    const query = `?company=${encodeURIComponent(companyId)}`;
    Promise.all([
      http.get<OwnerSubscriptionContext>(`saas/owner/subscription/${query}`),
      http.get<BillingRecord[]>(`saas/owner/payments/${query}`),
      http.get<SubscriptionChangeRequest[]>(`saas/owner/change-requests/${query}`),
      http.get<SupportSessionContext[]>(`saas/owner/support-history/${query}`),
      http.getPublic<PublicPlan[]>("public/plans/"),
    ]).then(([subscriptionData, paymentData, requestData, supportData, planData]) => {
      if (!active) return;
      setContext(subscriptionData);
      setPayments(paymentData);
      setRequests(requestData);
      setSupportHistory(supportData);
      setPlans(planData);
      const alternative = planData.find((plan) => plan.id !== subscriptionData.subscription.plan_version);
      setRequestedPlan((current) => current || String(alternative?.id || ""));
    }).catch((caught) => active && setError(caught instanceof Error ? caught.message : "Não foi possível carregar a assinatura."))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [companyId, reload]);

  function openAction(next: Exclude<Action, null>) {
    setAction(next);
    setReason("");
    setPassword("");
    setActionError("");
    setActionFields({});
  }

  function closeAction() {
    if (!submitting) setAction(null);
  }

  async function submitAction(event: React.FormEvent) {
    event.preventDefault();
    if (!companyId || !action) return;
    setSubmitting(true);
    setActionError("");
    setActionFields({});
    try {
      if (action === "change") {
        await http.post<SubscriptionChangeRequest>("saas/owner/change-requests/", {
          company: companyId,
          requested_plan_version: Number(requestedPlan),
          reason: reason.trim(),
          current_password: password,
        });
        setNotice("Solicitação de mudança enviada para análise.");
      } else {
        await http.post<SubscriptionChangeRequest>("saas/owner/cancel/", {
          company: companyId,
          reason: reason.trim(),
          current_password: password,
        });
        setNotice("Solicitação de cancelamento registrada para o fim do período.");
      }
      setAction(null);
      setReload((current) => current + 1);
    } catch (caught) {
      if (caught instanceof ApiError) {
        setActionError(caught.message);
        setActionFields(caught.fields);
      } else setActionError("Não foi possível enviar a solicitação.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <div className="flex min-h-[calc(100vh-9rem)] items-center justify-center text-primary"><Spinner className="size-7" /><span className="sr-only">Carregando assinatura</span></div>;
  if (error || !context) return <div className="px-4 py-8 sm:px-6 lg:px-8"><Alert message={error || "Assinatura não encontrada."} /><Button variant="secondary" className="mt-4" onClick={() => setReload((current) => current + 1)}>Tentar novamente</Button></div>;

  const subscription = context.subscription;
  const hasPendingChange = requests.some((item) => item.request_type === "PLAN_CHANGE" && item.status === "PENDING");
  const availablePlans = plans.filter((plan) => plan.id !== subscription.plan_version);

  return (
    <>
      <div className="border-b border-subtle bg-surface px-4 py-6 sm:px-6 lg:px-8">
        <p className="mb-1 text-[10px] font-bold uppercase tracking-[0.16em] text-primary">Área do Owner</p>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div><h1 className="text-xl font-bold tracking-tight text-fg">Assinatura</h1><p className="mt-1 text-xs text-muted">Plano, uso, pagamentos e histórico comercial de {currentCompany?.trade_name}.</p></div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Button variant="secondary" onClick={() => openAction("change")} disabled={hasPendingChange || !availablePlans.length}><ArrowRightLeft className="size-4" />Solicitar mudança</Button>
            <Button variant="secondary" className="border-danger/30 text-danger-strong hover:bg-danger-surface" onClick={() => openAction("cancel")} disabled={subscription.cancel_at_period_end || subscription.status === "CANCELLED"}><AlertTriangle className="size-4" />Solicitar cancelamento</Button>
          </div>
        </div>
      </div>

      <main className="space-y-6 px-4 py-6 sm:px-6 lg:px-8">
        {notice && <Alert type="success" message={notice} />}
        {!context.effective_status.includes("ACTIVE") && context.effective_status !== "TRIALING" && (
          <div className="rounded-lg border border-warning/30 bg-warning-surface p-4 text-sm text-warning-strong"><strong>{STATUS_LABELS[context.effective_status] || context.effective_status}.</strong> Esta área continua disponível para consulta e solicitações do Owner.</div>
        )}
        {subscription.cancel_at_period_end && <div className="rounded-lg border border-warning/30 bg-warning-surface p-4 text-sm text-warning-strong">O cancelamento está agendado para o fim do período atual, em <strong>{formatDate(subscription.current_period_end)}</strong>.</div>}

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4" aria-label="Resumo da assinatura">
          <div className="card p-5"><div className="flex items-start justify-between"><span className="text-xs font-semibold text-muted">Plano atual</span><CreditCard className="size-4 text-primary" /></div><strong className="mt-3 block text-xl text-fg">{subscription.plan_name}</strong><span className="mt-2 block text-[11px] text-muted">Versão {subscription.plan_version_number} · {BILLING_LABELS[subscription.billing_mode]}</span></div>
          <div className="card p-5"><div className="flex items-start justify-between"><span className="text-xs font-semibold text-muted">Situação efetiva</span><CalendarClock className="size-4 text-primary" /></div><div className="mt-3"><StatusPill status={context.effective_status} /></div><span className="mt-3 block text-[11px] text-muted">Status da assinatura: {STATUS_LABELS[subscription.status] || subscription.status}</span></div>
          <div className="card p-5"><div className="flex items-start justify-between"><span className="text-xs font-semibold text-muted">Período atual</span><History className="size-4 text-primary" /></div><strong className="mt-3 block text-sm text-fg">Até {formatDate(subscription.current_period_end)}</strong><span className="mt-2 block text-[11px] text-muted">Início em {formatDate(subscription.current_period_start)}</span></div>
          <div className="card p-5"><div className="flex items-start justify-between"><span className="text-xs font-semibold text-muted">Trial</span><CalendarClock className="size-4 text-primary" /></div><strong className="mt-3 block text-sm text-fg">{subscription.trial_ends_at ? `Até ${formatDate(subscription.trial_ends_at)}` : "Não aplicável"}</strong><span className="mt-2 block text-[11px] text-muted">Sem cartão ou gateway nesta versão</span></div>
        </section>

        <section className="card">
          <div className="card-header"><div><h2 className="text-sm font-bold text-fg">Uso e limites</h2><p className="mt-1 text-xs text-muted">Consumo atual dos recursos medidos pelo plano.</p></div><Users className="size-5 text-primary" /></div>
          <div className="grid gap-4 p-5 sm:grid-cols-2 sm:p-6">
            {context.usage.map((usage) => {
              const entitlement = context.entitlements.find((item) => item.capability_code === usage.capability_code);
              const limit = entitlement?.unlimited ? "Ilimitado" : String(entitlement?.limit_value ?? 0);
              const percent = entitlement?.unlimited || !entitlement?.limit_value ? 0 : Math.min(100, (usage.quantity / entitlement.limit_value) * 100);
              return <div key={usage.capability_code} className="rounded-lg border border-subtle bg-surface-muted p-4"><div className="flex items-center justify-between gap-3"><strong className="text-sm text-fg">{capabilityLabel(usage.capability_code)}</strong><span className="text-xs font-bold text-fg">{usage.quantity} / {limit}</span></div><div className="mt-3 h-2 overflow-hidden rounded-full bg-disabled-surface" aria-label={`${usage.quantity} usados de ${limit}`}><div className="h-full rounded-full bg-primary" style={{ width: entitlement?.unlimited ? "8%" : `${percent}%` }} /></div></div>;
            })}
          </div>
        </section>

        <section className="card">
          <div className="card-header"><div><h2 className="text-sm font-bold text-fg">Pagamentos confirmados</h2><p className="mt-1 text-xs text-muted">Histórico manual e imutável de confirmações.</p></div><CreditCard className="size-5 text-primary" /></div>
          {!payments.length ? <EmptyState title="Nenhum pagamento confirmado" description="As confirmações manuais aparecerão aqui quando forem registradas." /> : <div className="table-wrap"><table className="data-table"><caption className="sr-only">Histórico de pagamentos</caption><thead><tr><th>Pagamento</th><th>Valor</th><th>Método</th><th>Competência</th><th>Comprovante</th></tr></thead><tbody>{payments.map((payment) => <tr key={payment.id}><td>{formatDate(payment.paid_at)}</td><td className="font-bold">{formatBRL(payment.amount)}</td><td>{payment.payment_method}</td><td>{formatDate(payment.competency_start)} a {formatDate(payment.competency_end)}</td><td>{/^https:\/\//i.test(payment.proof_reference) ? <a href={payment.proof_reference} target="_blank" rel="noreferrer" className="font-semibold text-link hover:underline">Abrir</a> : payment.proof_reference || "-"}</td></tr>)}</tbody></table></div>}
        </section>

        <section className="card">
          <div className="card-header"><div><h2 className="text-sm font-bold text-fg">Solicitações</h2><p className="mt-1 text-xs text-muted">Mudanças de plano e cancelamentos enviados pela empresa.</p></div><ArrowRightLeft className="size-5 text-primary" /></div>
          {!requests.length ? <EmptyState title="Nenhuma solicitação" description="Solicitações comerciais aparecerão aqui com seu andamento." /> : <div className="divide-y divide-subtle">{requests.map((request) => { const plan = plans.find((item) => item.id === request.requested_plan_version); return <article key={request.id} className="grid gap-3 p-5 sm:grid-cols-[1fr_auto] sm:p-6"><div><div className="flex flex-wrap items-center gap-2"><strong className="text-sm text-fg">{request.request_type === "PLAN_CHANGE" ? `Mudança para ${plan?.name || `plano #${request.requested_plan_version}`}` : "Cancelamento"}</strong><StatusPill status={request.status} /></div><p className="mt-2 text-xs leading-5 text-muted">{request.reason}</p></div><time className="text-[11px] text-muted">{formatDate(request.created_at)}</time></article>; })}</div>}
        </section>

        <section className="card">
          <div className="card-header"><div><h2 className="text-sm font-bold text-fg">Histórico de suporte</h2><p className="mt-1 text-xs text-muted">Acessos temporários da equipe de suporte a esta empresa.</p></div><LifeBuoy className="size-5 text-primary" /></div>
          {!supportHistory.length ? <EmptyState title="Nenhum acesso de suporte" description="Sessões temporárias de suporte aparecerão aqui para consulta do Owner." /> : <div className="divide-y divide-subtle">{supportHistory.map((session) => { const active = !session.ended_at && new Date(session.expires_at) > new Date(); return <article key={session.id} className="grid gap-3 p-5 sm:grid-cols-[1fr_auto] sm:p-6"><div><div className="flex flex-wrap items-center gap-2"><strong className="text-sm text-fg">{session.actor_email || `Agente #${session.actor}`}</strong><span className="rounded-full bg-surface-muted px-2.5 py-1 text-[10px] font-bold text-muted">{session.mode === "READ_ONLY" ? "Somente leitura" : "Leitura e escrita"}</span>{active && <StatusPill status="ACTIVE" />}</div><p className="mt-2 text-xs leading-5 text-muted">{session.reason}</p>{session.impersonated_user && <p className="mt-1 text-[11px] text-muted">Usuário representado: {session.impersonated_user_name || `#${session.impersonated_user}`}</p>}</div><div className="text-left text-[11px] text-muted sm:text-right"><p>Início: {session.created_at ? formatDate(session.created_at) : "-"}</p><p className="mt-1">{session.ended_at ? `Encerrada: ${formatDate(session.ended_at)}` : `Expira: ${formatDate(session.expires_at)}`}</p></div></article>; })}</div>}
        </section>
      </main>

      <Modal open={action !== null} title={action === "change" ? "Solicitar mudança de plano" : "Solicitar cancelamento"} description="Esta ação exige motivo e confirmação com sua senha atual." onClose={closeAction} size="md">
        <form onSubmit={submitAction}>
          <div className="space-y-5 p-5 sm:p-6">
            {actionError && <Alert message={actionError} />}
            {action === "change" && <Field label="Novo plano" error={fieldError(actionFields, "requested_plan_version")}><Select required value={requestedPlan} onChange={(event) => setRequestedPlan(event.target.value)} aria-invalid={Boolean(fieldError(actionFields, "requested_plan_version"))} disabled={submitting}>{availablePlans.map((plan) => <option key={plan.id} value={plan.id}>{plan.name} · {formatBRL(plan.price)}</option>)}</Select></Field>}
            <Field label="Motivo" error={fieldError(actionFields, "reason")}><Textarea required value={reason} onChange={(event) => setReason(event.target.value)} placeholder={action === "change" ? "Explique por que este plano atende melhor a empresa" : "Informe o motivo do cancelamento"} aria-invalid={Boolean(fieldError(actionFields, "reason"))} disabled={submitting} /></Field>
            <Field label="Senha atual" error={fieldError(actionFields, "current_password")}><Input required type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} aria-invalid={Boolean(fieldError(actionFields, "current_password"))} disabled={submitting} /></Field>
            {action === "cancel" && <p className="rounded-md bg-warning-surface p-3 text-xs leading-5 text-warning-strong">O pedido agenda o cancelamento para o fim do período. Ele não exclui dados nem históricos.</p>}
          </div>
          <div className="flex flex-col-reverse gap-2 border-t border-subtle px-5 py-4 sm:flex-row sm:justify-end sm:px-6"><Button type="button" variant="secondary" onClick={closeAction} disabled={submitting}>Voltar</Button><Button type="submit" variant={action === "cancel" ? "danger" : "primary"} loading={submitting}>{action === "change" ? "Enviar solicitação" : "Confirmar cancelamento"}</Button></div>
        </form>
      </Modal>
    </>
  );
}
