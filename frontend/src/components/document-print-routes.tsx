"use client";

import { useEffect, useEffectEvent, useRef, useState } from "react";
import { Printer, RotateCcw, Save } from "lucide-react";
import { Alert, Button, EmptyState, Field, Input, Select, Spinner } from "@/components/ui";
import { ApiError, http } from "@/lib/http";
import { useAuth } from "@/providers/auth-provider";
import type { PosDevice, PrintDocumentFormat, PrintDocumentType, PrintRoute, PrintRouteMode, PrintRouteOverride, PrinterRouteDevice } from "@/types";

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
  return posDeviceId
    ? { id: -Date.now(), pos_device: posDeviceId, pos_device_name: "", document_type: documentType, inherit_branch: false, mode: "disabled", printer_device_ids: [], copies: 1, document_format: "detailed", created_at: "", updated_at: "" }
    : { id: -Date.now(), branch, document_type: documentType, mode: "disabled", printer_device_ids: [], copies: 1, document_format: "detailed", created_at: "", updated_at: "" };
}

function message(caught: unknown, fallback: string) {
  return caught instanceof ApiError ? caught.message : fallback;
}

function routeSnapshot(route: Route) {
  return JSON.stringify({
    document_type: route.document_type,
    mode: route.mode,
    printer_device_ids: [...route.printer_device_ids].sort(),
    copies: route.copies,
    document_format: route.document_format,
    inherit_branch: "inherit_branch" in route ? route.inherit_branch : undefined,
  });
}

function comparable(routes: Route[]) {
  return JSON.stringify(routes.map(routeSnapshot).sort());
}

function routePayload(route: Route) {
  return {
    document_type: route.document_type,
    mode: route.mode,
    printer_device_ids: route.printer_device_ids,
    copies: route.copies,
    document_format: route.document_format,
  };
}

export function DocumentPrintRoutes({ posDeviceId, branchId, branchName, onDirtyChange, onSavingChange }: { posDeviceId?: string; branchId?: number | string; branchName?: string; onDirtyChange?: (dirty: boolean) => void; onSavingChange?: (saving: boolean) => void }) {
  const { currentBranch, supportSession, user } = useAuth();
  const selectedBranchId = branchId ?? currentBranch?.id;
  const selectedBranchName = branchName ?? user?.branches.find((branch) => String(branch.id) === String(selectedBranchId))?.name ?? currentBranch?.name ?? "nenhuma";
  const readOnly = supportSession?.mode === "READ_ONLY";
  const loadRequest = useRef(0);
  const saveRequest = useRef(0);
  const revision = useRef(0);
  const baselineRoutes = useRef<Route[]>([]);
  const activeBranchName = useRef(selectedBranchName);
  const [activeBranchId, setActiveBranchId] = useState<number | string | undefined>(selectedBranchId);
  const [routes, setRoutes] = useState<Route[]>([]);
  const [branchRoutes, setBranchRoutes] = useState<PrintRoute[]>([]);
  const [printers, setPrinters] = useState<PrinterRouteDevice[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [baseline, setBaseline] = useState("");
  const dirty = !posDeviceId && !!baseline && baseline !== comparable(routes);

  useEffect(() => { onDirtyChange?.(dirty); }, [dirty, onDirtyChange]);
  useEffect(() => { onSavingChange?.(saving); }, [saving, onSavingChange]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  function valueFor(definition: PrintDocumentType, source = routes) {
    const route = source.find((item) => item.document_type === definition);
    const inherited = branchRoutes.find((item) => item.document_type === definition);
    const isInherited = Boolean(posDeviceId && (!route || ("inherit_branch" in route && route.inherit_branch)));
    return { route, inherited, isInherited, value: isInherited && inherited ? inherited : route || blank(definition, Number(activeBranchId) || 0, posDeviceId) };
  }

  function eligible(device?: PrinterRouteDevice) {
    return device?.status === "active" && device.connection_type === "network";
  }

  function invalidPrinterNames(route: Route) {
    return route.printer_device_ids.flatMap((id) => {
      const device = printers.find((item) => item.id === id);
      return eligible(device) ? [] : [device ? `${device.name} (${device.status === "inactive" ? "arquivada" : "transporte incompatível"})` : `Impressora #${id} indisponível`];
    });
  }

  async function load() {
    if (!activeBranchId) { setRoutes([]); setBranchRoutes([]); setPrinters([]); setLoading(false); return; }
    const token = ++loadRequest.current;
    const startedAtRevision = revision.current;
    setLoading(true);
    setError("");
    try {
      const [items, devices, inherited] = await Promise.all([
        http.getAll<PrintRoute | PrintRouteOverride>(posDeviceId ? "print-route-overrides/" : "print-routes/", { branchId: activeBranchId }),
        http.getAll<PrinterRouteDevice>("printer-devices/route-options/", { branchId: activeBranchId }),
        posDeviceId ? http.getAll<PrintRoute>("print-routes/", { branchId: activeBranchId }) : Promise.resolve([]),
      ]);
      if (token !== loadRequest.current || startedAtRevision !== revision.current) return;
      const visible = posDeviceId ? (items as PrintRouteOverride[]).filter((route) => route.pos_device === posDeviceId) : items;
      baselineRoutes.current = visible;
      setRoutes(visible);
      setBranchRoutes(inherited);
      setPrinters(devices);
      setBaseline(comparable(visible));
    } catch (caught) {
      if (token === loadRequest.current && startedAtRevision === revision.current) setError(message(caught, "Não foi possível carregar as rotas de impressão."));
    } finally {
      if (token === loadRequest.current) setLoading(false);
    }
  }

  const loadCurrent = useEffectEvent(() => { void load(); });
  useEffect(() => {
    if (String(selectedBranchId) === String(activeBranchId)) return;
    // A parent may propose a new branch while a save is in flight. Keep the
    // current context until it completes so its response cannot target another branch.
    if (saving) return;
    if (dirty && !window.confirm("Há alterações de rotas não salvas. Deseja descartá-las ao trocar de filial?")) return;
    revision.current += 1;
    activeBranchName.current = selectedBranchName;
    setActiveBranchId(selectedBranchId);
  }, [selectedBranchId, selectedBranchName, activeBranchId, dirty]);
  useEffect(() => {
    revision.current += 1;
    loadRequest.current += 1;
    setRoutes([]);
    setBranchRoutes([]);
    setBaseline("");
    loadCurrent();
  }, [activeBranchId, posDeviceId]);

  function update(type: PrintDocumentType, changes: Changes, inherited?: PrintRoute) {
    if (saving || readOnly) return;
    revision.current += 1;
    setRoutes((items) => {
      const existing = items.find((item) => item.document_type === type);
      const inheritedValues = inherited ? { mode: inherited.mode, printer_device_ids: inherited.printer_device_ids, copies: inherited.copies, document_format: inherited.document_format } : {};
      if (existing) return items.map((item) => item.document_type === type ? { ...item, ...(posDeviceId && "inherit_branch" in item && item.inherit_branch ? inheritedValues : {}), ...changes, ...(posDeviceId ? { inherit_branch: false } : {}) } : item);
      return [...items, { ...blank(type, Number(activeBranchId) || 0, posDeviceId), ...inheritedValues, ...changes }];
    });
  }

  function refresh() {
    if (saving) return;
    if (dirty && !window.confirm("Há alterações de rotas não salvas. Deseja descartá-las e atualizar?")) return;
    revision.current += 1;
    void load();
  }

  async function saveAll() {
    if (!activeBranchId || readOnly || saving) return;
    const changed = documentTypes.map((definition) => valueFor(definition.value).value).filter((route) => {
      const original = baselineRoutes.current.find((item) => item.document_type === route.document_type);
      return !original || routeSnapshot(route) !== routeSnapshot(original);
    });
    const invalid = changed.filter((route) => route.mode !== "disabled" && (!route.printer_device_ids.length || invalidPrinterNames(route).length));
    if (invalid.length) {
      setError("Rotas ativas precisam usar ao menos uma impressora NETWORK ativa. Corrija as rotas destacadas antes de salvar.");
      return;
    }
    if (!changed.length) return;
    const token = ++saveRequest.current;
    const savingBranchId = activeBranchId;
    const savingRevision = revision.current;
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const saved = await http.post<PrintRoute[]>("print-routes/bulk-update/", { routes: changed.map(routePayload) }, { branchId: savingBranchId });
      if (token !== saveRequest.current || savingBranchId !== activeBranchId || savingRevision !== revision.current) return;
      const savedByType = new Map(saved.map((route) => [route.document_type, route]));
      const next = routes.map((route) => savedByType.get(route.document_type) || route);
      baselineRoutes.current = next;
      setRoutes(next);
      setBaseline(comparable(next));
      setSuccess("Alterações de rotas salvas.");
    } catch (caught) {
      if (token === saveRequest.current && savingBranchId === activeBranchId) setError(message(caught, "Nenhuma rota foi salva. Revise as configurações destacadas."));
    } finally {
      if (token === saveRequest.current) setSaving(false);
    }
  }

  async function saveOverride(type: PrintDocumentType) {
    if (!activeBranchId || !posDeviceId || readOnly || saving) return;
    const { route, value } = valueFor(type);
    const invalid = value.mode !== "disabled" && (!value.printer_device_ids.length || invalidPrinterNames(value).length);
    if (invalid) { setError("Rotas ativas precisam usar ao menos uma impressora NETWORK ativa."); return; }
    const token = ++saveRequest.current;
    setSaving(true);
    setError("");
    try {
      const body = { ...routePayload(value), pos_device: posDeviceId, inherit_branch: false };
      const saved = route && route.id > 0 ? await http.patch<PrintRouteOverride>(`print-route-overrides/${route.id}/`, body, { branchId: activeBranchId }) : await http.post<PrintRouteOverride>("print-route-overrides/", body, { branchId: activeBranchId });
      if (token === saveRequest.current) {
        setRoutes((items) => items.some((item) => item.document_type === type) ? items.map((item) => item.document_type === type ? saved : item) : [...items, saved]);
        setSuccess("Override salvo.");
      }
    } catch (caught) {
      if (token === saveRequest.current) setError(message(caught, "Não foi possível salvar o override."));
    } finally {
      if (token === saveRequest.current) setSaving(false);
    }
  }

  async function inherit(type: PrintDocumentType) {
    const route = routes.find((item) => item.document_type === type);
    if (!route || !activeBranchId || saving) return;
    const token = ++saveRequest.current;
    setSaving(true);
    setError("");
    try {
      await http.delete(`print-route-overrides/${route.id}/`, { branchId: activeBranchId });
      if (token === saveRequest.current) { revision.current += 1; await load(); setSuccess("Override removido. O POS voltou a herdar a filial."); }
    } catch (caught) {
      if (token === saveRequest.current) setError(message(caught, "Não foi possível remover o override."));
    } finally {
      if (token === saveRequest.current) setSaving(false);
    }
  }

  return <section className="space-y-4 rounded-xl border border-subtle p-4">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h2 className="flex items-center gap-2 text-sm font-bold"><Printer className="size-4 text-primary" />{posDeviceId ? "Overrides de impressão do POS" : "Rotas de impressão"}</h2><p className="mt-1 text-xs text-muted">Filial: {activeBranchName.current}. {posDeviceId ? "Sem override, este POS herda a regra da filial." : "As alterações são salvas em uma única operação."}</p></div>
      <div className="flex gap-2"><Button variant="secondary" disabled={loading || saving} onClick={refresh}><RotateCcw className="size-4" />Atualizar</Button>{!posDeviceId && <Button disabled={readOnly || saving || !dirty} loading={saving} onClick={() => void saveAll()}><Save className="size-4" />Salvar alterações{dirty ? " *" : ""}</Button>}</div>
    </div>
    {!posDeviceId && <p className="rounded-md bg-surface-muted p-3 text-xs text-muted">As rotas da filial são a fonte oficial. Overrides por POS continuam separados e não são alterados por este salvamento.</p>}
    {dirty && <Alert message="Há alterações de rotas não salvas." />}{error && <Alert message={error} />}{success && <Alert type="success" message={success} />}
    {loading && !routes.length ? <div className="flex h-24 items-center justify-center text-primary"><Spinner /></div> : <div className="space-y-3">{documentTypes.map((definition) => {
      const { route, inherited, isInherited, value } = valueFor(definition.value);
      const invalidNames = invalidPrinterNames(value);
      const invalid = value.mode !== "disabled" && (!value.printer_device_ids.length || invalidNames.length > 0);
      return <article key={definition.value} className={`rounded-lg border p-4 ${invalid ? "border-danger/50" : "border-subtle"}`}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><div><strong className="text-sm">{definition.label}</strong>{isInherited && <span className="ml-2 rounded-full bg-surface-muted px-2 py-1 text-[11px] font-semibold text-muted">Herdando da filial</span>}</div><span className="text-xs text-muted">{modeLabels[value.mode]}</span></div>
        {invalidNames.length > 0 && <Alert message={`Associação indisponível: ${invalidNames.join(", ")}. Remova ou substitua a impressora para ativar esta rota.`} />}
        <div className="grid gap-3 md:grid-cols-3"><Field label="Modo"><Select value={value.mode} disabled={readOnly || saving} onChange={(event) => update(definition.value, { mode: event.target.value as PrintRouteMode }, inherited)}>{Object.entries(modeLabels).map(([mode, label]) => <option key={mode} value={mode}>{label}</option>)}</Select></Field><Field label="Cópias"><Input type="number" min="1" max="10" value={value.copies} disabled={readOnly || saving} onChange={(event) => update(definition.value, { copies: Number(event.target.value) || 1 }, inherited)} /></Field>{definition.format && <Field label="Formato"><Select value={value.document_format} disabled={readOnly || saving} onChange={(event) => update(definition.value, { document_format: event.target.value as PrintDocumentFormat }, inherited)}><option value="detailed">Detalhado</option><option value="simplified">Simplificado</option></Select></Field>}</div>
        <Field label="Impressoras NETWORK"><select multiple className="input mt-1 min-h-28 w-full" value={value.printer_device_ids.map(String)} disabled={readOnly || saving} onChange={(event) => update(definition.value, { printer_device_ids: Array.from(event.currentTarget.selectedOptions, (option) => Number(option.value)) }, inherited)}>{printers.map((device) => <option key={device.id} value={device.id} disabled={!eligible(device)}>{device.name}{eligible(device) ? "" : device.status === "inactive" ? " (arquivada)" : " (transporte incompatível)"}</option>)}</select></Field>
        {value.mode !== "disabled" && !printers.some(eligible) && <p className="mt-2 text-xs text-danger-strong">Não há impressora NETWORK ativa elegível nesta filial. Esta rota não pode ser ativada.</p>}
        {posDeviceId && <div className="mt-3 flex gap-2"><Button disabled={readOnly || saving} loading={saving} onClick={() => void saveOverride(definition.value)}>Salvar override</Button>{route && !isInherited && <Button variant="secondary" disabled={saving} onClick={() => void inherit(definition.value)}>Voltar a herdar</Button>}</div>}
      </article>;
    })}</div>}
  </section>;
}

export function PosDocumentRouteOverrides({ branchId }: { branchId?: string }) {
  const { currentCompany, currentBranch } = useAuth();
  const [devices, setDevices] = useState<PosDevice[]>([]);
  const [deviceId, setDeviceId] = useState("");
  useEffect(() => {
    const selected = branchId || String(currentBranch?.id || "");
    if (!currentCompany || !selected) return;
    http.getAll<PosDevice>(`pos/admin/devices/?company=${currentCompany.id}&branch=${selected}`, { branchId: selected }).then(setDevices).catch(() => setDevices([]));
  }, [branchId, currentCompany?.id, currentBranch?.id]);
  return <div className="space-y-3"><Field label="Dispositivo POS"><Select value={deviceId} onChange={(event) => setDeviceId(event.target.value)}><option value="">Selecione um POS para configurar overrides</option>{devices.map((device) => <option key={device.id} value={device.id}>{device.name}</option>)}</Select></Field>{deviceId ? <DocumentPrintRoutes posDeviceId={deviceId} branchId={branchId} /> : <EmptyState title="Selecione um dispositivo POS" description="Overrides são opcionais; a regra da filial continuará valendo sem eles." />}</div>;
}
