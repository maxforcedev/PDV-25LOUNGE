"use client";

import { useEffect, useState } from "react";
import { Building2, GitBranch, Pencil, Plus, Power } from "lucide-react";
import {
  Alert,
  Button,
  ConfirmDialog,
  EmptyState,
  Field,
  Input,
  Modal,
  Pagination,
  StatusBadge,
  TableLoading,
} from "@/components/ui";
import { PageHeader } from "@/components/page-header";
import { AdminGuard } from "@/components/admin-guard";
import { ApiError, http } from "@/lib/http";
import { fieldError, formatBRL, formatDate } from "@/lib/format";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { Company, CompanyPayload, Paginated } from "@/types";

const emptyForm: CompanyPayload = {
  trade_name: "",
  legal_name: "",
  cnpj: null,
  email: "",
  phone: "",
};

function CompaniesAdministration() {
  const { hasPermission } = useAuth();
  const canAdd = hasPermission(permissions.changeCompany);
  const canChange = hasPermission(permissions.changeCompany);
  const [data, setData] = useState<Paginated<Company> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Company | null>(null);
  const [form, setForm] = useState<CompanyPayload>(emptyForm);
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState<Company | null>(null);
  const [changingStatus, setChangingStatus] = useState(false);

  async function load(path = "companies/") {
    setLoading(true);
    setError("");
    try {
      setData(await http.get<Paginated<Company>>(path));
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível carregar as empresas.",
      );
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void load();
  }, []);

  function openCreate() {
    if (!canAdd) return;
    setEditing(null);
    setForm(emptyForm);
    setFields({});
    setError("");
    setModalOpen(true);
  }
  function openEdit(company: Company) {
    if (!canChange) return;
    setEditing(company);
    setForm({
      trade_name: company.trade_name,
      legal_name: company.legal_name,
      cnpj: company.cnpj,
      email: company.email,
      phone: company.phone,
    });
    setFields({});
    setError("");
    setModalOpen(true);
  }
  function update<K extends keyof CompanyPayload>(
    key: K,
    value: CompanyPayload[K],
  ) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (editing ? !canChange : !canAdd) return;
    setSaving(true);
    setFields({});
    setError("");
    setSuccess("");
    const payload = { ...form, cnpj: form.cnpj || null };
    try {
      const company = editing
        ? await http.patch<Company>(`companies/${editing.id}/`, payload)
        : await http.post<Company>("companies/", payload);
      setModalOpen(false);
      const matrixConfirmed = company.branches?.some(
        (branch) => branch.is_matrix,
      );
      setSuccess(
        editing
          ? "Empresa atualizada com sucesso."
          : `Empresa criada com sucesso. ${matrixConfirmed ? "Filial Matriz confirmada." : "Aguardando a confirmação da filial Matriz pela API."}`,
      );
      await load();
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setFields(caught.fields);
      } else setError("Não foi possível salvar a empresa.");
    } finally {
      setSaving(false);
    }
  }

  async function changeStatus() {
    if (!confirming || !canChange) return;
    setChangingStatus(true);
    setError("");
    setSuccess("");
    const action = confirming.status === "active" ? "deactivate" : "activate";
    try {
      await http.post(`companies/${confirming.id}/${action}/`);
      setSuccess(
        `Empresa ${action === "activate" ? "ativada" : "inativada"} com sucesso.`,
      );
      setConfirming(null);
      await load();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível alterar o status.",
      );
      setConfirming(null);
    } finally {
      setChangingStatus(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Empresas"
        description="Gerencie empresas e suas unidades matrizes."
        action={
          <Button
            onClick={openCreate}
            disabled={!canAdd}
            title={
              canAdd ? "Nova empresa" : "Sem permissão para criar empresas"
            }
          >
            <Plus className="size-4" />
            Nova empresa
          </Button>
        }
      />
      <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        {error && !modalOpen && <Alert message={error} />}
        {success && <Alert type="success" message={success} />}
        <section className="card overflow-hidden">
          <div className="card-header">
            <div>
              <h2 className="text-sm font-bold">Empresas cadastradas</h2>
              <p className="mt-1 text-[11px] text-slate-500">
                Razão social, matriz e situação cadastral
              </p>
            </div>
            <Building2 className="size-5 text-slate-300" />
          </div>
          {loading ? (
            <TableLoading />
          ) : data?.results.length ? (
            <>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Empresa</th>
                      <th>CNPJ</th>
                      <th>Filiais / configurações</th>
                      <th>Status</th>
                      <th>Atualização</th>
                      <th className="text-right">Ações</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.results.map((company) => {
                      return (
                        <tr key={company.id}>
                          <td>
                            <strong className="block text-dark">
                              {company.trade_name}
                            </strong>
                            <span className="mt-0.5 block text-[11px] text-slate-400">
                              {company.legal_name}
                            </span>
                          </td>
                          <td className="text-slate-600">
                            {company.cnpj || "Não informado"}
                          </td>
                          <td>
                            {company.branches?.length ? (
                              <div className="min-w-72 space-y-2">
                                {company.branches.map((branch) => (
                                  <div key={branch.id} className="rounded-md border border-slate-100 px-3 py-2">
                                    <strong className="flex items-center gap-1.5 text-xs">
                                      <GitBranch className="size-3.5 text-primary" />
                                      {branch.name}
                                    </strong>
                                    <span className="mt-1 block text-[10px] text-slate-500">
                                      Negativo: {branch.settings_summary?.allow_negative_stock ? "permitido" : "bloqueado"} · Taxa: {branch.settings_summary?.service_fee_rate || "0.00"}% · Comissão: {branch.settings_summary?.commission_rate || "0.00"}% · Fixo: {formatBRL(branch.settings_summary?.fixed_daily_cost || "0.00")}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <span className="text-[11px] font-medium text-amber-700">
                                Nenhuma filial visível
                              </span>
                            )}
                          </td>
                          <td>
                            <StatusBadge active={company.status === "active"} />
                          </td>
                          <td className="text-slate-500">
                            {formatDate(company.updated_at)}
                          </td>
                          <td>
                            <div className="flex justify-end gap-1">
                              <button
                                className="icon-button"
                                disabled={!canChange}
                                title={
                                  canChange
                                    ? "Editar"
                                    : "Sem permissão para editar empresas"
                                }
                                aria-label={`Editar ${company.trade_name}`}
                                onClick={() => openEdit(company)}
                              >
                                <Pencil className="size-4" />
                              </button>
                              <button
                                disabled={!canChange}
                                className={`icon-button ${company.status === "active" ? "hover:bg-danger/10 hover:text-danger" : "hover:bg-success/10 hover:text-success"}`}
                                title={
                                  canChange
                                    ? company.status === "active"
                                      ? "Inativar"
                                      : "Ativar"
                                    : "Sem permissão para alterar empresas"
                                }
                                aria-label={`${company.status === "active" ? "Inativar" : "Ativar"} ${company.trade_name}`}
                                onClick={() =>
                                  canChange && setConfirming(company)
                                }
                              >
                                <Power className="size-4" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
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
              title="Nenhuma empresa cadastrada"
              description="Crie a primeira empresa. O backend também criará sua unidade Matriz automaticamente."
            />
          )}
        </section>
      </div>
      <Modal
        open={modalOpen}
        title={editing ? "Editar empresa" : "Nova empresa"}
        description={
          editing
            ? "Atualize os dados cadastrais."
            : "Ao salvar, uma filial Matriz será criada automaticamente."
        }
        onClose={() => !saving && setModalOpen(false)}
      >
        <form onSubmit={submit}>
          <div className="grid gap-5 p-5 sm:grid-cols-2 sm:p-6">
            <div className="sm:col-span-2">
              {error && <Alert message={error} />}
            </div>
            <Field
              label="Nome fantasia"
              error={fieldError(fields, "trade_name")}
            >
              <Input
                required
                value={form.trade_name}
                onChange={(e) => update("trade_name", e.target.value)}
                disabled={saving}
              />
            </Field>
            <Field
              label="Razão social"
              error={fieldError(fields, "legal_name")}
            >
              <Input
                required
                value={form.legal_name}
                onChange={(e) => update("legal_name", e.target.value)}
                disabled={saving}
              />
            </Field>
            <Field label="CNPJ" optional error={fieldError(fields, "cnpj")}>
              <Input
                value={form.cnpj || ""}
                onChange={(e) => update("cnpj", e.target.value)}
                disabled={saving}
                placeholder="00.000.000/0000-00"
              />
            </Field>
            <Field label="E-mail" error={fieldError(fields, "email")}>
              <Input
                type="email"
                required
                value={form.email}
                onChange={(e) => update("email", e.target.value)}
                disabled={saving}
              />
            </Field>
            <Field label="Telefone" error={fieldError(fields, "phone")}>
              <Input
                required
                value={form.phone}
                onChange={(e) => update("phone", e.target.value)}
                disabled={saving}
              />
            </Field>
            <div className="rounded-md border border-dashed border-primary/25 bg-primary/5 p-3 text-xs text-primary">
              <strong className="block">Unidade Matriz</strong>
              <span className="mt-1 block text-[11px] text-slate-500">
                Criada e vinculada automaticamente na inclusão.
              </span>
            </div>
          </div>
          <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-4 sm:px-6">
            <Button
              type="button"
              variant="secondary"
              disabled={saving}
              onClick={() => setModalOpen(false)}
            >
              Cancelar
            </Button>
            <Button
              type="submit"
              loading={saving}
              disabled={editing ? !canChange : !canAdd}
            >
              {editing ? "Salvar alterações" : "Criar empresa"}
            </Button>
          </div>
        </form>
      </Modal>
      <ConfirmDialog
        open={!!confirming}
        title={`${confirming?.status === "active" ? "Inativar" : "Ativar"} empresa`}
        message={
          confirming?.status === "active"
            ? `Ao inativar “${confirming.trade_name}”, todas as filiais também serão inativadas. Para voltar a operá-las, cada filial precisará ser reativada individualmente depois.`
            : `Confirma a ativação de “${confirming?.trade_name || ""}”? As filiais permanecerão inativas até serem reativadas individualmente.`
        }
        confirmLabel={confirming?.status === "active" ? "Inativar" : "Ativar"}
        danger={confirming?.status === "active"}
        loading={changingStatus}
        onClose={() => !changingStatus && setConfirming(null)}
        onConfirm={changeStatus}
      />
    </>
  );
}

export default function CompaniesPage() {
  return (
    <AdminGuard
      requiredPermissions={[permissions.viewCompany, permissions.changeCompany]}
    >
      <CompaniesAdministration />
    </AdminGuard>
  );
}
