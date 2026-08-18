"use client";

import { useEffect, useRef, useState } from "react";
import {
  KeyRound,
  Pencil,
  Plus,
  Power,
  Search,
  Shield,
  SlidersHorizontal,
  Users,
} from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { UserCommissionSection } from "@/components/user-commission-section";
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
import { fieldError, formatDate, initials } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type {
  AccessProfile,
  Branch,
  Paginated,
  User,
  UserPayload,
  UserType,
} from "@/types";

const userTypes: Array<[UserType, string]> = [
  ["employee", "Funcionário"],
  ["promoter", "Promoter"],
  ["dj", "DJ"],
  ["artist", "Artista"],
  ["other", "Outro"],
];
const blank = (): UserPayload => ({
  email: null,
  password: null,
  can_login: false,
  user_type: "employee",
  first_name: "",
  last_name: "",
  company_accesses: [],
});
const typeLabel = (value: UserType) =>
  userTypes.find(([key]) => key === value)?.[1] || value;
interface UserFilters {
  search: string;
  status: string;
  canLogin: string;
  userType: string;
  accessProfile: string;
  branch: string;
}
const emptyFilters = (): UserFilters => ({
  search: "",
  status: "",
  canLogin: "",
  userType: "",
  accessProfile: "",
  branch: "",
});

function UsersAdministration() {
  const { user: actor, currentCompany, hasPermission } = useAuth();
  const companies = actor?.companies || [];
  const canAdd = hasPermission(permissions.addUser);
  const canChange = hasPermission(permissions.changeUser);
  const canStatus = hasPermission(permissions.changeUserStatus);
  const contextRef = useRef(currentCompany?.id);
  contextRef.current = currentCompany?.id;
  const [data, setData] = useState<Paginated<User> | null>(null);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [profiles, setProfiles] = useState<Record<number, AccessProfile[]>>({});
  const [loading, setLoading] = useState(true);
  const [dependenciesLoading, setDependenciesLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const [form, setForm] = useState<UserPayload>(blank());
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState<User | null>(null);
  const [draftFilters, setDraftFilters] = useState<UserFilters>(emptyFilters);
  const [appliedFilters, setAppliedFilters] =
    useState<UserFilters>(emptyFilters);

  function listPath(companyId: number, selected: UserFilters) {
    const params = new URLSearchParams({ company: String(companyId) });
    if (selected.search.trim()) params.set("search", selected.search.trim());
    if (selected.status) params.set("status", selected.status);
    if (selected.canLogin) params.set("can_login", selected.canLogin);
    if (selected.userType) params.set("user_type", selected.userType);
    if (selected.accessProfile)
      params.set("access_profile", selected.accessProfile);
    if (selected.branch) params.set("branch", selected.branch);
    return `users/?${params}`;
  }

  async function load(
    path?: string,
    companyId = currentCompany?.id,
    selected = appliedFilters,
  ) {
    if (!companyId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const response = await http.get<Paginated<User>>(
        path || listPath(companyId, selected),
      );
      if (contextRef.current === companyId) setData(response);
    } catch (caught) {
      if (contextRef.current === companyId)
        setError(
          caught instanceof ApiError
            ? caught.message
            : "Não foi possível carregar os usuários.",
        );
    } finally {
      if (contextRef.current === companyId) setLoading(false);
    }
  }
  useEffect(() => {
    const companyId = currentCompany?.id;
    if (!companyId) return;
    let active = true;
    const cleared = emptyFilters();
    setDraftFilters(cleared);
    setAppliedFilters(cleared);
    setData(null);
    void load(undefined, companyId, cleared);
    setDependenciesLoading(true);
    Promise.all([
      http.getAll<Branch>("branches/"),
      ...companies.map((company) =>
        http.getAll<AccessProfile>(
          `access-profiles/?company=${company.id}&status=active`,
        ),
      ),
    ])
      .then(([branchItems, ...profileItems]) => {
        if (active && contextRef.current === companyId) {
          setBranches(branchItems);
          setProfiles(
            Object.fromEntries(
              companies.map((company, index) => [
                company.id,
                profileItems[index],
              ]),
            ),
          );
        }
      })
      .catch(
        (caught) =>
          active &&
          setError(
            caught instanceof ApiError
              ? caught.message
              : "Não foi possível carregar perfis e filiais.",
          ),
      )
      .finally(() => active && setDependenciesLoading(false));
    return () => {
      active = false;
    };
  }, [currentCompany?.id, companies.map((company) => company.id).join(",")]);

  function applyFilters(event: React.FormEvent) {
    event.preventDefault();
    setAppliedFilters(draftFilters);
    void load(undefined, currentCompany?.id, draftFilters);
  }

  function clearFilters() {
    const cleared = emptyFilters();
    setDraftFilters(cleared);
    setAppliedFilters(cleared);
    void load(undefined, currentCompany?.id, cleared);
  }

  function show(target?: User) {
    if (target ? !canChange : !canAdd) return;
    const accesses =
      target?.companies.map((company) => ({
        company_id: company.id,
        access_profile_id: company.access_profile?.id ?? null,
        branch_accesses: target.branches
          .filter(
            (branch) =>
              branch.company_id === company.id && branch.access_profile?.id,
          )
          .map((branch) => ({
            branch_id: branch.id,
            access_profile_id: branch.access_profile!.id!,
          })),
      })) || [];
    setEditing(target || null);
    setForm(
      target
        ? {
            email: target.email,
            password: null,
            can_login: target.can_login,
            user_type: target.user_type,
            first_name: target.first_name,
            last_name: target.last_name,
            company_accesses: accesses,
          }
        : {
            ...blank(),
            company_accesses: currentCompany
              ? [
                  {
                    company_id: currentCompany.id,
                    access_profile_id: null,
                    branch_accesses: [],
                  },
                ]
              : [],
          },
    );
    setFields({});
    setError("");
    setOpen(true);
  }
  function update<K extends keyof UserPayload>(key: K, value: UserPayload[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }
  function updateAccess(
    companyId: number,
    value: Partial<UserPayload["company_accesses"][number]>,
  ) {
    setForm((current) => ({
      ...current,
      company_accesses: current.company_accesses.map((item) =>
        item.company_id === companyId ? { ...item, ...value } : item,
      ),
    }));
  }
  function toggleCompany(companyId: number) {
    setForm((current) => ({
      ...current,
      company_accesses: current.company_accesses.some(
        (item) => item.company_id === companyId,
      )
        ? current.company_accesses.filter(
            (item) => item.company_id !== companyId,
          )
        : [
            ...current.company_accesses,
            {
              company_id: companyId,
              access_profile_id: null,
              branch_accesses: [],
            },
          ],
    }));
  }
  function toggleBranch(companyId: number, branchId: number) {
    const access = form.company_accesses.find(
      (item) => item.company_id === companyId,
    );
    if (!access) return;
    const existing = access.branch_accesses.some(
      (item) => item.branch_id === branchId,
    );
    updateAccess(companyId, {
      branch_accesses: existing
        ? access.branch_accesses.filter((item) => item.branch_id !== branchId)
        : [
            ...access.branch_accesses,
            {
              branch_id: branchId,
              access_profile_id: profiles[companyId]?.[0]?.id || 0,
            },
          ],
    });
  }
  function updateBranchProfile(
    companyId: number,
    branchId: number,
    profileId: number,
  ) {
    const access = form.company_accesses.find(
      (item) => item.company_id === companyId,
    );
    if (access)
      updateAccess(companyId, {
        branch_accesses: access.branch_accesses.map((item) =>
          item.branch_id === branchId
            ? { ...item, access_profile_id: profileId }
            : item,
        ),
      });
  }
  function setCanLogin(value: boolean) {
    setForm((current) => ({
      ...current,
      can_login: value,
      email: value ? current.email : null,
      password: value ? current.password : null,
      company_accesses: value
        ? current.company_accesses
        : current.company_accesses.map((item) => ({
            ...item,
            access_profile_id: null,
            branch_accesses: [],
          })),
    }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (
      form.can_login &&
      form.company_accesses.some(
        (access) =>
          !access.access_profile_id ||
          !access.branch_accesses.length ||
          access.branch_accesses.some((branch) => !branch.access_profile_id),
      )
    ) {
      setError(
        "Com login, selecione perfil administrativo e ao menos uma filial com perfil.",
      );
      return;
    }
    setSaving(true);
    setError("");
    setFields({});
    try {
      const payload = {
        ...form,
        email: form.email?.trim() || null,
        password: form.password?.trim() || undefined,
      };
      if (editing) await http.patch(`users/${editing.id}/`, payload);
      else await http.post("users/", payload);
      setOpen(false);
      setSuccess(
        editing
          ? "Usuário atualizado com sucesso."
          : "Usuário criado com sucesso.",
      );
      await load();
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setFields(caught.fields);
      } else setError("Não foi possível salvar o usuário.");
    } finally {
      setSaving(false);
    }
  }
  async function changeStatus() {
    if (!confirming) return;
    setSaving(true);
    const action = confirming.is_active ? "deactivate" : "activate";
    try {
      await http.post(`users/${confirming.id}/${action}/`);
      setConfirming(null);
      setSuccess(`Usuário ${action === "activate" ? "ativado" : "inativado"}.`);
      await load();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível alterar o status.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Usuários"
        description="Cadastre pessoas com ou sem acesso ao sistema."
        action={
          <Button
            onClick={() => show()}
            disabled={!canAdd || dependenciesLoading}
          >
            <Plus className="size-4" />
            Novo usuário
          </Button>
        }
      />
      <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        {error && !open && <Alert message={error} />}
        {success && <Alert type="success" message={success} />}
        <form className="card space-y-3 p-4" onSubmit={applyFilters}>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-3 size-4 text-slate-400" />
              <Input
                className="pl-9"
                placeholder="Nome ou e-mail"
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
              aria-label="Status do usuário"
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
            <Select
              aria-label="Acesso ao sistema"
              value={draftFilters.canLogin}
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  canLogin: event.target.value,
                }))
              }
            >
              <option value="">Com e sem login</option>
              <option value="true">Pode fazer login</option>
              <option value="false">Sem login</option>
            </Select>
            <Select
              aria-label="Tipo de usuário"
              value={draftFilters.userType}
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  userType: event.target.value,
                }))
              }
            >
              <option value="">Todos os tipos</option>
              {userTypes.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
            <Select
              aria-label="Perfil de acesso"
              value={draftFilters.accessProfile}
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  accessProfile: event.target.value,
                }))
              }
            >
              <option value="">Todos os perfis</option>
              {(profiles[currentCompany?.id || 0] || []).map((profile) => (
                <option key={profile.id} value={profile.id}>
                  {profile.name}
                </option>
              ))}
            </Select>
            <Select
              aria-label="Filial com acesso ativo"
              value={draftFilters.branch}
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  branch: event.target.value,
                }))
              }
            >
              <option value="">Todas as filiais</option>
              {branches
                .filter(
                  (branch) =>
                    branch.company === currentCompany?.id &&
                    branch.status === "active",
                )
                .map((branch) => (
                  <option key={branch.id} value={branch.id}>
                    {branch.name}
                  </option>
                ))}
            </Select>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            <Button type="button" variant="secondary" onClick={clearFilters}>
              Limpar
            </Button>
            <Button type="submit">
              <SlidersHorizontal className="size-4" />
              Aplicar
            </Button>
          </div>
        </form>
        <section className="card overflow-hidden">
          <div className="card-header">
            <div>
              <h2 className="text-sm font-bold">Usuários cadastrados</h2>
              <p className="mt-1 text-[11px] text-slate-500">
                Pessoas operacionais também podem existir sem login
              </p>
            </div>
            <Users className="size-5 text-slate-300" />
          </div>
          {loading ? (
            <TableLoading />
          ) : data?.results.length ? (
            <>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Usuário</th>
                      <th>Tipo</th>
                      <th>Login</th>
                      <th>Perfil administrativo</th>
                      <th>Status</th>
                      <th>Cadastro</th>
                      <th className="text-right">Ações</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.results.map((item) => {
                      const company = item.companies.find(
                        (value) => value.id === currentCompany?.id,
                      );
                      return (
                        <tr key={item.id}>
                          <td>
                            <div className="flex items-center gap-3">
                              <span className="flex size-9 items-center justify-center rounded-full bg-primary/10 text-[11px] font-bold text-primary">
                                {initials(item.first_name, item.last_name)}
                              </span>
                              <div>
                                <strong className="block">
                                  {item.first_name} {item.last_name}
                                </strong>
                                <span className="text-[11px] text-slate-400">
                                  {item.email || "Sem e-mail"}
                                </span>
                              </div>
                            </div>
                          </td>
                          <td>
                            <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold">
                              {typeLabel(item.user_type)}
                            </span>
                          </td>
                          <td>
                            <span
                              className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${item.can_login ? "bg-primary/10 text-primary" : "bg-slate-100 text-slate-500"}`}
                            >
                              {item.can_login ? "Permitido" : "Sem login"}
                            </span>
                          </td>
                          <td>
                            <span className="inline-flex items-center gap-1.5">
                              <Shield className="size-3.5 text-primary" />
                              {item.is_superuser
                                ? "Superusuário"
                                : company?.access_profile?.name || "Sem perfil"}
                            </span>
                          </td>
                          <td>
                            <StatusBadge active={item.is_active} />
                          </td>
                          <td>{formatDate(item.created_at)}</td>
                          <td>
                            <div className="flex justify-end gap-1">
                              <button
                                className="icon-button"
                                aria-label="Editar usuário"
                                disabled={!canChange}
                                onClick={() => show(item)}
                              >
                                <Pencil className="size-4" />
                              </button>
                              <button
                                className="icon-button"
                                aria-label="Alterar status"
                                disabled={!canStatus || item.id === actor?.id}
                                onClick={() => setConfirming(item)}
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
              title={
                Object.values(appliedFilters).some(Boolean)
                  ? "Nenhum usuário encontrado"
                  : "Nenhum usuário cadastrado"
              }
              description={
                Object.values(appliedFilters).some(Boolean)
                  ? "Nenhum usuário corresponde aos filtros aplicados."
                  : "Cadastre a primeira pessoa desta empresa."
              }
            />
          )}
        </section>
      </div>
      <Modal
        open={open}
        title={editing ? "Editar usuário" : "Novo usuário"}
        description="O tipo é informativo e nunca concede permissões."
        onClose={() => !saving && setOpen(false)}
        size="xl"
      >
        <form onSubmit={submit}>
          <div className="grid gap-5 p-5 sm:grid-cols-2 sm:p-6">
            {error && (
              <div className="sm:col-span-2">
                <Alert message={error} />
              </div>
            )}
            <Field label="Nome" error={fieldError(fields, "first_name")}>
              <Input
                required
                value={form.first_name}
                onChange={(event) => update("first_name", event.target.value)}
              />
            </Field>
            <Field label="Sobrenome" error={fieldError(fields, "last_name")}>
              <Input
                required
                value={form.last_name}
                onChange={(event) => update("last_name", event.target.value)}
              />
            </Field>
            <Field label="Tipo de usuário">
              <Select
                value={form.user_type}
                onChange={(event) =>
                  update("user_type", event.target.value as UserType)
                }
              >
                {userTypes.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>
            <label className="flex items-center gap-3 rounded-lg border border-slate-200 p-4 text-xs font-semibold">
              <input
                type="checkbox"
                className="size-4 accent-primary"
                checked={form.can_login}
                onChange={(event) => setCanLogin(event.target.checked)}
              />
              <span>
                <strong className="block">Pode acessar o sistema</strong>
                <small className="font-normal text-slate-400">
                  Exige credenciais e acessos completos
                </small>
              </span>
            </label>
            <Field
              label="E-mail"
              optional={!form.can_login}
              error={fieldError(fields, "email")}
            >
              <Input
                type="email"
                required={form.can_login}
                value={form.email || ""}
                onChange={(event) =>
                  update("email", event.target.value || null)
                }
                disabled={!form.can_login}
              />
            </Field>
            <Field
              label={
                editing && editing.can_login === form.can_login
                  ? "Nova senha"
                  : "Senha"
              }
              optional={!!editing && editing.can_login && form.can_login}
              error={fieldError(fields, "password")}
            >
              <Input
                type="password"
                minLength={8}
                required={form.can_login && (!editing || !editing.can_login)}
                value={form.password || ""}
                onChange={(event) =>
                  update("password", event.target.value || null)
                }
                disabled={!form.can_login}
                placeholder={
                  editing && editing.can_login
                    ? "Deixe em branco para manter"
                    : "Mínimo de 8 caracteres"
                }
              />
            </Field>
            <div className="sm:col-span-2 space-y-3 border-t border-slate-100 pt-4">
              <div className="flex items-center gap-2">
                <KeyRound className="size-4 text-primary" />
                <h3 className="text-xs font-bold">Acessos por empresa</h3>
              </div>
              {companies.map((company) => {
                const access = form.company_accesses.find(
                  (item) => item.company_id === company.id,
                );
                const companyBranches = branches.filter(
                  (branch) => branch.company === company.id,
                );
                return (
                  <section
                    key={company.id}
                    className={`rounded-lg border p-4 ${access ? "border-primary/30 bg-primary/3" : "border-slate-200"}`}
                  >
                    <label className="flex items-center gap-3 text-xs font-bold">
                      <input
                        type="checkbox"
                        className="size-4 accent-primary"
                        checked={!!access}
                        onChange={() => toggleCompany(company.id)}
                      />
                      {company.trade_name}
                    </label>
                    {access && (
                      <div className="mt-4 space-y-3">
                        <Field
                          label="Perfil administrativo"
                          optional={!form.can_login}
                        >
                          <Select
                            required={form.can_login}
                            value={access.access_profile_id || ""}
                            onChange={(event) =>
                              updateAccess(company.id, {
                                access_profile_id: event.target.value
                                  ? Number(event.target.value)
                                  : null,
                                branch_accesses: event.target.value
                                  ? access.branch_accesses
                                  : [],
                              })
                            }
                          >
                            <option value="">Sem perfil administrativo</option>
                            {profiles[company.id]?.map((profile) => (
                              <option key={profile.id} value={profile.id}>
                                {profile.name}
                              </option>
                            ))}
                          </Select>
                        </Field>
                        {form.can_login && (
                          <div>
                            <p className="label">
                              Filiais e perfis operacionais
                            </p>
                            <div className="space-y-2">
                              {companyBranches.map((branch) => {
                                const branchAccess =
                                  access.branch_accesses.find(
                                    (item) => item.branch_id === branch.id,
                                  );
                                return (
                                  <div
                                    key={branch.id}
                                    className="grid gap-2 rounded-md border border-slate-200 p-3 sm:grid-cols-[1fr_14rem]"
                                  >
                                    <label className="flex items-center gap-2 text-xs">
                                      <input
                                        type="checkbox"
                                        className="size-4 accent-primary"
                                        checked={!!branchAccess}
                                        onChange={() =>
                                          toggleBranch(company.id, branch.id)
                                        }
                                      />
                                      {branch.name}
                                    </label>
                                    {branchAccess && (
                                      <Select
                                        required
                                        value={
                                          branchAccess.access_profile_id || ""
                                        }
                                        onChange={(event) =>
                                          updateBranchProfile(
                                            company.id,
                                            branch.id,
                                            Number(event.target.value),
                                          )
                                        }
                                      >
                                        <option value="">
                                          Selecione o perfil
                                        </option>
                                        {profiles[company.id]?.map(
                                          (profile) => (
                                            <option
                                              key={profile.id}
                                              value={profile.id}
                                            >
                                              {profile.name}
                                            </option>
                                          ),
                                        )}
                                      </Select>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </section>
                );
              })}
              {fieldError(fields, "company_accesses") && (
                <p className="field-error">
                  {fieldError(fields, "company_accesses")}
                </p>
              )}
            </div>
          </div>
          <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-4">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setOpen(false)}
              disabled={saving}
            >
              Cancelar
            </Button>
            <Button type="submit" loading={saving}>
              Salvar usuário
            </Button>
          </div>
        </form>
      </Modal>
      <ConfirmDialog
        open={!!confirming}
        title={`${confirming?.is_active ? "Inativar" : "Ativar"} usuário`}
        message={`Confirma a alteração de status de “${confirming?.first_name || ""} ${confirming?.last_name || ""}”?`}
        confirmLabel={confirming?.is_active ? "Inativar" : "Ativar"}
        danger={confirming?.is_active}
        loading={saving}
        onClose={() => setConfirming(null)}
        onConfirm={changeStatus}
      />
    </>
  );
}

export default function UsersPage() {
  return (
    <AdminGuard requiredPermissions={[permissions.viewUser]}>
      <>
        <UsersAdministration />
        <UserCommissionSection />
      </>
    </AdminGuard>
  );
}
