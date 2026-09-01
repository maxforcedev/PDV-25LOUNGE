"use client";

import { useEffect, useRef, useState } from "react";
import {
  Mail,
  MapPin,
  Pencil,
  Phone,
  Plus,
  Power,
  Search,
  SlidersHorizontal,
  Truck,
} from "lucide-react";
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
  Spinner,
  StatusBadge,
  TableLoading,
  Textarea,
} from "@/components/ui";
import { fieldError } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import {
  formatZipCode,
  lookupAddressByZipCode,
  ViaCepError,
  zipCodeDigits,
} from "@/lib/viacep";
import { useAuth } from "@/providers/auth-provider";
import type { Address, Paginated, Supplier } from "@/types";

type SupplierFilters = { search: string; status: string };
type SupplierForm = {
  company: number;
  legal_name: string;
  trade_name: string;
  tax_id: string;
  phone: string;
  email: string;
  address: Address;
  contact_name: string;
  notes: string;
};

const emptyFilters = (): SupplierFilters => ({ search: "", status: "" });
const emptyAddress = (): Address => ({
  zip_code: "",
  street: "",
  number: "",
  complement: "",
  neighborhood: "",
  city: "",
  state: "",
});
const emptyForm = (company = 0): SupplierForm => ({
  company,
  legal_name: "",
  trade_name: "",
  tax_id: "",
  phone: "",
  email: "",
  address: emptyAddress(),
  contact_name: "",
  notes: "",
});

function formatTaxId(value: string) {
  const digits = value.replace(/\D/g, "").slice(0, 14);
  if (digits.length <= 11) {
    if (digits.length <= 3) return digits;
    if (digits.length <= 6) return `${digits.slice(0, 3)}.${digits.slice(3)}`;
    if (digits.length <= 9)
      return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6)}`;
    return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6, 9)}-${digits.slice(9)}`;
  }
  const base = `${digits.slice(0, 2)}.${digits.slice(2, 5)}.${digits.slice(5, 8)}/${digits.slice(8, 12)}`;
  return digits.length > 12 ? `${base}-${digits.slice(12)}` : base;
}

function supplierName(supplier: Supplier) {
  return supplier.trade_name || supplier.legal_name;
}

function addressText(address: Supplier["address"]) {
  return (
    [
      address.street,
      address.number,
      address.neighborhood,
      address.city,
      address.state,
    ]
      .filter(Boolean)
      .join(", ") || "Não informado"
  );
}

function Suppliers() {
  const { currentCompany, currentBranch, hasPermission, supportSession } = useAuth();
  const readOnlySupport = supportSession?.mode === "READ_ONLY";
  const canChange =
    hasPermission(permissions.changeSupplier) && !readOnlySupport;
  const companyIdRef = useRef(currentCompany?.id);
  companyIdRef.current = currentCompany?.id;
  const branchIdRef = useRef(currentBranch?.id);
  branchIdRef.current = currentBranch?.id;

  const [data, setData] = useState<Paginated<Supplier> | null>(null);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState("");
  const [success, setSuccess] = useState("");
  const [draftFilters, setDraftFilters] =
    useState<SupplierFilters>(emptyFilters);
  const [appliedFilters, setAppliedFilters] =
    useState<SupplierFilters>(emptyFilters);

  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Supplier | null>(null);
  const [form, setForm] = useState<SupplierForm>(emptyForm);
  const addressRef = useRef(form.address);
  addressRef.current = form.address;
  const [addressEnabled, setAddressEnabled] = useState(false);
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const [zipCodeLoading, setZipCodeLoading] = useState(false);
  const [zipCodeError, setZipCodeError] = useState("");
  const [zipLookupEnabled, setZipLookupEnabled] = useState(false);

  const [confirming, setConfirming] = useState<Supplier | null>(null);
  const [changingStatus, setChangingStatus] = useState(false);
  const [relatedProducts, setRelatedProducts] = useState<Array<{ id: number; product_name: string; supplier_code: string; is_preferred: boolean; status: string }>>([]);
  const [loadingProducts, setLoadingProducts] = useState(false);

  function listPath(companyId: number, selected: SupplierFilters) {
    const params = new URLSearchParams({
      company: String(companyId),
      status: selected.status,
      search: selected.search.trim(),
    });
    return `suppliers/?${params}`;
  }

  async function load(
    path?: string,
    requestedCompanyId = currentCompany?.id,
    selected = appliedFilters,
  ) {
    const requestedBranchId = branchIdRef.current;
    if (!requestedCompanyId || !requestedBranchId) {
      setData(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setPageError("");
    try {
      const response = await http.get<Paginated<Supplier>>(
        path || listPath(requestedCompanyId, selected),
      );
      if (
        companyIdRef.current === requestedCompanyId
        && branchIdRef.current === requestedBranchId
      ) setData(response);
    } catch (caught) {
      if (companyIdRef.current === requestedCompanyId && branchIdRef.current === requestedBranchId) {
        setPageError(
          caught instanceof ApiError
            ? caught.message
            : "Não foi possível carregar os fornecedores.",
        );
      }
    } finally {
      if (companyIdRef.current === requestedCompanyId && branchIdRef.current === requestedBranchId) setLoading(false);
    }
  }

  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    const companyId = currentCompany?.id;
    const cleared = emptyFilters();
    setData(null);
    setLoading(Boolean(companyId));
    setPageError("");
    setSuccess("");
    setDraftFilters(cleared);
    setAppliedFilters(cleared);
    setOpen(false);
    setEditing(null);
    setConfirming(null);
    setSaving(false);
    setChangingStatus(false);
    if (companyId) void loadRef.current(undefined, companyId, cleared);
  }, [currentCompany?.id, currentBranch?.id]);

  useEffect(() => {
    const zipCode = zipCodeDigits(form.address.zip_code);
    const requestedCompanyId = currentCompany?.id;
    if (
      !open ||
      !addressEnabled ||
      !zipLookupEnabled ||
      zipCode.length !== 8 ||
      !requestedCompanyId
    ) {
      setZipCodeLoading(false);
      return;
    }

    const controller = new AbortController();
    const initialAddress = { ...addressRef.current };
    const timeout = window.setTimeout(() => {
      setZipCodeLoading(true);
      setZipCodeError("");
      lookupAddressByZipCode(zipCode, controller.signal)
        .then((address) => {
          if (companyIdRef.current !== requestedCompanyId) return;
          setForm((current) => {
            if (zipCodeDigits(current.address.zip_code) !== zipCode)
              return current;
            const nextAddress = { ...current.address };
            for (const key of [
              "street",
              "complement",
              "neighborhood",
              "city",
              "state",
            ] as const) {
              if (
                address[key] &&
                current.address[key] === initialAddress[key]
              ) {
                nextAddress[key] = address[key];
              }
            }
            return { ...current, address: nextAddress };
          });
        })
        .catch((caught) => {
          if (
            controller.signal.aborted ||
            companyIdRef.current !== requestedCompanyId
          )
            return;
          setZipCodeError(
            caught instanceof ViaCepError
              ? caught.message
              : "Não foi possível consultar o CEP. Preencha o endereço manualmente.",
          );
        })
        .finally(() => {
          if (
            !controller.signal.aborted &&
            companyIdRef.current === requestedCompanyId
          )
            setZipCodeLoading(false);
        });
    }, 450);

    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [
    addressEnabled,
    currentCompany?.id,
    form.address.zip_code,
    open,
    zipLookupEnabled,
  ]);

  function applyFilters(event: React.FormEvent) {
    event.preventDefault();
    const selected = { ...draftFilters };
    setAppliedFilters(selected);
    void load(undefined, currentCompany?.id, selected);
  }

  function clearFilters() {
    const cleared = emptyFilters();
    setDraftFilters(cleared);
    setAppliedFilters(cleared);
    void load(undefined, currentCompany?.id, cleared);
  }

  function openCreate() {
    if (!currentCompany || !canChange) return;
    setEditing(null);
    setForm(emptyForm(currentCompany.id));
    setAddressEnabled(false);
    setFields({});
    setFormError("");
    setZipCodeError("");
    setZipLookupEnabled(false);
    setOpen(true);
  }

  function openEdit(supplier: Supplier) {
    if (
      !currentCompany ||
      !canChange ||
      supplier.company !== currentCompany.id
    )
      return;
    setEditing(supplier);
    setForm({
      company: supplier.company,
      legal_name: supplier.legal_name,
      trade_name: supplier.trade_name,
      tax_id: supplier.tax_id || "",
      phone: supplier.phone || "",
      email: supplier.email || "",
      address: Object.keys(supplier.address).length
        ? { ...emptyAddress(), ...supplier.address }
        : emptyAddress(),
      contact_name: supplier.contact_name || "",
      notes: supplier.notes || "",
    });
    setAddressEnabled(Object.values(supplier.address).some(Boolean));
    setFields({});
    setFormError("");
    setZipCodeError("");
    setZipLookupEnabled(false);
    setOpen(true);
    setRelatedProducts([]);
    void loadRelatedProducts(supplier.id);
  }

  async function loadRelatedProducts(supplierId: number) {
    setLoadingProducts(true);
    try {
      const relations = await http.getAll<{ id: number; product_name: string; supplier_code: string; is_preferred: boolean; status: string }>(
        `product-suppliers/?supplier=${supplierId}&status=active`
      );
      setRelatedProducts(relations);
    } catch { setRelatedProducts([]); }
    finally { setLoadingProducts(false); }
  }

  function update<K extends keyof SupplierForm>(
    key: K,
    value: SupplierForm[K],
  ) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function updateAddress(key: keyof Address, value: string) {
    setForm((current) => ({
      ...current,
      address: { ...current.address, [key]: value },
    }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const requestedCompanyId = currentCompany?.id;
    if (
      !requestedCompanyId ||
      !canChange ||
      form.company !== requestedCompanyId
    )
      return;

    setSaving(true);
    setFields({});
    setFormError("");
    setSuccess("");
    const hasAddressValue = Object.values(form.address).some((value) =>
      value?.trim(),
    );
    const payload = {
      ...form,
      company: requestedCompanyId,
      tax_id: form.tax_id.trim() || null,
      phone: form.phone.trim(),
      email: form.email.trim(),
      contact_name: form.contact_name.trim(),
      notes: form.notes.trim(),
      address: addressEnabled && hasAddressValue ? form.address : {},
    };

    try {
      if (editing)
        await http.patch<Supplier>(`suppliers/${editing.id}/`, payload);
      else await http.post<Supplier>("suppliers/", payload);
      if (companyIdRef.current !== requestedCompanyId) return;
      setOpen(false);
      setSuccess(
        editing
          ? "Fornecedor atualizado com sucesso."
          : "Fornecedor criado com sucesso.",
      );
      await load(undefined, requestedCompanyId, appliedFilters);
    } catch (caught) {
      if (companyIdRef.current !== requestedCompanyId) return;
      if (caught instanceof ApiError) {
        setFormError(caught.message);
        setFields(caught.fields);
      } else setFormError("Não foi possível salvar o fornecedor.");
    } finally {
      if (companyIdRef.current === requestedCompanyId) setSaving(false);
    }
  }

  async function changeStatus() {
    const supplier = confirming;
    const requestedCompanyId = currentCompany?.id;
    if (
      !supplier ||
      !requestedCompanyId ||
      !canChange ||
      supplier.company !== requestedCompanyId
    )
      return;

    const action = supplier.status === "active" ? "delete" : "activate";
    setChangingStatus(true);
    setPageError("");
    setSuccess("");
    try {
      if (action === "delete") await http.delete(`suppliers/${supplier.id}/`);
      else await http.post(`suppliers/${supplier.id}/activate/`);
      if (companyIdRef.current !== requestedCompanyId) return;
      setConfirming(null);
      setSuccess(
        `Fornecedor ${action === "activate" ? "ativado" : "excluído"} com sucesso.`,
      );
      await load(undefined, requestedCompanyId, appliedFilters);
    } catch (caught) {
      if (companyIdRef.current !== requestedCompanyId) return;
      setConfirming(null);
      setPageError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível alterar o status do fornecedor.",
      );
    } finally {
      if (companyIdRef.current === requestedCompanyId)
        setChangingStatus(false);
    }
  }

  function supplierActions(supplier: Supplier) {
    return (
      <div className="flex justify-end gap-1">
        <button
          type="button"
          className="icon-button"
          disabled={!canChange}
          title={canChange ? "Editar fornecedor" : "Sem permissão para editar"}
          aria-label={`Editar ${supplierName(supplier)}`}
          onClick={() => openEdit(supplier)}
        >
          <Pencil className="size-4" />
        </button>
        <button
          type="button"
          className={`icon-button ${supplier.status === "active" ? "hover:bg-danger/10 hover:text-danger" : "hover:bg-success/10 hover:text-success"}`}
          disabled={!canChange}
          title={
            canChange
              ? supplier.status === "active"
                ? "Inativar fornecedor"
                : "Ativar fornecedor"
              : "Sem permissão para alterar o status"
          }
          aria-label={`${supplier.status === "active" ? "Inativar" : "Ativar"} ${supplierName(supplier)}`}
          onClick={() => setConfirming(supplier)}
        >
          <Power className="size-4" />
        </button>
      </div>
    );
  }

  const hasFilters = Boolean(appliedFilters.search || appliedFilters.status);

  return (
    <>
      <PageHeader
        title="Fornecedores"
        description={`Cadastro comercial de ${currentCompany?.trade_name || "sua empresa"}.`}
        action={
          <Button
            onClick={openCreate}
            disabled={!canChange || !currentCompany}
            title={
              canChange
                ? "Novo fornecedor"
                : "Sem permissão para alterar fornecedores"
            }
          >
            <Plus className="size-4" />
            Novo fornecedor
          </Button>
        }
      />

      <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        {pageError && <Alert message={pageError} />}
        {success && <Alert type="success" message={success} />}

        <form
          className="card grid gap-3 p-4 sm:grid-cols-[minmax(0,1fr)_12rem_auto_auto]"
          onSubmit={applyFilters}
        >
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-3 size-4 text-slate-400" />
            <Input
              className="pl-9"
              aria-label="Buscar fornecedores"
              placeholder="Nome, CPF/CNPJ, contato, telefone ou e-mail"
              value={draftFilters.search}
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  search: event.target.value,
                }))
              }
            />
          </div>
          <Select
            aria-label="Status do fornecedor"
            value={draftFilters.status}
            onChange={(event) =>
              setDraftFilters((current) => ({
                ...current,
                status: event.target.value,
              }))
            }
          >
            <option value="">Todos os status</option>
            <option value="active">Ativos</option>
            <option value="inactive">Inativos</option>
          </Select>
          <Button type="button" variant="secondary" onClick={clearFilters}>
            Limpar
          </Button>
          <Button type="submit">
            <SlidersHorizontal className="size-4" />
            Aplicar
          </Button>
        </form>

        <section className="card overflow-hidden">
          <div className="card-header">
            <div>
              <h2 className="text-sm font-bold">Fornecedores cadastrados</h2>
              <p className="mt-1 text-[11px] text-muted">
                Vínculos exclusivos da Company atual
              </p>
            </div>
            <Truck className="size-5 text-slate-300" />
          </div>

          {loading ? (
            <TableLoading columns={6} />
          ) : data?.results.length ? (
            <>
              <div className="divide-y divide-subtle md:hidden">
                {data.results.map((supplier) => (
                  <article key={supplier.id} className="space-y-3 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <strong className="block truncate text-sm">
                          {supplierName(supplier)}
                        </strong>
                        <span className="mt-0.5 block truncate text-[11px] text-muted">
                          {supplier.legal_name}
                        </span>
                      </div>
                      <StatusBadge active={supplier.status === "active"} />
                    </div>
                    <dl className="space-y-2 text-xs text-muted">
                      <div className="flex gap-2">
                        <dt className="font-semibold text-fg">CPF/CNPJ:</dt>
                        <dd>{supplier.tax_id ? formatTaxId(supplier.tax_id) : "Não informado"}</dd>
                      </div>
                      <div className="flex items-start gap-2">
                        <MapPin className="mt-0.5 size-3.5 shrink-0 text-primary" />
                        <dd>{addressText(supplier.address)}</dd>
                      </div>
                      {(supplier.phone || supplier.email) && (
                        <div className="flex flex-wrap gap-x-4 gap-y-1">
                          {supplier.phone && (
                            <span className="flex items-center gap-1.5">
                              <Phone className="size-3.5" /> {supplier.phone}
                            </span>
                          )}
                          {supplier.email && (
                            <span className="flex min-w-0 items-center gap-1.5">
                              <Mail className="size-3.5 shrink-0" />
                              <span className="truncate">{supplier.email}</span>
                            </span>
                          )}
                        </div>
                      )}
                    </dl>
                    <div className="border-t border-subtle pt-2">
                      {supplierActions(supplier)}
                    </div>
                  </article>
                ))}
              </div>

              <div className="table-wrap hidden md:block">
                <table className="data-table min-w-225">
                  <thead>
                    <tr>
                      <th>Fornecedor</th>
                      <th>CPF/CNPJ</th>
                      <th>Contato</th>
                      <th>Endereço</th>
                      <th>Status</th>
                      <th className="text-right">Ações</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.results.map((supplier) => (
                      <tr key={supplier.id}>
                        <td>
                          <strong className="block">
                            {supplierName(supplier)}
                          </strong>
                          <span className="mt-0.5 block max-w-64 truncate text-[11px] text-muted">
                            {supplier.legal_name}
                          </span>
                        </td>
                        <td>{supplier.tax_id ? formatTaxId(supplier.tax_id) : "-"}</td>
                        <td>
                          <span className="block font-medium">
                            {supplier.contact_name || "-"}
                          </span>
                          <span className="mt-0.5 block max-w-56 truncate text-[11px] text-muted">
                            {supplier.phone || supplier.email || "Sem contato informado"}
                          </span>
                        </td>
                        <td>
                          <span className="flex max-w-72 items-center gap-1.5 text-muted">
                            <MapPin className="size-3.5 shrink-0 text-primary" />
                            <span className="truncate">
                              {addressText(supplier.address)}
                            </span>
                          </span>
                        </td>
                        <td>
                          <StatusBadge active={supplier.status === "active"} />
                        </td>
                        <td>{supplierActions(supplier)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination
                count={data.count}
                next={data.next}
                previous={data.previous}
                onPage={(url) => void load(url, currentCompany?.id)}
              />
            </>
          ) : (
            <EmptyState
              title={
                hasFilters
                  ? "Nenhum fornecedor encontrado"
                  : "Nenhum fornecedor cadastrado"
              }
              description={
                hasFilters
                  ? "Revise a busca ou limpe os filtros para ver todos os fornecedores."
                  : "Cadastre o primeiro fornecedor da empresa para começar."
              }
            />
          )}
        </section>
      </div>

      <Modal
        open={open && canChange}
        title={editing ? "Editar fornecedor" : "Novo fornecedor"}
        description="O fornecedor ficará vinculado somente à Company atual."
        onClose={() => !saving && setOpen(false)}
        size="xl"
      >
        <form onSubmit={submit}>
          <div className="grid gap-5 p-5 sm:grid-cols-2 sm:p-6 lg:grid-cols-3">
            {formError && (
              <div className="sm:col-span-2 lg:col-span-3">
                <Alert message={formError} />
              </div>
            )}

            <Field label="Empresa" error={fieldError(fields, "company")}>
              <Input
                value={currentCompany?.trade_name || ""}
                disabled
                aria-describedby="supplier-company-help"
              />
              <span
                id="supplier-company-help"
                className="mt-1 block text-[10px] text-muted"
              >
                Definida pela Company selecionada no topo.
              </span>
            </Field>
            <Field
              label="Razão social"
              optional
              error={fieldError(fields, "legal_name")}
            >
              <Input
                maxLength={200}
                value={form.legal_name}
                onChange={(event) => update("legal_name", event.target.value)}
                disabled={saving || !canChange}
              />
            </Field>
            <Field
              label="Nome fantasia"
              error={fieldError(fields, "trade_name")}
            >
              <Input
                required
                maxLength={200}
                value={form.trade_name}
                onChange={(event) => update("trade_name", event.target.value)}
                disabled={saving || !canChange}
              />
            </Field>
            <Field
              label="CPF/CNPJ"
              optional
              error={fieldError(fields, "tax_id")}
            >
              <Input
                inputMode="numeric"
                autoComplete="off"
                maxLength={18}
                placeholder="000.000.000-00 ou 00.000.000/0000-00"
                value={form.tax_id}
                onChange={(event) =>
                  update("tax_id", formatTaxId(event.target.value))
                }
                disabled={saving || !canChange}
              />
            </Field>
            <Field
              label="Nome do contato"
              optional
              error={fieldError(fields, "contact_name")}
            >
              <Input
                maxLength={150}
                value={form.contact_name}
                onChange={(event) =>
                  update("contact_name", event.target.value)
                }
                disabled={saving || !canChange}
              />
            </Field>
            <Field
              label="Telefone"
              optional
              error={fieldError(fields, "phone")}
            >
              <Input
                type="tel"
                maxLength={30}
                value={form.phone}
                onChange={(event) => update("phone", event.target.value)}
                disabled={saving || !canChange}
              />
            </Field>
            <Field
              label="E-mail"
              optional
              error={fieldError(fields, "email")}
            >
              <Input
                type="email"
                maxLength={254}
                value={form.email}
                onChange={(event) => update("email", event.target.value)}
                disabled={saving || !canChange}
              />
            </Field>
            <div className="sm:col-span-2 lg:col-span-2">
              <Field
                label="Observações"
                optional
                error={fieldError(fields, "notes")}
              >
                <Textarea
                  rows={3}
                  value={form.notes}
                  onChange={(event) => update("notes", event.target.value)}
                  disabled={saving || !canChange}
                />
              </Field>
            </div>

            <div className="border-t border-subtle pt-4 sm:col-span-2 lg:col-span-3">
              <label className="flex cursor-pointer items-start gap-3">
                <input
                  type="checkbox"
                  className="mt-0.5 size-4 accent-primary"
                  checked={addressEnabled}
                  onChange={(event) => {
                    setAddressEnabled(event.target.checked);
                    setZipCodeError("");
                    setZipLookupEnabled(false);
                  }}
                  disabled={saving || !canChange}
                />
                <span>
                  <strong className="flex items-center gap-2 text-xs">
                    <MapPin className="size-4 text-primary" />
                    Informar endereço
                  </strong>
                  <small className="mt-1 block text-[11px] text-muted">
                    Opcional. Consulte o CEP pelo ViaCEP ou preencha os campos
                    manualmente.
                  </small>
                </span>
              </label>
              {fieldError(fields, "address") && (
                <p className="field-error">
                  {fieldError(fields, "address")}
                </p>
              )}
            </div>

            {addressEnabled && (
              <>
                <Field
                  label="CEP"
                  error={
                    fieldError(fields, "address.zip_code") || zipCodeError
                  }
                >
                  <Input
                    required
                    inputMode="numeric"
                    autoComplete="postal-code"
                    maxLength={9}
                    pattern="[0-9]{5}-?[0-9]{3}"
                    placeholder="00000-000"
                    value={form.address.zip_code}
                    onChange={(event) => {
                      setZipLookupEnabled(true);
                      updateAddress(
                        "zip_code",
                        formatZipCode(event.target.value),
                      );
                    }}
                    disabled={saving || !canChange}
                  />
                  {zipCodeLoading && (
                    <span className="mt-1.5 flex items-center gap-1.5 text-[11px] text-primary">
                      <Spinner className="size-3" />
                      Consultando CEP...
                    </span>
                  )}
                </Field>
                {(
                  [
                    ["street", "Logradouro", "address-line1"],
                    ["number", "Número", "address-line2"],
                    ["complement", "Complemento", "address-line2"],
                    ["neighborhood", "Bairro", "address-level3"],
                    ["city", "Cidade", "address-level2"],
                    ["state", "Estado", "address-level1"],
                  ] as Array<[keyof Address, string, string]>
                ).map(([key, label, autoComplete]) => (
                  <Field
                    key={key}
                    label={label}
                    optional={key === "complement"}
                    error={fieldError(fields, `address.${key}`)}
                  >
                    <Input
                      required={key !== "complement"}
                      maxLength={key === "state" ? 2 : undefined}
                      autoComplete={autoComplete}
                      value={form.address[key] || ""}
                      onChange={(event) =>
                        updateAddress(
                          key,
                          key === "state"
                            ? event.target.value.toUpperCase()
                            : event.target.value,
                        )
                      }
                      disabled={saving || !canChange}
                    />
                  </Field>
                ))}
              </>
            )}
          </div>

          {editing && (
            <section className="rounded-lg border border-slate-200">
              <div className="border-b border-slate-100 px-4 py-3">
                <h3 className="text-xs font-bold">Produtos relacionados</h3>
              </div>
              {loadingProducts ? (
                <p className="p-4 text-xs text-slate-400">Carregando...</p>
              ) : relatedProducts.length ? (
                <div className="divide-y divide-slate-100">
                  {relatedProducts.map((relation) => (
                    <div key={relation.id} className="grid gap-1 px-4 py-3 text-xs sm:grid-cols-[1fr_8rem_auto] sm:items-center">
                      <strong>{relation.product_name}</strong>
                      <span className="text-slate-500">{relation.supplier_code || "Sem código"}</span>
                      <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${relation.is_preferred ? "bg-primary/10 text-primary" : "bg-slate-100 text-slate-500"}`}>
                        {relation.is_preferred ? "Preferencial" : "Vinculado"}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="p-4 text-xs text-slate-400">
                  Nenhum produto vinculado a este fornecedor. O vínculo pode ser feito na página do produto.
                </p>
              )}
            </section>
          )}

          <div className="flex justify-end gap-2 border-t border-subtle px-5 py-4 sm:px-6">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setOpen(false)}
              disabled={saving}
            >
              Cancelar
            </Button>
            <Button type="submit" loading={saving} disabled={!canChange}>
              {editing ? "Salvar alterações" : "Criar fornecedor"}
            </Button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        open={!!confirming && canChange}
        title={`${confirming?.status === "active" ? "Excluir" : "Ativar"} fornecedor`}
        message={`Confirma ${confirming?.status === "active" ? "a exclusão de" : "a ativação de"} “${confirming ? supplierName(confirming) : ""}”? O histórico será preservado.`}
        confirmLabel={confirming?.status === "active" ? "Excluir" : "Ativar"}
        danger={confirming?.status === "active"}
        loading={changingStatus}
        onClose={() => !changingStatus && setConfirming(null)}
        onConfirm={changeStatus}
      />
    </>
  );
}

export default function SuppliersPage() {
  return (
    <AdminGuard requiredPermissions={[permissions.viewSupplier]}>
      <Suppliers />
    </AdminGuard>
  );
}
