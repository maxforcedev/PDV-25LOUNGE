"use client";

import { useEffect, useState } from "react";
import { Printer, RotateCcw } from "lucide-react";
import { Alert, Button, EmptyState, Field, Input, Select, Spinner } from "@/components/ui";
import { ApiError, http } from "@/lib/http";
import { useAuth } from "@/providers/auth-provider";
import type { PosDevice, PrintDocumentFormat, PrintDocumentType, PrintRoute, PrintRouteMode, PrintRouteOverride, PrinterDevice } from "@/types";

const documentTypes: Array<{ value: PrintDocumentType; label: string; format: boolean }> = [
  { value: "table_bill", label: "Conta da mesa", format: true },
  { value: "table_conference", label: "Conferencia", format: true },
  { value: "table_final_receipt", label: "Recibo final da mesa", format: true },
  { value: "quick_sale_receipt", label: "Recibo venda rapida", format: true },
  { value: "payment_receipt", label: "Comprovante de pagamento", format: true },
  { value: "ticket", label: "Ticket", format: false },
];

type Route = PrintRoute | PrintRouteOverride;
type RouteChanges = Partial<Pick<PrintRoute, "mode" | "printer_device_ids" | "copies" | "document_format">>;

function emptyRoute(documentType: PrintDocumentType, branch: number, posDeviceId?: string): Route {
  if (posDeviceId) return {
    id: -Date.now(),
    pos_device: posDeviceId,
    pos_device_name: "",
    document_type: documentType,
    inherit_branch: false,
    mode: "disabled",
    printer_device_ids: [],
    copies: 1,
    document_format: "detailed",
    created_at: "",
    updated_at: "",
  };
  return {
    id: -Date.now(),
    branch,
    document_type: documentType,
    mode: "disabled",
    printer_device_ids: [],
    copies: 1,
    document_format: "detailed",
    created_at: "",
    updated_at: "",
  };
}

function routeError(caught: unknown, fallback: string) {
  return caught instanceof ApiError ? caught.message : fallback;
}

export function DocumentPrintRoutes({ posDeviceId, branchId }: { posDeviceId?: string; branchId?: number | string }) {
  const { currentBranch, supportSession } = useAuth();
  const effectiveBranchId = branchId || currentBranch?.id;
  const readOnly = supportSession?.mode === "READ_ONLY";
  const [routes, setRoutes] = useState<Route[]>([]);
  const [branchRoutes, setBranchRoutes] = useState<PrintRoute[]>([]);
  const [printers, setPrinters] = useState<PrinterDevice[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<PrintDocumentType | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function load() {
    if (!effectiveBranchId) return;
    setLoading(true);
    setError("");
    try {
      if (posDeviceId) {
        const [overrides, devices, inherited] = await Promise.all([
          http.getAll<PrintRouteOverride>("print-route-overrides/", { branchId: effectiveBranchId }),
          http.getAll<PrinterDevice>("printer-devices/", { branchId: effectiveBranchId }),
          http.getAll<PrintRoute>("print-routes/", { branchId: effectiveBranchId }),
        ]);
        setRoutes(overrides.filter((route) => route.pos_device === posDeviceId));
        setBranchRoutes(inherited);
        setPrinters(devices.filter((device) => device.status === "active" && device.connection_type === "network"));
      } else {
        const [items, devices] = await Promise.all([
          http.getAll<PrintRoute>("print-routes/", { branchId: effectiveBranchId }),
          http.getAll<PrinterDevice>("printer-devices/", { branchId: effectiveBranchId }),
        ]);
        setRoutes(items);
        setBranchRoutes([]);
        setPrinters(devices.filter((device) => device.status === "active" && device.connection_type === "network"));
      }
    } catch (caught) {
      setError(routeError(caught, "Nao foi possivel carregar as rotas de impressao."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setRoutes([]);
    setBranchRoutes([]);
    void load();
  }, [effectiveBranchId, posDeviceId]);

  function update(type: PrintDocumentType, changes: RouteChanges, inheritedRoute?: PrintRoute) {
    setRoutes((items) => {
      const current = items.find((item) => item.document_type === type);
      if (current) {
        const base = posDeviceId && "inherit_branch" in current && current.inherit_branch && inheritedRoute ? {
          mode: inheritedRoute.mode,
          printer_device_ids: inheritedRoute.printer_device_ids,
          copies: inheritedRoute.copies,
          document_format: inheritedRoute.document_format,
        } : {};
        return items.map((item) => item.id === current.id ? { ...item, ...base, ...changes, ...(posDeviceId ? { inherit_branch: false } : {}) } : item);
      }
      const base = inheritedRoute ? {
        mode: inheritedRoute.mode,
        printer_device_ids: inheritedRoute.printer_device_ids,
        copies: inheritedRoute.copies,
        document_format: inheritedRoute.document_format,
      } : {};
      return [...items, { ...emptyRoute(type, Number(effectiveBranchId) || 0, posDeviceId), ...base, ...changes }];
    });
  }

  async function save(type: PrintDocumentType) {
    const existing = routes.find((item) => item.document_type === type);
    const inheritedRoute = branchRoutes.find((item) => item.document_type === type);
    const inherited = !!posDeviceId && (!existing || ("inherit_branch" in existing && existing.inherit_branch));
    const route = inherited && inheritedRoute ? inheritedRoute : existing || emptyRoute(type, Number(effectiveBranchId) || 0, posDeviceId);
    if (!effectiveBranchId) return;
    setSaving(type);
    setError("");
    setSuccess("");
    const body = {
      document_type: type,
      mode: route.mode,
      printer_device_ids: route.printer_device_ids,
      copies: route.copies,
      document_format: route.document_format,
    };
    try {
      const saved: Route = posDeviceId
        ? existing && existing.id > 0
          ? await http.patch<PrintRouteOverride>(`print-route-overrides/${existing.id}/`, { ...body, pos_device: posDeviceId, inherit_branch: false }, { branchId: effectiveBranchId })
          : await http.post<PrintRouteOverride>("print-route-overrides/", { ...body, pos_device: posDeviceId, inherit_branch: false }, { branchId: effectiveBranchId })
        : existing && existing.id > 0
          ? await http.patch<PrintRoute>(`print-routes/${existing.id}/`, body, { branchId: effectiveBranchId })
          : await http.post<PrintRoute>("print-routes/", body, { branchId: effectiveBranchId });
      setRoutes((items) => items.some((item) => item.document_type === type) ? items.map((item) => item.document_type === type ? saved : item) : [...items, saved]);
      setSuccess("Regra de impressao salva.");
    } catch (caught) {
      setError(routeError(caught, "Nao foi possivel salvar a regra de impressao."));
    } finally {
      setSaving(null);
    }
  }

  async function inherit(type: PrintDocumentType) {
    const route = routes.find((item) => item.document_type === type);
    if (!route || route.id <= 0) return;
    setSaving(type);
    setError("");
    try {
      await http.delete(`print-route-overrides/${route.id}/`, { branchId: effectiveBranchId });
      await load();
      setSuccess("Override removido. O POS voltou a herdar a regra da filial.");
    } catch (caught) {
      setError(routeError(caught, "Nao foi possivel remover o override."));
    } finally {
      setSaving(null);
    }
  }

  const title = posDeviceId ? "Overrides de impressao do POS" : "Rotas de documentos";
  return <section className="card space-y-4 p-4">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 className="flex items-center gap-2 text-sm font-bold"><Printer className="size-4 text-primary" />{title}</h2>
        <p className="mt-1 text-xs text-muted">
          Filial: {branchId ? String(branchId) : currentBranch?.name || "nenhuma"}. {posDeviceId ? "Cada override e opcional; sem override, o POS herda a filial." : "Configure finalidade, modo, varias impressoras, copias e formato."}
        </p>
      </div>
      <Button variant="secondary" disabled={loading} onClick={() => void load()}><RotateCcw className="size-4" />Atualizar</Button>
    </div>
    {!posDeviceId && <p className="rounded-md bg-surface-muted p-3 text-xs text-muted">Estas regras sao a fonte oficial para documentos. Os antigos campos de recibo do POS permanecem apenas para compatibilidade e nao devem ser usados para novo roteamento.</p>}
    {!posDeviceId && printers.length > 0 && routes.length > 0 && routes.every((route) => route.mode === "disabled") && <Alert message="Impressora cadastrada. CONFIGURAR ROTAS DE IMPRESSÃO abaixo antes de usar o POS." />}
    {error && <Alert message={error} />}
    {success && <Alert type="success" message={success} />}
    {loading ? <div className="flex h-24 items-center justify-center text-primary"><Spinner /></div> : <div className="space-y-3">
      {documentTypes.map((definition) => {
        const route = routes.find((item) => item.document_type === definition.value);
        const inheritedRoute = branchRoutes.find((item) => item.document_type === definition.value);
        const inherited = !!posDeviceId && (!route || ("inherit_branch" in route && route.inherit_branch));
          const value = inherited && inheritedRoute ? inheritedRoute : route || emptyRoute(definition.value, Number(effectiveBranchId) || 0, posDeviceId);
        return <article key={definition.value} className="rounded-lg border border-subtle p-3">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><strong className="text-sm">{definition.label}</strong>{inherited && <span className="rounded-full bg-surface-muted px-2 py-1 text-[11px] font-semibold text-muted">Herdando da filial</span>}</div>
          {inherited && <p className="mb-3 text-xs text-muted">Modo efetivo: <strong>{value.mode}</strong> · Impressoras efetivas: <strong>{value.printer_device_ids.map((id) => printers.find((printer) => printer.id === id)?.name || id).join(", ") || "nenhuma"}</strong> · Cópias: <strong>{value.copies}</strong></p>}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Modo"><Select value={value.mode} disabled={readOnly || saving === definition.value} onChange={(event) => update(definition.value, { mode: event.target.value as PrintRouteMode }, inheritedRoute)}><option value="disabled">Desabilitado</option><option value="manual">Manual</option><option value="automatic">Automatico</option></Select></Field>
            <Field label="Copias"><Input type="number" min="1" max="10" value={value.copies} disabled={readOnly || saving === definition.value} onChange={(event) => update(definition.value, { copies: Math.max(1, Number(event.target.value) || 1) }, inheritedRoute)} /></Field>
            {definition.format && <Field label="Formato"><Select value={value.document_format || "detailed"} disabled={readOnly || saving === definition.value} onChange={(event) => update(definition.value, { document_format: event.target.value as PrintDocumentFormat }, inheritedRoute)}><option value="detailed">Detalhado</option><option value="simplified">Simplificado</option></Select></Field>}
          </div>
          <fieldset className="mt-3"><legend className="label">Impressoras NETWORK ativas</legend><div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{printers.map((printer) => <label key={printer.id} className="flex items-center gap-2 text-xs"><input type="checkbox" checked={value.printer_device_ids.includes(printer.id)} disabled={readOnly || saving === definition.value} onChange={(event) => update(definition.value, { printer_device_ids: event.target.checked ? [...value.printer_device_ids, printer.id] : value.printer_device_ids.filter((id) => id !== printer.id) }, inheritedRoute)} />{printer.name}</label>)}</div>{!printers.length && <span className="text-xs text-muted">Nenhuma impressora NETWORK ativa nesta filial.</span>}{value.mode !== "disabled" && !value.printer_device_ids.length && <span className="mt-2 block text-xs text-danger">Selecione ao menos uma impressora NETWORK para ativar esta rota.</span>}</fieldset>
          <div className="mt-3 flex flex-wrap justify-end gap-2">{posDeviceId && route && <Button variant="secondary" disabled={readOnly || saving === definition.value} onClick={() => void inherit(definition.value)}>Usar regra da filial</Button>}<Button loading={saving === definition.value} disabled={readOnly} onClick={() => void save(definition.value)}>{inherited ? "Sobrescrever" : "Salvar"}</Button></div>
        </article>;
      })}
    </div>}
  </section>;
}

export function PosDocumentRouteOverrides({ branchId }: { branchId?: string }) {
  const { currentCompany, currentBranch } = useAuth();
  const [devices, setDevices] = useState<PosDevice[]>([]);
  const [deviceId, setDeviceId] = useState("");

  useEffect(() => {
    const selectedBranchId = branchId || String(currentBranch?.id || "");
    if (!currentCompany || !selectedBranchId) return;
    http.getAll<PosDevice>(`pos/admin/devices/?company=${currentCompany.id}&branch=${selectedBranchId}`, { branchId: selectedBranchId }).then(setDevices).catch(() => setDevices([]));
  }, [branchId, currentCompany?.id, currentBranch?.id]);

  return <div className="space-y-3"><Field label="Dispositivo POS"><Select value={deviceId} onChange={(event) => setDeviceId(event.target.value)}><option value="">Selecione um POS para configurar overrides</option>{devices.map((device) => <option key={device.id} value={device.id}>{device.name}</option>)}</Select></Field>{deviceId ? <DocumentPrintRoutes posDeviceId={deviceId} branchId={branchId} /> : <EmptyState title="Selecione um dispositivo POS" description="Os overrides sao opcionais e cada finalidade pode continuar herdando a regra da filial." />}</div>;
}
