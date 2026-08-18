"use client";

import { useEffect, useState } from "react";
import { GitBranch, MapPin, Pencil, Plus, Power, Settings2 } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, ConfirmDialog, EmptyState, Field, Input, Modal, MoneyInput, Pagination, Select, Spinner, StatusBadge, TableLoading } from "@/components/ui";
import { fieldError, formatDate } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { formatZipCode, lookupAddressByZipCode, ViaCepError, zipCodeDigits } from "@/lib/viacep";
import { useAuth } from "@/providers/auth-provider";
import type { Address, Branch, BranchPayload, BranchSettings, Company, Paginated } from "@/types";

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
  return [address.street, address.number, address.city, address.state].filter(Boolean).join(", ") || "Não informado";
}

function BranchesAdministration() {
  const { user, currentCompany, hasPermission } = useAuth();
  const canAdd = hasPermission(permissions.addBranch);
  const canChange = hasPermission(permissions.changeBranch);
  const canSettings = hasPermission(permissions.changeBranchSettings);
  const canChangeCommission = hasPermission(permissions.changeBranchCommission);
  const [data, setData] = useState<Paginated<Branch> | null>(null);
  const [companies, setCompanies] = useState<Company[]>([]);
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
  const [settings, setSettings] = useState<BranchSettings | null>(null);
  const [settingsFields, setSettingsFields] = useState<Record<string, string[]>>({});
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [settingsSaving, setSettingsSaving] = useState(false);

  async function load(path = currentCompany ? `branches/?company=${currentCompany.id}` : "branches/") {
    setLoading(true);
    setError("");
    try {
      setData(await http.get<Paginated<Branch>>(path));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as filiais.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!currentCompany) return;
    void load(`branches/?company=${currentCompany.id}`);
    http.getAll<Company>("companies/")
      .then((items) => setCompanies(items.filter((company) => company.id === currentCompany.id)))
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as empresas."));
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
            if (zipCodeDigits(current.address.zip_code) !== zipCode) return current;
            const nextAddress = { ...current.address };
            for (const key of ["street", "complement", "neighborhood", "city", "state"] as const) {
              if (address[key] && current.address[key] === initialAddress[key]) {
                nextAddress[key] = address[key];
              }
            }
            return { ...current, address: nextAddress };
          });
        })
        .catch((caught) => {
          if (controller.signal.aborted) return;
          setZipCodeError(caught instanceof ViaCepError ? caught.message : "Não foi possível consultar o CEP. Preencha o endereço manualmente.");
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
    if (branch.address && typeof branch.address === "object") return { ...emptyAddress, ...branch.address };
    return { ...emptyAddress, street: typeof branch.address === "string" ? branch.address : "" };
  }

  function openCreate() {
    if (!canAdd) return;
    setEditing(null);
    setForm({ ...emptyForm, company: currentCompany?.id || companies[0]?.id || 0, address: { ...emptyAddress } });
    setFields({});
    setError("");
    setZipCodeError("");
    setZipLookupEnabled(false);
    setModalOpen(true);
  }

  function openEdit(branch: Branch) {
    if (!canChange) return;
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

  function update<K extends keyof BranchPayload>(key: K, value: BranchPayload[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function updateAddress(key: keyof Address, value: string) {
    setForm((current) => ({ ...current, address: { ...current.address, [key]: value } }));
  }

  function updateZipCode(value: string) {
    setZipLookupEnabled(true);
    updateAddress("zip_code", formatZipCode(value));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (editing ? !canChange : !canAdd) return;
    setSaving(true);
    setFields({});
    setError("");
    setSuccess("");
    try {
      const addressEditable = !editing || user?.is_superuser || editing.address_pending;
      const payload = { ...form, cnpj: form.cnpj || null } as Partial<BranchPayload>;
      if (!addressEditable) delete payload.address;
      if (editing) await http.patch(`branches/${editing.id}/`, payload);
      else await http.post("branches/", payload);
      setModalOpen(false);
      setSuccess(editing ? "Filial atualizada com sucesso." : "Filial criada e vinculada à empresa selecionada.");
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
    if (!confirming || !canChange) return;
    setChangingStatus(true);
    setError("");
    setSuccess("");
    const action = confirming.status === "active" ? "deactivate" : "activate";
    try {
      await http.post(`branches/${confirming.id}/${action}/`);
      setSuccess(`Filial ${action === "activate" ? "ativada" : "inativada"} com sucesso.`);
      setConfirming(null);
      await load();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível alterar o status.");
      setConfirming(null);
    } finally {
      setChangingStatus(false);
    }
  }

  async function openSettings(branch: Branch) {
    if (!canSettings) return;
    setSettingsBranch(branch);
    setSettings(null);
    setSettingsFields({});
    setError("");
    setSettingsLoading(true);
    try {
      setSettings(await http.get<BranchSettings>(`branches/${branch.id}/settings/`));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as configurações da filial.");
      setSettingsBranch(null);
    } finally {
      setSettingsLoading(false);
    }
  }

  async function saveSettings(event: React.FormEvent) {
    event.preventDefault();
    if (!settingsBranch || !settings || !canSettings) return;
    setSettingsSaving(true);
    setSettingsFields({});
    setError("");
    try {
      setSettings(await http.patch<BranchSettings>(`branches/${settingsBranch.id}/settings/`, {
        allow_negative_stock: settings.allow_negative_stock,
        service_fee_rate: settings.service_fee_rate,
        commission_rate: settings.commission_rate,
        fixed_daily_cost: settings.fixed_daily_cost,
      }));
      setSettingsBranch(null);
      setSuccess("Configurações da filial salvas com sucesso.");
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setSettingsFields(caught.fields);
        if (caught.code === "negative_stocks_must_be_regularized") {
          setSettingsFields((current) => ({ ...current, allow_negative_stock: ["Use o fluxo Regularizar negativos na tela de Estoque."] }));
        }
      } else setError("Não foi possível salvar as configurações da filial.");
    } finally {
      setSettingsSaving(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Filiais"
        description="Organize as unidades vinculadas a cada empresa."
        action={<Button onClick={openCreate} disabled={!canAdd || !companies.length} title={!canAdd ? "Sem permissão para criar filiais" : "Nova filial"}><Plus className="size-4" />Nova filial</Button>}
      />
      <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        {error && !modalOpen && <Alert message={error} />}
        {success && <Alert type="success" message={success} />}
        {!companies.length && !loading && <Alert message="Cadastre uma empresa antes de criar filiais." />}
        <section className="card overflow-hidden">
          <div className="card-header"><div><h2 className="text-sm font-bold">Filiais cadastradas</h2><p className="mt-1 text-[11px] text-slate-500">Unidades e empresas responsáveis</p></div><GitBranch className="size-5 text-slate-300" /></div>
          {loading ? <TableLoading /> : data?.results.length ? (
            <>
              <div className="table-wrap">
                <table className="data-table">
                  <thead><tr><th>Filial</th><th>Empresa</th><th>Endereço</th><th>Status</th><th>Atualização</th><th className="text-right">Ações</th></tr></thead>
                  <tbody>
                    {data.results.map((branch) => (
                      <tr key={branch.id}>
                        <td><strong className="block">{branch.name}</strong><span className="mt-0.5 block text-[11px] text-slate-400">{branch.cnpj || "CNPJ não informado"}</span></td>
                        <td className="font-medium text-slate-600">{branch.company_name}</td>
                        <td><span className="flex max-w-64 items-center gap-1.5 text-slate-500"><MapPin className="size-3.5 shrink-0 text-primary" /><span className="truncate">{addressText(branch.address)}</span></span></td>
                        <td><StatusBadge active={branch.status === "active"} /></td>
                        <td className="text-slate-500">{formatDate(branch.updated_at)}</td>
                        <td><div className="flex justify-end gap-1"><button className="icon-button" disabled={!canSettings} title={canSettings ? "Configurações operacionais" : "Sem permissão para configurar filiais"} onClick={() => void openSettings(branch)}><Settings2 className="size-4" /></button><button className="icon-button" disabled={!canChange} title={canChange ? "Editar" : "Sem permissão para editar filiais"} onClick={() => openEdit(branch)}><Pencil className="size-4" /></button><button disabled={!canChange} className={`icon-button ${branch.status === "active" ? "hover:bg-danger/10 hover:text-danger" : "hover:bg-success/10 hover:text-success"}`} title={canChange ? (branch.status === "active" ? "Inativar" : "Ativar") : "Sem permissão para alterar filiais"} onClick={() => canChange && setConfirming(branch)}><Power className="size-4" /></button></div></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination count={data.count} next={data.next} previous={data.previous} onPage={load} />
            </>
          ) : <EmptyState title="Nenhuma filial cadastrada" description="Selecione uma empresa e adicione uma unidade para começar." />}
        </section>
      </div>

      <Modal open={modalOpen} title={editing ? "Editar filial" : "Nova filial"} description="Os dados serão vinculados à empresa selecionada." onClose={() => !saving && setModalOpen(false)} size="xl">
        <form onSubmit={submit}>
          <div className="grid gap-5 p-5 sm:grid-cols-2 sm:p-6 lg:grid-cols-3">
            <div className="sm:col-span-2 lg:col-span-3">{error && <Alert message={error} />}</div>
            <Field label="Empresa" error={fieldError(fields, "company")}><Select required value={form.company || ""} onChange={(event) => update("company", Number(event.target.value))} disabled={saving || !!editing}><option value="" disabled>Selecione uma empresa</option>{companies.map((company) => <option key={company.id} value={company.id}>{company.trade_name}</option>)}</Select></Field>
            <Field label="Nome da filial" error={fieldError(fields, "name")}><Input required value={form.name} onChange={(event) => update("name", event.target.value)} disabled={saving} /></Field>
            <Field label="CNPJ" optional error={fieldError(fields, "cnpj")}><Input value={form.cnpj || ""} onChange={(event) => update("cnpj", event.target.value)} disabled={saving} placeholder="00.000.000/0000-00" /></Field>
            <Field label="E-mail" error={fieldError(fields, "email")}><Input type="email" required value={form.email} onChange={(event) => update("email", event.target.value)} disabled={saving} /></Field>
            <Field label="Telefone" optional error={fieldError(fields, "phone")}><Input type="tel" value={form.phone} onChange={(event) => update("phone", event.target.value)} disabled={saving} /></Field>
            <div className="hidden lg:block" />

            <div className="border-t border-slate-100 pt-4 sm:col-span-2 lg:col-span-3">
              <h3 className="text-xs font-bold text-dark">Endereço</h3>
              {editing && !user?.is_superuser && !editing.address_pending && <p className="mt-1 text-[11px] text-slate-500">Endereço concluído. Alterações posteriores são exclusivas do superusuário da plataforma.</p>}
              {editing?.address_pending && <p className="mt-1 text-[11px] font-semibold text-amber-700">Complete o endereço inicial da Matriz. Após salvar, ele se tornará somente leitura.</p>}
              {fieldError(fields, "address") && <p className="field-error">{fieldError(fields, "address")}</p>}
            </div>
            <Field label="CEP" error={fieldError(fields, "address.zip_code") || zipCodeError}>
              <Input required inputMode="numeric" autoComplete="postal-code" maxLength={9} pattern="[0-9]{5}-?[0-9]{3}" value={form.address.zip_code} onChange={(event) => updateZipCode(event.target.value)} disabled={saving || !!editing && !user?.is_superuser && !editing.address_pending} placeholder="00000-000" />
              {zipCodeLoading && <span className="mt-1.5 flex items-center gap-1.5 text-[11px] text-primary"><Spinner className="size-3" />Consultando CEP...</span>}
            </Field>
            {([['street','Logradouro'],['number','Número'],['complement','Complemento'],['neighborhood','Bairro'],['city','Cidade'],['state','Estado']] as Array<[keyof Address,string]>).map(([key,label]) => <Field key={key} label={label} optional={key === 'complement'} error={fieldError(fields, `address.${key}`)}><Input required={key !== 'complement'} value={form.address[key] || ""} onChange={(event) => updateAddress(key, key === 'state' ? event.target.value.toUpperCase() : event.target.value)} disabled={saving || !!editing && !user?.is_superuser && !editing.address_pending} /></Field>)}
          </div>
          <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-4 sm:px-6"><Button type="button" variant="secondary" disabled={saving} onClick={() => setModalOpen(false)}>Cancelar</Button><Button type="submit" loading={saving} disabled={editing ? !canChange : !canAdd}>{editing ? "Salvar alterações" : "Criar filial"}</Button></div>
        </form>
      </Modal>
      <Modal open={!!settingsBranch} title={`Configurações de ${settingsBranch?.name || "filial"}`} description="Defina as regras operacionais específicas desta unidade." onClose={() => !settingsSaving && setSettingsBranch(null)}>
        {settingsLoading || !settings ? <div className="flex min-h-48 items-center justify-center text-primary"><Spinner className="size-6" /></div> : (
          <form onSubmit={saveSettings}>
            <div className="space-y-5 p-5 sm:p-6">
              {error && <Alert message={error} />}
              <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-slate-200 p-4">
                 <input type="checkbox" className="mt-0.5 size-4 accent-primary" checked={settings.allow_negative_stock} onChange={(event) => setSettings((value) => value ? { ...value, allow_negative_stock: event.target.checked } : value)} disabled={settingsSaving} />
                 <span><strong className="block text-xs">Permitir estoque negativo</strong><small className="mt-1 block text-[11px] text-slate-500">Vendas e saídas poderão deixar o saldo abaixo de zero nesta filial.</small></span>
               </label>
              {fieldError(settingsFields, "allow_negative_stock") && <div><p className="field-error">{fieldError(settingsFields, "allow_negative_stock")}</p><a className="mt-2 inline-block text-xs font-bold text-primary" href="/estoque?state=negative&regularize=true">Regularizar negativos</a></div>}
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Taxa de serviço (%)" error={fieldError(settingsFields, "service_fee_rate")}><Input required type="number" min="0" max="100" step="0.01" value={settings.service_fee_rate} onChange={(event) => setSettings((value) => value ? { ...value, service_fee_rate: event.target.value } : value)} disabled={settingsSaving} /></Field>
                 <Field label="Comissão padrão (%)" error={fieldError(settingsFields, "commission_rate")}><Input required type="number" min="0" max="100" step="0.01" value={settings.commission_rate} onChange={(event) => setSettings((value) => value ? { ...value, commission_rate: event.target.value } : value)} disabled={settingsSaving || !canChangeCommission} /></Field>
              </div>
              <Field label="Custo fixo diário" error={fieldError(settingsFields, "fixed_daily_cost")}><MoneyInput required value={settings.fixed_daily_cost} onValueChange={(value) => setSettings((current) => current ? { ...current, fixed_daily_cost: value } : current)} disabled={settingsSaving} /></Field>
            </div>
            <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-4 sm:px-6"><Button type="button" variant="secondary" disabled={settingsSaving} onClick={() => setSettingsBranch(null)}>Cancelar</Button><Button type="submit" loading={settingsSaving}>Salvar configurações</Button></div>
          </form>
        )}
      </Modal>
      <ConfirmDialog open={!!confirming} title={`${confirming?.status === "active" ? "Inativar" : "Ativar"} filial`} message={`Confirma a alteração de status de “${confirming?.name || ""}”?`} confirmLabel={confirming?.status === "active" ? "Inativar" : "Ativar"} danger={confirming?.status === "active"} loading={changingStatus} onClose={() => !changingStatus && setConfirming(null)} onConfirm={changeStatus} />
    </>
  );
}

export default function BranchesPage() {
  return <AdminGuard requiredPermissions={[permissions.viewBranch, permissions.addBranch, permissions.changeBranch]}><BranchesAdministration /></AdminGuard>;
}
