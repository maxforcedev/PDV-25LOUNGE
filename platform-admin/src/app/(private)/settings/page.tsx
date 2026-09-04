"use client";

import { FormEvent, useEffect, useState } from "react";
import { AlertOctagon, Check, Globe2, Image as ImageIcon, Save, ShieldCheck } from "lucide-react";
import { CriticalFields, ErrorBlock, LoadingBlock, Modal, Notice, Status } from "@/components/ui";
import { api } from "@/lib/api";
import { dateTime } from "@/lib/format";
import type { GlobalSettings } from "@/lib/types";
import { useAuth } from "@/providers/auth-provider";

export default function SettingsPage() {
  const { can } = useAuth();
  const allowed = can("platform.settings.manage");
  const [settings, setSettings] = useState<GlobalSettings | null>(null);
  const [form, setForm] = useState<GlobalSettings | null>(null);
  const [links, setLinks] = useState("{}");
  const [reason, setReason] = useState("");
  const [password, setPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [enabling, setEnabling] = useState(false);
  const [enableModal, setEnableModal] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!allowed) return;
    let active = true; api.get<GlobalSettings>("platform/settings/").then((value) => { if (active) { setSettings(value); setForm(value); setLinks(JSON.stringify(value.institutional_links || {}, null, 2)); } }).catch((value) => { if (active) setError(value); }); return () => { active = false; };
  }, [allowed, reload]);

  async function save(event: FormEvent) {
    event.preventDefault(); if (!form) return; setSaving(true); setActionError(null);
    try {
      let institutional_links: Record<string, string>;
      try { institutional_links = JSON.parse(links); } catch { throw new Error("Links institucionais devem formar um objeto JSON valido."); }
      const editable = {
        auto_approve_signups: form.auto_approve_signups,
        past_due_days: form.past_due_days,
        restricted_after_days: form.restricted_after_days,
        support_session_minutes: form.support_session_minutes,
        public_signup_billing_mode: form.public_signup_billing_mode,
        platform_name: form.platform_name,
        logo_url: form.logo_url,
        compact_logo_url: form.compact_logo_url,
        favicon_url: form.favicon_url,
        logo_light_url: form.logo_light_url,
        logo_dark_url: form.logo_dark_url,
        compact_logo_light_url: form.compact_logo_light_url,
        compact_logo_dark_url: form.compact_logo_dark_url,
        primary_color: form.primary_color,
        support_email: form.support_email,
        support_phone: form.support_phone,
        support_whatsapp: form.support_whatsapp,
        institutional_links,
      };
      const value = await api.patch<GlobalSettings>("platform/settings/", { ...editable, reason, current_password: password });
      setSettings(value); setForm(value); setLinks(JSON.stringify(value.institutional_links || {}, null, 2)); setReason(""); setPassword(""); setNotice("Politicas globais atualizadas.");
    } catch (value) { setActionError(value); } finally { setSaving(false); }
  }

  async function enable() {
    setEnabling(true); setActionError(null);
    try { await api.post("platform/settings/", { reason, current_password: password }); setEnableModal(false); setReason(""); setPassword(""); setNotice("Enforcement SaaS habilitado."); setReload((value) => value + 1); } catch (value) { setActionError(value); } finally { setEnabling(false); }
  }

  if (!allowed) return <ErrorBlock error={new Error("Seu perfil nao possui acesso as politicas globais.")} />;
  if (error) return <ErrorBlock error={error} retry={() => setReload((value) => value + 1)} />;
  if (!settings || !form) return <LoadingBlock label="Carregando politicas globais" />;
  return <div className="enter space-y-6"><div><p className="eyebrow">Governanca da plataforma</p><h1 className="mt-2 text-3xl font-black tracking-tight sm:text-4xl">Politicas globais</h1><p className="mt-2 text-sm text-steel/65">Aprovacao, ciclo financeiro, suporte e identidade publica.</p></div>{notice && <Notice message={notice} />}
    <form onSubmit={save} className="space-y-6"><section className="panel"><div className="panel-head"><div><p className="eyebrow">Entrada e ciclo</p><h2 className="mt-1 font-bold">Politica comercial</h2></div><Globe2 size={18} className="text-steel/45" /></div><div className="grid gap-5 p-5 md:grid-cols-2 xl:grid-cols-4"><Toggle label="Aprovar cadastros automaticamente" checked={form.auto_approve_signups} onChange={(value) => setForm({ ...form, auto_approve_signups: value })} /><Field label="Modalidade de novos cadastros"><select className="input" value={form.public_signup_billing_mode} onChange={(event) => setForm({ ...form, public_signup_billing_mode: event.target.value as "PAID" | "FREE" })}><option value="PAID">Pago</option><option value="FREE">Gratuito</option></select></Field><Field label="Dias ate inadimplencia"><input className="input" type="number" min="0" value={form.past_due_days} onChange={(event) => setForm({ ...form, past_due_days: Number(event.target.value) })} required /></Field><Field label="Dias ate restricao"><input className="input" type="number" min="0" value={form.restricted_after_days} onChange={(event) => setForm({ ...form, restricted_after_days: Number(event.target.value) })} required /></Field><Field label="Duracao de suporte (minutos)"><input className="input" type="number" min="1" max="240" value={form.support_session_minutes} onChange={(event) => setForm({ ...form, support_session_minutes: Number(event.target.value) })} required /></Field></div></section>
      <section className="panel"><div className="panel-head"><div><p className="eyebrow">Identidade publica</p><h2 className="mt-1 font-bold">Branding da plataforma</h2></div><ImageIcon size={18} className="text-steel/45" /></div><div className="grid gap-5 p-5 md:grid-cols-2"><Field label="Nome da plataforma"><input className="input" value={form.platform_name} onChange={(event) => setForm({ ...form, platform_name: event.target.value })} required /></Field><Field label="Cor primaria"><div className="flex"><input className="h-10 w-12 border border-r-0 border-line bg-white p-1" type="color" value={/^#[0-9a-f]{6}$/i.test(form.primary_color) ? form.primary_color : "#111827"} onChange={(event) => setForm({ ...form, primary_color: event.target.value })} /><input className="input" value={form.primary_color} onChange={(event) => setForm({ ...form, primary_color: event.target.value })} /></div></Field><Field label="URL do logotipo"><input className="input" type="url" value={form.logo_url} onChange={(event) => setForm({ ...form, logo_url: event.target.value })} /></Field><Field label="URL do logotipo compacto"><input className="input" type="url" value={form.compact_logo_url} onChange={(event) => setForm({ ...form, compact_logo_url: event.target.value })} /></Field><Field label="URL do favicon"><input className="input" type="url" value={form.favicon_url} onChange={(event) => setForm({ ...form, favicon_url: event.target.value })} /></Field><Field label="E-mail de suporte"><input className="input" type="email" value={form.support_email} onChange={(event) => setForm({ ...form, support_email: event.target.value })} /></Field><Field label="Telefone de suporte"><input className="input" value={form.support_phone} onChange={(event) => setForm({ ...form, support_phone: event.target.value })} /></Field><div className="field md:col-span-2"><label>Links institucionais (JSON)</label><textarea className="textarea min-h-32 font-mono text-xs" value={links} onChange={(event) => setLinks(event.target.value)} spellCheck={false} placeholder={'{"termos": "https://...", "privacidade": "https://..."}'} /></div></div></section>
      <section className="panel"><div className="panel-head"><div><p className="eyebrow">Canais de suporte</p><h2 className="mt-1 font-bold">Contato operacional</h2></div></div><div className="grid gap-5 p-5 md:grid-cols-2"><Field label="WhatsApp de suporte"><input className="input" value={form.support_whatsapp} onChange={(event) => setForm({ ...form, support_whatsapp: event.target.value })} /></Field></div></section>
      <section className="panel"><div className="panel-head"><div><p className="eyebrow">Versoes para contraste</p><h2 className="mt-1 font-bold">Assets claro e escuro</h2></div><ImageIcon size={18} className="text-steel/45" /></div><div className="grid gap-5 p-5 md:grid-cols-2"><Field label="Logo clara (fundo claro)"><input className="input" type="url" value={form.logo_light_url} onChange={(event) => setForm({ ...form, logo_light_url: event.target.value })} /></Field><Field label="Logo escura (fundo escuro)"><input className="input" type="url" value={form.logo_dark_url} onChange={(event) => setForm({ ...form, logo_dark_url: event.target.value })} /></Field><Field label="Logo compacta clara"><input className="input" type="url" value={form.compact_logo_light_url} onChange={(event) => setForm({ ...form, compact_logo_light_url: event.target.value })} /></Field><Field label="Logo compacta escura"><input className="input" type="url" value={form.compact_logo_dark_url} onChange={(event) => setForm({ ...form, compact_logo_dark_url: event.target.value })} /></Field></div></section>
      {actionError ? <ErrorBlock error={actionError} /> : null}
      <section className="panel"><div className="panel-head"><div><p className="eyebrow">Autorizacao da alteracao</p><h2 className="mt-1 font-bold">Confirmacao auditavel</h2></div></div><CriticalFields reason={reason} password={password} onReason={setReason} onPassword={setPassword} error={actionError} /><div className="flex justify-end p-5"><button className="btn btn-signal" disabled={saving || !reason || !password}><Save size={15} />{saving ? "Salvando..." : "Salvar politicas"}</button></div></section>
    </form>
    <section className={`border p-5 sm:p-6 ${settings.enforcement_enabled ? "border-cyan/30 bg-cyan-50" : "border-alert/40 bg-red-50"}`}><div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-center"><div className="flex gap-4">{settings.enforcement_enabled ? <ShieldCheck className="text-cyan-800" /> : <AlertOctagon className="text-alert" />}<div><div className="flex items-center gap-2"><h2 className="font-black">Enforcement SaaS</h2><Status value={settings.enforcement_enabled ? "ENABLED" : "DISABLED"} positive={settings.enforcement_enabled} /></div><p className="mt-2 max-w-2xl text-sm text-steel/70">{settings.enforcement_enabled ? `Ativo desde ${dateTime(settings.enforcement_enabled_at)}. O cutover nao pode ser revertido.` : "O runtime ainda nao bloqueia tenants por estado SaaS. A ativacao e irreversivel e exige que toda a base esteja mapeada."}</p></div></div>{!settings.enforcement_enabled && <button type="button" className="btn btn-danger" onClick={() => { setReason(""); setPassword(""); setActionError(null); setEnableModal(true); }}>Habilitar enforcement</button>}</div></section>
    {enableModal && <Modal title="Habilitar enforcement SaaS" description="Cutover irreversivel: tenants nao mapeados serao bloqueados." onClose={() => setEnableModal(false)}><div className="border-b border-alert/25 bg-red-50 p-5 text-sm text-red-900"><strong>Verificacao obrigatoria</strong><p className="mt-1">Confirme que todos os tenants possuem assinatura e entitlements validos.</p></div>{actionError ? <div className="px-5 pt-4"><ErrorBlock error={actionError} /></div> : null}<CriticalFields reason={reason} password={password} onReason={setReason} onPassword={setPassword} error={actionError} /><div className="flex justify-end gap-2 p-5"><button className="btn btn-quiet" onClick={() => setEnableModal(false)}>Cancelar</button><button className="btn btn-danger" disabled={enabling || !reason || !password} onClick={() => void enable()}>{enabling ? "Habilitando..." : "Confirmar cutover"}</button></div></Modal>}
  </div>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) { return <div className="field"><label>{label}</label>{children}</div>; }
function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) { return <div className="flex min-h-20 items-center gap-3 border border-line bg-white p-4 text-xs font-bold uppercase tracking-wider"><button type="button" role="switch" aria-label={label} aria-checked={checked} className={`flex h-6 w-11 items-center border p-0.5 transition ${checked ? "border-ink bg-ink justify-end" : "border-line bg-[#e5e8e3] justify-start"}`} onClick={() => onChange(!checked)}><span className={`flex size-4 items-center justify-center ${checked ? "bg-signal" : "bg-white"}`}>{checked && <Check size={11} />}</span></button><span>{label}</span></div>; }
