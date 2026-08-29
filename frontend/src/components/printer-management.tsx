"use client";

import { useEffect, useEffectEvent, useRef, useState } from "react";
import { Archive, History, Pencil, Plus, Power } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import {
  Alert,
  Button,
  EmptyState,
  Field,
  Input,
  Modal,
  Pagination,
  Select,
  StatusBadge,
  TableLoading,
} from "@/components/ui";
import { fieldError, formatDate } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { Paginated, PrinterDevice, PrintJob, PrintJobStatus } from "@/types";

const connectionLabels = {
  network: "Rede",
  usb: "USB",
  bluetooth: "Bluetooth",
} as const;

const operationalLabels = {
  not_tested: "Não testada",
  online: "Online",
  offline: "Offline",
  bridge_unavailable: "Bridge indisponível",
  failed: "Falha",
} as const;

const jobStatusLabels: Record<PrintJobStatus, string> = {
  pending: "Pendente",
  processing: "Processando",
  printed: "Impresso",
  failed: "Falhou",
  cancelled: "Cancelado",
};

function JobStatusBadge({ status }: { status: PrintJobStatus }) {
  return <span className="text-xs font-semibold text-muted">{jobStatusLabels[status]}</span>;
}

export function PrinterManagement({ embedded = false }: { embedded?: boolean }) {
  const { currentBranch, currentCompany, supportSession, hasPermission } = useAuth();
  const readOnly = supportSession?.mode === "READ_ONLY";
  const canReprint = hasPermission(permissions.reprintPrintJobs) && !readOnly;
  const contextRef = useRef("");
  contextRef.current = `${currentCompany?.id || ""}:${currentBranch?.id || ""}`;
  const [devices, setDevices] = useState<PrinterDevice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [editing, setEditing] = useState<PrinterDevice | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState<number | null>(null);
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [name, setName] = useState("");
  const [connectionType, setConnectionType] =
    useState<PrinterDevice["connection_type"]>("network");
  const [deviceStatus, setDeviceStatus] = useState<"active" | "inactive">("active");
  const [host, setHost] = useState("");
  const [port, setPort] = useState("9100");
  const [vendorId, setVendorId] = useState("");
  const [productId, setProductId] = useState("");
  const [serial, setSerial] = useState("");
  const [deviceName, setDeviceName] = useState("");
  const [identifier, setIdentifier] = useState("");
  const [historyDevice, setHistoryDevice] = useState<PrinterDevice | null>(null);
  const [history, setHistory] = useState<Paginated<PrintJob> | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);

  async function load(context = contextRef.current) {
    if (!currentBranch) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const items = await http.getAll<PrinterDevice>("printer-devices/");
      if (context === contextRef.current) setDevices(items);
    } catch (caught) {
      if (context === contextRef.current)
        setError(
          caught instanceof ApiError
            ? caught.message
            : "Não foi possível carregar as impressoras.",
        );
    } finally {
      if (context === contextRef.current) setLoading(false);
    }
  }

  const loadForContext = useEffectEvent((context: string) => {
    void load(context);
  });

  useEffect(() => {
    const context = contextRef.current;
    setDevices([]);
    setEditorOpen(false);
    loadForContext(context);
  }, [currentCompany?.id, currentBranch?.id]);

  function show(device?: PrinterDevice) {
    const config = device?.technical_configuration || {};
    setEditing(device || null);
    setName(device?.name || "");
    setConnectionType(device?.connection_type || "network");
    setDeviceStatus(device?.status || "active");
    setHost(String(config.host || ""));
    setPort(String(config.port || "9100"));
    setVendorId(String(config.vendor_id || ""));
    setProductId(String(config.product_id || ""));
    setSerial(String(config.serial || ""));
    setDeviceName(String(config.device_name || ""));
    setIdentifier(String(config.identifier || ""));
    setFields({});
    setError("");
    setEditorOpen(true);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!currentBranch || readOnly) return;
    const technical_configuration =
      connectionType === "network"
        ? { host: host.trim(), port: Number(port), timeout: 5 }
        : connectionType === "usb"
          ? {
              vendor_id: vendorId.trim(),
              product_id: productId.trim(),
              serial: serial.trim(),
              identifier:
                serial.trim() || `${vendorId.trim()}:${productId.trim()}`,
            }
          : {
              device_name: deviceName.trim(),
              identifier: identifier.trim(),
            };
    setSaving(true);
    setError("");
    setFields({});
    try {
      const body = {
        name,
        connection_type: connectionType,
        status: deviceStatus,
        technical_configuration,
      };
      if (editing) await http.patch(`printer-devices/${editing.id}/`, body);
      else await http.post("printer-devices/", body);
      setEditorOpen(false);
      setSuccess(editing ? "Impressora atualizada." : "Impressora cadastrada.");
      await load();
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setFields(caught.fields);
      } else setError("Não foi possível salvar a impressora.");
    } finally {
      setSaving(false);
    }
  }

  async function testPrinter(device: PrinterDevice) {
    setBusy(device.id);
    setError("");
    setSuccess("");
    try {
      const job = await http.post<PrintJob>(
        `printer-devices/${device.id}/test/`,
        {},
      );
      if (job.status === "printed")
        setSuccess("Teste de impressão enviado com sucesso.");
      else
        setError(job.error_summary || "Não foi possível testar esta impressora.");
      await load();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível testar esta impressora.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function toggle(device: PrinterDevice) {
    setBusy(device.id);
    setError("");
    try {
      await http.patch(`printer-devices/${device.id}/`, {
        status: device.status === "active" ? "inactive" : "active",
      });
      setSuccess(
        device.status === "active"
          ? "Impressora excluída da operação."
          : "Impressora ativada.",
      );
      await load();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível alterar a impressora.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function openHistory(device: PrinterDevice, path?: string) {
    setHistoryDevice(device);
    setHistoryLoading(true);
    setError("");
    try {
      setHistory(
        await http.get<Paginated<PrintJob>>(
          path || `printer-devices/${device.id}/history/`,
        ),
      );
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível carregar o histórico.",
      );
    } finally {
      setHistoryLoading(false);
    }
  }

  async function reprint(job: PrintJob) {
    setBusy(job.id);
    try {
      await http.post(`print-jobs/${job.id}/reprint/`, {
        reason: "Reimpressão solicitada pelo histórico da impressora.",
      });
      setSuccess("Reimpressão criada e incluída na fila.");
      if (historyDevice) await openHistory(historyDevice);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível reimprimir.",
      );
    } finally {
      setBusy(null);
    }
  }

  const workspace = (
    <div className={embedded ? "space-y-4" : "space-y-4 p-4 sm:p-6 lg:p-8"}>
      {error && !editorOpen && <Alert message={error} />}
      {success && <Alert type="success" message={success} />}
      <div className="flex justify-end">
        {!readOnly && (
          <Button onClick={() => show()}>
            <Plus className="size-4" />
            Adicionar impressora
          </Button>
        )}
      </div>
      <section className="overflow-hidden rounded-xl border border-subtle">
        {loading ? (
          <TableLoading columns={5} />
        ) : devices.length ? (
          <div className="grid gap-3 p-4 lg:grid-cols-2">
            {devices.map((device) => (
              <article
                key={device.id}
                className="rounded-xl border border-subtle bg-surface p-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <strong className="text-base">{device.name}</strong>
                    <p className="mt-1 text-xs text-muted">
                      {connectionLabels[device.connection_type]}
                      {device.connection_summary
                        ? ` · ${device.connection_summary}`
                        : ""}
                    </p>
                  </div>
                  <StatusBadge active={device.status === "active"} />
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                  <span
                    className={
                      device.operational_status === "online"
                        ? "font-semibold text-success-strong"
                        : device.operational_status === "failed"
                          ? "font-semibold text-danger-strong"
                          : "font-semibold text-muted"
                    }
                  >
                    {operationalLabels[device.operational_status]}
                  </span>
                  <span className="text-muted">
                    Último teste: {device.last_test_at ? formatDate(device.last_test_at) : "não realizado"}
                  </span>
                </div>
                {device.connection_type !== "network" &&
                  device.operational_status !== "online" && (
                    <p className="mt-3 rounded-md bg-warning-surface p-2 text-xs text-warning-strong">
                      Print Bridge necessária para utilizar esta impressora.
                    </p>
                  )}
                {device.last_operational_error && (
                  <p className="mt-3 text-xs font-medium text-danger-strong">
                    {device.last_operational_error}
                  </p>
                )}
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="secondary"
                    loading={busy === device.id}
                    disabled={readOnly || device.status !== "active"}
                    onClick={() => void testPrinter(device)}
                  >
                    {device.connection_type === "bluetooth" ? "Conectar" : "Testar"}
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => void openHistory(device)}
                  >
                    <History className="size-4" />
                    Histórico
                  </Button>
                  {!readOnly && (
                    <>
                      <Button type="button" variant="secondary" onClick={() => show(device)}>
                        <Pencil className="size-4" />
                        Editar
                      </Button>
                      <Button
                        type="button"
                        variant="secondary"
                        loading={busy === device.id}
                        onClick={() => void toggle(device)}
                      >
                        {device.status === "active" ? (
                          <Archive className="size-4" />
                        ) : (
                          <Power className="size-4" />
                        )}
                        {device.status === "active" ? "Arquivar" : "Ativar"}
                      </Button>
                    </>
                  )}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            title="Nenhuma impressora cadastrada"
            description="Adicione a primeira impressora ou setor desta filial."
          />
        )}
      </section>
    </div>
  );

  return (
    <>
      {!embedded && (
        <PageHeader
          title="Impressoras"
          description={`Configuração da filial ${currentBranch?.name || "atual"}.`}
        />
      )}
      {workspace}
      <Modal
        open={editorOpen}
        title={editing ? "Editar impressora" : "Adicionar impressora"}
        description="O nome também será usado como setor operacional."
        onClose={() => !saving && setEditorOpen(false)}
        size="xl"
      >
        <form onSubmit={submit}>
          <div className="space-y-4 p-5">
            {error && <Alert message={error} />}
            <Field label="Nome da impressora" error={fieldError(fields, "name")}>
              <Input
                required
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Ex.: Cozinha"
              />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Tipo de conexão">
                <Select
                  value={connectionType}
                  onChange={(event) =>
                    setConnectionType(
                      event.target.value as PrinterDevice["connection_type"],
                    )
                  }
                >
                  <option value="network">Rede</option>
                  <option value="usb">USB</option>
                  <option value="bluetooth">Bluetooth</option>
                </Select>
              </Field>
              <Field label="Status administrativo">
                <Select
                  value={deviceStatus}
                  onChange={(event) =>
                    setDeviceStatus(event.target.value as "active" | "inactive")
                  }
                >
                  <option value="active">Ativa</option>
                  <option value="inactive">Inativa</option>
                </Select>
              </Field>
            </div>
            {connectionType === "network" && (
              <div className="grid gap-4 sm:grid-cols-[1fr_9rem]">
                <Field label="IP ou hostname">
                  <Input
                    required
                    value={host}
                    onChange={(event) => setHost(event.target.value)}
                    placeholder="192.168.1.50"
                  />
                </Field>
                <Field label="Porta">
                  <Input
                    required
                    inputMode="numeric"
                    value={port}
                    onChange={(event) =>
                      setPort(event.target.value.replace(/\D/g, ""))
                    }
                  />
                </Field>
              </div>
            )}
            {connectionType === "usb" && (
              <>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Vendor ID">
                    <Input
                      required
                      value={vendorId}
                      onChange={(event) => setVendorId(event.target.value)}
                    />
                  </Field>
                  <Field label="Product ID">
                    <Input
                      required
                      value={productId}
                      onChange={(event) => setProductId(event.target.value)}
                    />
                  </Field>
                </div>
                <Field label="Serial / identificador" optional>
                  <Input value={serial} onChange={(event) => setSerial(event.target.value)} />
                </Field>
                <Alert message="Print Bridge necessária para utilizar esta impressora USB." />
              </>
            )}
            {connectionType === "bluetooth" && (
              <>
                <Field label="Nome amigável do dispositivo">
                  <Input
                    required
                    value={deviceName}
                    onChange={(event) => setDeviceName(event.target.value)}
                  />
                </Field>
                <Field label="Identificador Bluetooth">
                  <Input
                    required
                    value={identifier}
                    onChange={(event) => setIdentifier(event.target.value)}
                  />
                </Field>
                <Alert message="Print Bridge necessária para conectar esta impressora Bluetooth." />
              </>
            )}
          </div>
          <div className="flex justify-end gap-2 border-t border-subtle p-4">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setEditorOpen(false)}
              disabled={saving}
            >
              Cancelar
            </Button>
            <Button type="submit" loading={saving}>
              Salvar
            </Button>
          </div>
        </form>
      </Modal>
      <Modal
        open={!!historyDevice}
        title={`Histórico · ${historyDevice?.name || "Impressora"}`}
        description="Impressões mais recentes desta impressora."
        onClose={() => {
          setHistoryDevice(null);
          setHistory(null);
        }}
        size="xl"
      >
        <div className="p-5">
          {historyLoading ? (
            <TableLoading columns={5} />
          ) : history?.results.length ? (
            <>
              <div className="divide-y divide-subtle rounded-lg border border-subtle">
                {history.results.map((job) => (
                  <article
                    key={job.id}
                    className="flex flex-col gap-3 p-3 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <strong>
                          {job.origin_label}
                        </strong>
                        <JobStatusBadge status={job.status} />
                      </div>
                      <p className="mt-1 text-xs text-muted">
                        {formatDate(job.created_at)} · tentativa {job.attempts}
                        {job.reprint_number
                          ? ` · reimpressão ${job.reprint_number}`
                          : ""}
                      </p>
                      {job.error_summary && (
                        <p className="mt-1 text-xs text-danger-strong">
                          {job.error_summary}
                        </p>
                      )}
                    </div>
                    {canReprint && !job.is_test && (
                      <Button
                        type="button"
                        variant="secondary"
                        loading={busy === job.id}
                        onClick={() => void reprint(job)}
                      >
                        Reimprimir
                      </Button>
                    )}
                  </article>
                ))}
              </div>
              <Pagination
                count={history.count}
                next={history.next}
                previous={history.previous}
                onPage={(path) =>
                  historyDevice && void openHistory(historyDevice, path)
                }
              />
            </>
          ) : (
            <EmptyState
              title="Sem histórico"
              description="Nenhuma impressão foi registrada para este equipamento."
            />
          )}
        </div>
      </Modal>
    </>
  );
}
