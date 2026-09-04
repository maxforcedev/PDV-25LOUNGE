"use client";

import { Boxes, Check, ChevronRight, CircleDollarSign, LockKeyhole, Plus, Settings2 } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { CriticalFields, Empty, ErrorBlock, LoadingBlock, Modal, Notice, Status } from "@/components/ui";
import { api } from "@/lib/api";
import { money } from "@/lib/format";
import type { Capability, Entitlement, Plan, PlanVersion } from "@/lib/types";
import { useAuth } from "@/providers/auth-provider";

type Editor = "plan-create" | "plan-edit" | "version-create" | "version-edit" | "entitlement-create" | "entitlement-edit";

export default function PlansPage() {
  const { can } = useAuth();
  const allowed = can("platform.plans.manage");
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [capabilities, setCapabilities] = useState<Capability[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState<number | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<number | null>(null);
  const [editor, setEditor] = useState<Editor | null>(null);
  const [editingEntitlement, setEditingEntitlement] = useState<Entitlement | null>(null);
  const [values, setValues] = useState<Record<string, string | boolean>>({});
  const [reason, setReason] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!allowed) return;
    let active = true;
    Promise.all([api.list<Plan>("platform/plans/"), api.list<Capability>("platform/capabilities/")])
      .then(([planRows, capabilityRows]) => { if (active) { setPlans(planRows); setCapabilities(capabilityRows); setSelectedPlanId((current) => current ?? planRows[0]?.id ?? null); } })
      .catch((value) => { if (active) setError(value); });
    return () => { active = false; };
  }, [allowed, reload]);

  const selectedPlan = plans?.find((plan) => plan.id === selectedPlanId) || null;
  const selectedVersion = selectedPlan?.versions.find((version) => version.id === selectedVersionId) || selectedPlan?.versions[0] || null;

  function open(next: Editor, entitlement?: Entitlement) {
    setEditor(next); setReason(""); setPassword(""); setActionError(null); setEditingEntitlement(entitlement || null);
    if (next === "plan-create") setValues({ code: "", name: "", description: "", is_active: true });
    if (next === "plan-edit" && selectedPlan) setValues({ code: selectedPlan.code, name: selectedPlan.name, description: selectedPlan.description, is_active: selectedPlan.is_active });
    if (next === "version-create") setValues({ version: String(Math.max(0, ...(selectedPlan?.versions.map((item) => item.version) || [])) + 1), price: "0.00", currency: "BRL", billing_period_months: "1", trial_days: "0", is_public: false, is_active: true });
    if (next === "version-edit" && selectedVersion) setValues({ version: String(selectedVersion.version), price: selectedVersion.price, currency: selectedVersion.currency, billing_period_months: String(selectedVersion.billing_period_months), trial_days: String(selectedVersion.trial_days), is_public: selectedVersion.is_public, is_active: selectedVersion.is_active });
    if (next === "entitlement-create") setValues({ capability: "", enabled: true, unlimited: false, limit_value: "" });
    if (next === "entitlement-edit" && entitlement) setValues({ capability: String(entitlement.capability), enabled: entitlement.enabled, unlimited: entitlement.unlimited, limit_value: entitlement.limit_value === null ? "" : String(entitlement.limit_value) });
  }

  async function save(event: FormEvent) {
    event.preventDefault(); if (!editor) return; setSaving(true); setActionError(null);
    const critical = { reason, current_password: password };
    try {
      if (editor === "plan-create") await api.post("platform/plans/", { ...values, ...critical });
      if (editor === "plan-edit") await api.patch(`platform/plans/${selectedPlan?.id}/`, { ...values, ...critical });
      if (editor === "version-create") await api.post("platform/plan-versions/", { ...versionPayload(values), plan: selectedPlan?.id, ...critical });
      if (editor === "version-edit") await api.patch(`platform/plan-versions/${selectedVersion?.id}/`, { ...versionPayload(values), plan: selectedPlan?.id, ...critical });
      if (editor === "entitlement-create") await api.post("platform/entitlements/", { ...entitlementPayload(values), plan_version: selectedVersion?.id, ...critical });
      if (editor === "entitlement-edit") await api.patch(`platform/entitlements/${editingEntitlement?.id}/`, { ...entitlementPayload(values), plan_version: selectedVersion?.id, ...critical });
      setNotice("Catalogo de planos atualizado."); setEditor(null); setReload((value) => value + 1);
    } catch (value) { setActionError(value); } finally { setSaving(false); }
  }

  if (!allowed) return <ErrorBlock error={new Error("Seu perfil nao possui acesso ao catalogo de planos.")} />;
  if (error) return <ErrorBlock error={error} retry={() => setReload((value) => value + 1)} />;
  if (!plans) return <LoadingBlock label="Carregando catalogo comercial" />;
  return <div className="enter space-y-6"><div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="eyebrow">Catalogo e enforcement</p><h1 className="mt-2 text-3xl font-black tracking-tight sm:text-4xl">Planos e limites</h1><p className="mt-2 text-sm text-steel/65">Versoes historicas e capacidades aplicadas aos tenants.</p></div><button className="btn btn-signal" onClick={() => open("plan-create")}><Plus size={16} />Novo plano</button></div>{notice && <Notice message={notice} />}
    <div className="grid gap-6 xl:grid-cols-[340px_1fr]"><section className="panel self-start"><div className="panel-head"><div><p className="eyebrow">Produtos</p><h2 className="mt-1 font-bold">Catalogo</h2></div><span className="font-mono text-[10px] text-steel/50">{plans.length}</span></div>{plans.length === 0 ? <Empty title="Catalogo vazio" detail="Crie o primeiro plano comercial." /> : <div className="divide-y divide-line">{plans.map((plan) => <button key={plan.id} onClick={() => { setSelectedPlanId(plan.id); setSelectedVersionId(null); }} className={`flex w-full items-center gap-3 p-4 text-left transition ${plan.id === selectedPlan?.id ? "bg-ink text-white" : "hover:bg-white"}`}><span className={`flex size-9 items-center justify-center ${plan.id === selectedPlan?.id ? "bg-signal text-ink" : "bg-[#e5e8e3] text-steel"}`}><Boxes size={16} /></span><span className="min-w-0 flex-1"><span className="block truncate text-sm font-bold">{plan.name}</span><span className={`font-mono text-[9px] uppercase ${plan.id === selectedPlan?.id ? "text-white/45" : "text-steel/45"}`}>{plan.code} / {plan.versions.length} versoes</span></span><ChevronRight size={15} /></button>)}</div>}</section>
      {selectedPlan ? <section className="space-y-6"><div className="panel"><div className="panel-head"><div><div className="flex items-center gap-2"><h2 className="text-xl font-black">{selectedPlan.name}</h2><Status value={selectedPlan.is_active ? "ACTIVE" : "INACTIVE"} /></div><p className="mt-1 text-sm text-steel/60">{selectedPlan.description || "Sem descricao comercial."}</p></div><button className="btn btn-quiet" onClick={() => open("plan-edit")}><Settings2 size={15} />Editar</button></div><div className="flex gap-2 overflow-x-auto p-4"><button className="btn btn-signal" onClick={() => open("version-create")}><Plus size={15} />Nova versao</button>{selectedPlan.versions.map((version) => <button key={version.id} onClick={() => setSelectedVersionId(version.id)} className={`btn ${version.id === selectedVersion?.id ? "btn-primary" : "btn-quiet"}`}>v{version.version}{version.is_used && <LockKeyhole size={13} />}</button>)}</div></div>
        {selectedVersion ? <VersionPanel version={selectedVersion} capabilities={capabilities} open={open} /> : <div className="panel"><Empty title="Nenhuma versao" detail="Crie uma versao para definir preco e capacidades." /></div>}
      </section> : <section className="panel"><Empty title="Selecione um plano" detail="Os detalhes e as versoes serao exibidos aqui." /></section>}</div>
    {editor && <Modal title={editorTitle(editor)} description={editor.includes("entitlement") ? "Limites de versoes em uso sao imutaveis." : "Esta alteracao exige justificativa e reautenticacao."} onClose={() => setEditor(null)} wide={editor.includes("version")}><form onSubmit={save}><EditorFields editor={editor} values={values} setValues={setValues} capabilities={capabilities} editing={editingEntitlement} />{actionError ? <div className="px-5 pt-4"><ErrorBlock error={actionError} /></div> : null}<CriticalFields reason={reason} password={password} onReason={setReason} onPassword={setPassword} error={actionError} /><div className="flex justify-end gap-2 p-5"><button type="button" className="btn btn-quiet" onClick={() => setEditor(null)}>Cancelar</button><button className="btn btn-signal" disabled={saving || !reason || !password}>{saving ? "Salvando..." : "Salvar alteracao"}</button></div></form></Modal>}
  </div>;
}

function VersionPanel({ version, capabilities, open }: { version: PlanVersion; capabilities: Capability[]; open: (editor: Editor, entitlement?: Entitlement) => void }) {
  return <div className="panel"><div className="panel-head"><div><div className="flex flex-wrap items-center gap-2"><h3 className="text-lg font-black">Versao {version.version}</h3><Status value={version.is_active ? "ACTIVE" : "INACTIVE"} />{version.is_public && <span className="status border-line bg-white">PUBLICA</span>}{version.is_used && <span className="status border-amber/30 bg-amber-50 text-amber-900"><LockKeyhole size={11} />IMUTAVEL EM USO</span>}</div><p className="mt-2 flex items-center gap-2 text-sm text-steel/65"><CircleDollarSign size={15} />{money(version.price, version.currency)} a cada {version.billing_period_months} mes(es) / trial {version.trial_days} dias</p></div><button className="btn btn-quiet" disabled={version.is_used} onClick={() => open("version-edit")}><Settings2 size={15} />Editar versao</button></div><div className="border-b border-line bg-[#e8ebe7] px-5 py-3"><div className="flex items-center justify-between"><p className="eyebrow">Entitlements</p><button className="text-xs font-bold uppercase tracking-wider hover:underline disabled:no-underline" disabled={version.is_used} onClick={() => open("entitlement-create")}><Plus size={14} className="inline" /> Adicionar</button></div></div>{version.entitlements.length === 0 ? <Empty title="Sem capacidades" detail="Uma versao precisa de core.enabled, users.max e branches.max para ser utilizavel." /> : <div className="divide-y divide-line">{version.entitlements.map((entitlement) => { const capability = capabilities.find((item) => item.id === entitlement.capability); return <div className="flex flex-col justify-between gap-3 p-4 sm:flex-row sm:items-center" key={entitlement.id}><div className="flex items-center gap-3"><span className={`flex size-8 items-center justify-center ${entitlement.enabled ? "bg-signal" : "bg-line"}`}>{entitlement.enabled ? <Check size={15} /> : <span className="size-2 bg-steel/40" />}</span><div><p className="font-mono text-xs font-bold">{entitlement.capability_code}</p><p className="text-xs text-steel/55">{capability?.name}</p></div></div><div className="flex items-center gap-4"><span className="font-mono text-xs font-bold">{!entitlement.enabled ? "DESABILITADO" : entitlement.unlimited ? "ILIMITADO" : capability?.value_type === "BOOLEAN" ? "HABILITADO" : `LIMITE ${entitlement.limit_value}`}</span><button className="text-xs font-bold uppercase text-steel/60 hover:text-ink disabled:opacity-30" disabled={version.is_used} onClick={() => open("entitlement-edit", entitlement)}>Editar</button></div></div>; })}</div>}</div>;
}

function EditorFields({ editor, values, setValues, capabilities, editing }: { editor: Editor; values: Record<string, string | boolean>; setValues: (values: Record<string, string | boolean>) => void; capabilities: Capability[]; editing: Entitlement | null }) {
  const set = (key: string, value: string | boolean) => setValues({ ...values, [key]: value });
  if (editor.includes("plan-") && !editor.includes("version")) return <div className="grid gap-4 p-5 sm:grid-cols-2"><Field label="Codigo"><input className="input" value={String(values.code)} onChange={(e) => set("code", e.target.value)} required /></Field><Field label="Nome"><input className="input" value={String(values.name)} onChange={(e) => set("name", e.target.value)} required /></Field><div className="field sm:col-span-2"><label>Descricao</label><textarea className="textarea" value={String(values.description)} onChange={(e) => set("description", e.target.value)} /></div><CheckField label="Plano ativo" checked={Boolean(values.is_active)} onChange={(value) => set("is_active", value)} /></div>;
  if (editor.includes("version")) return <div className="grid gap-4 p-5 sm:grid-cols-2 lg:grid-cols-3"><Field label="Numero da versao"><input className="input" type="number" min="1" value={String(values.version)} onChange={(e) => set("version", e.target.value)} required /></Field><Field label="Preco"><input className="input" type="number" min="0" step="0.01" value={String(values.price)} onChange={(e) => set("price", e.target.value)} required /></Field><Field label="Moeda"><input className="input" maxLength={3} value={String(values.currency)} onChange={(e) => set("currency", e.target.value.toUpperCase())} required /></Field><Field label="Periodo em meses"><input className="input" type="number" min="1" value={String(values.billing_period_months)} onChange={(e) => set("billing_period_months", e.target.value)} required /></Field><Field label="Dias de trial"><input className="input" type="number" min="0" value={String(values.trial_days)} onChange={(e) => set("trial_days", e.target.value)} required /></Field><div className="grid gap-2"><CheckField label="Versao ativa" checked={Boolean(values.is_active)} onChange={(value) => set("is_active", value)} /><CheckField label="Visivel publicamente" checked={Boolean(values.is_public)} onChange={(value) => set("is_public", value)} /></div></div>;
  const capability = capabilities.find((item) => item.id === Number(values.capability));
  return <div className="grid gap-4 p-5 sm:grid-cols-2"><Field label="Capacidade"><select className="input" value={String(values.capability)} onChange={(e) => set("capability", e.target.value)} required disabled={!!editing}><option value="">Selecione</option>{capabilities.map((item) => <option value={item.id} key={item.id}>{item.code} / {item.name}</option>)}</select></Field>{capability?.value_type === "INTEGER" && !values.unlimited && values.enabled ? <Field label="Limite numerico"><input className="input" type="number" min="0" value={String(values.limit_value)} onChange={(e) => set("limit_value", e.target.value)} required /></Field> : <div />}<CheckField label="Habilitada" checked={Boolean(values.enabled)} onChange={(value) => set("enabled", value)} />{capability?.value_type === "INTEGER" && <CheckField label="Ilimitada" checked={Boolean(values.unlimited)} onChange={(value) => set("unlimited", value)} />}</div>;
}

function versionPayload(values: Record<string, string | boolean>) { return { version: Number(values.version), price: values.price, currency: values.currency, billing_period_months: Number(values.billing_period_months), trial_days: Number(values.trial_days), is_public: values.is_public, is_active: values.is_active }; }
function entitlementPayload(values: Record<string, string | boolean>) { const enabled = Boolean(values.enabled); const unlimited = enabled && Boolean(values.unlimited); return { capability: Number(values.capability), enabled, unlimited, limit_value: enabled && !unlimited && values.limit_value !== "" ? Number(values.limit_value) : null }; }
function editorTitle(editor: Editor) { return ({ "plan-create": "Criar plano", "plan-edit": "Editar plano", "version-create": "Criar versao", "version-edit": "Editar versao", "entitlement-create": "Adicionar entitlement", "entitlement-edit": "Editar entitlement" })[editor]; }
function Field({ label, children }: { label: string; children: React.ReactNode }) { return <div className="field"><label>{label}</label>{children}</div>; }
function CheckField({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) { return <label className="flex min-h-10 items-center gap-3 border border-line bg-white px-3 text-xs font-bold uppercase tracking-wider"><input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="size-4 accent-ink" />{label}</label>; }
