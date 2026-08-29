"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  ExternalLink,
  Pencil,
  Plus,
  RotateCcw,
  Send,
  Printer,
} from "lucide-react";
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
  Textarea,
} from "@/components/ui";
import { formatDate, fieldError } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type {
  Paginated,
  PrinterDevice,
  PrintJob,
  PrintJobStatus,
  ProductionDestination,
} from "@/types";
export { PrinterManagement as Printers } from "@/components/printer-management";

const statusLabels: Record<PrintJobStatus, string> = {
  pending: "Pendente",
  processing: "Processando",
  printed: "Impresso",
  failed: "Falhou",
  cancelled: "Cancelado",
};
const statusClasses: Record<PrintJobStatus, string> = {
  pending: "bg-warning-surface text-warning-strong",
  processing: "bg-primary/10 text-primary",
  printed: "bg-success-surface text-success-strong",
  failed: "bg-danger-surface text-danger-strong",
  cancelled: "bg-surface-muted text-muted",
};

export function PrintJobStatusBadge({ status }: { status: PrintJobStatus }) {
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-semibold ${statusClasses[status]}`}
    >
      {statusLabels[status]}
    </span>
  );
}

function destinationName(job: PrintJob, destinations: ProductionDestination[]) {
  const snapshot = job.payload_snapshot.destination as
    | { name?: string }
    | undefined;
  return (
    snapshot?.name ||
    destinations.find((item) => item.id === job.destination)?.name ||
    `Destino #${job.destination}`
  );
}

export function PrintQueue({
  failuresOnly = false,
}: {
  failuresOnly?: boolean;
}) {
  const { currentBranch, currentCompany, hasPermission, supportSession } =
    useAuth();
  const canRetry =
    hasPermission(permissions.retryPrintJobs) &&
    supportSession?.mode !== "READ_ONLY";
  const canReprint =
    hasPermission(permissions.reprintPrintJobs) &&
    supportSession?.mode !== "READ_ONLY";
  const contextRef = useRef("");
  contextRef.current = `${currentCompany?.id || ""}:${currentBranch?.id || ""}`;
  const [data, setData] = useState<Paginated<PrintJob> | null>(null);
  const [destinations, setDestinations] = useState<ProductionDestination[]>([]);
  const [status, setStatus] = useState(failuresOnly ? "failed" : "");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function load(path?: string, context = contextRef.current) {
    if (!currentBranch) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    const query = status ? `print-jobs/?status=${status}` : "print-jobs/";
    try {
      const [jobs, availableDestinations] = await Promise.all([
        http.get<Paginated<PrintJob>>(path || query),
        http
          .getAll<ProductionDestination>("production-destinations/")
          .catch(() => []),
      ]);
      if (context === contextRef.current) {
        setData(jobs);
        setDestinations(availableDestinations);
      }
    } catch (caught) {
      if (context === contextRef.current)
        setError(
          caught instanceof ApiError
            ? caught.message
            : "Não foi possível carregar a fila de impressão.",
        );
    } finally {
      if (context === contextRef.current) setLoading(false);
    }
  }

  useEffect(() => {
    const context = contextRef.current;
    setData(null);
    setStatus(failuresOnly ? "failed" : "");
    setSuccess("");
    void load(
      failuresOnly ? "print-jobs/?status=failed" : "print-jobs/",
      context,
    );
  }, [currentCompany?.id, currentBranch?.id, failuresOnly]);

  async function act(
    job: PrintJob,
    action: "retry" | "reprint" | "manual-dispatch",
  ) {
    setBusy(job.id);
    setError("");
    setSuccess("");
    try {
      await http.post(`print-jobs/${job.id}/${action}/`);
      setSuccess(
        action === "reprint"
          ? "Reimpressão criada e incluída na fila."
          : action === "retry"
            ? "Job reenviado para a fila."
            : "Despacho manual registrado.",
      );
      await load();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível atualizar o job.",
      );
    } finally {
      setBusy(null);
    }
  }

  const actions = (job: PrintJob) => (
    <div className="flex flex-wrap gap-1">
      <Link
        className="icon-button"
        href={`/producao/jobs/${job.id}`}
        aria-label={`Ver job ${job.id}`}
      >
        <ExternalLink className="size-4" />
      </Link>
      {canRetry && job.status !== "printed" && (
        <button
          className="icon-button"
          disabled={busy === job.id}
          onClick={() => void act(job, "retry")}
          title="Tentar novamente"
        >
          <RotateCcw className="size-4" />
        </button>
      )}
      {canRetry && (job.status === "pending" || job.status === "failed") && (
        <button
          className="icon-button"
          disabled={busy === job.id}
          onClick={() => void act(job, "manual-dispatch")}
          title="Registrar despacho manual"
        >
          <Send className="size-4" />
        </button>
      )}
      {canReprint && job.status === "printed" && (
        <button
          className="icon-button"
          disabled={busy === job.id}
          onClick={() => void act(job, "reprint")}
          title="Criar reimpressão"
        >
          <Printer className="size-4" />
        </button>
      )}
    </div>
  );
  const title = failuresOnly ? "Falhas de impressão" : "Fila de impressão";
  return (
    <>
      <PageHeader
        title={title}
        description={`Filial atual: ${currentBranch?.name || "nenhuma filial selecionada"}. Acompanhe somente os jobs deste contexto.`}
      />
      <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        {error && <Alert message={error} />}
        {success && <Alert type="success" message={success} />}
        <form
          className="card flex flex-col gap-3 p-4 sm:flex-row sm:items-center"
          onSubmit={(event) => {
            event.preventDefault();
            void load();
          }}
        >
          <Select
            value={status}
            disabled={failuresOnly}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="">Todos os status</option>
            {Object.entries(statusLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
          <Button type="submit">Atualizar</Button>
        </form>
        <section className="card overflow-hidden">
          <div className="card-header">
            <div>
              <h2 className="text-sm font-bold">
                {failuresOnly ? "Jobs com erro" : "Jobs de impressão"}
              </h2>
              <p className="mt-1 text-[11px] text-muted">
                Ações técnicas são auditadas. Reimpressões são sempre
                explícitas.
              </p>
            </div>
            <Printer className="size-5 text-muted" />
          </div>
          {loading ? (
            <TableLoading columns={6} />
          ) : data?.results.length ? (
            <>
              <div className="hidden md:block table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Job</th>
                      <th>Destino</th>
                      <th>Impressora</th>
                      <th>Status</th>
                      <th>Criado em</th>
                      <th className="text-right">Ações</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.results.map((job) => (
                      <tr key={job.id}>
                        <td>
                          <strong>#{job.id}</strong>
                          <span className="block text-[11px] text-muted">
                            {job.production_event === "cancel"
                              ? "Cancelamento"
                              : "Novo pedido"}
                          </span>
                        </td>
                        <td>{destinationName(job, destinations)}</td>
                        <td>{job.printer_name}</td>
                        <td>
                          <PrintJobStatusBadge status={job.status} />
                          {job.last_error && (
                            <span
                              className="mt-1 block max-w-56 truncate text-[11px] text-danger-strong"
                              title={job.last_error}
                            >
                              {job.last_error}
                            </span>
                          )}
                        </td>
                        <td>{formatDate(job.created_at)}</td>
                        <td>
                          <div className="flex justify-end">{actions(job)}</div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="divide-y divide-subtle md:hidden">
                {data.results.map((job) => (
                  <article key={job.id} className="space-y-3 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <strong className="text-sm">Job #{job.id}</strong>
                        <p className="mt-1 text-xs text-muted">
                          {destinationName(job, destinations)} ·{" "}
                          {job.printer_name}
                        </p>
                      </div>
                      <PrintJobStatusBadge status={job.status} />
                    </div>
                    {job.last_error && (
                      <p className="rounded bg-danger-surface p-2 text-xs text-danger-strong">
                        {job.last_error}
                      </p>
                    )}
                    <p className="text-xs text-muted">
                      Criado em {formatDate(job.created_at)}
                    </p>
                    {actions(job)}
                  </article>
                ))}
              </div>
              <Pagination
                count={data.count}
                next={data.next}
                previous={data.previous}
                onPage={load}
              />
            </>
          ) : (
            <EmptyState
              title="Nenhum job encontrado"
              description={
                failuresOnly
                  ? "Não há falhas de impressão nesta filial."
                  : "A fila está vazia para os filtros selecionados."
              }
            />
          )}
        </section>
      </div>
    </>
  );
}

export function LegacyPrinterDiagnostics() {
  const { currentBranch, currentCompany, supportSession } = useAuth();
  const readOnly = supportSession?.mode === "READ_ONLY";
  const contextRef = useRef("");
  contextRef.current = `${currentCompany?.id || ""}:${currentBranch?.id || ""}`;
  const [devices, setDevices] = useState<PrinterDevice[]>([]);
  const [destinations, setDestinations] = useState<ProductionDestination[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [editing, setEditing] = useState<PrinterDevice | null>(null);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [name, setName] = useState("");
  const [type, setType] = useState<"manual" | "development">("manual");
  const [deviceStatus, setDeviceStatus] = useState<"active" | "inactive">(
    "active",
  );
  const [selected, setSelected] = useState<number[]>([]);
  const [configuration, setConfiguration] = useState("{}");
  async function load(context = contextRef.current) {
    if (!currentBranch) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [items, availableDestinations] = await Promise.all([
        http.getAll<PrinterDevice>("printer-devices/"),
        http
          .getAll<ProductionDestination>("production-destinations/")
          .catch(() => []),
      ]);
      if (context === contextRef.current) {
        setDevices(items);
        setDestinations(availableDestinations);
      }
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
  useEffect(() => {
    const context = contextRef.current;
    setDevices([]);
    setOpen(false);
    void load(context);
  }, [currentCompany?.id, currentBranch?.id]);
  function show(device?: PrinterDevice) {
    setEditing(device || null);
    setName(device?.name || "");
    setType(device?.device_type || "manual");
    setDeviceStatus(device?.status || "active");
    setSelected(device?.destination_ids || []);
    setConfiguration(
      JSON.stringify(device?.technical_configuration || {}, null, 2),
    );
    setFields({});
    setError("");
    setOpen(true);
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!currentBranch || readOnly) return;
    let technical_configuration: Record<string, unknown>;
    try {
      technical_configuration = JSON.parse(configuration || "{}");
      if (
        !technical_configuration ||
        Array.isArray(technical_configuration) ||
        typeof technical_configuration !== "object"
      )
        throw new Error();
    } catch {
      setFields({
        technical_configuration: ["Informe um JSON de configuração válido."],
      });
      return;
    }
    setSaving(true);
    setError("");
    setFields({});
    try {
      const body = {
        branch: currentBranch.id,
        name,
        device_type: type,
        status: deviceStatus,
        destination_ids: selected,
        technical_configuration,
      };
      if (editing) await http.patch(`printer-devices/${editing.id}/`, body);
      else await http.post("printer-devices/", body);
      setOpen(false);
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
  return (
    <>
      <PageHeader
        title="Impressoras"
        description={`Dispositivos vinculados à filial ${currentBranch?.name || "atual"}.`}
        action={
          !readOnly ? (
            <Button onClick={() => show()}>
              <Plus className="size-4" />
              Nova impressora
            </Button>
          ) : undefined
        }
      />
      <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        {error && !open && <Alert message={error} />}
        {success && <Alert type="success" message={success} />}
        <section className="card overflow-hidden">
          <div className="card-header">
            <div>
              <h2 className="text-sm font-bold">Dispositivos da filial</h2>
              <p className="mt-1 text-[11px] text-muted">
                A configuração técnica é aplicada pelo adaptador de impressão.
              </p>
            </div>
            <Printer className="size-5 text-muted" />
          </div>
          {loading ? (
            <TableLoading columns={5} />
          ) : devices.length ? (
            <div className="divide-y divide-subtle">
              {devices.map((device) => (
                <article
                  key={device.id}
                  className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <strong className="text-sm">{device.name}</strong>
                      <StatusBadge active={device.status === "active"} />
                    </div>
                    <p className="mt-1 text-xs text-muted">
                      {device.device_type === "manual"
                        ? "Manual"
                        : "Desenvolvimento"}{" "}
                      ·{" "}
                      {device.destination_ids.length
                        ? device.destination_ids
                            .map(
                              (id) =>
                                destinations.find((item) => item.id === id)
                                  ?.name || `#${id}`,
                            )
                            .join(", ")
                        : "Sem destinos"}
                    </p>
                    <p className="mt-1 text-[11px] text-muted">
                      Última atividade:{" "}
                      {device.last_seen_at
                        ? formatDate(device.last_seen_at)
                        : "não informada"}
                    </p>
                  </div>
                  {!readOnly && (
                    <button
                      className="icon-button self-start sm:self-auto"
                      onClick={() => show(device)}
                      aria-label={`Editar ${device.name}`}
                    >
                      <Pencil className="size-4" />
                    </button>
                  )}
                </article>
              ))}
            </div>
          ) : (
            <EmptyState
              title="Nenhuma impressora cadastrada"
              description="Cadastre um dispositivo para vincular os destinos de produção."
            />
          )}
        </section>
      </div>
      <Modal
        open={open}
        title={editing ? "Editar impressora" : "Nova impressora"}
        description="O dispositivo ficará vinculado apenas à filial atual."
        onClose={() => !saving && setOpen(false)}
        size="lg"
      >
        <form onSubmit={submit}>
          <div className="space-y-4 p-5 sm:p-6">
            {error && <Alert message={error} />}
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Nome" error={fieldError(fields, "name")}>
                <Input
                  autoFocus
                  required
                  maxLength={100}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
              </Field>
              <Field label="Tipo">
                <Select
                  value={type}
                  onChange={(event) =>
                    setType(event.target.value as "manual" | "development")
                  }
                >
                  <option value="manual">Manual</option>
                  <option value="development">Desenvolvimento</option>
                </Select>
              </Field>
            </div>
            <Field label="Status">
              <Select
                value={deviceStatus}
                onChange={(event) =>
                  setDeviceStatus(event.target.value as "active" | "inactive")
                }
              >
                <option value="active">Ativo</option>
                <option value="inactive">Inativo</option>
              </Select>
            </Field>
            <fieldset>
              <legend className="label">Destinos atendidos</legend>
              <div className="grid gap-2 sm:grid-cols-2">
                {destinations
                  .filter((item) => item.status === "active")
                  .map((item) => (
                    <label
                      key={item.id}
                      className="flex items-center gap-2 text-xs"
                    >
                      <input
                        type="checkbox"
                        checked={selected.includes(item.id)}
                        onChange={() =>
                          setSelected((items) =>
                            items.includes(item.id)
                              ? items.filter((id) => id !== item.id)
                              : [...items, item.id],
                          )
                        }
                      />
                      {item.name}
                    </label>
                  ))}
              </div>
              {!destinations.length && (
                <p className="text-xs text-muted">
                  Nenhum destino disponível ou sem permissão para consultá-los.
                </p>
              )}
            </fieldset>
            <Field
              label="Configuração técnica (JSON)"
              error={fieldError(fields, "technical_configuration")}
            >
              <Textarea
                rows={5}
                value={configuration}
                onChange={(event) => setConfiguration(event.target.value)}
                spellCheck={false}
                className="font-mono text-xs"
              />
            </Field>
          </div>
          <div className="flex justify-end gap-2 border-t border-subtle px-5 py-4">
            <Button
              type="button"
              variant="secondary"
              disabled={saving}
              onClick={() => setOpen(false)}
            >
              Cancelar
            </Button>
            <Button type="submit" loading={saving}>
              Salvar
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
}

export function PrintJobDetail({ id }: { id: string }) {
  const router = useRouter();
  const { hasPermission, supportSession } = useAuth();
  const readOnly = supportSession?.mode === "READ_ONLY";
  const canRetry = hasPermission(permissions.retryPrintJobs) && !readOnly;
  const canReprint = hasPermission(permissions.reprintPrintJobs) && !readOnly;
  const [job, setJob] = useState<PrintJob | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function load() {
    setError("");
    try {
      setJob(await http.get<PrintJob>(`print-jobs/${id}/`));
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível carregar o job.",
      );
    }
  }
  useEffect(() => {
    void load();
  }, [id]);
  async function act(action: "retry" | "reprint" | "manual-dispatch") {
    setBusy(true);
    setError("");
    try {
      const updated = await http.post<PrintJob>(`print-jobs/${id}/${action}/`);
      if (action === "reprint") {
        router.push(`/producao/jobs/${updated.id}`);
        return;
      }
      setJob(updated);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível atualizar o job.",
      );
    } finally {
      setBusy(false);
    }
  }
  const snapshot = job?.payload_snapshot || {};
  const order = snapshot.order_item as
    | {
        product_name?: string;
        internal_code?: string;
        quantity?: string;
        unit?: string;
        modifiers?: Array<{
          group_name?: string;
          option_name?: string;
          name?: string;
        }>;
      }
    | undefined;
  const command = snapshot.command as
    | { number?: string; identifier?: string }
    | undefined;
  const destination = snapshot.destination as
    | { name?: string; code?: string }
    | undefined;
  return (
    <>
      <PageHeader
        title={job ? `Job de impressão #${job.id}` : "Job de impressão"}
        description="Snapshot imutável gerado no momento do envio para produção."
        action={
          <Link className="btn btn-secondary" href="/producao/fila">
            Voltar para fila
          </Link>
        }
      />
      <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        {error && <Alert message={error} />}
        {!job ? (
          <TableLoading columns={3} />
        ) : (
          <>
            <section className="card p-5 sm:p-6">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <PrintJobStatusBadge status={job.status} />
                    {job.reprint_number > 0 && (
                      <span className="text-xs font-semibold text-muted">
                        Reimpressão #{job.reprint_number}
                      </span>
                    )}
                  </div>
                  <h2 className="mt-3 text-lg font-bold">
                    {order?.product_name || "Item de produção"}
                  </h2>
                  <p className="mt-1 text-sm text-muted">
                    {command?.number
                      ? `Comanda ${command.number}`
                      : "Comanda não identificada"}
                    {command?.identifier ? ` · ${command.identifier}` : ""}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {canRetry && job.status !== "printed" && (
                    <Button
                      variant="secondary"
                      loading={busy}
                      onClick={() => void act("retry")}
                    >
                      <RotateCcw className="size-4" />
                      Tentar novamente
                    </Button>
                  )}
                  {canRetry &&
                    (job.status === "pending" || job.status === "failed") && (
                      <Button
                        variant="secondary"
                        loading={busy}
                        onClick={() => void act("manual-dispatch")}
                      >
                        <Send className="size-4" />
                        Despacho manual
                      </Button>
                    )}
                  {canReprint && job.status === "printed" && (
                    <Button loading={busy} onClick={() => void act("reprint")}>
                      <Printer className="size-4" />
                      Reimprimir
                    </Button>
                  )}
                </div>
              </div>
              {job.last_error && (
                <div className="mt-5 rounded-md border border-danger/30 bg-danger-surface p-3 text-sm text-danger-strong">
                  <strong>Último erro:</strong> {job.last_error}
                </div>
              )}
            </section>
            <div className="grid gap-4 lg:grid-cols-2">
              <section className="card p-5">
                <h2 className="text-sm font-bold">Pedido e modificadores</h2>
                <dl className="mt-4 grid gap-3 text-sm">
                  <div>
                    <dt className="text-xs text-muted">Item</dt>
                    <dd className="font-semibold">
                      {order?.product_name || "-"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Quantidade</dt>
                    <dd>
                      {order?.quantity || "-"} {order?.unit || ""}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Código</dt>
                    <dd>{order?.internal_code || "-"}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Modificadores</dt>
                    <dd>
                      {order?.modifiers?.length
                        ? order.modifiers.map((item, index) => (
                            <span
                              key={index}
                              className="mr-1 inline-block rounded bg-surface-muted px-2 py-1 text-xs"
                            >
                              {item.group_name ? `${item.group_name}: ` : ""}
                              {item.option_name || item.name || "Opção"}
                            </span>
                          ))
                        : "Sem modificadores"}
                    </dd>
                  </div>
                </dl>
              </section>
              <section className="card p-5">
                <h2 className="text-sm font-bold">Roteamento e histórico</h2>
                <dl className="mt-4 grid gap-3 text-sm">
                  <div>
                    <dt className="text-xs text-muted">Destino</dt>
                    <dd>
                      {destination?.name || `#${job.destination}`}
                      {destination?.code ? ` (${destination.code})` : ""}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Dispositivo</dt>
                    <dd>{job.printer_name}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Evento</dt>
                    <dd>
                      {job.production_event === "cancel"
                        ? "Cancelamento"
                        : "Novo pedido"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Tentativas</dt>
                    <dd>{job.attempts}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Criado em</dt>
                    <dd>{formatDate(job.created_at)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Processado em</dt>
                    <dd>
                      {job.processing_at ? formatDate(job.processing_at) : "-"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Impresso em</dt>
                    <dd>{job.printed_at ? formatDate(job.printed_at) : "-"}</dd>
                  </div>
                </dl>
              </section>
            </div>
          </>
        )}
      </div>
    </>
  );
}
