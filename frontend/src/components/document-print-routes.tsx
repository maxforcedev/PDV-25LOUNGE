"use client";

import { useEffect, useEffectEvent, useRef, useState } from "react";
import { Printer, RotateCcw, Save } from "lucide-react";
import { Alert, Button, EmptyState, Field, Input, Select, Spinner } from "@/components/ui";
import { ApiError, http } from "@/lib/http";
import { buildPrintRouteBatch, isCurrentPrintAdministrationRequest } from "@/lib/print-administration";
import { useAuth } from "@/providers/auth-provider";
import type { PosDevice, PrintDocumentFormat, PrintDocumentType, PrintRoute, PrintRouteMode, PrintRouteOverride, PrinterDevice } from "@/types";

const documentTypes: Array<{ value: PrintDocumentType; label: string; format: boolean }> = [
  { value: "table_conference", label: "Conferência de mesa", format: true },
  { value: "table_final_receipt", label: "Recibo final da mesa", format: true },
  { value: "quick_sale_receipt", label: "Recibo de venda rápida", format: true },
  { value: "payment_receipt", label: "Comprovante de pagamento", format: true },
  { value: "ticket", label: "Ticket", format: false },
];
type Route = PrintRoute | PrintRouteOverride;
type Changes = Partial<Pick<PrintRoute, "mode" | "printer_device_ids" | "copies" | "document_format">>;
const modeLabels: Record<PrintRouteMode, string> = { disabled: "Desabilitado", manual: "Manual", automatic: "Automático" };
function blank(documentType: PrintDocumentType, branch: number, posDeviceId?: string): Route {
  return posDeviceId ? { id: -Date.now(), pos_device: posDeviceId, pos_device_name: "", document_type: documentType, inherit_branch: false, mode: "disabled", printer_device_ids: [], copies: 1, document_format: "detailed", created_at: "", updated_at: "" }
    : { id: -Date.now(), branch, document_type: documentType, mode: "disabled", printer_device_ids: [], copies: 1, document_format: "detailed", created_at: "", updated_at: "" };
}
function message(caught: unknown, fallback: string) { return caught instanceof ApiError ? caught.message : fallback; }
function comparable(routes: Route[]) { return JSON.stringify(routes.map(({ document_type, mode, printer_device_ids, copies, document_format, ...rest }) => ({ document_type, mode, printer_device_ids: [...printer_device_ids].sort(), copies, document_format, inherit_branch: "inherit_branch" in rest ? rest.inherit_branch : undefined })).sort((a, b) => a.document_type.localeCompare(b.document_type))); }

export function DocumentPrintRoutes({ posDeviceId, branchId, branchName, onDirtyChange }: { posDeviceId?: string; branchId?: number | string; branchName?: string; onDirtyChange?: (dirty: boolean) => void }) {
  const { currentBranch, supportSession, user } = useAuth();
  const selectedBranchId = branchId ?? currentBranch?.id;
  const selectedBranchName = branchName ?? user?.branches.find((branch) => String(branch.id) === String(selectedBranchId))?.name ?? currentBranch?.name ?? "nenhuma";
  const readOnly = supportSession?.mode === "READ_ONLY";
  const request = useRef(0);
  const [routes, setRoutes] = useState<Route[]>([]);
  const [branchRoutes, setBranchRoutes] = useState<PrintRoute[]>([]);
  const [printers, setPrinters] = useState<PrinterDevice[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [baseline, setBaseline] = useState("");
  const dirty = !posDeviceId && !!baseline && baseline !== comparable(routes);
  useEffect(() => { onDirtyChange?.(dirty); }, [dirty, onDirtyChange]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn); return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  async function load() {
    if (!selectedBranchId) { setRoutes([]); setLoading(false); return; }
    const token = ++request.current; setLoading(true); setError("");
    try {
      const [items, devices, inherited] = await Promise.all([
        http.getAll<PrintRoute | PrintRouteOverride>(posDeviceId ? "print-route-overrides/" : "print-routes/", { branchId: selectedBranchId }),
        http.getAll<PrinterDevice>("printer-devices/", { branchId: selectedBranchId }),
        posDeviceId ? http.getAll<PrintRoute>("print-routes/", { branchId: selectedBranchId }) : Promise.resolve([]),
      ]);
      if (!isCurrentPrintAdministrationRequest(token, request.current)) return;
      const visible = posDeviceId ? (items as PrintRouteOverride[]).filter((route) => route.pos_device === posDeviceId) : items;
      setRoutes(visible); setBranchRoutes(inherited); setPrinters(devices.filter((device) => device.status === "active" && device.connection_type === "network")); setBaseline(comparable(visible));
    } catch (caught) { if (isCurrentPrintAdministrationRequest(token, request.current)) setError(message(caught, "Não foi possível carregar as rotas de impressão.")); }
    finally { if (isCurrentPrintAdministrationRequest(token, request.current)) setLoading(false); }
  }
  const loadCurrent = useEffectEvent(() => { void load(); });
  useEffect(() => { request.current += 1; setRoutes([]); setBranchRoutes([]); setBaseline(""); loadCurrent(); }, [selectedBranchId, posDeviceId]);
  function valueFor(definition: PrintDocumentType) {
    const route = routes.find((item) => item.document_type === definition);
    const inherited = branchRoutes.find((item) => item.document_type === definition);
    const isInherited = Boolean(posDeviceId && (!route || ("inherit_branch" in route && route.inherit_branch)));
    return { route, inherited, isInherited, value: isInherited && inherited ? inherited : route || blank(definition, Number(selectedBranchId) || 0, posDeviceId) };
  }
  function update(type: PrintDocumentType, changes: Changes, inherited?: PrintRoute) {
    setRoutes((items) => {
      const existing = items.find((item) => item.document_type === type);
      const inheritedValues = inherited ? { mode: inherited.mode, printer_device_ids: inherited.printer_device_ids, copies: inherited.copies, document_format: inherited.document_format } : {};
      if (existing) return items.map((item) => item.document_type === type ? { ...item, ...(posDeviceId && "inherit_branch" in item && item.inherit_branch ? inheritedValues : {}), ...changes, ...(posDeviceId ? { inherit_branch: false } : {}) } : item);
      return [...items, { ...blank(type, Number(selectedBranchId) || 0, posDeviceId), ...inheritedValues, ...changes }];
    });
  }
  async function saveAll() {
    if (!selectedBranchId || readOnly) return;
    const payload = buildPrintRouteBatch(documentTypes.map((definition) => definition.value), (documentType) => valueFor(documentType as PrintDocumentType).value);
    setSaving(true); setError(""); setSuccess("");
    try { const saved = await http.post<PrintRoute[]>("print-routes/bulk-update/", { routes: payload }, { branchId: selectedBranchId }); setRoutes(saved); setBaseline(comparable(saved)); setSuccess("Todas as rotas foram salvas."); }
    catch (caught) { setError(message(caught, "Nenhuma rota foi salva. Revise as configurações destacadas.")); }
    finally { setSaving(false); }
  }
  async function saveOverride(type: PrintDocumentType) {
    if (!selectedBranchId || !posDeviceId || readOnly) return;
    const { route, value } = valueFor(type); setSaving(true); setError("");
    const body = { document_type: type, mode: value.mode, printer_device_ids: value.printer_device_ids, copies: value.copies, document_format: value.document_format, pos_device: posDeviceId, inherit_branch: false };
    try { const saved = route && route.id > 0 ? await http.patch<PrintRouteOverride>(`print-route-overrides/${route.id}/`, body, { branchId: selectedBranchId }) : await http.post<PrintRouteOverride>("print-route-overrides/", body, { branchId: selectedBranchId }); setRoutes((items) => items.some((item) => item.document_type === type) ? items.map((item) => item.document_type === type ? saved : item) : [...items, saved]); setSuccess("Override salvo."); }
    catch (caught) { setError(message(caught, "Não foi possível salvar o override.")); } finally { setSaving(false); }
  }
  async function inherit(type: PrintDocumentType) {
    const route = routes.find((item) => item.document_type === type); if (!route || !selectedBranchId) return;
    setSaving(true); setError("");
    try { await http.delete(`print-route-overrides/${route.id}/`, { branchId: selectedBranchId }); await load(); setSuccess("Override removido. O POS voltou a herdar a filial."); }
    catch (caught) { setError(message(caught, "Não foi possível remover o override.")); } finally { setSaving(false); }
  }
  return <section className="space-y-4 rounded-xl border border-subtle p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="flex items-center gap-2 text-sm font-bold"><Printer className="size-4 text-primary" />{posDeviceId ? "Overrides de impressão do POS" : "Rotas de impressão"}</h2><p className="mt-1 text-xs text-muted">Filial: {selectedBranchName}. {posDeviceId ? "Sem override, este POS herda a regra da filial." : "Defina todos os documentos e salve as alterações em uma única operação."}</p></div><div className="flex gap-2"><Button variant="secondary" disabled={loading || saving} onClick={() => void load()}><RotateCcw className="size-4" />Atualizar</Button>{!posDeviceId && <Button disabled={readOnly || saving || !dirty} loading={saving} onClick={() => void saveAll()}><Save className="size-4" />Salvar alterações{dirty ? " *" : ""}</Button>}</div></div>{!posDeviceId && <p className="rounded-md bg-surface-muted p-3 text-xs text-muted">As rotas da filial são a fonte oficial. Overrides por POS continuam separados e não são alterados por este salvamento.</p>}{dirty && <Alert message="Há alterações de rotas não salvas." />}{error && <Alert message={error} />}{success && <Alert type="success" message={success} />}{loading ? <div className="flex h-24 items-center justify-center text-primary"><Spinner /></div> : <div className="space-y-3">{documentTypes.map((definition) => { const { route, inherited, isInherited, value } = valueFor(definition.value); const invalid = value.mode !== "disabled" && !value.printer_device_ids.length; return <article key={definition.value} className={`rounded-lg border p-4 ${invalid ? "border-danger/50" : "border-subtle"}`}><div className="mb-3 flex flex-wrap items-center justify-between gap-2"><div><strong className="text-sm">{definition.label}</strong>{isInherited && <span className="ml-2 rounded-full bg-surface-muted px-2 py-1 text-[11px] font-semibold text-muted">Herdando da filial</span>}</div><span className="text-xs font-semibold text-muted">{modeLabels[value.mode]}</span></div>{isInherited && inherited && <p className="mb-3 text-xs text-muted">Efetivo: {inherited.printer_device_ids.map((id) => printers.find((printer) => printer.id === id)?.name || id).join(", ") || "sem impressora"} · {inherited.copies} cópia(s)</p>}<div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><Field label="Modo"><Select value={value.mode} disabled={readOnly || saving} onChange={(event) => update(definition.value, { mode: event.target.value as PrintRouteMode }, inherited)}><option value="disabled">Desabilitado</option><option value="manual">Manual</option><option value="automatic">Automático</option></Select></Field><Field label="Cópias"><Input type="number" min="1" max="10" value={value.copies} disabled={readOnly || saving} onChange={(event) => update(definition.value, { copies: Math.max(1, Number(event.target.value) || 1) }, inherited)} /></Field>{definition.format && <Field label="Formato"><Select value={value.document_format || "detailed"} disabled={readOnly || saving} onChange={(event) => update(definition.value, { document_format: event.target.value as PrintDocumentFormat }, inherited)}><option value="detailed">Detalhado</option><option value="simplified">Simplificado</option></Select></Field>}</div><fieldset className="mt-3"><legend className="label">Impressoras de rede ativas</legend><div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{printers.map((printer) => <label key={printer.id} className="flex items-center gap-2 text-xs"><input type="checkbox" checked={value.printer_device_ids.includes(printer.id)} disabled={readOnly || saving} onChange={(event) => update(definition.value, { printer_device_ids: event.target.checked ? [...value.printer_device_ids, printer.id] : value.printer_device_ids.filter((id) => id !== printer.id) }, inherited)} />{printer.name}</label>)}</div>{!printers.length && <span className="text-xs text-muted">Nenhuma impressora de rede ativa nesta filial.</span>}{invalid && <span className="mt-2 block text-xs text-danger">Selecione ao menos uma impressora para ativar esta rota.</span>}</fieldset>{posDeviceId && <div className="mt-3 flex justify-end gap-2">{route && route.id > 0 && <Button variant="secondary" disabled={readOnly || saving} onClick={() => void inherit(definition.value)}>Usar regra da filial</Button>}<Button disabled={readOnly || saving || invalid} loading={saving} onClick={() => void saveOverride(definition.value)}>{isInherited ? "Criar override" : "Salvar override"}</Button></div>}</article>; })}</div>}</section>;
}

export function PosDocumentRouteOverrides({ branchId }: { branchId?: string }) {
  const { currentCompany, currentBranch } = useAuth(); const [devices, setDevices] = useState<PosDevice[]>([]); const [deviceId, setDeviceId] = useState("");
  useEffect(() => { const selected = branchId || String(currentBranch?.id || ""); if (!currentCompany || !selected) return; http.getAll<PosDevice>(`pos/admin/devices/?company=${currentCompany.id}&branch=${selected}`, { branchId: selected }).then(setDevices).catch(() => setDevices([])); }, [branchId, currentCompany?.id, currentBranch?.id]);
  return <div className="space-y-3"><Field label="Dispositivo POS"><Select value={deviceId} onChange={(event) => setDeviceId(event.target.value)}><option value="">Selecione um POS para configurar overrides</option>{devices.map((device) => <option key={device.id} value={device.id}>{device.name}</option>)}</Select></Field>{deviceId ? <DocumentPrintRoutes posDeviceId={deviceId} branchId={branchId} /> : <EmptyState title="Selecione um dispositivo POS" description="Overrides são opcionais; a regra da filial continuará valendo sem eles." />}</div>;
}
