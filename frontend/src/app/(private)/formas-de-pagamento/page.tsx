"use client";

import { useEffect, useRef, useState } from "react";
import { CreditCard, Pencil, Power } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import {
  Alert,
  Button,
  ConfirmDialog,
  EmptyState,
  Field,
  Input,
  Modal,
  Pagination,
  Select,
  StatusBadge,
  TableLoading,
} from "@/components/ui";
import { fieldError } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { Paginated, PaymentMethod } from "@/types";

function errorText(caught: unknown, fallback: string) {
  if (!(caught instanceof ApiError)) return fallback;
  return Object.values(caught.fields).flat().join(" ") || caught.message;
}
const methodCodeLabels: Record<string, string> = { cash: "Dinheiro", pix: "PIX", credit_card: "Cartão de crédito", debit_card: "Cartão de débito" };

function PaymentMethods() {
  const { currentCompany, currentBranch, hasPermission } = useAuth();
  const canChange = hasPermission(permissions.changePaymentMethod);
  const contextRef = useRef("");
  contextRef.current = `${currentCompany?.id || ""}:${currentBranch?.id || ""}`;
  const [data, setData] = useState<Paginated<PaymentMethod> | null>(null);
  const [status, setStatus] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [editing, setEditing] = useState<PaymentMethod | null | undefined>(
    undefined,
  );
  const [name, setName] = useState("");
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState<PaymentMethod | null>(null);

  async function load(
    path?: string,
    context = contextRef.current,
    selectedStatus = status,
  ) {
    if (!currentBranch) {
      setData(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const response = await http.get<Paginated<PaymentMethod>>(
        path || `payment-methods/?status=${selectedStatus}`,
      );
      if (contextRef.current === context) setData(response);
    } catch (caught) {
      if (contextRef.current === context)
        setError(
          errorText(
            caught,
            "Não foi possível carregar as formas de pagamento.",
          ),
        );
    } finally {
      if (contextRef.current === context) setLoading(false);
    }
  }

  useEffect(() => {
    const context = contextRef.current;
    setStatus("all");
    setData(null);
    setError("");
    setSuccess("");
    setEditing(undefined);
    setConfirming(null);
    void load("payment-methods/?status=all", context, "all");
  }, [currentCompany?.id, currentBranch?.id]);

  function show(method: PaymentMethod) {
    if (!canChange || method.is_system) return;
    setEditing(method);
    setName(method.name);
    setFields({});
    setError("");
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!editing || !canChange) return;
    setSaving(true);
    setError("");
    setFields({});
    try {
      await http.patch(`payment-methods/${editing.id}/`, { name });
      setEditing(undefined);
      setSuccess("Forma de pagamento atualizada.");
      await load();
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setFields(caught.fields);
      } else setError("Não foi possível salvar a forma de pagamento.");
    } finally {
      setSaving(false);
    }
  }

  async function changeStatus() {
    if (!confirming || !canChange) return;
    const method = confirming;
    const action = method.status === "active" ? "deactivate" : "activate";
    setSaving(true);
    setError("");
    try {
      await http.post(`payment-methods/${method.id}/${action}/`);
      setConfirming(null);
      setSuccess(
        `Forma de pagamento ${action === "activate" ? "ativada" : "inativada"}.`,
      );
      await load();
    } catch (caught) {
      setConfirming(null);
      setError(errorText(caught, "Não foi possível alterar o status."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Formas de pagamento"
        description={`Empresa atual: ${currentCompany?.trade_name || "nenhuma"}. Ative ou inative os métodos disponíveis para todas as filiais.`}
      />
      <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        {error && editing === undefined && <Alert message={error} />}
        {success && <Alert type="success" message={success} />}
        <div className="card flex items-center gap-3 p-4">
          <label className="text-xs font-semibold" htmlFor="method-status">
            Exibir
          </label>
          <Select
            id="method-status"
            className="max-w-52"
            value={status}
            onChange={(event) => {
              const value = event.target.value;
              setStatus(value);
              void load(
                `payment-methods/?status=${value}`,
                contextRef.current,
                value,
              );
            }}
          >
            <option value="active">Somente ativas</option>
            <option value="all">Ativas e inativas</option>
          </Select>
        </div>
        <section className="card overflow-hidden">
          <div className="card-header">
            <div>
              <h2 className="text-sm font-bold">Métodos disponíveis</h2>
              <p className="mt-1 text-[11px] text-slate-500">
                Os quatro métodos padrão são imutáveis; métodos personalizados
                legados permitem alterar somente o nome.
              </p>
            </div>
            <CreditCard className="size-5 text-slate-300" />
          </div>
          {loading ? (
            <TableLoading columns={4} />
          ) : data?.results.length ? (
            <>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Nome</th>
                      <th>Identificador</th>
                      <th>Origem</th>
                      <th>Status</th>
                      <th className="text-right">Ações</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.results.map((method) => (
                      <tr key={method.id}>
                        <td className="font-semibold">{method.name}</td>
                        <td>
                          <code className="rounded bg-slate-100 px-2 py-1 text-xs">
                            {methodCodeLabels[method.code] || "Personalizado"}
                          </code>
                        </td>
                        <td>
                          <span
                            className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${method.is_system ? "bg-primary/10 text-primary" : "bg-slate-100 text-slate-600"}`}
                          >
                            {method.is_system
                              ? "Padrão do sistema"
                              : "Personalizada legada"}
                          </span>
                        </td>
                        <td>
                          <StatusBadge active={method.status === "active"} />
                        </td>
                        <td>
                          <div className="flex justify-end gap-1">
                            {canChange && !method.is_system && (
                              <button
                                className="icon-button"
                                aria-label={`Editar ${method.name}`}
                                onClick={() => show(method)}
                              >
                                <Pencil className="size-4" />
                              </button>
                            )}
                            {canChange && (
                              <button
                                className="icon-button"
                                aria-label={`${method.status === "active" ? "Inativar" : "Ativar"} ${method.name}`}
                                onClick={() => setConfirming(method)}
                              >
                                <Power className="size-4" />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
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
              title="Nenhuma forma de pagamento"
              description="Não há métodos para o filtro selecionado."
            />
          )}
        </section>
      </div>
      <Modal
        open={editing !== undefined}
        title="Editar forma personalizada"
        description="Somente o nome do método legado pode ser alterado."
        onClose={() => !saving && setEditing(undefined)}
        size="md"
      >
        <form onSubmit={submit}>
          <div className="space-y-4 p-5 sm:p-6">
            {error && <Alert message={error} />}
            <Field label="Nome" error={fieldError(fields, "name")}>
              <Input
                required
                maxLength={100}
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </Field>
          </div>
          <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-4">
            <Button
              type="button"
              variant="secondary"
              disabled={saving}
              onClick={() => setEditing(undefined)}
            >
              Cancelar
            </Button>
            <Button type="submit" loading={saving}>
              Salvar
            </Button>
          </div>
        </form>
      </Modal>
      <ConfirmDialog
        open={!!confirming}
        title={`${confirming?.status === "active" ? "Inativar" : "Ativar"} forma de pagamento`}
        message={`Confirma a alteração de “${confirming?.name || ""}”? Vendas históricas continuam exibindo o nome registrado no momento da operação.`}
        confirmLabel={confirming?.status === "active" ? "Inativar" : "Ativar"}
        danger={confirming?.status === "active"}
        loading={saving}
        onClose={() => setConfirming(null)}
        onConfirm={changeStatus}
      />
    </>
  );
}

export default function PaymentMethodsPage() {
  return (
    <AdminGuard requiredPermissions={[permissions.viewPaymentMethod]}>
      <PaymentMethods />
    </AdminGuard>
  );
}
