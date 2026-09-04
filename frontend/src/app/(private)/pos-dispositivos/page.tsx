"use client";

import { useEffect, useState } from "react";
import { Copy, KeyRound, MonitorSmartphone, Pencil, Power, RotateCw, Settings2, ShieldBan, Trash2 } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, ConfirmDialog, EmptyState, Field, Input, Modal, Pagination, Select, Spinner, TableLoading } from "@/components/ui";
import { formatDate } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { BranchPosSettings, Paginated, PosDevice, PosSettings } from "@/types";

type DeviceAction = "block" | "unblock" | "revoke" | "replace" | "clear-settings";
type LicensingCodeResponse = { licensing_code: string };
type DeviceSettings = PosSettings & { effective_settings?: PosSettings };

const onlineWindow = 5 * 60 * 1000;
const statusLabel = { PENDING: "Pendente", ACTIVE: "Ativo", BLOCKED: "Bloqueado", REVOKED: "Revogado", REPLACED: "Substituído" } as const;

function isOnline(device: PosDevice) {
  return device.status === "ACTIVE" && !!device.last_seen_at && Date.now() - new Date(device.last_seen_at).getTime() <= onlineWindow;
}

function OnlineBadge({ device }: { device: PosDevice }) {
  const online = isOnline(device);
  return <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold ${online ? "bg-success-surface text-success-strong" : "bg-surface-muted text-muted"}`}><span className={`size-1.5 rounded-full ${online ? "bg-success" : "bg-disabled"}`} />{online ? "Online" : "Offline"}</span>;
}

function PosSettingsFields<T extends PosSettings>({ value, onChange, disabled }: { value: T; onChange: (next: T) => void; disabled: boolean }) {
  const update = <K extends keyof T>(key: K, next: T[K]) => onChange({ ...value, [key]: next });
  const cashRegisters = value.cash_register_options || [];
  const inheritsCash = value.cash_binding_mode === null;

  return <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
    <Field label="Vínculo de caixa"><Select value={value.cash_binding_mode || ""} disabled={disabled} onChange={(event) => update("cash_binding_mode", (event.target.value || null) as T["cash_binding_mode"])}><option value="">Usar padrão</option><option value="FLEXIBLE">Flexível</option><option value="FIXED">Fixo</option></Select></Field>
    <Field label="Caixa padrão"><Select value={value.default_cash_register || ""} disabled={disabled || inheritsCash} onChange={(event) => update("default_cash_register", (event.target.value ? Number(event.target.value) : null) as T["default_cash_register"])}><option value="">{inheritsCash ? "Definido pela filial" : "Nenhum caixa padrão"}</option>{cashRegisters.map((register) => <option key={register.id} value={register.id}>{register.name}</option>)}</Select></Field>
    <Field label="Impressora de recibo"><Input value={value.receipt_printer || ""} disabled={disabled} placeholder="Usar padrão" onChange={(event) => update("receipt_printer", (event.target.value || null) as T["receipt_printer"])} /></Field>
    <Field label="Modo de impressão"><Select value={value.receipt_print_mode || ""} disabled={disabled} onChange={(event) => update("receipt_print_mode", (event.target.value || null) as T["receipt_print_mode"])}><option value="">Usar padrão</option><option value="automatic">Automático</option><option value="manual">Manual</option></Select></Field>
    <Field label="Formato do recibo"><Select value={value.receipt_format || ""} disabled={disabled} onChange={(event) => update("receipt_format", (event.target.value || null) as T["receipt_format"])}><option value="">Usar padrão</option><option value="detailed">Detalhado</option><option value="simplified">Simplificado</option></Select></Field>
    <Field label="Largura do papel (mm)"><Input type="number" min="40" max="120" value={value.paper_width ?? ""} disabled={disabled} onChange={(event) => update("paper_width", (event.target.value ? Number(event.target.value) : null) as T["paper_width"])} /></Field>
    <Field label="Cópias"><Input type="number" min="1" max="10" value={value.copies ?? ""} disabled={disabled} onChange={(event) => update("copies", (event.target.value ? Number(event.target.value) : null) as T["copies"])} /></Field>
    <Field label="Tempo de tela (segundos)" optional><Input type="number" min="0" value={value.screen_timeout_seconds ?? ""} disabled={disabled} onChange={(event) => update("screen_timeout_seconds", (event.target.value ? Number(event.target.value) : null) as T["screen_timeout_seconds"])} /></Field>
    <label className="flex items-center gap-2 self-end pb-2 text-sm font-medium"><input type="checkbox" className="size-4 accent-primary" checked={value.sale_confirmation_print || false} disabled={disabled} onChange={(event) => update("sale_confirmation_print", event.target.checked as T["sale_confirmation_print"])} />Imprimir confirmação</label>
    <label className="flex items-center gap-2 self-end pb-2 text-sm font-medium"><input type="checkbox" className="size-4 accent-primary" checked={value.sound_enabled ?? true} disabled={disabled} onChange={(event) => update("sound_enabled", event.target.checked as T["sound_enabled"])} />Som habilitado</label>
  </div>;
}

function EffectiveSettings({ value }: { value: PosSettings }) {
  return <div className="grid gap-2 rounded-lg border border-subtle bg-surface-muted p-3 text-xs sm:grid-cols-2">
    <span>Caixa: <strong>{value.cash_binding_mode || "Flexível"}</strong></span>
    <span>Impressora: <strong>{value.receipt_printer || "Nenhuma"}</strong></span>
    <span>Impressão: <strong>{value.receipt_print_mode || "manual"}</strong></span>
    <span>Recibo: <strong>{value.receipt_format || "detailed"}, {value.copies || 1} via(s)</strong></span>
  </div>;
}

function PosDevicesAdministration() {
  const { currentCompany, currentBranch, user, hasPermission } = useAuth();
  const canManage = hasPermission(permissions.managePosDevices);
  const [devices, setDevices] = useState<Paginated<PosDevice> | null>(null);
  const [branchId, setBranchId] = useState("");
  const [branchSettings, setBranchSettings] = useState<BranchPosSettings | null>(null);
  const [licensingCode, setLicensingCode] = useState("");
  const [selected, setSelected] = useState<PosDevice | null>(null);
  const [settings, setSettings] = useState<DeviceSettings | null>(null);
  const [tab, setTab] = useState<"general" | "settings">("general");
  const [name, setName] = useState("");
  const [replacementDevice, setReplacementDevice] = useState("");
  const [pendingAction, setPendingAction] = useState<DeviceAction | null>(null);
  const [confirmRotateLicense, setConfirmRotateLicense] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const availableBranches = (user?.branches || []).filter((branch) => branch.company_id === currentCompany?.id && branch.status === "active");
  const settingsBranchId = branchId || (currentBranch ? String(currentBranch.id) : "");
  const settingsBranch = availableBranches.find((branch) => String(branch.id) === settingsBranchId);

  async function load(path?: string, companyId = currentCompany?.id, branch = branchId) {
    if (!companyId) { setDevices(null); setLoading(false); return; }
    setLoading(true); setError("");
    const query = new URLSearchParams({ company: String(companyId) });
    if (branch) query.set("branch", branch);
    try { setDevices(await http.get<Paginated<PosDevice>>(path || `pos/admin/devices/?${query}`)); }
    catch (caught) { setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar os dispositivos POS."); }
    finally { setLoading(false); }
  }

  useEffect(() => {
    const initialBranch = currentBranch ? String(currentBranch.id) : "";
    setBranchId(initialBranch); setSelected(null); setSettings(null); setSuccess("");
    void load(undefined, currentCompany?.id, initialBranch);
  }, [currentCompany?.id, currentBranch?.id]);

  useEffect(() => {
    if (!settingsBranchId || !currentCompany) { setBranchSettings(null); setLicensingCode(""); return; }
    let active = true;
    Promise.all([
      http.get<BranchPosSettings>(`branches/${settingsBranchId}/pos-settings/?company=${currentCompany.id}`),
      http.get<LicensingCodeResponse>(`branches/${settingsBranchId}/licensing-code/?company=${currentCompany.id}`),
    ]).then(([defaults, license]) => {
      if (!active) return;
      setBranchSettings(defaults); setLicensingCode(license.licensing_code);
    }).catch((caught) => active && setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as configurações do POS."));
    return () => { active = false; };
  }, [settingsBranchId, currentCompany?.id]);

  async function openDevice(device: PosDevice) {
    if (!currentCompany) return;
    setSelected(device); setName(device.name); setSettings(null); setTab("general"); setReplacementDevice(""); setError("");
    try { const detail = await http.get<PosDevice>(`pos/admin/devices/${device.id}/?company=${currentCompany.id}`); setSelected(detail); setName(detail.name); }
    catch (caught) { setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar o dispositivo."); }
  }

  async function openSettings() {
    if (!selected || !currentCompany || settings) return;
    setSettingsLoading(true); setError("");
    try { setSettings(await http.get<DeviceSettings>(`pos/admin/devices/${selected.id}/settings/?company=${currentCompany.id}`)); }
    catch (caught) { setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as configurações do dispositivo."); }
    finally { setSettingsLoading(false); }
  }

  async function saveName() {
    if (!selected || !currentCompany || !canManage || !name.trim()) return;
    setSaving(true); setError("");
    try { setSelected(await http.patch<PosDevice>(`pos/admin/devices/${selected.id}/?company=${currentCompany.id}`, { name: name.trim() })); setSuccess("Dispositivo atualizado."); await load(); }
    catch (caught) { setError(caught instanceof ApiError ? caught.message : "Não foi possível atualizar o dispositivo."); }
    finally { setSaving(false); }
  }

  async function saveSettings() {
    if (!selected || !settings || !currentCompany || !canManage) return;
    setSaving(true); setError("");
    try { setSettings(await http.patch<DeviceSettings>(`pos/admin/devices/${selected.id}/settings/?company=${currentCompany.id}`, settings)); setSuccess("Override do dispositivo salvo."); }
    catch (caught) { setError(caught instanceof ApiError ? caught.message : "Não foi possível salvar as configurações do dispositivo."); }
    finally { setSaving(false); }
  }

  async function saveBranchSettings() {
    if (!branchSettings || !settingsBranchId || !currentCompany || !canManage) return;
    setSaving(true); setError("");
    try { setBranchSettings(await http.patch<BranchPosSettings>(`branches/${settingsBranchId}/pos-settings/?company=${currentCompany.id}`, branchSettings)); setSuccess("Configurações padrão da filial salvas."); }
    catch (caught) { setError(caught instanceof ApiError ? caught.message : "Não foi possível salvar as configurações do POS."); }
    finally { setSaving(false); }
  }

  async function copyLicensingCode() {
    if (!licensingCode) return;
    try { await navigator.clipboard.writeText(licensingCode); setSuccess("Código de licenciamento copiado."); }
    catch { setError("Não foi possível copiar o código de licenciamento."); }
  }

  async function performAction() {
    if (!selected || !pendingAction || !currentCompany || !canManage) return;
    setSaving(true); setError("");
    try {
      if (pendingAction === "clear-settings") {
        await http.delete(`pos/admin/devices/${selected.id}/settings/?company=${currentCompany.id}`);
        setSettings(null); setSuccess("Override removido. O dispositivo voltou a usar os padrões da filial.");
      } else {
        const body = pendingAction === "replace" ? { replacement_device: replacementDevice } : undefined;
        const updated = await http.post<PosDevice>(`pos/admin/devices/${selected.id}/${pendingAction}/?company=${currentCompany.id}`, body);
        setSelected(updated); setSuccess(`Dispositivo ${pendingAction === "block" ? "bloqueado" : pendingAction === "unblock" ? "reativado" : pendingAction === "revoke" ? "revogado" : "substituído"}.`); await load();
      }
      setPendingAction(null);
    } catch (caught) { setError(caught instanceof ApiError ? caught.message : "Não foi possível concluir a ação."); }
    finally { setSaving(false); }
  }

  async function rotateLicense() {
    if (!settingsBranchId || !currentCompany || !canManage) return;
    setSaving(true); setError("");
    try { const response = await http.post<LicensingCodeResponse>(`branches/${settingsBranchId}/rotate-licensing-code/?company=${currentCompany.id}`); setLicensingCode(response.licensing_code); setSuccess("Código de licenciamento rotacionado."); }
    catch (caught) { setError(caught instanceof ApiError ? caught.message : "Não foi possível rotacionar o código de licenciamento."); }
    finally { setSaving(false); setConfirmRotateLicense(false); }
  }

  const actionLabel = pendingAction === "block" ? "Bloquear" : pendingAction === "unblock" ? "Reativar" : pendingAction === "revoke" ? "Revogar" : pendingAction === "replace" ? "Substituir" : "Remover override";
  return <>
    <PageHeader title="Dispositivos POS" description="Administre dispositivos, licenciamento e configurações do CORE POS." />
    <main className="space-y-4 p-4 sm:p-6 lg:p-8">
      {error && !selected && <Alert message={error} />}
      {success && <Alert type="success" message={success} />}
      <section className="card space-y-4 p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between"><Field label="Filial"><Select value={branchId} onChange={(event) => { setBranchId(event.target.value); void load(undefined, currentCompany?.id, event.target.value); }}><option value="">Todas as filiais</option>{availableBranches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}</Select></Field><Button variant="secondary" onClick={() => void load()}><RotateCw className="size-4" />Atualizar</Button></div>
        {settingsBranch && <div className="space-y-4 border-t border-subtle pt-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-sm font-bold">Padrões POS: {settingsBranch.name}</h2><p className="mt-1 text-xs text-muted">A filial define os defaults; o dispositivo só pode aplicar override local.</p></div>{licensingCode && <div className="flex items-center gap-2"><code className="rounded bg-surface-muted px-2 py-1 text-xs">{licensingCode}</code><Button variant="secondary" onClick={() => void copyLicensingCode()}><Copy className="size-4" />Copiar</Button><Button variant="secondary" disabled={!canManage} onClick={() => setConfirmRotateLicense(true)}><KeyRound className="size-4" />Rotacionar</Button></div>}</div>{branchSettings ? <><PosSettingsFields value={branchSettings} onChange={setBranchSettings} disabled={!canManage || saving} /><div className="flex justify-end"><Button loading={saving} disabled={!canManage} onClick={() => void saveBranchSettings()}><Settings2 className="size-4" />Salvar padrões</Button></div></> : <div className="flex h-20 items-center justify-center text-primary"><Spinner /></div>}</div>}
      </section>
      <section className="card overflow-hidden"><div className="card-header"><div><h2 className="text-sm font-bold">Dispositivos cadastrados</h2><p className="mt-1 text-[11px] text-muted">Online considera heartbeat nos últimos cinco minutos.</p></div><MonitorSmartphone className="size-5 text-muted" /></div>{loading ? <TableLoading columns={7} /> : devices?.results.length ? <><div className="table-wrap"><table className="data-table"><thead><tr><th>Dispositivo</th><th>Filial</th><th>Status</th><th>Conexão</th><th>Pareado em</th><th>Último sinal</th><th className="text-right">Ações</th></tr></thead><tbody>{devices.results.map((device) => <tr key={device.id}><td><strong className="block">{device.name}</strong><small className="text-muted">{device.device_type} · {device.device_model || "Modelo não informado"} · {device.app_version || "Versão não informada"}</small></td><td>{device.branch_name || "-"}</td><td><span className="text-xs font-semibold">{statusLabel[device.status]}</span></td><td><OnlineBadge device={device} /></td><td>{device.paired_at ? formatDate(device.paired_at) : "Não informado"}</td><td>{device.last_seen_at ? formatDate(device.last_seen_at) : "Nunca"}</td><td><div className="flex justify-end"><button className="icon-button" aria-label="Ver dispositivo" onClick={() => void openDevice(device)}><Pencil className="size-4" /></button></div></td></tr>)}</tbody></table></div><Pagination count={devices.count} next={devices.next} previous={devices.previous} onPage={load} /></> : <EmptyState title="Nenhum dispositivo encontrado" description="Altere a filial selecionada ou pareie um dispositivo no aplicativo POS." />}</section>
    </main>
    <Modal open={!!selected} title={selected?.name || "Dispositivo POS"} description="Inventário, lifecycle e configurações locais sem expor credenciais." onClose={() => !saving && setSelected(null)} size="xl">{selected && <div><div className="flex border-b border-subtle"><button className={`border-b-2 px-5 py-3 text-xs font-semibold ${tab === "general" ? "border-primary text-primary" : "border-transparent text-muted"}`} onClick={() => setTab("general")}>Geral</button><button className={`border-b-2 px-5 py-3 text-xs font-semibold ${tab === "settings" ? "border-primary text-primary" : "border-transparent text-muted"}`} onClick={() => { setTab("settings"); void openSettings(); }}>Configuração</button></div><div className="space-y-5 p-5 sm:p-6">{error && <Alert message={error} />}{tab === "general" ? <><div className="grid gap-4 sm:grid-cols-2"><Field label="Nome"><Input value={name} disabled={!canManage || saving} onChange={(event) => setName(event.target.value)} /></Field><div><span className="label">Situação</span><p className="text-sm font-semibold">{statusLabel[selected.status]} · <OnlineBadge device={selected} /></p></div><div><span className="label">Tipo e modelo</span><p className="text-sm">{selected.device_type} · {selected.device_model || "Não informado"}</p></div><div><span className="label">Filial</span><p className="text-sm">{selected.branch_name || "Não informada"}</p></div><div><span className="label">Versão</span><p className="text-sm">{selected.app_version || "Não informada"}</p></div><div><span className="label">Pareado em</span><p className="text-sm">{selected.paired_at ? formatDate(selected.paired_at) : "Não informado"}</p></div><div><span className="label">Último sinal</span><p className="text-sm">{selected.last_seen_at ? formatDate(selected.last_seen_at) : "Nunca"}</p></div></div><div className="flex justify-end"><Button loading={saving} disabled={!canManage || !name.trim()} onClick={() => void saveName()}>Salvar nome</Button></div><div className="border-t border-subtle pt-5"><h3 className="text-sm font-bold">Ações do dispositivo</h3><div className="mt-3 flex flex-wrap gap-2"><Button variant="secondary" disabled={!canManage || selected.status !== "ACTIVE"} onClick={() => setPendingAction("block")}><ShieldBan className="size-4" />Bloquear</Button><Button variant="secondary" disabled={!canManage || selected.status !== "BLOCKED"} onClick={() => setPendingAction("unblock")}><Power className="size-4" />Reativar</Button><Button variant="danger" disabled={!canManage || ["REVOKED", "REPLACED"].includes(selected.status)} onClick={() => setPendingAction("revoke")}><Trash2 className="size-4" />Revogar</Button></div><div className="mt-4 grid gap-2 sm:grid-cols-[1fr_auto]"><Select value={replacementDevice} disabled={!canManage} onChange={(event) => setReplacementDevice(event.target.value)}><option value="">Dispositivo substituto da mesma filial</option>{(devices?.results || []).filter((device) => device.id !== selected.id && device.branch === selected.branch && device.status === "ACTIVE").map((device) => <option key={device.id} value={device.id}>{device.name}</option>)}</Select><Button variant="secondary" disabled={!canManage || !replacementDevice || selected.status !== "ACTIVE"} onClick={() => setPendingAction("replace")}>Substituir</Button></div></div></> : settingsLoading ? <div className="flex h-40 items-center justify-center text-primary"><Spinner /></div> : settings ? <><p className="text-xs text-muted">Campos vazios usam a configuração padrão da filial. Nenhum destes campos concede permissões.</p><PosSettingsFields value={settings} onChange={setSettings} disabled={!canManage || saving} />{settings.effective_settings && <><h3 className="text-sm font-bold">Configuração efetiva</h3><EffectiveSettings value={settings.effective_settings} /></>}<div className="flex flex-wrap justify-end gap-2"><Button variant="secondary" disabled={!canManage} onClick={() => setPendingAction("clear-settings")}>Remover override</Button><Button loading={saving} disabled={!canManage} onClick={() => void saveSettings()}><Settings2 className="size-4" />Salvar override</Button></div></> : null}</div></div>}</Modal>
    <ConfirmDialog open={!!pendingAction} title={`${actionLabel} dispositivo`} message={pendingAction === "clear-settings" ? "Remover as configurações específicas? O dispositivo voltará a usar os padrões da filial." : `Confirma ${actionLabel.toLowerCase()} “${selected?.name || ""}”?${pendingAction === "revoke" ? " A credencial atual deixará de operar." : ""}`} confirmLabel={actionLabel} danger={pendingAction === "block" || pendingAction === "revoke" || pendingAction === "clear-settings"} loading={saving} onClose={() => !saving && setPendingAction(null)} onConfirm={() => void performAction()} />
    <ConfirmDialog open={confirmRotateLicense} title="Rotacionar código de licenciamento" message="O código atual deixará de valer. Dispositivos já pareados não serão revogados." confirmLabel="Rotacionar" danger loading={saving} onClose={() => !saving && setConfirmRotateLicense(false)} onConfirm={() => void rotateLicense()} />
  </>;
}

export default function PosDevicesPage() {
  return <AdminGuard requiredPermissions={[permissions.viewPosDevices, permissions.managePosDevices]}><PosDevicesAdministration /></AdminGuard>;
}
