"use client";

import { useEffect, useEffectEvent, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  GitBranch,
  MapPin,
  Pencil,
  Plus,
  Printer,
  Power,
  Settings2,
} from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import { PrinterManagement } from "@/components/printer-management";
import {
  Alert,
  Button,
  ConfirmDialog,
  EmptyState,
  Field,
  Input,
  Modal,
  MoneyInput,
  Pagination,
  Select,
  Spinner,
  StatusBadge,
  TableLoading,
} from "@/components/ui";
import { fieldError, formatDate, formatEditableDecimal } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import {
  formatZipCode,
  lookupAddressByZipCode,
  ViaCepError,
  zipCodeDigits,
} from "@/lib/viacep";
import { useAuth } from "@/providers/auth-provider";
import type {
  Address,
  Branch,
  BranchPayload,
  BranchSettings,
  Paginated,
} from "@/types";

type BusinessOverview = {
  company: { id: number; trade_name: string; status: "active" | "inactive" };
  counts: {
    branches: number;
    products: number;
    active_users: number;
    printer_devices: number;
  };
};

const emptyAddress: Address = {
  zip_code: "",
  street: "",
  number: "",
  complement: "",
  neighborhood: "",
  city: "",
  state: "",
};

const emptyForm: BranchPayload = {
  company: 0,
  name: "",
  cnpj: null,
  phone: "",
  email: "",
  address: emptyAddress,
};

function addressText(address: Branch["address"]) {
  if (!address) return "Não informado";
  if (typeof address === "string") return address;
  return (
    [address.street, address.number, address.city, address.state]
      .filter(Boolean)
      .join(", ") || "Não informado"
  );
}

function BranchesAdministration() {
  const router = useRouter();
  const { user, currentCompany, hasPermission, setCurrentBranchId, refreshUser } = useAuth();
  const canAdd = hasPermission(permissions.addBranch);
  const canChange = hasPermission(permissions.changeBranch);
  const canSettings = hasPermission(permissions.changeBranchSettings);
  const canManagePrinters = hasPermission(permissions.managePrinters);
  const canChangeCommission = hasPermission(permissions.changeBranchCommission);
  const [data, setData] = useState<Paginated<Branch> | null>(null);
  const [overview, setOverview] = useState<BusinessOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Branch | null>(null);
  const [form, setForm] = useState<BranchPayload>(emptyForm);
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState<Branch | null>(null);
  const [changingStatus, setChangingStatus] = useState(false);
  const [zipCodeLoading, setZipCodeLoading] = useState(false);
  const [zipCodeError, setZipCodeError] = useState("");
  const [zipLookupEnabled, setZipLookupEnabled] = useState(false);
  const [settingsBranch, setSettingsBranch] = useState<Branch | null>(null);
  const [printersBranch, setPrintersBranch] = useState<Branch | null>(null);
  const [settings, setSettings] = useState<BranchSettings | null>(null);
  const [settingsFields, setSettingsFields] = useState<
    Record<string, string[]>
  >({});
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [negativeRecovery, setNegativeRecovery] = useState<{
    count: number;
    names: string[];
    legacy: boolean;
  } | null>(null);
  const companyContextRef = useRef<number | null>(null);
  companyContextRef.current = currentCompany?.id || null;

  async function load(path?: string, companyId = currentCompany?.id) {
    if (!companyId) {
      setData(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const response = await http.get<Paginated<Branch>>(path || `branches/?company=${companyId}`);
      if (response.results.some((branch) => branch.company !== companyId)) {
        throw new ApiError("A API retornou filiais fora da empresa selecionada.");
      }
      if (companyContextRef.current === companyId) setData(response);
    } catch (caught) {
      if (companyContextRef.current === companyId) setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível carregar as filiais.",
      );
    } finally {
      if (companyContextRef.current === companyId) setLoading(false);
    }
  }

  async function loadOverview(companyId = currentCompany?.id) {
    if (!companyId) {
      setOverview(null);
      return;
    }
    try {
      const response = await http.get<BusinessOverview>(
        `branches/overview/?company=${companyId}`,
      );
      if (companyContextRef.current === companyId) setOverview(response);
    } catch {
      if (companyContextRef.current === companyId) setOverview(null);
    }
  }

  const loadForCompany = useEffectEvent((companyId: number) => {
    void load(undefined, companyId);
  });

  useEffect(() => {
    setModalOpen(false);
    setSettingsBranch(null);
    setPrintersBranch(null);
    setConfirming(null);
    setData(null);
    setOverview(null);
    const companyId = currentCompany?.id;
    if (!companyId) {
      setLoading(false);
      return;
    }
    loadForCompany(companyId);
    void loadOverview(companyId);
  }, [currentCompany?.id]);

  useEffect(() => {
    const zipCode = zipCodeDigits(form.address.zip_code);
    if (!modalOpen || !zipLookupEnabled || zipCode.length !== 8) {
      setZipCodeLoading(false);
      setZipCodeError("");
      return;
    }

    const controller = new AbortController();
    const initialAddress = { ...form.address };
    const timeout = window.setTimeout(() => {
      setZipCodeLoading(true);
      setZipCodeError("");
      lookupAddressByZipCode(zipCode, controller.signal)
        .then((address) => {
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
          if (controller.signal.aborted) return;
          setZipCodeError(
            caught instanceof ViaCepError
              ? caught.message
              : "Não foi possível consultar o CEP. Preencha o endereço manualmente.",
          );
        })
        .finally(() => {
          if (!controller.signal.aborted) setZipCodeLoading(false);
        });
    }, 450);
    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [form.address.zip_code, modalOpen, zipLookupEnabled]);

  function normalizedAddress(branch: Branch): Address {
    if (branch.address && typeof branch.address === "object")
      return { ...emptyAddress, ...branch.address };
    return {
      ...emptyAddress,
      street: typeof branch.address === "string" ? branch.address : "",
    };
  }

  function openCreate() {
    if (!canAdd) return;
    setEditing(null);
    setForm({
      ...emptyForm,
      company: currentCompany?.id || 0,
      address: { ...emptyAddress },
    });
    setFields({});
    setError("");
    setZipCodeError("");
    setZipLookupEnabled(false);
    setModalOpen(true);
  }

  function openEdit(branch: Branch) {
    if (!canChange || branch.company !== currentCompany?.id) return;
    setEditing(branch);
    setForm({
      company: branch.company,
      name: branch.name,
      cnpj: branch.cnpj,
      phone: branch.phone || "",
      email: branch.email,
      address: normalizedAddress(branch),
    });
    setFields({});
    setError("");
    setZipCodeError("");
    setZipLookupEnabled(false);
    setModalOpen(true);
  }

  function update<K extends keyof BranchPayload>(
    key: K,
    value: BranchPayload[K],
  ) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function updateAddress(key: keyof Address, value: string) {
    setForm((current) => ({
      ...current,
      address: { ...current.address, [key]: value },
    }));
  }

  function updateZipCode(value: string) {
    setZipLookupEnabled(true);
    updateAddress("zip_code", formatZipCode(value));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!currentCompany || (editing ? !canChange || editing.company !== currentCompany.id : !canAdd)) return;
    setSaving(true);
    setFields({});
    setError("");
    setSuccess("");
    try {
      const addressEditable =
        !editing || user?.is_superuser || editing.address_pending;
      const payload = {
        ...form,
        cnpj: form.cnpj || null,
      } as Partial<BranchPayload>;
      if (!addressEditable) delete payload.address;
      if (editing) await http.patch(`branches/${editing.id}/?company=${currentCompany.id}`, payload);
      else await http.post(`branches/?company=${currentCompany.id}`, payload);
      setModalOpen(false);
      setSuccess(
        editing
          ? "Filial atualizada com sucesso."
          : "Filial criada e vinculada à empresa selecionada.",
      );
      await load();
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setFields(caught.fields);
      } else {
        setError("Não foi possível salvar a filial.");
      }
    } finally {
      setSaving(false);
    }
  }

  async function changeStatus() {
    if (!confirming || !canChange || confirming.company !== currentCompany?.id) return;
    setChangingStatus(true);
    setError("");
    setSuccess("");
    const action = confirming.status === "active" ? "deactivate" : "activate";
    try {
      await http.post(`branches/${confirming.id}/${action}/?company=${currentCompany?.id}`);
      setSuccess(
        `Filial ${action === "activate" ? "ativada" : "inativada"} com sucesso.`,
      );
      setConfirming(null);
      await refreshUser();
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

  async function openSettings(branch: Branch) {
    if (!canSettings || branch.company !== currentCompany?.id) return;
    setSettingsBranch(branch);
    setSettings(null);
    setSettingsFields({});
    setNegativeRecovery(null);
    setError("");
    setSettingsLoading(true);
    try {
      const nextSettings = await http.get<BranchSettings>(
        `branches/${branch.id}/settings/?company=${currentCompany?.id}`,
      );
       setSettings({
         ...nextSettings,
         command_consumption_limit: nextSettings.command_consumption_limit === null ? null : formatEditableDecimal(nextSettings.command_consumption_limit),
         table_consumption_limit: nextSettings.table_consumption_limit === null ? null : formatEditableDecimal(nextSettings.table_consumption_limit),
         service_fee_rate: formatEditableDecimal(nextSettings.service_fee_rate),
         ...(nextSettings.commission_rate === undefined ? {} : { commission_rate: formatEditableDecimal(nextSettings.commission_rate) }),
         fixed_daily_cost: formatEditableDecimal(nextSettings.fixed_daily_cost),
       });
      if (nextSettings.negative_stock_state === "legacy_inconsistent") {
        setNegativeRecovery({
          count: nextSettings.negative_stock_count,
          names: [],
          legacy: true,
        });
      }
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível carregar as configurações da filial.",
      );
      setSettingsBranch(null);
    } finally {
      setSettingsLoading(false);
    }
  }

  async function saveSettings(event: React.FormEvent) {
    event.preventDefault();
    if (!settingsBranch || !settings || !canSettings || settingsBranch.company !== currentCompany?.id) return;
    setSettingsSaving(true);
    setSettingsFields({});
    setError("");
    try {
      setSettings(
        await http.patch<BranchSettings>(
          `branches/${settingsBranch.id}/settings/?company=${currentCompany?.id}`,
          {
            allow_negative_stock: settings.allow_negative_stock,
            service_fee_rate: settings.service_fee_rate,
            commission_rate: settings.commission_rate,
            fixed_daily_cost: settings.fixed_daily_cost,
            uses_tables: settings.uses_tables,
            uses_commands: settings.uses_commands,
            uses_counter: settings.uses_counter,
            uses_consumption: settings.uses_consumption,
            uses_cash_register: settings.uses_cash_register,
            charges_service_fee: settings.charges_service_fee,
          },
        ),
      );
      setSettingsBranch(null);
      setSuccess("Configurações da filial salvas com sucesso.");
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setSettingsFields(caught.fields);
        if (caught.code === "negative_stocks_must_be_regularized") {
          setSettingsFields((current) => ({
            ...current,
            allow_negative_stock: [
              "Use o fluxo Regularizar negativos na tela de Estoque.",
            ],
          }));
          const stocks = Array.isArray(caught.details.stocks)
            ? (caught.details.stocks as Array<Record<string, unknown>>)
            : [];
          setNegativeRecovery({
            count:
              typeof caught.details.count === "number"
                ? caught.details.count
                : stocks.length,
            names: stocks
              .map((stock) => String(stock.product__name || ""))
              .filter(Boolean),
            legacy: false,
          });
        }
      } else setError("Não foi possível salvar as configurações da filial.");
    } finally {
      setSettingsSaving(false);
    }
  }

  function startNegativeRecovery() {
    if (!settingsBranch || settingsBranch.company !== currentCompany?.id) return;
    setCurrentBranchId(settingsBranch.id);
    router.push(
      `/estoque/regularizar?branch=${settingsBranch.id}${negativeRecovery?.legacy ? "&legacy=true" : ""}`,
    );
  }

  function openPrinters(branch: Branch) {
    const targetAccess = user?.branches.find((item) => item.id === branch.id);
    if (
      branch.company !== currentCompany?.id ||
      branch.status !== "active" ||
      !targetAccess ||
      !targetAccess.permissions.includes(permissions.managePrinters)
    ) return;
    setCurrentBranchId(branch.id);
    setPrintersBranch(branch);
  }

  return (
    <>
      <PageHeader
        title="Meu negócio"
        description={currentCompany ? `Empresa atual: ${currentCompany.trade_name}` : "Selecione uma empresa para consultar suas filiais."}
        action={
          <Button
            onClick={openCreate}
            disabled={!canAdd || !currentCompany}
            title={!canAdd ? "Sem permissão para criar filiais" : "Nova filial"}
          >
            <Plus className="size-4" />
            Nova filial
          </Button>
        }
      />
      <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        {error && !modalOpen && <Alert message={error} />}
        {success && <Alert type="success" message={success} />}
        {!currentCompany && !loading && (
          <Alert message="Selecione uma empresa no topo para consultar e administrar suas filiais." />
        )}
        {overview && (
          <section className="card grid gap-4 p-5 sm:grid-cols-2 xl:grid-cols-5">
            <div className="sm:col-span-2 xl:col-span-1">
              <span className="label">Empresa</span>
              <strong className="block text-lg">{overview.company.trade_name}</strong>
              <StatusBadge active={overview.company.status === "active"} />
            </div>
            <div><span className="label">Produtos</span><strong className="block text-2xl">{overview.counts.products}</strong></div>
            <div><span className="label">Usuários ativos</span><strong className="block text-2xl">{overview.counts.active_users}</strong></div>
            <div><span className="label">Dispositivos</span><strong className="block text-2xl">{overview.counts.printer_devices}</strong></div>
            <div><span className="label">Filiais</span><strong className="block text-2xl">{overview.counts.branches}</strong></div>
          </section>
        )}
        <section className="card overflow-hidden">
          <div className="card-header">
            <div>
              <h2 className="text-sm font-bold">{currentCompany ? `Unidades de ${currentCompany.trade_name}` : "Unidades da empresa"}</h2>
              <p className="mt-1 text-[11px] text-slate-500">
                Unidades e empresas responsáveis
              </p>
            </div>
            <GitBranch className="size-5 text-slate-300" />
          </div>
          {loading ? (
            <TableLoading />
          ) : data?.results.length ? (
            <>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Unidade</th>
                      <th>Empresa</th>
                      <th>Endereço</th>
                      <th>Status</th>
                      <th>Atualização</th>
                      <th className="text-right">Ações</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.results.map((branch) => (
                      <tr key={branch.id}>
                        <td>
                          <strong className="block">{branch.name}</strong>
                          <span className="mt-0.5 block text-[11px] text-slate-400">
                            {branch.cnpj || "CNPJ não informado"}
                          </span>
                        </td>
                        <td className="font-medium text-slate-600">
                          {branch.company_name}
                        </td>
                        <td>
                          <span className="flex max-w-64 items-center gap-1.5 text-slate-500">
                            <MapPin className="size-3.5 shrink-0 text-primary" />
                            <span className="truncate">
                              {addressText(branch.address)}
                            </span>
                          </span>
                        </td>
                        <td>
                          <StatusBadge active={branch.status === "active"} />
                        </td>
                        <td className="text-slate-500">
                          {formatDate(branch.updated_at)}
                        </td>
                        <td>
                          <div className="flex justify-end gap-1">
                            <button
                              className="icon-button"
                              disabled={
                                branch.company !== currentCompany?.id ||
                                branch.status !== "active" ||
                                !user?.branches.some((item) => item.id === branch.id && item.permissions.includes(permissions.managePrinters))
                              }
                              title={
                                canManagePrinters
                                  ? "Configurar impressoras desta filial"
                                  : "Sem permissão para gerenciar impressoras"
                              }
                              onClick={() => openPrinters(branch)}
                            >
                              <Printer className="size-4" />
                            </button>
                            <button
                              className="icon-button"
                              disabled={!canSettings || branch.company !== currentCompany?.id}
                              title={
                                canSettings
                                  ? "Configurações operacionais"
                                  : "Sem permissão para configurar filiais"
                              }
                              onClick={() => void openSettings(branch)}
                            >
                              <Settings2 className="size-4" />
                            </button>
                            <button
                              className="icon-button"
                              disabled={!canChange || branch.company !== currentCompany?.id}
                              title={
                                canChange
                                  ? "Editar"
                                  : "Sem permissão para editar filiais"
                              }
                              onClick={() => openEdit(branch)}
                            >
                              <Pencil className="size-4" />
                            </button>
                            <button
                              disabled={!canChange || branch.company !== currentCompany?.id}
                              className={`icon-button ${branch.status === "active" ? "hover:bg-danger/10 hover:text-danger" : "hover:bg-success/10 hover:text-success"}`}
                              title={
                                canChange
                                  ? branch.status === "active"
                                    ? "Inativar"
                                    : "Ativar"
                                  : "Sem permissão para alterar filiais"
                              }
                              onClick={() => canChange && setConfirming(branch)}
                            >
                              <Power className="size-4" />
                            </button>
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
              title="Nenhuma filial cadastrada"
              description={currentCompany ? `Nenhuma filial encontrada para ${currentCompany.trade_name}.` : "Selecione uma empresa para continuar."}
            />
          )}
        </section>
      </div>

      <Modal
        open={modalOpen}
        title={editing ? "Editar filial" : "Nova filial"}
        description="Os dados serão vinculados à empresa selecionada."
        onClose={() => !saving && setModalOpen(false)}
        size="xl"
      >
        <form onSubmit={submit}>
          <div className="grid gap-5 p-5 sm:grid-cols-2 sm:p-6 lg:grid-cols-3">
            <div className="sm:col-span-2 lg:col-span-3">
              {error && <Alert message={error} />}
            </div>
            <Field label="Empresa" error={fieldError(fields, "company")}>
              <Select
                required
                value={form.company || ""}
                onChange={(event) =>
                  update("company", Number(event.target.value))
                }
                disabled={saving || !!editing}
              >
                <option value="" disabled>
                  Selecione uma empresa
                </option>
                {currentCompany && <option value={currentCompany.id}>{currentCompany.trade_name}</option>}
              </Select>
            </Field>
            <Field label="Nome da filial" error={fieldError(fields, "name")}>
              <Input
                required
                value={form.name}
                onChange={(event) => update("name", event.target.value)}
                disabled={saving}
              />
            </Field>
            <Field label="CNPJ" optional error={fieldError(fields, "cnpj")}>
              <Input
                value={form.cnpj || ""}
                onChange={(event) => update("cnpj", event.target.value)}
                disabled={saving}
                placeholder="00.000.000/0000-00"
              />
            </Field>
            <Field label="E-mail" error={fieldError(fields, "email")}>
              <Input
                type="email"
                required
                value={form.email}
                onChange={(event) => update("email", event.target.value)}
                disabled={saving}
              />
            </Field>
            <Field
              label="Telefone"
              optional
              error={fieldError(fields, "phone")}
            >
              <Input
                type="tel"
                value={form.phone}
                onChange={(event) => update("phone", event.target.value)}
                disabled={saving}
              />
            </Field>
            <div className="hidden lg:block" />

            <div className="border-t border-slate-100 pt-4 sm:col-span-2 lg:col-span-3">
              <h3 className="text-xs font-bold text-dark">Endereço</h3>
              {editing && !user?.is_superuser && !editing.address_pending && (
                <p className="mt-1 text-[11px] text-slate-500">
                  Endereço concluído. Alterações posteriores são exclusivas do
                  superusuário da plataforma.
                </p>
              )}
              {editing?.address_pending && (
                <p className="mt-1 text-[11px] font-semibold text-warning-strong">
                  Complete o endereço inicial da Matriz. Após salvar, ele se
                  tornará somente leitura.
                </p>
              )}
              {fieldError(fields, "address") && (
                <p className="field-error">{fieldError(fields, "address")}</p>
              )}
            </div>
            <Field
              label="CEP"
              error={fieldError(fields, "address.zip_code") || zipCodeError}
            >
              <Input
                required
                inputMode="numeric"
                autoComplete="postal-code"
                maxLength={9}
                pattern="[0-9]{5}-?[0-9]{3}"
                value={form.address.zip_code}
                onChange={(event) => updateZipCode(event.target.value)}
                disabled={
                  saving ||
                  (!!editing && !user?.is_superuser && !editing.address_pending)
                }
                placeholder="00000-000"
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
                ["street", "Logradouro"],
                ["number", "Número"],
                ["complement", "Complemento"],
                ["neighborhood", "Bairro"],
                ["city", "Cidade"],
                ["state", "Estado"],
              ] as Array<[keyof Address, string]>
            ).map(([key, label]) => (
              <Field
                key={key}
                label={label}
                optional={key === "complement"}
                error={fieldError(fields, `address.${key}`)}
              >
                <Input
                  required={key !== "complement"}
                  value={form.address[key] || ""}
                  onChange={(event) =>
                    updateAddress(
                      key,
                      key === "state"
                        ? event.target.value.toUpperCase()
                        : event.target.value,
                    )
                  }
                  disabled={
                    saving ||
                    (!!editing &&
                      !user?.is_superuser &&
                      !editing.address_pending)
                  }
                />
              </Field>
            ))}
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
              {editing ? "Salvar alterações" : "Criar filial"}
            </Button>
          </div>
        </form>
      </Modal>
      <Modal
        open={!!settingsBranch}
        title={`Configurações de ${settingsBranch?.name || "filial"}`}
        description="Defina as regras operacionais específicas desta unidade."
        onClose={() => !settingsSaving && setSettingsBranch(null)}
      >
        {settingsLoading || !settings ? (
          <div className="flex min-h-48 items-center justify-center text-primary">
            <Spinner className="size-6" />
          </div>
        ) : (
          <form onSubmit={saveSettings}>
            <div className="space-y-5 p-5 sm:p-6">
              {error && <Alert message={error} />}
              <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-slate-200 p-4">
                <input
                  type="checkbox"
                  className="mt-0.5 size-4 accent-primary"
                  checked={settings.allow_negative_stock}
                  onChange={(event) =>
                    setSettings((value) =>
                      value
                        ? {
                            ...value,
                            allow_negative_stock: event.target.checked,
                          }
                        : value,
                    )
                  }
                  disabled={settingsSaving}
                />
                <span>
                  <strong className="block text-xs">
                    Permitir estoque negativo
                  </strong>
                  <small className="mt-1 block text-[11px] text-slate-500">
                    Vendas e saídas poderão deixar o saldo abaixo de zero nesta
                    filial.
                  </small>
                </span>
              </label>
              {fieldError(settingsFields, "allow_negative_stock") && (
                <p className="field-error">
                  {fieldError(settingsFields, "allow_negative_stock")}
                </p>
              )}
              {negativeRecovery && (
                <div className="rounded-lg border border-warning/35 bg-warning/10 p-4 text-xs">
                  <strong className="block text-warning-strong">
                    {negativeRecovery.legacy
                      ? "Recuperação de estado legado"
                      : "Desativação bloqueada"}
                  </strong>
                  <p className="mt-1 text-muted">
                    {negativeRecovery.count}{" "}
                    {negativeRecovery.count === 1
                      ? "produto possui"
                      : "produtos possuem"}{" "}
                    saldo negativo.{" "}
                    {negativeRecovery.names.length
                      ? `Afetados: ${negativeRecovery.names.slice(0, 5).join(", ")}${negativeRecovery.names.length > 5 ? "…" : ""}.`
                      : "Abra a lista para revisar os afetados."}
                  </p>
                  <Button
                    type="button"
                    variant="secondary"
                    className="mt-3"
                    onClick={startNegativeRecovery}
                  >
                    Ver produtos e regularizar
                  </Button>
                </div>
              )}
              <div className="rounded-lg border border-slate-200 p-4">
                <strong className="block text-xs">Operação</strong>
                <small className="mt-1 block text-[11px] text-slate-500">Ative ou desative recursos desta filial.</small>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <label className="flex items-center gap-2 text-xs">
                    <input type="checkbox" className="size-4 accent-primary" checked={settings.uses_tables ?? false} onChange={(event) => setSettings((value) => value ? { ...value, uses_tables: event.target.checked } : value)} disabled={settingsSaving} />
                    Mesas
                  </label>
                  <label className="flex items-center gap-2 text-xs">
                    <input type="checkbox" className="size-4 accent-primary" checked={settings.uses_commands ?? false} onChange={(event) => setSettings((value) => value ? { ...value, uses_commands: event.target.checked } : value)} disabled={settingsSaving} />
                    Comandas
                  </label>
                  <label className="flex items-center gap-2 text-xs">
                    <input type="checkbox" className="size-4 accent-primary" checked={settings.uses_counter ?? true} onChange={(event) => setSettings((value) => value ? { ...value, uses_counter: event.target.checked } : value)} disabled={settingsSaving} />
                    Balcão
                  </label>
                  <label className="flex items-center gap-2 text-xs">
                    <input type="checkbox" className="size-4 accent-primary" checked={settings.uses_consumption ?? true} onChange={(event) => setSettings((value) => value ? { ...value, uses_consumption: event.target.checked } : value)} disabled={settingsSaving} />
                    Consumação
                  </label>
                  <label className="flex items-center gap-2 text-xs">
                    <input type="checkbox" className="size-4 accent-primary" checked={settings.uses_cash_register ?? true} onChange={(event) => setSettings((value) => value ? { ...value, uses_cash_register: event.target.checked } : value)} disabled={settingsSaving} />
                    Caixa
                  </label>
                  <label className="flex items-center gap-2 text-xs">
                    <input type="checkbox" className="size-4 accent-primary" checked={settings.charges_service_fee ?? false} onChange={(event) => setSettings((value) => value ? { ...value, charges_service_fee: event.target.checked } : value)} disabled={settingsSaving} />
                    Cobra taxa de serviço
                  </label>
                </div>
              </div>
              <div className="rounded-lg border border-slate-200 p-4"><strong className="block text-xs">Mesas e limites de consumo</strong><div className="mt-3 grid gap-3 sm:grid-cols-3"><Field label="Mesas no lote padrão"><Input type="number" min="1" max="500" value={settings.default_table_quantity} onChange={(event) => setSettings((value) => value ? { ...value, default_table_quantity: Number(event.target.value) } : value)} disabled={settingsSaving} /></Field><Field label="Lugares padrão"><Input type="number" min="0" value={settings.default_table_seats} onChange={(event) => setSettings((value) => value ? { ...value, default_table_seats: Number(event.target.value) } : value)} disabled={settingsSaving} /></Field><Field label="Prefixo padrão"><Input value={settings.default_table_prefix} onChange={(event) => setSettings((value) => value ? { ...value, default_table_prefix: event.target.value } : value)} disabled={settingsSaving} /></Field></div><label className="mt-4 flex items-center gap-2 text-xs"><input type="checkbox" className="size-4 accent-primary" checked={settings.consumption_limit_enabled} onChange={(event) => setSettings((value) => value ? { ...value, consumption_limit_enabled: event.target.checked } : value)} disabled={settingsSaving} />Habilitar limite de consumo confirmado</label>{settings.consumption_limit_enabled && <div className="mt-3 grid gap-3 sm:grid-cols-2"><Field label="Limite por comanda (R$)" optional><Input inputMode="decimal" value={settings.command_consumption_limit || ""} onChange={(event) => setSettings((value) => value ? { ...value, command_consumption_limit: event.target.value || null } : value)} disabled={settingsSaving} /></Field><Field label="Limite agregado por mesa (R$)" optional><Input inputMode="decimal" value={settings.table_consumption_limit || ""} onChange={(event) => setSettings((value) => value ? { ...value, table_consumption_limit: event.target.value || null } : value)} disabled={settingsSaving} /></Field></div>}</div>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field
                  label="Taxa de serviço (%)"
                  error={fieldError(settingsFields, "service_fee_rate")}
                >
                  <Input
                    required
                    type="number"
                    min="0"
                    max="100"
                    step="0.01"
                    value={settings.service_fee_rate}
                    onChange={(event) =>
                      setSettings((value) =>
                        value
                          ? { ...value, service_fee_rate: event.target.value }
                          : value,
                      )
                    }
                    disabled={settingsSaving}
                  />
                </Field>
                <Field
                  label="Comissão padrão (%)"
                  error={fieldError(settingsFields, "commission_rate")}
                >
                  <Input
                    required
                    type="number"
                    min="0"
                    max="100"
                    step="0.01"
                    value={settings.commission_rate}
                    onChange={(event) =>
                      setSettings((value) =>
                        value
                          ? { ...value, commission_rate: event.target.value }
                          : value,
                      )
                    }
                    disabled={settingsSaving || !canChangeCommission}
                  />
                </Field>
              </div>
              <Field
                label="Custo fixo diário"
                error={fieldError(settingsFields, "fixed_daily_cost")}
              >
                <MoneyInput
                  required
                  value={settings.fixed_daily_cost}
                  onValueChange={(value) =>
                    setSettings((current) =>
                      current
                        ? { ...current, fixed_daily_cost: value }
                        : current,
                    )
                  }
                  disabled={settingsSaving}
                />
              </Field>
            </div>
            <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-4 sm:px-6">
              <Button
                type="button"
                variant="secondary"
                disabled={settingsSaving}
                onClick={() => setSettingsBranch(null)}
              >
                Cancelar
              </Button>
              <Button type="submit" loading={settingsSaving}>
                Salvar configurações
              </Button>
            </div>
          </form>
        )}
      </Modal>
      <Modal
        open={!!printersBranch}
        title={`Impressoras · ${printersBranch?.name || "filial"}`}
        description="Cadastre os setores de impressão desta filial sem precisar selecionar a unidade novamente."
        onClose={() => setPrintersBranch(null)}
        size="xxl"
        tall
      >
        <div className="p-5 sm:p-6">
          <PrinterManagement embedded />
        </div>
      </Modal>
      <ConfirmDialog
        open={!!confirming}
        title={`${confirming?.status === "active" ? "Inativar" : "Ativar"} filial`}
        message={`Confirma a alteração de status de “${confirming?.name || ""}”?`}
        confirmLabel={confirming?.status === "active" ? "Inativar" : "Ativar"}
        danger={confirming?.status === "active"}
        loading={changingStatus}
        onClose={() => !changingStatus && setConfirming(null)}
        onConfirm={changeStatus}
      />
    </>
  );
}

export default function BranchesPage() {
  const { currentCompany } = useAuth();
  if (!currentCompany) {
    return <>
      <PageHeader title="Meu negócio" description="Selecione uma empresa para consultar suas unidades." />
      <div className="p-4 sm:p-6 lg:p-8"><section className="card"><EmptyState title="Nenhuma empresa selecionada" description="Use o seletor no topo para escolher a empresa que deseja administrar." /></section></div>
    </>;
  }
  return (
    <AdminGuard
      requiredPermissions={[
        permissions.viewBranch,
        permissions.addBranch,
        permissions.changeBranch,
      ]}
    >
      <BranchesAdministration />
    </AdminGuard>
  );
}
