"use client";

import Link from "next/link";
import { ArrowRight, Building2, Plus, Search } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { CriticalFields, Empty, ErrorBlock, LoadingBlock, Modal, Notice, Status } from "@/components/ui";
import { api } from "@/lib/api";
import type { Plan, TenantSummary } from "@/lib/types";
import { useAuth } from "@/providers/auth-provider";

interface CreateForm {
  trade_name: string; legal_name: string; cnpj: string; email: string; phone: string;
  owner_email: string; owner_password: string; plan_version: string; billing_mode: string;
}
const emptyForm: CreateForm = { trade_name: "", legal_name: "", cnpj: "", email: "", phone: "", owner_email: "", owner_password: "", plan_version: "", billing_mode: "PAID" };

export default function TenantsPage() {
  const { can } = useAuth();
  const canTenants = can("platform.tenants.manage");
  const canPlans = can("platform.plans.manage");
  const [tenants, setTenants] = useState<TenantSummary[] | null>(null);
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [plansError, setPlansError] = useState<unknown>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<CreateForm>(emptyForm);
  const [reason, setReason] = useState("");
  const [password, setPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!canTenants) return;
    let active = true;
    const suffix = query ? `?search=${encodeURIComponent(query)}` : "";
    api.get<TenantSummary[]>(`platform/tenants/${suffix}`).then((value) => { if (active) setTenants(value); }).catch((value) => { if (active) setError(value); });
    return () => { active = false; };
  }, [canTenants, query, reload]);
  useEffect(() => {
    if (!canPlans) return;
    let active = true;
    api.list<Plan>("platform/plans/").then((value) => { if (active) { setPlans(value); setPlansError(null); } }).catch((value) => { if (active) setPlansError(value); });
    return () => { active = false; };
  }, [canPlans, reload]);

  const versions = (plans || []).flatMap((plan) => plan.versions).filter((version) => version.is_active);
  async function create(event: FormEvent) {
    event.preventDefault();
    if (!plans) { setActionError(plansError || new Error("O catalogo de planos ainda esta carregando.")); return; }
    setSaving(true); setActionError(null);
    try {
      await api.post("platform/tenants/", { ...form, plan_version: Number(form.plan_version), idempotency_key: crypto.randomUUID(), reason, current_password: password });
      setCreating(false); setForm(emptyForm); setReason(""); setPassword(""); setNotice("Tenant provisionado com sucesso."); setReload((value) => value + 1);
    } catch (value) { setActionError(value); } finally { setSaving(false); }
  }

  if (!canTenants) return <ErrorBlock error={new Error("Seu perfil nao possui acesso a tenants.")} />;
  return <div className="enter space-y-6"><div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="eyebrow">Governanca de contas</p><h1 className="mt-2 text-3xl font-black tracking-tight sm:text-4xl">Tenants</h1><p className="mt-2 text-sm text-steel/65">Pesquisa, provisionamento e acesso ao contexto 360.</p></div>{canPlans && <button className="btn btn-signal" onClick={() => setCreating(true)}><Plus size={16} />Provisionar tenant</button>}</div>
    {notice && <Notice message={notice} />}{plansError ? <ErrorBlock error={plansError} retry={() => { setPlansError(null); setPlans(null); setReload((value) => value + 1); }} /> : null}
    <section className="panel"><div className="panel-head"><form className="flex w-full max-w-xl gap-2" onSubmit={(event) => { event.preventDefault(); setError(null); setTenants(null); setQuery(search.trim()); }}><div className="relative flex-1"><Search className="absolute left-3 top-3 text-steel/45" size={16} /><input className="input pl-9" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Nome, razao social ou CNPJ" aria-label="Pesquisar tenants" /></div><button className="btn btn-primary">Buscar</button></form><span className="hidden font-mono text-[10px] uppercase text-steel/50 sm:block">{tenants?.length ?? "-"} registros</span></div>
      {error ? <div className="p-5"><ErrorBlock error={error} retry={() => { setError(null); setTenants(null); setReload((value) => value + 1); }} /></div> : !tenants ? <LoadingBlock label="Consultando tenants" /> : tenants.length === 0 ? <Empty title="Nenhum tenant encontrado" detail="Revise o termo pesquisado ou crie um tenant manualmente." /> : <div className="table-wrap"><table className="data-table"><thead><tr><th>Tenant</th><th>Estado efetivo</th><th>Operacao</th><th className="text-right">Contexto</th></tr></thead><tbody>{tenants.map((tenant) => <tr key={tenant.id}><td><div className="flex items-center gap-3"><span className="flex size-9 items-center justify-center bg-ink text-signal"><Building2 size={16} /></span><div><p className="font-bold">{tenant.trade_name}</p><p className="font-mono text-[10px] text-steel/50">ID {tenant.id}</p></div></div></td><td><Status value={tenant.effective_status} positive={tenant.can_operate} /></td><td><span className={`text-xs font-bold uppercase ${tenant.can_operate ? "text-cyan-800" : "text-alert"}`}>{tenant.can_operate ? "Liberada" : "Bloqueada"}</span></td><td className="text-right"><Link href={`/tenants/${tenant.id}`} className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-wider hover:underline">Abrir 360 <ArrowRight size={15} /></Link></td></tr>)}</tbody></table></div>}
    </section>
    {creating && <Modal title="Provisionar tenant" description="Cria empresa, matriz, Owner e assinatura em uma unica operacao." onClose={() => setCreating(false)} wide><form onSubmit={create}><div className="grid gap-4 p-5 sm:grid-cols-2"><Field label="Nome fantasia"><input className="input" value={form.trade_name} onChange={(e) => setForm({ ...form, trade_name: e.target.value })} required /></Field><Field label="Razao social"><input className="input" value={form.legal_name} onChange={(e) => setForm({ ...form, legal_name: e.target.value })} required /></Field><Field label="CNPJ"><input className="input" value={form.cnpj} onChange={(e) => setForm({ ...form, cnpj: e.target.value })} /></Field><Field label="E-mail da empresa"><input className="input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field><Field label="Telefone"><input className="input" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field><Field label="Plano / versao"><select className="input" value={form.plan_version} onChange={(e) => setForm({ ...form, plan_version: e.target.value })} required><option value="">Selecione</option>{versions.map((version) => <option value={version.id} key={version.id}>{version.plan_name} v{version.version}</option>)}</select></Field><Field label="E-mail do novo Owner"><input className="input" type="email" value={form.owner_email} onChange={(e) => setForm({ ...form, owner_email: e.target.value })} required /></Field><Field label="Senha inicial do Owner"><input className="input" type="password" value={form.owner_password} onChange={(e) => setForm({ ...form, owner_password: e.target.value })} required autoComplete="new-password" /></Field><Field label="Modalidade"><select className="input" value={form.billing_mode} onChange={(e) => setForm({ ...form, billing_mode: e.target.value })}><option value="PAID">Pago</option><option value="FREE">Gratuito</option><option value="INTERNAL">Interno</option></select></Field></div>{actionError ? <div className="px-5 pb-4"><ErrorBlock error={actionError} /></div> : null}<CriticalFields reason={reason} password={password} onReason={setReason} onPassword={setPassword} error={actionError} /><div className="flex justify-end gap-2 p-5"><button type="button" className="btn btn-quiet" onClick={() => setCreating(false)}>Cancelar</button><button className="btn btn-signal" disabled={saving || !reason || !password}>{saving ? "Provisionando..." : "Confirmar provisionamento"}</button></div></form></Modal>}
  </div>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) { return <div className="field"><label>{label}</label>{children}</div>; }
