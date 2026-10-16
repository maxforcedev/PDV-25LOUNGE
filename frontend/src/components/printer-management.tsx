"use client";

import { useEffect, useEffectEvent, useRef, useState } from "react";
import { Activity, Archive, Pencil, Plus, Power, Printer } from "lucide-react";
import { DocumentPrintRoutes } from "@/components/document-print-routes";
import { Alert, Button, EmptyState, Field, Input, Modal, Pagination, Select, StatusBadge, TableLoading } from "@/components/ui";
import { fieldError, formatDate } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { isCurrentPrintAdministrationRequest } from "@/lib/print-administration";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { Paginated, PrinterDevice, PrintJob, PrintJobStatus, ProductionDestination } from "@/types";

const connectionLabels = { network: "Rede", usb: "USB", bluetooth: "Bluetooth", stone_integrated: "Stone integrada" } as const;
const operationalLabels = { not_tested: "Não testada", online: "Online", offline: "Offline", bridge_unavailable: "Executor indisponível", failed: "Falha" } as const;
const jobStatusLabels: Record<PrintJobStatus, string> = { pending: "Pendente", processing: "Processando", printed: "Impresso", failed: "Falhou", uncertain: "Resultado incerto", cancelled: "Cancelado" };
type Tab = "equipment" | "routes" | "history" | "diagnostic";

export function PrinterManagement({ embedded = false, branchId, branchName, branchPermissions, onRouteChanges }: {
  embedded?: boolean;
  branchId?: number;
  branchName?: string;
  branchPermissions?: readonly string[];
  onRouteChanges?: (dirty: boolean) => void;
}) {
  const { currentBranch, supportSession, user } = useAuth();
  const selectedBranchId = branchId ?? currentBranch?.id;
  const selectedBranchName = branchName ?? currentBranch?.name ?? "filial selecionada";
  const selectedPermissions = branchPermissions ?? currentBranch?.permissions ?? [];
  const hasBranchPermission = (permission: string) => Boolean(user?.is_superuser || selectedPermissions.includes(permission));
  const readOnly = supportSession?.mode === "READ_ONLY";
  const canManage = hasBranchPermission(permissions.managePrinters) && !readOnly;
  const canRoutes = hasBranchPermission(permissions.managePrintRoutes) && !readOnly;
  const canHistory = hasBranchPermission(permissions.viewPrintJobs);
  const canRetry = hasBranchPermission(permissions.retryPrintJobs) && !readOnly;
  const canReprint = hasBranchPermission(permissions.reprintPrintJobs) && !readOnly;
  const equipmentRequestRef = useRef(0);
  const historyRequestRef = useRef(0);
  const saveRequestRef = useRef(0);
  const [tab, setTab] = useState<Tab>("equipment");
  const [routesDirty, setRoutesDirty] = useState(false);
  const [devices, setDevices] = useState<PrinterDevice[]>([]);
  const [destinations, setDestinations] = useState<ProductionDestination[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [editing, setEditing] = useState<PrinterDevice | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState<number | null>(null);
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [name, setName] = useState("");
  const [connectionType, setConnectionType] = useState<PrinterDevice["connection_type"]>("network");
  const [deviceStatus, setDeviceStatus] = useState<"active" | "inactive">("active");
  const [host, setHost] = useState("");
  const [port, setPort] = useState("9100");
  const [timeout, setTimeout] = useState("5");
  const [paperWidth, setPaperWidth] = useState("80");
  const [vendorId, setVendorId] = useState("");
  const [productId, setProductId] = useState("");
  const [serial, setSerial] = useState("");
  const [deviceName, setDeviceName] = useState("");
  const [identifier, setIdentifier] = useState("");
  const [destinationIds, setDestinationIds] = useState<number[]>([]);
  const [history, setHistory] = useState<Paginated<PrintJob> | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyStatus, setHistoryStatus] = useState<"" | PrintJobStatus>("");
  const [historyOrigin, setHistoryOrigin] = useState<"" | "test" | "document" | "production">("");

  const options = selectedBranchId ? { branchId: selectedBranchId } : undefined;
  async function load() {
    if (!selectedBranchId || !canManage) { setDevices([]); setDestinations([]); setLoading(false); return; }
    const token = ++equipmentRequestRef.current;
    setLoading(true); setError("");
    try {
      const [items, availableDestinations] = await Promise.all([
        http.getAll<PrinterDevice>("printer-devices/", { branchId: selectedBranchId }),
        http.getAll<ProductionDestination>("production-destinations/", { branchId: selectedBranchId }).catch(() => []),
      ]);
      if (isCurrentPrintAdministrationRequest(token, equipmentRequestRef.current)) { setDevices(items); setDestinations(availableDestinations); }
    } catch (caught) {
      if (isCurrentPrintAdministrationRequest(token, equipmentRequestRef.current)) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as impressoras.");
    } finally { if (isCurrentPrintAdministrationRequest(token, equipmentRequestRef.current)) setLoading(false); }
  }
  const loadCurrent = useEffectEvent(() => { void load(); });
  useEffect(() => {
    equipmentRequestRef.current += 1;
    historyRequestRef.current += 1;
    saveRequestRef.current += 1;
    setEditorOpen(false);
    setHistory(null);
    if (canManage) loadCurrent(); else setLoading(false);
  }, [selectedBranchId, canManage]);

  function show(device?: PrinterDevice) {
    const config = device?.technical_configuration || {};
    setEditing(device || null); setName(device?.name || ""); setConnectionType(device?.connection_type || "network"); setDeviceStatus(device?.status || "active");
    setHost(String(config.host || "")); setPort(String(config.port || "9100")); setTimeout(String(config.timeout || 5)); setPaperWidth(String(config.paper_width || 80));
    setVendorId(String(config.vendor_id || "")); setProductId(String(config.product_id || "")); setSerial(String(config.serial || "")); setDeviceName(String(config.device_name || "")); setIdentifier(String(config.identifier || ""));
    setDestinationIds(device?.destination_ids || []); setFields({}); setError(""); setEditorOpen(true);
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault(); if (!selectedBranchId || !canManage) return;
    const technical_configuration = connectionType === "network" ? { host: host.trim(), port: Number(port), timeout: Number(timeout), paper_width: Number(paperWidth), cut: true }
      : connectionType === "usb" ? { vendor_id: vendorId.trim(), product_id: productId.trim(), serial: serial.trim(), identifier: serial.trim() || `${vendorId.trim()}:${productId.trim()}` }
      : connectionType === "bluetooth" ? { device_name: deviceName.trim(), identifier: identifier.trim() } : editing?.technical_configuration || {};
    const token = ++saveRequestRef.current;
    setSaving(true); setError(""); setFields({});
    try {
      const body = { name, connection_type: connectionType, status: deviceStatus, destination_ids: destinationIds, technical_configuration };
      if (editing) await http.patch(`printer-devices/${editing.id}/`, body, options); else await http.post("printer-devices/", body, options);
      if (token !== saveRequestRef.current) return;
      setEditorOpen(false); setSuccess(editing ? "Impressora atualizada." : "Impressora cadastrada."); await load();
    } catch (caught) { if (token === saveRequestRef.current) { if (caught instanceof ApiError) { setError(caught.message); setFields(caught.fields); } else setError("Não foi possível salvar a impressora."); } } finally { if (token === saveRequestRef.current) setSaving(false); }
  }
  async function testPrinter(device: PrinterDevice) {
    const token = ++saveRequestRef.current;
    setBusy(device.id); setError(""); setSuccess("");
    try { await http.post<PrintJob>(`printer-devices/${device.id}/test/`, {}, options); if (token !== saveRequestRef.current) return; setSuccess("Teste solicitado. Aguardando confirmação do CORE POS local."); await load(); }
    catch (caught) { if (token === saveRequestRef.current) setError(caught instanceof ApiError ? caught.message : "Não foi possível solicitar o teste."); } finally { if (token === saveRequestRef.current) setBusy(null); }
  }
  async function toggle(device: PrinterDevice) {
    const token = ++saveRequestRef.current;
    setBusy(device.id); setError("");
    try {
      await http.patch(`printer-devices/${device.id}/`, { status: device.status === "active" ? "inactive" : "active" }, options);
      if (token !== saveRequestRef.current) return;
      setSuccess(device.status === "active" ? "Impressora arquivada. Os vínculos com setores e o histórico foram preservados; novos jobs não serão encaminhados a ela." : "Impressora ativada."); await load();
    } catch (caught) { if (token === saveRequestRef.current) setError(caught instanceof ApiError ? caught.message : "Não foi possível alterar a impressora."); } finally { if (token === saveRequestRef.current) setBusy(null); }
  }
  async function loadHistory(path?: string, status = historyStatus) {
    if (!selectedBranchId) return;
    const token = ++historyRequestRef.current; setHistoryLoading(true); setError("");
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (historyOrigin) params.set("origin", historyOrigin);
    const query = `print-jobs/${params.size ? `?${params}` : ""}`;
    try { const result = await http.get<Paginated<PrintJob>>(path || query, { branchId: selectedBranchId }); if (isCurrentPrintAdministrationRequest(token, historyRequestRef.current)) setHistory(result); }
    catch (caught) { if (isCurrentPrintAdministrationRequest(token, historyRequestRef.current)) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar o histórico."); }
    finally { if (isCurrentPrintAdministrationRequest(token, historyRequestRef.current)) setHistoryLoading(false); }
  }
  useEffect(() => { if (tab === "history" && canHistory) void loadHistory(); }, [tab, selectedBranchId, historyStatus, historyOrigin]);
  async function action(job: PrintJob, name: "retry" | "reprint") {
    const token = ++saveRequestRef.current;
    setBusy(job.id); setError("");
    try {
      await http.post(`print-jobs/${job.id}/${name}/`, name === "reprint" ? { reason: "Reimpressão solicitada pela administração da filial." } : {}, options);
      if (token !== saveRequestRef.current) return;
      setSuccess(name === "retry" ? "Retry técnico solicitado para o CORE POS local." : "Reimpressão explícita criada na fila."); await loadHistory();
    } catch (caught) { if (token === saveRequestRef.current) setError(caught instanceof ApiError ? caught.message : "Não foi possível concluir a ação."); } finally { if (token === saveRequestRef.current) setBusy(null); }
  }
  function changeTab(next: Tab) {
    if (routesDirty && next !== "routes" && !window.confirm("Há alterações de rotas não salvas. Deseja descartá-las?")) return;
    if (routesDirty && next !== "routes") setRoutesDirty(false);
    setTab(next);
  }
  useEffect(() => {
    if (tab === "equipment" && !canManage) setTab(canRoutes ? "routes" : "history");
  }, [tab, canManage, canRoutes]);
  const tabs: Array<[Tab, string, boolean]> = [["equipment", "Equipamentos", canManage], ["routes", "Rotas", canRoutes], ["history", "Histórico", canHistory], ["diagnostic", "Diagnóstico", canManage]];
  const shell = <div className={embedded ? "space-y-4" : "space-y-4 p-4 sm:p-6 lg:p-8"}>
    {error && !editorOpen && <Alert message={error} />}{success && <Alert type="success" message={success} />}
    <div className="flex flex-wrap gap-1 rounded-lg border border-subtle bg-surface-muted p-1" role="tablist" aria-label="Administração de impressão">
      {tabs.filter(([, , allowed]) => allowed).map(([value, label]) => <button key={value} type="button" role="tab" aria-selected={tab === value} onClick={() => changeTab(value)} className={`rounded-md px-3 py-2 text-xs font-semibold ${tab === value ? "bg-surface text-fg shadow-sm" : "text-muted hover:text-fg"}`}>{label}</button>)}
    </div>
    {tab === "equipment" && <>
      {!canManage ? <Alert message="Seu perfil pode consultar outros dados de impressão, mas não pode administrar equipamentos." /> : <div className="flex justify-end"><Button onClick={() => show()}><Plus className="size-4" />Adicionar impressora</Button></div>}
      <section className="overflow-hidden rounded-xl border border-subtle">{loading ? <TableLoading columns={5} /> : devices.length ? <div className="grid gap-3 p-4 lg:grid-cols-2">{devices.map((device) => <article key={device.id} className="rounded-xl border border-subtle bg-surface p-4"><div className="flex items-start justify-between gap-3"><div><strong>{device.name}</strong><p className="mt-1 text-xs text-muted">{connectionLabels[device.connection_type]}{device.connection_summary ? ` · ${device.connection_summary}` : ""}</p></div><StatusBadge active={device.status === "active"} /></div><p className="mt-3 text-xs text-muted">Estado operacional: <strong>{operationalLabels[device.operational_status]}</strong> · Último teste: {device.last_test_at ? formatDate(device.last_test_at) : "não realizado"}</p><p className="mt-2 text-xs text-muted">Setores: {device.destination_ids.map((id) => destinations.find((item) => item.id === id)?.name || `Setor #${id}`).join(", ") || "Nenhum vínculo"}</p>{device.connection_type !== "network" && <p className="mt-3 rounded-md bg-warning-surface p-2 text-xs text-warning-strong">Cadastro preservado. USB e Bluetooth exigem executor compatível e não são executados pelo CORE POS atual.</p>}{device.last_operational_error && <p className="mt-2 text-xs text-danger-strong">{device.last_operational_error}</p>}<div className="mt-4 flex flex-wrap gap-2">{device.connection_type === "network" && <Button type="button" variant="secondary" loading={busy === device.id} disabled={!canManage || device.status !== "active"} onClick={() => void testPrinter(device)}>Testar</Button>}{canManage && <><Button type="button" variant="secondary" onClick={() => show(device)}><Pencil className="size-4" />Editar</Button><Button type="button" variant="secondary" loading={busy === device.id} onClick={() => void toggle(device)}>{device.status === "active" ? <Archive className="size-4" /> : <Power className="size-4" />}{device.status === "active" ? "Arquivar" : "Ativar"}</Button></>}</div></article>)}</div> : <EmptyState title="Nenhuma impressora cadastrada" description="Cadastre o primeiro equipamento desta filial." />}</section>
    </>}
    {tab === "routes" && (canRoutes ? <DocumentPrintRoutes branchId={selectedBranchId} branchName={selectedBranchName} onDirtyChange={(dirty) => { setRoutesDirty(dirty); onRouteChanges?.(dirty); }} /> : <Alert message="Seu perfil não pode administrar rotas de impressão." />)}
    {tab === "history" && <section className="space-y-3 rounded-xl border border-subtle p-4"><div className="flex flex-wrap items-end justify-between gap-3"><div><strong className="text-sm">Histórico da filial</strong><p className="mt-1 text-xs text-muted">Jobs são paginados no servidor. Retry só vale para falha antes do envio físico; resultado incerto exige reimpressão explícita.</p></div><div className="flex gap-2"><Field label="Ocorrência"><Select value={historyOrigin} onChange={(event) => setHistoryOrigin(event.target.value as "" | "test" | "document" | "production")}><option value="">Todas</option><option value="document">Documento</option><option value="production">Produção</option><option value="test">Teste</option></Select></Field><Field label="Status"><Select value={historyStatus} onChange={(event) => setHistoryStatus(event.target.value as "" | PrintJobStatus)}><option value="">Todos</option>{Object.entries(jobStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select></Field></div></div>{historyLoading ? <TableLoading columns={5} /> : history?.results.length ? <><div className="divide-y divide-subtle rounded-lg border border-subtle">{history.results.map((job) => <article key={job.id} className="flex flex-col gap-3 p-3 sm:flex-row sm:items-center sm:justify-between"><div><strong className="text-sm">{job.origin_label}</strong><p className="mt-1 text-xs text-muted">{formatDate(job.created_at)} · {job.printer_name} · {jobStatusLabels[job.status]} · tentativa {job.attempts}{job.reprint_number ? ` · reimpressão ${job.reprint_number}` : ""}</p>{job.error_summary && <p className="mt-1 text-xs text-danger-strong">{job.error_summary}</p>}</div><div className="flex gap-2">{canRetry && job.status === "failed" && !job.physical_dispatch_started_at && <Button variant="secondary" loading={busy === job.id} onClick={() => void action(job, "retry")}>Tentar novamente</Button>}{canReprint && job.reprint_eligible && <Button variant="secondary" loading={busy === job.id} onClick={() => void action(job, "reprint")}>Reimprimir</Button>}</div></article>)}</div><Pagination count={history.count} next={history.next} previous={history.previous} onPage={(path) => void loadHistory(path)} /></> : <EmptyState title="Sem histórico" description="Nenhum trabalho atende aos filtros desta filial." />}</section>}
    {tab === "diagnostic" && <section className="grid gap-3 md:grid-cols-2">{loading ? <TableLoading columns={2} /> : devices.map((device) => <article key={device.id} className="rounded-xl border border-subtle p-4"><div className="flex items-center gap-2"><Activity className="size-4 text-primary" /><strong>{device.name}</strong></div><p className="mt-3 text-sm">{operationalLabels[device.operational_status]}</p><p className="mt-1 text-xs text-muted">Última confirmação: {device.last_seen_at ? formatDate(device.last_seen_at) : "nenhuma"}</p>{device.last_operational_error && <p className="mt-3 text-xs text-danger-strong">{device.last_operational_error}</p>}</article>)}</section>}
  </div>;
  return <>{!embedded && <div className="p-4 sm:p-6 lg:p-8"><div className="flex items-center gap-2"><Printer className="size-5 text-primary" /><div><h1 className="text-lg font-bold">Impressoras</h1><p className="text-xs text-muted">Administração da filial {selectedBranchName}.</p></div></div></div>}{shell}<Modal open={editorOpen} title={editing ? "Editar impressora" : "Adicionar impressora"} description="Uma impressora pode atender vários setores sem alterar os vínculos históricos." onClose={() => !saving && setEditorOpen(false)} size="xl"><form onSubmit={submit}><div className="space-y-4 p-5">{error && <Alert message={error} />}<Field label="Nome da impressora" error={fieldError(fields, "name")}><Input required value={name} onChange={(event) => setName(event.target.value)} placeholder="Ex.: Cozinha" /></Field><div className="grid gap-4 sm:grid-cols-2"><Field label="Tipo de conexão"><Select value={connectionType} onChange={(event) => setConnectionType(event.target.value as PrinterDevice["connection_type"])}><option value="network">Rede</option><option value="usb">USB</option><option value="bluetooth">Bluetooth</option><option value="stone_integrated" disabled>Stone integrada</option></Select></Field><Field label="Status administrativo"><Select value={deviceStatus} onChange={(event) => setDeviceStatus(event.target.value as "active" | "inactive")}><option value="active">Ativa</option><option value="inactive">Inativa</option></Select></Field></div><fieldset><legend className="label">Setores atendidos</legend><p className="mb-2 text-xs text-muted">Arquivar preserva estes vínculos e os produtos associados.</p><div className="grid gap-2 sm:grid-cols-2">{destinations.map((destination) => <label key={destination.id} className="flex items-center gap-2 text-xs"><input type="checkbox" checked={destinationIds.includes(destination.id)} disabled={destination.status !== "active"} onChange={(event) => setDestinationIds((current) => event.target.checked ? [...current, destination.id] : current.filter((id) => id !== destination.id))} />{destination.name}{destination.status !== "active" ? " (inativo)" : ""}</label>)}</div></fieldset>{connectionType === "network" && <><div className="grid gap-4 sm:grid-cols-[1fr_8rem_8rem]"><Field label="IP ou hostname"><Input required value={host} onChange={(event) => setHost(event.target.value)} placeholder="192.168.1.50" /></Field><Field label="Porta"><Input required inputMode="numeric" value={port} onChange={(event) => setPort(event.target.value.replace(/\D/g, ""))} /></Field><Field label="Timeout (s)"><Input required inputMode="numeric" value={timeout} onChange={(event) => setTimeout(event.target.value.replace(/\D/g, ""))} /></Field></div><Field label="Largura do papel"><Select value={paperWidth} onChange={(event) => setPaperWidth(event.target.value)}><option value="80">80 mm</option><option value="58">58 mm</option></Select></Field></>}{connectionType === "usb" && <><div className="grid gap-4 sm:grid-cols-2"><Field label="Vendor ID"><Input required value={vendorId} onChange={(event) => setVendorId(event.target.value)} /></Field><Field label="Product ID"><Input required value={productId} onChange={(event) => setProductId(event.target.value)} /></Field></div><Field label="Serial / identificador" optional><Input value={serial} onChange={(event) => setSerial(event.target.value)} /></Field><Alert message="USB será salvo para um executor compatível futuro; o CORE POS atual não o executa." /></>}{connectionType === "bluetooth" && <><Field label="Nome amigável"><Input required value={deviceName} onChange={(event) => setDeviceName(event.target.value)} /></Field><Field label="Identificador Bluetooth"><Input required value={identifier} onChange={(event) => setIdentifier(event.target.value)} /></Field><Alert message="Bluetooth será salvo para um executor compatível futuro; o CORE POS atual não o executa." /></>}</div><div className="flex justify-end gap-2 border-t border-subtle p-4"><Button type="button" variant="secondary" disabled={saving} onClick={() => setEditorOpen(false)}>Cancelar</Button><Button type="submit" loading={saving}>Salvar</Button></div></form></Modal></>;
}
