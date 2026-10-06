"use client";

import { ChangeEvent, FormEvent, useEffect, useState } from "react";
import { AlertOctagon, Check, Globe2, Image as ImageIcon, Save, ShieldCheck } from "lucide-react";
import { CriticalFields, ErrorBlock, LoadingBlock, Modal, Notice, Status } from "@/components/ui";
import { api } from "@/lib/api";
import { dateTime } from "@/lib/format";
import type { GlobalSettings, LegalSettings } from "@/lib/types";
import { useAuth } from "@/providers/auth-provider";

type BrandingSlot = "logo" | "compact_logo" | "favicon" | "logo_light" | "logo_dark" | "compact_logo_light" | "compact_logo_dark";
type InstitutionalLink = "terms" | "privacy" | "website" | "help" | "cookies";

const brandingFields: { slot: BrandingSlot; label: string; accept: string; detail: string }[] = [
  { slot: "logo", label: "Logotipo principal", accept: "image/png,image/jpeg,image/webp", detail: "PNG, JPG ou WEBP, ate 2 MB." },
  { slot: "compact_logo", label: "Logotipo compacto", accept: "image/png,image/jpeg,image/webp", detail: "PNG, JPG ou WEBP, ate 2 MB." },
  { slot: "favicon", label: "Favicon", accept: "image/png,image/jpeg,image/webp,image/x-icon", detail: "PNG, JPG, WEBP ou ICO, ate 2 MB." },
  { slot: "logo_light", label: "Logo para fundo claro", accept: "image/png,image/jpeg,image/webp", detail: "PNG, JPG ou WEBP, ate 2 MB." },
  { slot: "logo_dark", label: "Logo para fundo escuro", accept: "image/png,image/jpeg,image/webp", detail: "PNG, JPG ou WEBP, ate 2 MB." },
  { slot: "compact_logo_light", label: "Logo compacta para fundo claro", accept: "image/png,image/jpeg,image/webp", detail: "PNG, JPG ou WEBP, ate 2 MB." },
  { slot: "compact_logo_dark", label: "Logo compacta para fundo escuro", accept: "image/png,image/jpeg,image/webp", detail: "PNG, JPG ou WEBP, ate 2 MB." },
];

const institutionalFields: { key: InstitutionalLink; label: string }[] = [
  { key: "terms", label: "Termos de uso" },
  { key: "privacy", label: "Politica de privacidade" },
  { key: "website", label: "Site institucional" },
  { key: "help", label: "Central de ajuda / suporte" },
  { key: "cookies", label: "Politica de cookies" },
];

function institutionalLinks(links: Record<string, string>) {
  return Object.fromEntries(institutionalFields.map(({ key }) => [key, typeof links[key] === "string" ? links[key] : ""]));
}

export default function SettingsPage() {
  const { can } = useAuth();
  const allowed = can("platform.settings.manage");
  const [settings, setSettings] = useState<GlobalSettings | null>(null);
  const [form, setForm] = useState<GlobalSettings | null>(null);
  const [pendingAssets, setPendingAssets] = useState<Partial<Record<BrandingSlot, File>>>({});
  const [reason, setReason] = useState("");
  const [password, setPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [assetAction, setAssetAction] = useState<BrandingSlot | null>(null);
  const [enabling, setEnabling] = useState(false);
  const [enableModal, setEnableModal] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!allowed) return;
    let active = true;
    api.get<GlobalSettings>("platform/settings/")
      .then((value) => { if (active) { setSettings(value); setForm(value); } })
      .catch((value) => { if (active) setError(value); });
    return () => { active = false; };
  }, [allowed, reload]);

  function updateLegal(key: keyof LegalSettings, value: string) {
    if (!form) return;
    setForm({ ...form, legal_settings: { ...form.legal_settings, [key]: value } });
  }

  function updateLink(key: InstitutionalLink, value: string) {
    if (!form) return;
    setForm({ ...form, institutional_links: { ...form.institutional_links, [key]: value } });
  }

  function selectAsset(slot: BrandingSlot, event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const extension = file.name.toLowerCase().split(".").pop();
    const allowedExtensions = slot === "favicon" ? ["png", "jpg", "jpeg", "webp", "ico"] : ["png", "jpg", "jpeg", "webp"];
    if (!extension || !allowedExtensions.includes(extension)) {
      setActionError(new Error(slot === "favicon" ? "Envie favicon PNG, JPG, WEBP ou ICO." : "Envie imagem PNG, JPG ou WEBP."));
      event.target.value = "";
      return;
    }
    if (file.size > 2 * 1024 * 1024) {
      setActionError(new Error("O arquivo de branding deve ter no maximo 2 MB."));
      event.target.value = "";
      return;
    }
    setActionError(null);
    setPendingAssets((current) => ({ ...current, [slot]: file }));
  }

  function applyBranding(value: GlobalSettings) {
    setSettings(value);
    // Preserve unsaved policy and legal edits while the file action refreshes its own data.
    setForm((current) => current ? { ...current, branding_assets: value.branding_assets } : value);
  }

  async function changeAsset(slot: BrandingSlot, remove = false) {
    const file = pendingAssets[slot];
    if (!remove && !file) return;
    setAssetAction(slot);
    setActionError(null);
    try {
      const data = new FormData();
      data.append("reason", reason);
      data.append("current_password", password);
      if (!remove && file) data.append("asset", file);
      if (remove) {
        await api.deleteForm<null>(`platform/settings/branding/${slot}/`, data);
        setSettings((current) => current ? { ...current, branding_assets: { ...current.branding_assets, [slot]: "" } } : current);
        setForm((current) => current ? { ...current, branding_assets: { ...current.branding_assets, [slot]: "" } } : current);
        setNotice("Asset de branding removido. O frontend usara o fallback local.");
      } else {
        const value = await api.postForm<GlobalSettings>(`platform/settings/branding/${slot}/`, data);
        applyBranding(value);
        setNotice("Asset de branding atualizado.");
      }
      setPendingAssets((current) => ({ ...current, [slot]: undefined }));
      setReason("");
      setPassword("");
    } catch (value) {
      setActionError(value);
    } finally {
      setAssetAction(null);
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!form) return;
    setSaving(true);
    setActionError(null);
    try {
      const editable = {
        public_signup_enabled: form.public_signup_enabled,
        auto_approve_signups: form.auto_approve_signups,
        past_due_days: form.past_due_days,
        restricted_after_days: form.restricted_after_days,
        support_session_minutes: form.support_session_minutes,
        public_signup_billing_mode: form.public_signup_billing_mode,
        platform_name: form.platform_name,
        primary_color: form.primary_color,
        support_email: form.support_email,
        support_phone: form.support_phone,
        support_whatsapp: form.support_whatsapp,
        institutional_links: institutionalLinks(form.institutional_links || {}),
        legal_settings: form.legal_settings || {},
      };
      const value = await api.patch<GlobalSettings>("platform/settings/", { ...editable, reason, current_password: password });
      setSettings(value);
      setForm(value);
      setReason("");
      setPassword("");
      setNotice("Politicas globais atualizadas.");
    } catch (value) {
      setActionError(value);
    } finally {
      setSaving(false);
    }
  }

  async function enable() {
    setEnabling(true);
    setActionError(null);
    try {
      await api.post("platform/settings/", { reason, current_password: password });
      setEnableModal(false);
      setReason("");
      setPassword("");
      setNotice("Cutover SaaS registrado.");
      setReload((value) => value + 1);
    } catch (value) {
      setActionError(value);
    } finally {
      setEnabling(false);
    }
  }

  if (!allowed) return <ErrorBlock error={new Error("Seu perfil nao possui acesso as politicas globais.")} />;
  if (error) return <ErrorBlock error={error} retry={() => setReload((value) => value + 1)} />;
  if (!settings || !form) return <LoadingBlock label="Carregando politicas globais" />;

  return <div className="enter space-y-6">
    <div><p className="eyebrow">Governanca da plataforma</p><h1 className="mt-2 text-3xl font-black tracking-tight sm:text-4xl">Politicas globais</h1><p className="mt-2 text-sm text-steel/65">Aprovacao, ciclo financeiro, suporte e identidade publica.</p></div>
    {notice && <Notice message={notice} />}
    <form onSubmit={save} className="space-y-6">
      <section className="panel"><div className="panel-head"><div><p className="eyebrow">Entrada e ciclo</p><h2 className="mt-1 font-bold">Politica comercial</h2></div><Globe2 size={18} className="text-steel/45" /></div><div className="grid gap-5 p-5 md:grid-cols-2 xl:grid-cols-4"><Toggle label="Cadastro publico" checked={form.public_signup_enabled} onChange={(value) => setForm({ ...form, public_signup_enabled: value })} /><Toggle label="Aprovar cadastros automaticamente" checked={form.auto_approve_signups} onChange={(value) => setForm({ ...form, auto_approve_signups: value })} /><Field label="Modalidade de novos cadastros"><select className="input" value={form.public_signup_billing_mode} onChange={(event) => setForm({ ...form, public_signup_billing_mode: event.target.value as "PAID" | "FREE" })}><option value="PAID">Pago</option><option value="FREE">Gratuito</option></select></Field><Field label="Dias ate inadimplencia"><input className="input" type="number" min="0" value={form.past_due_days} onChange={(event) => setForm({ ...form, past_due_days: Number(event.target.value) })} required /></Field><Field label="Dias ate restricao"><input className="input" type="number" min="0" value={form.restricted_after_days} onChange={(event) => setForm({ ...form, restricted_after_days: Number(event.target.value) })} required /></Field><Field label="Duracao de suporte (minutos)"><input className="input" type="number" min="1" max="240" value={form.support_session_minutes} onChange={(event) => setForm({ ...form, support_session_minutes: Number(event.target.value) })} required /></Field></div></section>

      <section className="panel"><div className="panel-head"><div><p className="eyebrow">Site e documentos</p><h2 className="mt-1 font-bold">Dados juridicos publicos</h2><p className="mt-2 text-sm text-steel/65">Usados nos termos, na privacidade e no rodape.</p></div></div><div className="grid gap-5 p-5 md:grid-cols-2"><Field label="Razao social"><input className="input" value={form.legal_settings?.legal_name || ""} onChange={(event) => updateLegal("legal_name", event.target.value)} /></Field><Field label="Nome fantasia"><input className="input" value={form.legal_settings?.trade_name || ""} onChange={(event) => updateLegal("trade_name", event.target.value)} /></Field><Field label="CNPJ"><input className="input" value={form.legal_settings?.cnpj || ""} onChange={(event) => updateLegal("cnpj", event.target.value)} /></Field><Field label="Endereco completo"><input className="input" value={form.legal_settings?.address || ""} onChange={(event) => updateLegal("address", event.target.value)} /></Field><Field label="Cidade/UF da sede"><input className="input" value={form.legal_settings?.jurisdiction || ""} onChange={(event) => updateLegal("jurisdiction", event.target.value)} /></Field><Field label="E-mail comercial"><input className="input" type="email" value={form.legal_settings?.commercial_email || ""} onChange={(event) => updateLegal("commercial_email", event.target.value)} /></Field><Field label="E-mail juridico"><input className="input" type="email" value={form.legal_settings?.legal_email || ""} onChange={(event) => updateLegal("legal_email", event.target.value)} /></Field><Field label="E-mail de privacidade"><input className="input" type="email" value={form.legal_settings?.privacy_email || ""} onChange={(event) => updateLegal("privacy_email", event.target.value)} /></Field><Field label="E-mail de seguranca"><input className="input" type="email" value={form.legal_settings?.security_email || ""} onChange={(event) => updateLegal("security_email", event.target.value)} /></Field><Field label="Encarregado/DPO"><input className="input" value={form.legal_settings?.dpo_name || ""} onChange={(event) => updateLegal("dpo_name", event.target.value)} /></Field><Field label="E-mail do DPO"><input className="input" type="email" value={form.legal_settings?.dpo_email || ""} onChange={(event) => updateLegal("dpo_email", event.target.value)} /></Field><Field label="Site juridico"><input className="input" type="url" value={form.legal_settings?.website_url || ""} onChange={(event) => updateLegal("website_url", event.target.value)} /></Field><Field label="Pagina de subprocessadores"><input className="input" type="url" value={form.legal_settings?.subprocessors_url || ""} onChange={(event) => updateLegal("subprocessors_url", event.target.value)} /></Field><Field label="Data de vigencia"><input className="input" type="date" value={form.legal_settings?.effective_date || ""} onChange={(event) => updateLegal("effective_date", event.target.value)} /></Field></div></section>

      <section className="panel"><div className="panel-head"><div><p className="eyebrow">Identidade publica</p><h2 className="mt-1 font-bold">Dados e links</h2></div><ImageIcon size={18} className="text-steel/45" /></div><div className="grid gap-5 p-5 md:grid-cols-2"><Field label="Nome da plataforma"><input className="input" value={form.platform_name} onChange={(event) => setForm({ ...form, platform_name: event.target.value })} required /></Field><Field label="Cor primaria"><div className="flex"><input className="h-10 w-12 border border-r-0 border-line bg-white p-1" type="color" value={/^#[0-9a-f]{6}$/i.test(form.primary_color) ? form.primary_color : "#111827"} onChange={(event) => setForm({ ...form, primary_color: event.target.value })} /><input className="input" value={form.primary_color} onChange={(event) => setForm({ ...form, primary_color: event.target.value })} /></div></Field><Field label="E-mail de suporte"><input className="input" type="email" value={form.support_email} onChange={(event) => setForm({ ...form, support_email: event.target.value })} /></Field><Field label="Telefone de suporte"><input className="input" value={form.support_phone} onChange={(event) => setForm({ ...form, support_phone: event.target.value })} /></Field><Field label="WhatsApp de suporte"><input className="input" value={form.support_whatsapp} onChange={(event) => setForm({ ...form, support_whatsapp: event.target.value })} /></Field>{institutionalFields.map(({ key, label }) => <Field key={key} label={label}><input className="input" type="url" value={form.institutional_links?.[key] || ""} onChange={(event) => updateLink(key, event.target.value)} placeholder="https://" /></Field>)}</div></section>

      <section className="panel"><div className="panel-head"><div><p className="eyebrow">Autorizacao da alteracao</p><h2 className="mt-1 font-bold">Confirmacao auditavel</h2><p className="mt-2 text-sm text-steel/65">Tambem exigida para enviar, substituir ou remover assets de branding.</p></div></div><CriticalFields reason={reason} password={password} onReason={setReason} onPassword={setPassword} error={actionError} /><div className="flex justify-end p-5"><button className="btn btn-signal" disabled={saving || !reason || !password}><Save size={15} />{saving ? "Salvando..." : "Salvar politicas"}</button></div></section>
    </form>

    <section className="panel"><div className="panel-head"><div><p className="eyebrow">Identidade visual</p><h2 className="mt-1 font-bold">Assets de branding</h2><p className="mt-2 text-sm text-steel/65">Arquivos internos substituem os assets locais do CORE. Remover um arquivo restaura o fallback local.</p></div><ImageIcon size={18} className="text-steel/45" /></div><div className="grid gap-5 p-5 md:grid-cols-2">{brandingFields.map((field) => <BrandingAssetControl key={field.slot} {...field} currentUrl={form.branding_assets?.[field.slot] || ""} selected={pendingAssets[field.slot]} busy={assetAction === field.slot} ready={Boolean(reason && password)} onSelect={(event) => selectAsset(field.slot, event)} onUpload={() => void changeAsset(field.slot)} onRemove={() => void changeAsset(field.slot, true)} />)}</div>{actionError ? <div className="border-t border-line p-5"><ErrorBlock error={actionError} /></div> : null}</section>

    <section className={`border p-5 sm:p-6 ${settings.enforcement_enabled ? "border-cyan/30 bg-cyan-50" : "border-alert/40 bg-red-50"}`}><div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-center"><div className="flex gap-4">{settings.enforcement_enabled ? <ShieldCheck className="text-cyan-800" /> : <AlertOctagon className="text-alert" />}<div><div className="flex items-center gap-2"><h2 className="font-black">Cutover SaaS</h2><Status value={settings.enforcement_enabled ? "CONCLUIDO" : "PENDENTE"} positive={settings.enforcement_enabled} /></div><p className="mt-2 max-w-2xl text-sm text-steel/70">{settings.enforcement_enabled ? `Base legada validada desde ${dateTime(settings.enforcement_enabled_at)}. Este marco e irreversivel.` : "A validacao de runtime SaaS ja permanece ativa para todos os tenants. Este cutover irreversivel registra a validacao da base legada."}</p></div></div>{!settings.enforcement_enabled && <button type="button" className="btn btn-danger" onClick={() => { setReason(""); setPassword(""); setActionError(null); setEnableModal(true); }}>Validar base legada</button>}</div></section>
    {enableModal && <Modal title="Realizar cutover SaaS" description="Marco irreversivel de validacao da base legada." onClose={() => setEnableModal(false)}><div className="border-b border-alert/25 bg-red-50 p-5 text-sm text-red-900"><strong>Verificacao obrigatoria</strong><p className="mt-1">O runtime ja aplica a validacao SaaS. Confirme que toda a base legada foi revisada antes de registrar este cutover.</p></div>{actionError ? <div className="px-5 pt-4"><ErrorBlock error={actionError} /></div> : null}<CriticalFields reason={reason} password={password} onReason={setReason} onPassword={setPassword} error={actionError} /><div className="flex justify-end gap-2 p-5"><button className="btn btn-quiet" onClick={() => setEnableModal(false)}>Cancelar</button><button className="btn btn-danger" disabled={enabling || !reason || !password} onClick={() => void enable()}>{enabling ? "Registrando..." : "Confirmar cutover"}</button></div></Modal>}
  </div>;
}

function BrandingAssetControl({ label, accept, detail, currentUrl, selected, busy, ready, onSelect, onUpload, onRemove }: { label: string; accept: string; detail: string; currentUrl: string; selected?: File; busy: boolean; ready: boolean; onSelect: (event: ChangeEvent<HTMLInputElement>) => void; onUpload: () => void; onRemove: () => void }) {
  return <div className="border border-line bg-white p-4"><div className="flex min-h-20 items-center gap-4"><div className="flex size-16 shrink-0 items-center justify-center overflow-hidden border border-line bg-[#edf0eb]">{currentUrl ? <img src={currentUrl} alt={`Preview de ${label}`} className="max-h-full max-w-full object-contain" /> : <ImageIcon size={20} className="text-steel/35" />}</div><div className="min-w-0"><p className="font-bold">{label}</p><p className="mt-1 text-xs text-steel/60">{currentUrl ? "Arquivo atual disponivel." : "Usando fallback local do CORE."}</p><p className="mt-1 text-xs text-steel/50">{detail}</p></div></div><input className="mt-4 block w-full text-xs text-steel/70 file:mr-3 file:border-0 file:bg-ink file:px-3 file:py-2 file:text-xs file:font-bold file:text-white" type="file" accept={accept} onChange={onSelect} /><div className="mt-3 flex flex-wrap items-center gap-2"><button type="button" className="btn btn-signal" disabled={!selected || !ready || busy} onClick={onUpload}>{busy ? "Enviando..." : currentUrl ? "Substituir arquivo" : "Enviar arquivo"}</button>{currentUrl && <button type="button" className="btn btn-quiet" disabled={!ready || busy} onClick={onRemove}>Remover</button>}{selected && <span className="max-w-full truncate text-xs text-steel/60">Selecionado: {selected.name}</span>}</div>{!ready && <p className="mt-3 text-xs text-steel/55">Informe motivo e senha na confirmacao auditavel para alterar este asset.</p>}</div>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) { return <div className="field"><label>{label}</label>{children}</div>; }
function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) { return <div className="flex min-h-20 items-center gap-3 border border-line bg-white p-4 text-xs font-bold uppercase tracking-wider"><button type="button" role="switch" aria-label={label} aria-checked={checked} className={`flex h-6 w-11 items-center border p-0.5 transition ${checked ? "border-ink bg-ink justify-end" : "border-line bg-[#e5e8e3] justify-start"}`} onClick={() => onChange(!checked)}><span className={`flex size-4 items-center justify-center ${checked ? "bg-signal" : "bg-white"}`}>{checked && <Check size={11} />}</span></button><span>{label}</span></div>; }
