"use client";

import Link from "next/link";
import { ArrowLeft, Banknote, Building2, Check, CirclePause, Clock3, Headphones, Landmark, Play, RefreshCw, ShieldAlert, UserRoundCog, X } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { CriticalFields, Empty, ErrorBlock, LoadingBlock, Modal, Notice, Status } from "@/components/ui";
import { SupportAccessActions, SupportSessionCreated } from "@/components/support-access";
import { api } from "@/lib/api";
import { dateInput, dateTime, money } from "@/lib/format";
import type { Plan, PlanVersion, SubscriptionRequest, SupportSession, TenantDetail } from "@/lib/types";
import { useAuth } from "@/providers/auth-provider";

type Action = "approve" | "reject" | "admin-suspend" | "admin-resume" | "archive" | "transfer-owner" | "map-subscription" | "billing-mode" | "financial-suspend" | "financial-resume" | "extend-trial" | "process-lifecycle" | "payment" | "request-approve" | "request-reject" | "support";
const actionTitles: Record<Action, string> = {
  approve: "Aprovar tenant", reject: "Rejeitar cadastro", "admin-suspend": "Suspender administrativamente", "admin-resume": "Retomar operacao", archive: "Arquivar tenant", "transfer-owner": "Transferir titularidade", "map-subscription": "Mapear assinatura", "billing-mode": "Alterar modalidade", "financial-suspend": "Suspender financeiramente", "financial-resume": "Retomar por regularizacao", "extend-trial": "Estender trial", "process-lifecycle": "Processar ciclo agora", payment: "Registrar pagamento", "request-approve": "Aprovar solicitacao", "request-reject": "Rejeitar solicitacao", support: "Iniciar Support Session",
};
const billingActions: Action[] = ["map-subscription", "billing-mode", "financial-suspend", "financial-resume", "extend-trial", "process-lifecycle", "payment", "request-approve", "request-reject"];

export default function TenantDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const canTenants = can("platform.tenants.manage");
  const canPlans = can("platform.plans.manage");
  const canBill = can("platform.billing.manage");
  const canSupport = can("platform.support.manage");
  const [tenant, setTenant] = useState<TenantDetail | null>(null);
  const [requests, setRequests] = useState<SubscriptionRequest[] | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [tenantError, setTenantError] = useState<unknown>(null);
  const [requestsError, setRequestsError] = useState<unknown>(null);
  const [plansError, setPlansError] = useState<unknown>(null);
  const [supportError, setSupportError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const [tab, setTab] = useState("overview");
  const [action, setAction] = useState<Action | null>(null);
  const [requestId, setRequestId] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const [password, setPassword] = useState("");
  const [actionError, setActionError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const [reload, setReload] = useState(0);
  const [values, setValues] = useState<Record<string, string>>({});
  const [createdSupportSession, setCreatedSupportSession] = useState<SupportSession | null>(null);

  useEffect(() => {
    if (!canTenants) return;
    let active = true;
    api.get<TenantDetail>(`platform/tenants/${id}/`)
      .then((detail) => { if (active) { setTenant({ ...detail, subscription: detail.subscription ?? null, payments: detail.payments ?? [], support_sessions: detail.support_sessions ?? [] }); setTenantError(null); } })
      .catch((value) => { if (active) setTenantError(value); });
    return () => { active = false; };
  }, [canTenants, id, reload]);

  useEffect(() => {
    if (!canTenants || !canBill) return;
    let active = true;
    api.list<SubscriptionRequest>(`platform/subscription-requests/?company=${id}`)
      .then((value) => { if (active) { setRequests(value); setRequestsError(null); } })
      .catch((value) => { if (active) setRequestsError(value); });
    return () => { active = false; };
  }, [canBill, canTenants, id, reload]);

  useEffect(() => {
    if (!canTenants || !canBill || !canPlans) return;
    let active = true;
    api.list<Plan>("platform/plans/")
      .then((value) => { if (active) { setPlans(value); setPlansError(null); } })
      .catch((value) => { if (active) setPlansError(value); });
    return () => { active = false; };
  }, [canBill, canPlans, canTenants, reload]);

  function open(next: Action, extra: Record<string, string> = {}, selectedRequest?: number) {
    const subscription = tenant?.subscription;
    setAction(next); setRequestId(selectedRequest ?? null); setReason(""); setPassword(""); setActionError(null);
    setValues({
      billing_mode: subscription?.billing_mode || "PAID",
      days: "7",
      target_user_id: "",
      plan_version: "",
      mode: "READ_ONLY",
      impersonated_user: "",
      amount: subscription ? plans.flatMap((plan) => plan.versions).find((version) => version.id === subscription.plan_version)?.price || "" : "",
      paid_at: dateInput(),
      idempotency_key: next === "payment" ? crypto.randomUUID() : "",
      payment_method: "PIX",
      proof_reference: "",
      note: "",
      ...extra,
    });
  }

  function close() { setAction(null); setActionError(null); }
  async function execute(event: FormEvent) {
    event.preventDefault();
    if (!tenant || !action || (billingActions.includes(action) && !canBill) || (action === "support" && !canSupport)) return;
    setSaving(true); setActionError(null);
    const critical = { reason, current_password: password };
    try {
      if (["approve", "reject", "admin-suspend", "admin-resume", "archive"].includes(action)) {
        await api.post(`platform/tenants/${tenant.id}/${action}/`, critical);
      } else if (action === "transfer-owner") {
        await api.post(`platform/tenants/${tenant.id}/transfer-owner/`, { ...critical, target_user_id: Number(values.target_user_id) });
      } else if (action === "map-subscription") {
        await api.post(`platform/tenants/${tenant.id}/map-subscription/`, { ...critical, plan_version: Number(values.plan_version), billing_mode: values.billing_mode });
      } else if (["billing-mode", "financial-suspend", "financial-resume", "extend-trial", "process-lifecycle"].includes(action)) {
        const payload: Record<string, unknown> = { ...critical };
        if (action === "billing-mode") payload.billing_mode = values.billing_mode;
        if (action === "extend-trial") payload.days = Number(values.days);
        await api.post(`platform/subscriptions/${tenant.subscription?.id}/${action}/`, payload);
      } else if (action === "payment") {
        await api.post("platform/payments/", { ...critical, subscription: tenant.subscription?.id, amount: values.amount, paid_at: new Date(values.paid_at).toISOString(), payment_method: values.payment_method, proof_reference: values.proof_reference, note: values.note, idempotency_key: values.idempotency_key });
      } else if (action === "request-approve" || action === "request-reject") {
        await api.post(`platform/subscription-requests/${requestId}/${action === "request-approve" ? "approve" : "reject"}/`, critical);
      } else if (action === "support") {
        const session = await api.post<SupportSession>("platform/support-sessions/", { company: tenant.id, mode: values.mode, reason, current_password: password, impersonated_user: values.impersonated_user ? Number(values.impersonated_user) : null });
        setCreatedSupportSession(session);
      }
      setNotice(`${actionTitles[action]} concluido com sucesso.`); close(); setReload((value) => value + 1);
    } catch (value) { setActionError(value); } finally { setSaving(false); }
  }

  async function endSupport(sessionId: number) {
    try { await api.post(`platform/support-sessions/${sessionId}/end/`); setNotice("Support Session encerrada."); setSupportError(null); setReload((value) => value + 1); } catch (value) { setSupportError(value); }
  }

  if (!canTenants) return <div className="space-y-4"><ErrorBlock error={new Error("Seu perfil nao possui acesso aos dados de gestao do tenant.")} />{canBill && <Link href="/billing" className="btn btn-signal">Abrir area de cobranca</Link>}</div>;
  if (tenantError) return <ErrorBlock error={tenantError} retry={() => { setTenantError(null); setTenant(null); setReload((value) => value + 1); }} />;
  if (!tenant) return <LoadingBlock label="Montando contexto 360 do tenant" />;
  const activeSessions = tenant.support_sessions.filter((session) => !session.ended_at && new Date(session.expires_at) > new Date());
  const versions = plans.flatMap((plan) => plan.versions).filter((version) => version.is_active);

  return <div className="enter space-y-6"><Link href="/tenants" className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-steel/65 hover:text-ink"><ArrowLeft size={15} />Todos os tenants</Link>
    <header className="border border-ink bg-ink p-5 text-white sm:p-7"><div className="flex flex-col justify-between gap-6 lg:flex-row lg:items-end"><div><div className="flex items-center gap-3"><span className="flex size-10 items-center justify-center bg-signal text-ink"><Building2 size={19} /></span><div><p className="font-mono text-[9px] uppercase tracking-[.15em] text-white/45">Tenant ID {tenant.id}</p><h1 className="text-2xl font-black tracking-tight sm:text-3xl">{tenant.trade_name}</h1></div></div><p className="mt-4 text-sm text-white/50">{tenant.legal_name}{tenant.cnpj ? ` / ${tenant.cnpj}` : ""}</p></div><div className="flex flex-wrap items-center gap-3"><Status value={tenant.effective_status} positive={tenant.can_operate} /><span className={`font-mono text-[10px] uppercase ${tenant.can_operate ? "text-signal" : "text-red-300"}`}>{tenant.can_operate ? "Operacao liberada" : "Operacao bloqueada"}</span></div></div></header>
    {notice && <Notice message={notice} />}
    {createdSupportSession && <SupportSessionCreated session={createdSupportSession} />}
    <nav className="flex gap-1 overflow-x-auto border-b border-line" aria-label="Secoes do tenant">{[["overview", "Visao geral"], ...(canBill ? [["subscription", "Assinatura"], ["requests", `Solicitacoes (${requests?.filter((item) => item.status === "PENDING").length ?? "-"})`], ["billing", "Pagamentos"]] : []), ...(canSupport ? [["support", `Suporte (${activeSessions.length})`]] : [])].map(([key, text]) => <button key={key} onClick={() => setTab(key)} className={`whitespace-nowrap border-b-2 px-4 py-3 text-xs font-bold uppercase tracking-wider ${tab === key ? "border-ink text-ink" : "border-transparent text-steel/50 hover:text-ink"}`}>{text}</button>)}</nav>

    {tab === "overview" && <Overview tenant={tenant} open={open} canSupport={canSupport} />}
    {tab === "subscription" && canBill && <div className="space-y-4">{plansError ? <ErrorBlock error={plansError} retry={() => { setPlansError(null); setReload((value) => value + 1); }} /> : null}<SubscriptionPanel tenant={tenant} open={open} canPlans={canPlans && !plansError} /></div>}
    {tab === "billing" && canBill && <BillingPanel tenant={tenant} open={open} />}
    {tab === "requests" && canBill && (requestsError ? <ErrorBlock error={requestsError} retry={() => { setRequestsError(null); setRequests(null); setReload((value) => value + 1); }} /> : requests ? <RequestsPanel requests={requests} versions={versions} open={open} /> : <LoadingBlock label="Carregando solicitacoes de assinatura" />)}
    {tab === "support" && canSupport && <div className="space-y-4">{supportError ? <ErrorBlock error={supportError} /> : null}<SupportPanel tenant={tenant} activeSessions={activeSessions} open={open} endSupport={endSupport} /></div>}

    {action && (!billingActions.includes(action) || canBill) && (action !== "support" || canSupport) && <Modal title={actionTitles[action]} description="A justificativa e a reautenticacao serao registradas no trilho de auditoria." onClose={close} wide={action === "payment"}><form onSubmit={execute}><ActionInputs action={action} values={values} setValues={setValues} tenant={tenant} versions={versions} />{actionError ? <div className="px-5 pt-4"><ErrorBlock error={actionError} /></div> : null}<CriticalFields reason={reason} password={password} onReason={setReason} onPassword={setPassword} error={actionError} /><div className="flex justify-end gap-2 p-5"><button type="button" className="btn btn-quiet" onClick={close}>Cancelar</button><button className={`btn ${["reject", "archive", "admin-suspend", "financial-suspend"].includes(action) ? "btn-danger" : "btn-signal"}`} disabled={saving || !reason || !password}>{saving ? "Processando..." : "Confirmar acao"}</button></div></form></Modal>}
  </div>;
}

function Overview({ tenant, open, canSupport }: { tenant: TenantDetail; open: (action: Action) => void; canSupport: boolean }) {
  const state = tenant.saas_state;
  return <div className="grid gap-6 xl:grid-cols-[1fr_360px]"><div className="grid gap-6"><section className="panel"><div className="panel-head"><div><p className="eyebrow">Identidade e titularidade</p><h2 className="mt-1 font-bold">Dados cadastrais</h2></div><button className="btn btn-quiet" onClick={() => open("transfer-owner")}><UserRoundCog size={15} />Transferir Owner</button></div><div className="grid gap-px bg-line sm:grid-cols-2"><Datum label="E-mail" value={tenant.email} /><Datum label="Telefone" value={tenant.phone} /><Datum label="Owner" value={tenant.owner?.email || "Nao definido"} /><Datum label="Estado operacional" value={tenant.operational_status} /></div></section><section className="panel"><div className="panel-head"><div><p className="eyebrow">Capacidade ativa</p><h2 className="mt-1 font-bold">Estrutura do tenant</h2></div></div><div className="grid gap-px bg-line sm:grid-cols-2"><div className="bg-paper p-5"><p className="eyebrow">Filiais</p><p className="mt-3 text-3xl font-black">{tenant.branches.length}</p><div className="mt-4 space-y-2">{tenant.branches.map((branch) => <div className="flex justify-between text-xs" key={branch.id}><span>{branch.name}{branch.is_matrix ? " (Matriz)" : ""}</span><span className="font-mono uppercase text-steel/50">{branch.status}</span></div>)}</div></div><div className="bg-paper p-5"><p className="eyebrow">Usuarios vinculados</p><p className="mt-3 text-3xl font-black">{tenant.users.length}</p><p className="mt-4 text-xs text-steel/60">{tenant.users.filter((user) => user.is_active).length} acessos ativos</p></div></div></section></div>
    <aside className="panel self-start"><div className="panel-head"><div><p className="eyebrow">Controles criticos</p><h2 className="mt-1 font-bold">Governanca</h2></div><ShieldAlert size={18} className="text-steel/50" /></div><div className="grid gap-2 p-4">{state?.approval_status === "PENDING" && <><button className="btn btn-signal justify-start" onClick={() => open("approve")}><Check size={15} />Aprovar cadastro</button><button className="btn btn-danger justify-start" onClick={() => open("reject")}><X size={15} />Rejeitar cadastro</button></>}{state?.is_admin_suspended ? <button className="btn btn-signal justify-start" onClick={() => open("admin-resume")}><Play size={15} />Retomar operacao</button> : <button className="btn btn-quiet justify-start" onClick={() => open("admin-suspend")}><CirclePause size={15} />Suspender administrativamente</button>}{canSupport && <button className="btn btn-quiet justify-start" onClick={() => open("support")}><Headphones size={15} />Iniciar suporte</button>}<button className="btn btn-danger mt-3 justify-start" onClick={() => open("archive")}><ShieldAlert size={15} />Arquivar tenant</button></div></aside></div>;
}

function SubscriptionPanel({ tenant, open, canPlans }: { tenant: TenantDetail; open: (action: Action) => void; canPlans: boolean }) {
  const subscription = tenant.subscription;
  if (!subscription) return <section className="panel"><Empty title="Tenant sem assinatura corrente" detail={canPlans ? "Mapeie uma versao de plano para habilitar a governanca SaaS." : "Seu perfil nao pode consultar o catalogo necessario para mapear uma assinatura."} />{canPlans && <div className="flex justify-center pb-8"><button className="btn btn-signal" onClick={() => open("map-subscription")}><Landmark size={15} />Mapear assinatura</button></div>}</section>;
  return <div className="grid gap-6 xl:grid-cols-[1fr_360px]"><section className="panel"><div className="panel-head"><div><p className="eyebrow">Contrato corrente</p><h2 className="mt-1 text-xl font-black">{subscription.plan_name} v{subscription.plan_version_number}</h2></div><Status value={subscription.status} /></div><div className="grid gap-px bg-line sm:grid-cols-2"><Datum label="Modalidade" value={subscription.billing_mode} /><Datum label="Versao" value={`#${subscription.plan_version}`} /><Datum label="Inicio do periodo" value={dateTime(subscription.current_period_start)} /><Datum label="Fim do periodo" value={dateTime(subscription.current_period_end)} /><Datum label="Fim do trial" value={dateTime(subscription.trial_ends_at)} /><Datum label="Cancelamento no fim" value={subscription.cancel_at_period_end ? "Sim" : "Nao"} /></div>{subscription.cancellation_reason && <div className="border-t border-line p-5"><p className="eyebrow">Motivo de cancelamento</p><p className="mt-2 text-sm">{subscription.cancellation_reason}</p></div>}</section><aside className="panel self-start"><div className="panel-head"><p className="font-bold">Acoes de assinatura</p></div><div className="grid gap-2 p-4"><button className="btn btn-quiet justify-start" onClick={() => open("billing-mode")}><RefreshCw size={15} />Alterar modalidade</button><button className="btn btn-quiet justify-start" onClick={() => open("extend-trial")}><Clock3 size={15} />Estender trial</button>{subscription.status === "SUSPENDED_FINANCIAL" ? <button className="btn btn-signal justify-start" onClick={() => open("financial-resume")}><Play size={15} />Retomar financeiro</button> : <button className="btn btn-quiet justify-start" onClick={() => open("financial-suspend")}><CirclePause size={15} />Suspender financeiro</button>}<button className="btn btn-quiet justify-start" onClick={() => open("process-lifecycle")}><RefreshCw size={15} />Processar ciclo</button></div></aside></div>;
}

function BillingPanel({ tenant, open }: { tenant: TenantDetail; open: (action: Action) => void }) {
  return <section className="panel"><div className="panel-head"><div><p className="eyebrow">Historico append-only</p><h2 className="mt-1 font-bold">Pagamentos confirmados</h2></div>{tenant.subscription && <button className="btn btn-signal" onClick={() => open("payment")}><Banknote size={15} />Registrar pagamento</button>}</div>{tenant.payments.length === 0 ? <Empty title="Nenhum pagamento registrado" detail="Confirmacoes manuais aparecerao neste historico imutavel." /> : <div className="table-wrap"><table className="data-table"><thead><tr><th>Pagamento</th><th>Competencia</th><th>Metodo</th><th>Operador</th></tr></thead><tbody>{tenant.payments.map((payment) => <tr key={payment.id}><td><p className="font-black">{money(payment.amount)}</p><p className="text-xs text-steel/55">{dateTime(payment.paid_at)}</p></td><td>{dateTime(payment.competency_start)}<br /><span className="text-xs text-steel/50">ate {dateTime(payment.competency_end)}</span></td><td>{payment.payment_method}{payment.proof_reference && <p className="max-w-48 truncate text-xs text-steel/50">{payment.proof_reference}</p>}</td><td className="text-xs">{payment.actor_email}</td></tr>)}</tbody></table></div>}</section>;
}

function RequestsPanel({ requests, versions, open }: { requests: SubscriptionRequest[]; versions: PlanVersion[]; open: (action: Action, extra?: Record<string, string>, requestId?: number) => void }) {
  return <section className="panel"><div className="panel-head"><div><p className="eyebrow">Decisoes comerciais</p><h2 className="mt-1 font-bold">Solicitacoes do Owner</h2></div></div>{requests.length === 0 ? <Empty title="Sem solicitacoes" detail="Mudancas de plano e cancelamentos solicitados pelo Owner aparecerao aqui." /> : <div className="divide-y divide-line">{requests.map((request) => <div className="grid gap-4 p-5 lg:grid-cols-[1fr_auto] lg:items-center" key={request.id}><div><div className="flex flex-wrap items-center gap-2"><p className="font-bold">{request.request_type === "PLAN_CHANGE" ? "Mudanca de plano" : "Cancelamento"}</p><Status value={request.status} /></div><p className="mt-2 text-sm text-steel/70">{request.reason}</p><p className="mt-2 font-mono text-[10px] uppercase text-steel/45">{dateTime(request.created_at)}{request.requested_plan_version ? ` / destino: ${versions.find((item) => item.id === request.requested_plan_version)?.plan_name || "versao"} #${request.requested_plan_version}` : ""}</p></div>{request.status === "PENDING" && <div className="flex gap-2"><button className="btn btn-signal" onClick={() => open("request-approve", {}, request.id)}>Aprovar</button><button className="btn btn-danger" onClick={() => open("request-reject", {}, request.id)}>Rejeitar</button></div>}</div>)}</div>}</section>;
}

function SupportPanel({ tenant, activeSessions, open, endSupport }: { tenant: TenantDetail; activeSessions: TenantDetail["support_sessions"]; open: (action: Action) => void; endSupport: (id: number) => Promise<void> }) {
  return <section className="panel"><div className="panel-head"><div><p className="eyebrow">Acesso temporario e auditado</p><h2 className="mt-1 font-bold">Support Sessions</h2></div><button className="btn btn-signal" onClick={() => open("support")}><Headphones size={15} />Iniciar sessao</button></div>{tenant.support_sessions.length === 0 ? <Empty title="Sem sessoes de suporte" detail="Nenhum acesso temporario foi iniciado neste tenant." /> : <div className="divide-y divide-line">{tenant.support_sessions.map((session) => { const active = activeSessions.some((item) => item.id === session.id); return <div className="grid gap-4 p-5 lg:grid-cols-[1fr_auto] lg:items-center" key={session.id}><div><div className="flex flex-wrap items-center gap-2"><Status value={active ? "ACTIVE" : session.ended_at ? "ENDED" : "EXPIRED"} /><span className="font-mono text-[10px] font-bold uppercase">{session.mode.replace("_", " ")}</span></div><p className="mt-3 text-sm">{session.reason}</p><p className="mt-2 text-xs text-steel/55">{session.actor_email} / expira {dateTime(session.expires_at)}{session.impersonated_user ? ` / usuario #${session.impersonated_user}` : " / sem impersonacao"}</p></div>{active && <div className="flex flex-wrap gap-2"><SupportAccessActions sessionId={session.id} /><button className="btn btn-danger" onClick={() => void endSupport(session.id)}>Encerrar</button></div>}</div>; })}</div>}</section>;
}

function ActionInputs({ action, values, setValues, tenant, versions }: { action: Action; values: Record<string, string>; setValues: (values: Record<string, string>) => void; tenant: TenantDetail; versions: PlanVersion[] }) {
  const field = (key: string, value: string) => setValues({ ...values, [key]: value });
  if (action === "transfer-owner") return <div className="p-5"><div className="field"><label>Novo Owner</label><select className="input" value={values.target_user_id} onChange={(e) => field("target_user_id", e.target.value)} required><option value="">Selecione um usuario vinculado</option>{tenant.users.filter((user) => user.is_active && !user.is_owner).map((user) => <option value={user.user_id} key={user.user_id}>{user.user__email} (#{user.user_id})</option>)}</select></div></div>;
  if (action === "map-subscription") return <div className="grid gap-4 p-5 sm:grid-cols-2"><Field label="Plano / versao"><select className="input" value={values.plan_version} onChange={(e) => field("plan_version", e.target.value)} required><option value="">Selecione</option>{versions.map((version) => <option value={version.id} key={version.id}>{version.plan_name} v{version.version}</option>)}</select></Field><BillingMode value={values.billing_mode} onChange={(value) => field("billing_mode", value)} /></div>;
  if (action === "billing-mode") return <div className="p-5"><BillingMode value={values.billing_mode} onChange={(value) => field("billing_mode", value)} /></div>;
  if (action === "extend-trial") return <div className="p-5"><Field label="Dias adicionais"><input className="input" type="number" min="1" value={values.days} onChange={(e) => field("days", e.target.value)} required /></Field></div>;
  if (action === "payment") return <div className="grid gap-4 p-5 sm:grid-cols-2"><Field label="Valor confirmado"><input className="input" type="number" min="0.01" step="0.01" value={values.amount} onChange={(e) => field("amount", e.target.value)} required /></Field><Field label="Data do pagamento"><input className="input" type="datetime-local" value={values.paid_at} onChange={(e) => field("paid_at", e.target.value)} required /></Field><Field label="Metodo"><input className="input" value={values.payment_method} onChange={(e) => field("payment_method", e.target.value)} required /></Field><Field label="Referencia do comprovante"><input className="input" value={values.proof_reference} onChange={(e) => field("proof_reference", e.target.value)} placeholder="receipts/arquivo.pdf ou https://..." /></Field><div className="field sm:col-span-2"><label>Nota</label><textarea className="textarea" value={values.note} onChange={(e) => field("note", e.target.value)} /></div><p className="sm:col-span-2 text-xs text-steel/60">A competencia sera derivada pelo backend a partir do periodo corrente autoritativo da assinatura.</p><p className="sm:col-span-2 font-mono text-[10px] uppercase text-steel/50">Idempotencia preservada nesta tentativa: {values.idempotency_key}</p></div>;
  if (action === "support") return <div className="grid gap-4 p-5 sm:grid-cols-2"><Field label="Modo"><select className="input" value={values.mode} onChange={(e) => field("mode", e.target.value)}><option value="READ_ONLY">Somente leitura</option><option value="READ_WRITE">Leitura e escrita</option></select></Field><Field label="Impersonar usuario (opcional)"><select className="input" value={values.impersonated_user} onChange={(e) => field("impersonated_user", e.target.value)}><option value="">Ator de plataforma</option>{tenant.users.filter((user) => user.is_active).map((user) => <option value={user.user_id} key={user.user_id}>{user.user__email}</option>)}</select></Field><p className="sm:col-span-2 text-xs text-steel/60">Sessoes de escrita e contextos impersonados exigem reautenticacao e ficam limitados ao tenant.</p></div>;
  return <div className="p-5 text-sm text-steel/70">Revise o impacto desta operacao antes de confirmar.</div>;
}

function BillingMode({ value, onChange }: { value: string; onChange: (value: string) => void }) { return <Field label="Modalidade"><select className="input" value={value} onChange={(e) => onChange(e.target.value)}><option value="PAID">Pago</option><option value="FREE">Gratuito</option><option value="INTERNAL">Interno</option></select></Field>; }
function Datum({ label, value }: { label: string; value: React.ReactNode }) { return <div className="bg-paper p-5"><p className="eyebrow">{label}</p><div className="mt-2 text-sm font-semibold">{value || "-"}</div></div>; }
function Field({ label, children }: { label: string; children: React.ReactNode }) { return <div className="field"><label>{label}</label>{children}</div>; }
