"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { FileSearch } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import { PeriodFilter, type PeriodValue } from "@/components/period-filter";
import {
  Alert,
  Button,
  EmptyState,
  Field,
  Input,
  Modal,
  Pagination,
  Select,
  TableLoading,
  Tooltip,
} from "@/components/ui";
import { formatBRL, formatDate, formatQuantity } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { businessPeriodPreset } from "@/lib/period";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type {
  AuditLog,
  AuditOptions,
  Branch,
  Paginated,
  User,
} from "@/types";

const valueLabels: Record<string, string> = {
  active: "Ativo",
  inactive: "Inativo",
  open: "Aberto",
  closed: "Fechado",
  finalized: "Finalizada",
  cancelled: "Cancelada",
  entry: "Entrada",
  exit: "Saída",
  adjustment: "Ajuste",
  manual_entry: "Entrada manual",
  withdrawal: "Sangria",
  sale_cancellation: "Cancelamento de venda",
  consumption_cancellation: "Cancelamento de consumação",
  regularization: "Regularização",
  opening_balance: "Saldo inicial",
  balance_correction: "Correção de saldo",
  operating_expense: "Despesa operacional",
  neutral: "Não afeta o resultado",
  direct: "Estoque próprio",
  none: "Sem estoque",
  components: "Baixa por componentes",
  counter: "Balcão",
  table: "Mesa",
  command: "Comanda",
  ml: "mL",
  g: "g",
};
const auditActionLabels: Record<string, string> = {
  "product.branch_config.copy": "Configuração do produto copiada entre filiais",
  "category.branch_config.copy": "Configuração da categoria copiada entre filiais",
};
const auditFieldLabels: Record<string, string> = {
  branch_id: "Filial de destino",
  is_available: "Disponibilidade",
  channel_overrides: "Disponibilidade por canal",
  effective_channels: "Canais efetivos",
  price_override: "Preço específico da filial",
  effective_price: "Preço efetivo",
  destinations: "Destinos de produção",
  source_branch: "Filial de origem",
  copied_from: "Configuração da filial de origem",
  category_id: "Categoria",
};
function auditActionLabel(action: string, fallback: string) {
  return auditActionLabels[action] || fallback;
}
function auditFieldLabel(field: string, fallback: string) {
  return auditFieldLabels[field] || fallback;
}
function humanValue(value: unknown): string {
  if (value === null || value === undefined || value === "")
    return "Não informado";
  if (value === true) return "Sim";
  if (value === false) return "Não";
  if (Array.isArray(value)) return value.map(humanValue).join(", ");
  if (typeof value === "object") return "Dados estruturados";
  return valueLabels[String(value)] || String(value);
}
function changeSummary(log: AuditLog) {
  const changed = (log.changes || [])
    .filter((change) => auditFieldLabel(change.field, change.field_label) !== "Campo técnico")
    .slice(0, 2);
  if (!changed.length) return "Alteração registrada";
  return changed
    .map(
      (change) =>
        `${auditFieldLabel(change.field, change.field_label)}: ${change.before_label} → ${change.after_label}`,
    )
    .join(" · ");
}

interface SaleAuditItem {
  product_name: string;
  quantity?: string;
  unit_price?: string;
  promotion_discount?: string;
  manual_item_discount?: string;
}

interface SaleAuditPayment {
  payment_method_name: string;
  amount?: string;
  received_amount?: string | null;
}

function saleItems(metadata: Record<string, unknown>): SaleAuditItem[] {
  if (!Array.isArray(metadata.items)) return [];
  return metadata.items.filter(
    (item): item is SaleAuditItem =>
      !!item &&
      typeof item === "object" &&
      typeof (item as Record<string, unknown>).product_name === "string",
  );
}

function salePayments(metadata: Record<string, unknown>): SaleAuditPayment[] {
  if (!Array.isArray(metadata.payments)) return [];
  return metadata.payments.filter(
    (payment): payment is SaleAuditPayment =>
      !!payment &&
      typeof payment === "object" &&
      typeof (payment as Record<string, unknown>).payment_method_name ===
        "string",
  );
}
function objectHref(log: AuditLog) {
  const model = log.object_type.split(".").at(-1)?.toLowerCase();
  if (model === "sale") {
    return log.action.startsWith("consumption.")
      ? `/consumacoes/${log.object_id}`
      : `/vendas/${log.object_id}`;
  }
  if (model === "cashsession") return `/caixas/sessoes/${log.object_id}`;
  if (model === "branch") return "/filiais";
  if (model === "user") return "/usuarios";
  if (model === "accessprofile") return "/perfis";
  if (model === "product") return `/produtos?edit=${log.object_id}`;
  if (["productsupplier", "productsupplierunit"].includes(model || "")) return "/produtos";
  return null;
}

interface AuditFilters {
  search: string;
  branch: string;
  actor: string;
  module: string;
  action: string;
}
const emptyFilters: AuditFilters = {
  search: "",
  branch: "",
  actor: "",
  module: "",
  action: "",
};

function AuditPageInner() {
  const { currentCompany, currentBranch } = useAuth();
  const contextKey = `${currentCompany?.id || 0}:${currentBranch?.id || 0}`;
  const contextRef = useRef(contextKey);
  const listRequestRef = useRef(0);
  const optionsRequestRef = useRef(0);
  contextRef.current = contextKey;
  const [period, setPeriod] = useState<PeriodValue>(() =>
    businessPeriodPreset("today"),
  );
  const [search, setSearch] = useState("");
  const [branch, setBranch] = useState("");
  const [actor, setActor] = useState("");
  const [module, setModule] = useState("");
  const [action, setAction] = useState("");
  const [appliedFilters, setAppliedFilters] =
    useState<AuditFilters>(emptyFilters);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [options, setOptions] = useState<AuditOptions>({
    modules: [],
    actions: [],
  });
  const [optionsLoading, setOptionsLoading] = useState(true);
  const [optionsError, setOptionsError] = useState("");
  const [data, setData] = useState<Paginated<AuditLog> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<AuditLog | null>(null);

  function selectedFilters(): AuditFilters {
    return { search, branch, actor, module, action };
  }

  function url(
    path: string | undefined,
    selectedPeriod: PeriodValue,
    filters: AuditFilters,
  ) {
    if (path) return path;
    const params = new URLSearchParams({
      start_datetime: selectedPeriod.start,
      end_datetime: selectedPeriod.end,
    });
    if (!selectedPeriod.start) params.delete("start_datetime");
    if (!selectedPeriod.end) params.delete("end_datetime");
    if (!filters.branch) params.set("scope", "all");
    if (currentCompany) params.set("company", String(currentCompany.id));
    if (filters.search.trim()) params.set("search", filters.search.trim());
    if (filters.branch) params.set("branch", filters.branch);
    if (filters.actor) params.set("actor", filters.actor);
    if (filters.module) params.set("module", filters.module);
    if (filters.action) params.set("action", filters.action);
    return `audit-logs/?${params}`;
  }

  function syncUrl(selectedPeriod: PeriodValue, filters: AuditFilters) {
    const params = new URLSearchParams();
    if (selectedPeriod.start)
      params.set("start_datetime", selectedPeriod.start);
    if (selectedPeriod.end) params.set("end_datetime", selectedPeriod.end);
    if (filters.search.trim()) params.set("search", filters.search.trim());
    if (filters.branch) params.set("branch", filters.branch);
    if (filters.actor) params.set("actor", filters.actor);
    if (filters.module) params.set("module", filters.module);
    if (filters.action) params.set("action", filters.action);
    window.history.replaceState(
      null,
      "",
      `${window.location.pathname}${params.size ? `?${params}` : ""}`,
    );
  }

  async function load(
    path?: string,
    token = contextRef.current,
    selectedPeriod = period,
    filters = appliedFilters,
  ) {
    if (!currentBranch) return;
    const requestId = ++listRequestRef.current;
    setLoading(true);
    setError("");
    setData(null);
    if (!path) {
      setAppliedFilters(filters);
      syncUrl(selectedPeriod, filters);
    }
    try {
      const response = await http.get<Paginated<AuditLog>>(
        url(path, selectedPeriod, filters),
      );
      if (
        contextRef.current === token &&
        listRequestRef.current === requestId
      )
        setData(response);
    } catch (caught) {
      if (
        contextRef.current === token &&
        listRequestRef.current === requestId
      )
        setError(
          caught instanceof ApiError
            ? caught.message
            : "Não foi possível carregar a auditoria.",
        );
    } finally {
      if (
        contextRef.current === token &&
        listRequestRef.current === requestId
      )
        setLoading(false);
    }
  }

  async function loadOptions(token = contextRef.current) {
    if (!currentCompany || !currentBranch) return;
    const requestId = ++optionsRequestRef.current;
    setOptionsLoading(true);
    setOptionsError("");
    const params = new URLSearchParams({
      scope: "all",
      company: String(currentCompany.id),
    });
    try {
      const response = await http.get<AuditOptions>(
        `audit-logs/options/?${params}`,
      );
      if (
        contextRef.current === token &&
        optionsRequestRef.current === requestId
      )
        setOptions(response);
    } catch {
      if (
        contextRef.current === token &&
        optionsRequestRef.current === requestId
      ) {
        setOptions({ modules: [], actions: [] });
        setOptionsError(
          "Não foi possível carregar as opções de módulo e ação.",
        );
      }
    } finally {
      if (
        contextRef.current === token &&
        optionsRequestRef.current === requestId
      )
        setOptionsLoading(false);
    }
  }

  function clearFilters() {
    const clearedPeriod = { start: "", end: "" };
    setPeriod(clearedPeriod);
    setSearch("");
    setBranch("");
    setActor("");
    setModule("");
    setAction("");
    setAppliedFilters(emptyFilters);
    setSelected(null);
    void load(undefined, contextRef.current, clearedPeriod, emptyFilters);
  }

  useEffect(() => {
    const token = contextRef.current;
    const query = new URLSearchParams(window.location.search);
    const defaultPeriod = businessPeriodPreset("today");
    const initialPeriod =
      query.get("start_datetime") && query.get("end_datetime")
        ? {
            start: query.get("start_datetime")!,
            end: query.get("end_datetime")!,
          }
        : defaultPeriod;
    const initialFilters = {
      search: query.get("search") || "",
      branch: query.get("branch") || "",
      actor: query.get("actor") || "",
      module: query.get("module") || "",
      action: query.get("action") || "",
    };
    setPeriod(initialPeriod);
    setSearch(initialFilters.search);
    setBranch(initialFilters.branch);
    setActor(initialFilters.actor);
    setModule(initialFilters.module);
    setAction(initialFilters.action);
    setAppliedFilters(initialFilters);
    setSelected(null);
    setBranches([]);
    setUsers([]);
    setOptions({ modules: [], actions: [] });
    void load(undefined, token, initialPeriod, initialFilters);
    void loadOptions(token);
    if (currentCompany) {
      void http
        .getAll<Branch>(`branches/?company=${currentCompany.id}`)
        .then((items) => {
          if (contextRef.current === token) setBranches(items);
        })
        .catch(() => {
          if (contextRef.current === token) setBranches([]);
        });
      void http
        .getAll<User>(`users/?company=${currentCompany.id}`)
        .then((items) => {
          if (contextRef.current === token) setUsers(items);
        })
        .catch(() => {
          if (contextRef.current === token) setUsers([]);
        });
    }
  }, [currentCompany?.id, currentBranch?.id]);

  return (
    <>
      <PageHeader
        title="Auditoria"
        description="Consulta append-only das alterações críticas do sistema."
      />
      <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        {error && <Alert message={error} />}
        {optionsError && <Alert message={optionsError} />}
        <form
          className="card p-4"
          onSubmit={(event) => {
            event.preventDefault();
            const filters = selectedFilters();
            void load(undefined, contextRef.current, period, filters);
          }}
        >
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
            <PeriodFilter
              className="sm:col-span-2 xl:col-span-6"
              value={period}
              onChange={setPeriod}
              onApply={(next) => {
                setPeriod(next);
                void load(
                  undefined,
                  contextRef.current,
                  next,
                  appliedFilters,
                );
              }}
              showActions={false}
            />
            <Field label="Filial">
              <Select
                value={branch}
                onChange={(event) => setBranch(event.target.value)}
              >
                <option value="">Todas autorizadas</option>
                {branches.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Ator">
              <Select
                value={actor}
                onChange={(event) => setActor(event.target.value)}
              >
                <option value="">Todos</option>
                {users.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.first_name} {item.last_name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Módulo">
              <Select
                value={module}
                onChange={(event) => setModule(event.target.value)}
                disabled={optionsLoading}
              >
                <option value="">
                  {optionsLoading ? "Carregando opções..." : "Todos"}
                </option>
                {options.modules.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Ação">
              <Select
                value={action}
                onChange={(event) => setAction(event.target.value)}
                disabled={optionsLoading}
              >
                <option value="">
                  {optionsLoading ? "Carregando opções..." : "Todas"}
                </option>
                {options.actions.map((item) => (
                  <option key={item.value} value={item.value}>
                    {auditActionLabel(item.value, item.label)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Busca">
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Objeto ou ação"
              />
            </Field>
            <div className="flex items-end gap-2">
              <Button type="submit">
                <FileSearch className="size-4" />
                Aplicar
              </Button>
              <Button type="button" variant="secondary" onClick={clearFilters}>
                Limpar
              </Button>
            </div>
          </div>
        </form>
        <section className="card overflow-hidden">
          <div className="card-header">
            <h2 className="text-sm font-bold">Logs</h2>
          </div>
          {loading ? (
            <TableLoading />
          ) : data?.results.length ? (
            <>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Quando</th>
                      <th>Ação</th>
                      <th>Ator</th>
                      <th>Módulo / objeto</th>
                      <th>Resumo</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.results.map((log) => (
                      <tr key={log.id}>
                        <td>{formatDate(log.created_at)}</td>
                        <td>
                          <strong>{auditActionLabel(log.action, log.action_label)}</strong>
                          <span className="block text-[11px] text-muted">
                            {log.branch_name ||
                              log.company_name ||
                              "Escopo global"}
                          </span>
                        </td>
                        <td>{log.actor_name || "Sistema"}</td>
                        <td>
                          <strong className="block text-[11px]">
                            {log.module_label}
                          </strong>
                          <span className="text-[11px]">
                            {log.object_label}
                          </span>
                        </td>
                        <td className="max-w-md text-[11px]">
                          <Tooltip content={changeSummary(log)}>
                            <span className="block max-w-md truncate">
                              {changeSummary(log)}
                            </span>
                          </Tooltip>
                        </td>
                        <td>
                          <Button
                            variant="secondary"
                            onClick={() => setSelected(log)}
                          >
                            Detalhes
                          </Button>
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
                onPage={(path) => void load(path)}
              />
            </>
          ) : (
            <EmptyState
              title="Sem logs"
              description="Nenhuma alteração crítica encontrada para o período."
            />
          )}
        </section>
      </div>
      <Modal
        open={!!selected}
        title="Detalhes da auditoria"
        description={
          selected
            ? `${auditActionLabel(selected.action, selected.action_label)} em ${formatDate(selected.created_at)}`
            : ""
        }
        onClose={() => setSelected(null)}
        size="xl"
      >
        {selected && (
          <div className="space-y-5 p-5">
            <div className="grid gap-3 rounded-lg bg-surface-muted p-4 text-xs sm:grid-cols-2">
              <p>
                <strong className="block text-muted">Responsável</strong>
                {selected.actor_name || "Sistema"}
              </p>
              <p>
                <strong className="block text-muted">Escopo</strong>
                {selected.branch_name || selected.company_name || "Global"}
              </p>
              <p>
                <strong className="block text-muted">Objeto técnico</strong>
                {selected.object_type} #{selected.object_id}
              </p>
              <p>
                <strong className="block text-muted">Endereço IP</strong>
                {humanValue(selected.metadata?.ip_address)}
              </p>
              <p>
                <strong className="block text-muted">ID da requisição</strong>
                {humanValue(selected.metadata?.request_id)}
              </p>
              <p>
                <strong className="block text-muted">Correlação</strong>
                {humanValue(selected.metadata?.correlation_id)}
              </p>
              {selected.metadata?.operation_reference ? (
                <p className="break-all sm:col-span-2">
                  <strong className="block text-muted">
                    Referência da operação
                  </strong>
                  {humanValue(selected.metadata.operation_reference)}
                </p>
              ) : null}
              <p className="break-all sm:col-span-2">
                <strong className="block text-muted">Dispositivo</strong>
                {humanValue(selected.metadata?.user_agent)}
              </p>
              {objectHref(selected) && (
                <p className="sm:col-span-2">
                  <Link
                    className="font-bold text-primary"
                    href={objectHref(selected)!}
                  >
                    Abrir objeto relacionado
                  </Link>
                </p>
              )}
            </div>
            <div className="table-wrap rounded-lg border border-subtle">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Campo</th>
                    <th>De</th>
                    <th>Para</th>
                  </tr>
                </thead>
                <tbody>
                  {selected.changes?.length ? selected.changes.map((change, index) => (
                    <tr key={`${change.field}-${index}`}>
                      <td className="font-semibold">{auditFieldLabel(change.field, change.field_label)}</td>
                      <td>{change.before_label}</td>
                      <td>{change.after_label}</td>
                    </tr>
                  )) : <tr><td colSpan={3} className="text-muted">Sem alteração de campos para apresentar.</td></tr>}
                </tbody>
              </table>
            </div>
            {(saleItems(selected.metadata).length > 0 ||
              salePayments(selected.metadata).length > 0) && (
              <div className="grid gap-4 lg:grid-cols-2">
                {saleItems(selected.metadata).length > 0 && (
                  <section className="overflow-hidden rounded-lg border border-subtle bg-surface">
                    <h3 className="border-b border-subtle bg-surface-muted px-4 py-3 text-xs font-bold text-fg">
                      Itens da operação
                    </h3>
                    <div className="table-wrap">
                      <table className="data-table min-w-120">
                        <thead>
                          <tr>
                            <th>Produto</th>
                            <th>Quantidade</th>
                            <th>Preço unitário</th>
                            <th>Descontos</th>
                          </tr>
                        </thead>
                        <tbody>
                          {saleItems(selected.metadata).map((item, index) => {
                            const discount =
                              Number(item.promotion_discount || 0) +
                              Number(item.manual_item_discount || 0);
                            return (
                              <tr key={`${item.product_name}-${index}`}>
                                <td className="font-semibold">
                                  {item.product_name}
                                </td>
                                <td>{formatQuantity(item.quantity)}</td>
                                <td>{formatBRL(item.unit_price)}</td>
                                <td>{formatBRL(discount.toFixed(2))}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </section>
                )}
                {salePayments(selected.metadata).length > 0 && (
                  <section className="overflow-hidden rounded-lg border border-subtle bg-surface">
                    <h3 className="border-b border-subtle bg-surface-muted px-4 py-3 text-xs font-bold text-fg">
                      Pagamentos
                    </h3>
                    <div className="table-wrap">
                      <table className="data-table min-w-96">
                        <thead>
                          <tr>
                            <th>Forma</th>
                            <th>Valor</th>
                            <th>Recebido</th>
                          </tr>
                        </thead>
                        <tbody>
                          {salePayments(selected.metadata).map(
                            (payment, index) => (
                              <tr
                                key={`${payment.payment_method_name}-${index}`}
                              >
                                <td className="font-semibold">
                                  {payment.payment_method_name}
                                </td>
                                <td>{formatBRL(payment.amount)}</td>
                                <td>
                                  {payment.received_amount
                                    ? formatBRL(payment.received_amount)
                                    : "Não se aplica"}
                                </td>
                              </tr>
                            ),
                          )}
                        </tbody>
                      </table>
                    </div>
                  </section>
                )}
              </div>
            )}
          </div>
        )}
      </Modal>
    </>
  );
}

export default function AuditPage() {
  return (
    <AdminGuard requiredPermissions={[permissions.viewAuditLog]}>
      <AuditPageInner />
    </AdminGuard>
  );
}
