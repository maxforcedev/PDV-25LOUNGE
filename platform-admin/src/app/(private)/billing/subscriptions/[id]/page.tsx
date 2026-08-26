"use client";

import Link from "next/link";
import { ArrowLeft, Banknote, CirclePause, Clock3, Play, RefreshCw } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { CriticalFields, Empty, ErrorBlock, LoadingBlock, Modal, Notice, Status } from "@/components/ui";
import { api } from "@/lib/api";
import { dateInput, dateTime, money } from "@/lib/format";
import type { Payment, Subscription, SubscriptionRequest } from "@/lib/types";
import { useAuth } from "@/providers/auth-provider";

type Action = "payment" | "billing-mode" | "financial-suspend" | "financial-resume" | "extend-trial" | "process-lifecycle" | "request-approve" | "request-reject";
const titles: Record<Action, string> = {
  payment: "Registrar pagamento",
  "billing-mode": "Alterar modalidade",
  "financial-suspend": "Suspender financeiramente",
  "financial-resume": "Retomar por regularizacao",
  "extend-trial": "Estender trial",
  "process-lifecycle": "Processar ciclo agora",
  "request-approve": "Aprovar solicitacao",
  "request-reject": "Rejeitar solicitacao",
};

export default function BillingSubscriptionPage() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const allowed = can("platform.billing.manage");
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [payments, setPayments] = useState<Payment[] | null>(null);
  const [requests, setRequests] = useState<SubscriptionRequest[] | null>(null);
  const [subscriptionError, setSubscriptionError] = useState<unknown>(null);
  const [paymentsError, setPaymentsError] = useState<unknown>(null);
  const [requestsError, setRequestsError] = useState<unknown>(null);
  const [action, setAction] = useState<Action | null>(null);
  const [requestId, setRequestId] = useState<number | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("");
  const [password, setPassword] = useState("");
  const [actionError, setActionError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!allowed) return;
    let active = true;
    api.get<Subscription>(`platform/subscriptions/${id}/`)
      .then((value) => { if (active) { setSubscription(value); setSubscriptionError(null); } })
      .catch((value) => { if (active) setSubscriptionError(value); });
    return () => { active = false; };
  }, [allowed, id, reload]);

  useEffect(() => {
    if (!allowed || !subscription) return;
    let active = true;
    api.list<Payment>(`platform/payments/?company=${subscription.company}`)
      .then((value) => { if (active) { setPayments(value.filter((item) => item.subscription === subscription.id)); setPaymentsError(null); } })
      .catch((value) => { if (active) setPaymentsError(value); });
    return () => { active = false; };
  }, [allowed, reload, subscription]);

  useEffect(() => {
    if (!allowed || !subscription) return;
    let active = true;
    api.list<SubscriptionRequest>(`platform/subscription-requests/?company=${subscription.company}`)
      .then((value) => { if (active) { setRequests(value.filter((item) => item.subscription === subscription.id)); setRequestsError(null); } })
      .catch((value) => { if (active) setRequestsError(value); });
    return () => { active = false; };
  }, [allowed, reload, subscription]);

  function open(next: Action, selectedRequest?: number) {
    setAction(next); setRequestId(selectedRequest ?? null); setReason(""); setPassword(""); setActionError(null);
    setValues({
      billing_mode: subscription?.billing_mode || "PAID",
      days: "7",
      amount: "",
      paid_at: dateInput(),
      payment_method: "PIX",
      proof_reference: "",
      note: "",
      idempotency_key: next === "payment" ? crypto.randomUUID() : "",
    });
  }

  async function execute(event: FormEvent) {
    event.preventDefault();
    if (!allowed || !subscription || !action) return;
    setSaving(true); setActionError(null);
    const critical = { reason, current_password: password };
    try {
      if (action === "payment") {
        await api.post("platform/payments/", { ...critical, subscription: subscription.id, amount: values.amount, paid_at: new Date(values.paid_at).toISOString(), payment_method: values.payment_method, proof_reference: values.proof_reference, note: values.note, idempotency_key: values.idempotency_key });
      } else if (action === "request-approve" || action === "request-reject") {
        await api.post(`platform/subscription-requests/${requestId}/${action === "request-approve" ? "approve" : "reject"}/`, critical);
      } else {
        const payload: Record<string, unknown> = { ...critical };
        if (action === "billing-mode") payload.billing_mode = values.billing_mode;
        if (action === "extend-trial") payload.days = Number(values.days);
        await api.post(`platform/subscriptions/${subscription.id}/${action}/`, payload);
      }
      setNotice(`${titles[action]} concluido com sucesso.`); setAction(null); setReload((value) => value + 1);
    } catch (value) { setActionError(value); } finally { setSaving(false); }
  }

  if (!allowed) return <ErrorBlock error={new Error("Seu perfil nao possui acesso a cobranca.")} />;
  if (subscriptionError) return <ErrorBlock error={subscriptionError} retry={() => { setSubscriptionError(null); setSubscription(null); setReload((value) => value + 1); }} />;
  if (!subscription) return <LoadingBlock label="Carregando assinatura" />;

  return <div className="enter space-y-6"><Link href="/billing" className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-steel/65 hover:text-ink"><ArrowLeft size={15} />Cobranca</Link>{notice && <Notice message={notice} />}<header className="border border-ink bg-ink p-5 text-white sm:p-7"><div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end"><div><p className="font-mono text-[9px] uppercase tracking-[.15em] text-white/45">Assinatura #{subscription.id} / Tenant #{subscription.company}</p><h1 className="mt-2 text-2xl font-black">{subscription.plan_name} v{subscription.plan_version_number}</h1><p className="mt-2 text-sm text-white/50">{subscription.billing_mode} / {dateTime(subscription.current_period_start)} ate {dateTime(subscription.current_period_end)}</p></div><Status value={subscription.status} /></div></header><div className="grid gap-6 xl:grid-cols-[1fr_340px]"><section className="panel"><div className="panel-head"><div><p className="eyebrow">Contrato de cobranca</p><h2 className="mt-1 font-bold">Ciclo atual</h2></div></div><div className="grid gap-px bg-line sm:grid-cols-2"><Datum label="Modalidade" value={subscription.billing_mode} /><Datum label="Estado" value={subscription.status} /><Datum label="Inicio do periodo" value={dateTime(subscription.current_period_start)} /><Datum label="Fim do periodo" value={dateTime(subscription.current_period_end)} /><Datum label="Fim do trial" value={dateTime(subscription.trial_ends_at)} /><Datum label="Cancelamento agendado" value={subscription.cancel_at_period_end ? "Sim" : "Nao"} /></div></section>{subscription.is_current && <aside className="panel self-start"><div className="panel-head"><p className="font-bold">Acoes de cobranca</p></div><div className="grid gap-2 p-4"><button className="btn btn-signal justify-start" onClick={() => open("payment")}><Banknote size={15} />Registrar pagamento</button><button className="btn btn-quiet justify-start" onClick={() => open("billing-mode")}><RefreshCw size={15} />Alterar modalidade</button><button className="btn btn-quiet justify-start" onClick={() => open("extend-trial")}><Clock3 size={15} />Estender trial</button>{subscription.status === "SUSPENDED_FINANCIAL" ? <button className="btn btn-signal justify-start" onClick={() => open("financial-resume")}><Play size={15} />Retomar financeiro</button> : <button className="btn btn-quiet justify-start" onClick={() => open("financial-suspend")}><CirclePause size={15} />Suspender financeiro</button>}<button className="btn btn-quiet justify-start" onClick={() => open("process-lifecycle")}><RefreshCw size={15} />Processar ciclo</button></div></aside>}</div>
    <section className="panel"><div className="panel-head"><div><p className="eyebrow">Append-only</p><h2 className="mt-1 font-bold">Pagamentos desta assinatura</h2></div></div>{paymentsError ? <div className="p-5"><ErrorBlock error={paymentsError} retry={() => { setPaymentsError(null); setPayments(null); setReload((value) => value + 1); }} /></div> : !payments ? <LoadingBlock label="Carregando pagamentos" /> : payments.length === 0 ? <Empty title="Nenhum pagamento" detail="Nao existem confirmacoes para esta assinatura." /> : <div className="table-wrap"><table className="data-table"><thead><tr><th>Valor</th><th>Pago em</th><th>Competencia derivada</th><th>Metodo</th></tr></thead><tbody>{payments.map((payment) => <tr key={payment.id}><td className="font-black">{money(payment.amount)}</td><td>{dateTime(payment.paid_at)}</td><td>{dateTime(payment.competency_start)} ate {dateTime(payment.competency_end)}</td><td>{payment.payment_method}</td></tr>)}</tbody></table></div>}</section>
    <section className="panel"><div className="panel-head"><div><p className="eyebrow">Decisoes comerciais</p><h2 className="mt-1 font-bold">Solicitacoes</h2></div></div>{requestsError ? <div className="p-5"><ErrorBlock error={requestsError} retry={() => { setRequestsError(null); setRequests(null); setReload((value) => value + 1); }} /></div> : !requests ? <LoadingBlock label="Carregando solicitacoes" /> : requests.length === 0 ? <Empty title="Sem solicitacoes" detail="Nao existem solicitacoes para esta assinatura." /> : <div className="divide-y divide-line">{requests.map((request) => <div className="flex flex-col justify-between gap-4 p-5 sm:flex-row sm:items-center" key={request.id}><div><div className="flex items-center gap-2"><p className="font-bold">{request.request_type.replaceAll("_", " ")}</p><Status value={request.status} /></div><p className="mt-2 text-sm text-steel/65">{request.reason}</p>{request.requested_plan_version && <p className="mt-1 font-mono text-[10px] text-steel/50">PLAN VERSION #{request.requested_plan_version}</p>}</div>{request.status === "PENDING" && <div className="flex gap-2"><button className="btn btn-signal" onClick={() => open("request-approve", request.id)}>Aprovar</button><button className="btn btn-danger" onClick={() => open("request-reject", request.id)}>Rejeitar</button></div>}</div>)}</div>}</section>
    {action && <Modal title={titles[action]} description="Operacao de cobranca protegida por reautenticacao." onClose={() => setAction(null)} wide={action === "payment"}><form onSubmit={execute}><ActionFields action={action} values={values} setValues={setValues} />{actionError ? <div className="px-5 pt-4"><ErrorBlock error={actionError} /></div> : null}<CriticalFields reason={reason} password={password} onReason={setReason} onPassword={setPassword} error={actionError} /><div className="flex justify-end gap-2 p-5"><button type="button" className="btn btn-quiet" onClick={() => setAction(null)}>Cancelar</button><button className={`btn ${["financial-suspend", "request-reject"].includes(action) ? "btn-danger" : "btn-signal"}`} disabled={saving || !reason || !password}>{saving ? "Processando..." : "Confirmar"}</button></div></form></Modal>}
  </div>;
}

function ActionFields({ action, values, setValues }: { action: Action; values: Record<string, string>; setValues: (value: Record<string, string>) => void }) {
  const field = (key: string, value: string) => setValues({ ...values, [key]: value });
  if (action === "payment") return <div className="grid gap-4 p-5 sm:grid-cols-2"><Field label="Valor confirmado"><input className="input" type="number" min="0.01" step="0.01" value={values.amount} onChange={(event) => field("amount", event.target.value)} required /></Field><Field label="Data do pagamento"><input className="input" type="datetime-local" value={values.paid_at} onChange={(event) => field("paid_at", event.target.value)} required /></Field><Field label="Metodo"><input className="input" value={values.payment_method} onChange={(event) => field("payment_method", event.target.value)} required /></Field><Field label="Referencia do comprovante"><input className="input" value={values.proof_reference} onChange={(event) => field("proof_reference", event.target.value)} /></Field><div className="field sm:col-span-2"><label>Nota</label><textarea className="textarea" value={values.note} onChange={(event) => field("note", event.target.value)} /></div><p className="sm:col-span-2 text-xs text-steel/60">A competencia sera derivada pelo backend. Idempotencia: {values.idempotency_key}</p></div>;
  if (action === "billing-mode") return <div className="p-5"><Field label="Modalidade"><select className="input" value={values.billing_mode} onChange={(event) => field("billing_mode", event.target.value)}><option value="PAID">Pago</option><option value="FREE">Gratuito</option><option value="INTERNAL">Interno</option></select></Field></div>;
  if (action === "extend-trial") return <div className="p-5"><Field label="Dias adicionais"><input className="input" type="number" min="1" value={values.days} onChange={(event) => field("days", event.target.value)} required /></Field></div>;
  return <div className="p-5 text-sm text-steel/65">Revise o impacto financeiro antes de confirmar.</div>;
}

function Datum({ label, value }: { label: string; value: React.ReactNode }) { return <div className="bg-paper p-5"><p className="eyebrow">{label}</p><div className="mt-2 text-sm font-semibold">{value || "-"}</div></div>; }
function Field({ label, children }: { label: string; children: React.ReactNode }) { return <div className="field"><label>{label}</label>{children}</div>; }
