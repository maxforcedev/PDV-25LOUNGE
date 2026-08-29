"use client";

import { useEffect, useRef, useState } from "react";
import { Pencil, Plus, Power, Search } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
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
  Spinner,
  StatusBadge,
  Textarea,
} from "@/components/ui";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { Customer, Paginated } from "@/types";

type CustomerForm = Pick<
  Customer,
  "name" | "phone" | "document" | "email" | "birth_date" | "notes"
>;
const blank = (): CustomerForm => ({
  name: "",
  phone: "",
  document: "",
  email: "",
  birth_date: null,
  notes: "",
});

function CustomersPage() {
  const { currentCompany, hasPermission, supportSession } = useAuth();
  const readOnly = supportSession?.mode === "READ_ONLY";
  const canAdd = hasPermission(permissions.addCustomer) && !readOnly;
  const canChange = hasPermission(permissions.changeCustomer) && !readOnly;
  const canDeactivate =
    hasPermission(permissions.deactivateCustomer) && !readOnly;
  const companyRef = useRef(currentCompany?.id);
  companyRef.current = currentCompany?.id;
  const [data, setData] = useState<Paginated<Customer> | null>(null);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("active");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Customer | null>(null);
  const [form, setForm] = useState<CustomerForm>(blank);
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [saving, setSaving] = useState(false);

  function path(page?: string) {
    const params = new URLSearchParams({
      company: String(currentCompany?.id || ""),
      status,
      search: search.trim(),
    });
    return page || `customers/?${params}`;
  }
  async function load(page?: string) {
    const companyId = currentCompany?.id;
    if (!companyId) {
      setData(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const response = await http.get<Paginated<Customer>>(path(page));
      if (companyRef.current === companyId) setData(response);
    } catch (caught) {
      if (companyRef.current === companyId)
        setError(
          caught instanceof ApiError
            ? caught.message
            : "Não foi possível carregar os clientes.",
        );
    } finally {
      if (companyRef.current === companyId) setLoading(false);
    }
  }
  useEffect(() => {
    setSearch("");
    setStatus("active");
    void load();
  }, [currentCompany?.id]);
  function start(customer?: Customer) {
    setEditing(customer || null);
    setFields({});
    setError("");
    setForm(
      customer
        ? {
            name: customer.name,
            phone: customer.phone,
            document: customer.document || "",
            email: customer.email,
            birth_date: customer.birth_date,
            notes: customer.notes,
          }
        : blank(),
    );
    setOpen(true);
  }
  async function save() {
    if (!currentCompany) return;
    setSaving(true);
    setFields({});
    setError("");
    const payload = {
      ...form,
      company: currentCompany.id,
      birth_date: form.birth_date || null,
    };
    try {
      await (editing
        ? http.patch<Customer>(`customers/${editing.id}/`, payload)
        : http.post<Customer>("customers/", payload));
      setOpen(false);
      await load();
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setFields(caught.fields);
      } else setError("Não foi possível salvar o cliente.");
    } finally {
      setSaving(false);
    }
  }
  async function deactivate(customer: Customer) {
    if (!window.confirm(`Inativar ${customer.name}?`)) return;
    setError("");
    try {
      await http.post(`customers/${customer.id}/deactivate/`);
      await load();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível inativar o cliente.",
      );
    }
  }
  const input = (
    key: keyof CustomerForm,
    label: string,
    type = "text",
    optional = false,
  ) => (
    <Field label={label} optional={optional} error={fields[key]?.join(" ")}>
      <Input
        required={key === "name"}
        type={type}
        value={form[key] || ""}
        onChange={(event) =>
          setForm((current) => ({ ...current, [key]: event.target.value }))
        }
        disabled={saving}
      />
    </Field>
  );

  return (
    <>
      <PageHeader
        title="Clientes"
        description="Cadastro simples de clientes da empresa atual."
        action={
          canAdd ? (
            <Button onClick={() => start()}>
              <Plus className="size-4" />
              Novo cliente
            </Button>
          ) : undefined
        }
      />
      <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        {error && !open && <Alert message={error} />}
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void load();
          }}
        >
          <div className="relative min-w-56 flex-1">
            <Search className="absolute left-3 top-3 size-4 text-muted" />
            <Input
              className="pl-9"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Nome, telefone, e-mail ou documento"
            />
          </div>
          <Select
            className="w-36"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="active">Ativos</option>
            <option value="inactive">Inativos</option>
            <option value="">Todos</option>
          </Select>
          <Button>Buscar</Button>
        </form>
        {loading ? (
          <Spinner />
        ) : data?.results.length ? (
          <>
            <section className="card overflow-hidden">
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Cliente</th>
                      <th>Telefone</th>
                      <th>E-mail</th>
                      <th>Status</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {data.results.map((customer) => (
                      <tr key={customer.id}>
                        <td>
                          <strong>{customer.name}</strong>
                          {customer.duplicate_warning && (
                            <small className="mt-1 block text-warning">
                              {customer.duplicate_warning.message}
                            </small>
                          )}
                        </td>
                        <td>{customer.phone || "-"}</td>
                        <td>{customer.email || "-"}</td>
                        <td>
                          <StatusBadge active={customer.status === "active"} />
                        </td>
                        <td>
                          <div className="flex justify-end gap-2">
                            {canChange && (
                              <button
                                className="icon-button"
                                onClick={() => start(customer)}
                                title="Editar"
                              >
                                <Pencil className="size-4" />
                              </button>
                            )}
                            {canDeactivate && customer.status === "active" && (
                              <button
                                className="icon-button text-danger"
                                onClick={() => void deactivate(customer)}
                                title="Inativar"
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
            </section>
            <Pagination
              count={data.count}
              next={data.next}
              previous={data.previous}
              onPage={(next) => void load(next)}
            />
          </>
        ) : (
          <EmptyState
            title="Nenhum cliente encontrado"
            description="Cadastre um cliente ou ajuste a busca."
          />
        )}
      </div>
      <Modal
        open={open}
        title={editing ? "Editar cliente" : "Novo cliente"}
        onClose={() => setOpen(false)}
      >
        <div className="space-y-4 p-5">
          {input("name", "Nome")}
          {input("phone", "Telefone", "text", true)}
          {input("document", "Documento", "text", true)}
          {input("email", "E-mail", "email", true)}
          {input("birth_date", "Data de nascimento", "date", true)}
          <Field label="Observações" optional error={fields.notes?.join(" ")}>
            <Textarea
              value={form.notes}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  notes: event.target.value,
                }))
              }
              disabled={saving}
            />
          </Field>
          {error && <Alert message={error} />}
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setOpen(false)}>
              Cancelar
            </Button>
            <Button loading={saving} onClick={() => void save()}>
              Salvar
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}
export default function CustomersPageWrapper() {
  return (
    <AdminGuard requiredPermissions={[permissions.viewCustomer]}>
      <CustomersPage />
    </AdminGuard>
  );
}
