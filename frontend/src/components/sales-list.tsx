"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ClipboardList, ExternalLink, Search } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { PeriodFilter, type PeriodValue } from "@/components/period-filter";
import {
  Alert,
  Button,
  EmptyState,
  Field,
  Input,
  Pagination,
  Select,
  TableLoading,
} from "@/components/ui";
import { formatBRL, formatDate } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { Paginated, Sale, SaleBeneficiary, SaleOperation } from "@/types";

interface SalesFilters {
  search: string;
  number: string;
  status: string;
  beneficiary: string;
}

const emptyFilters = (): SalesFilters => ({
  search: "",
  number: "",
  status: "",
  beneficiary: "",
});

function SaleStatusBadge({ status }: { status: Sale["status"] }) {
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-semibold ${status === "finalized" ? "bg-success/10 text-success-strong" : "bg-danger/10 text-danger-strong"}`}
    >
      {status === "finalized" ? "Finalizada" : "Cancelada"}
    </span>
  );
}

export function SalesList({ operation }: { operation: SaleOperation }) {
  const consumption = operation === "consumption";
  const { currentCompany, currentBranch, hasFeature, hasPermission } = useAuth();
  const canLoadBeneficiaries =
    hasFeature("consumption") && (
      hasPermission(permissions.viewConsumption) ||
      hasPermission(permissions.createConsumption)
    );
  const contextRef = useRef("");
  const requestRef = useRef(0);
  contextRef.current = `${currentCompany?.id || ""}:${currentBranch?.id || ""}:${operation}`;
  const [data, setData] = useState<Paginated<Sale> | null>(null);
  const [beneficiaries, setBeneficiaries] = useState<SaleBeneficiary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [number, setNumber] = useState("");
  const [status, setStatus] = useState("");
  const [beneficiary, setBeneficiary] = useState("");
  const [period, setPeriod] = useState<PeriodValue>({ start: "", end: "" });
  const [appliedFilters, setAppliedFilters] =
    useState<SalesFilters>(emptyFilters);

  function query(
    selectedPeriod = period,
    selectedFilters = appliedFilters,
  ) {
    const params = new URLSearchParams({ operation_type: operation });
    if (selectedFilters.number.trim())
      params.set("number", selectedFilters.number.trim());
    if (selectedFilters.search.trim())
      params.set("search", selectedFilters.search.trim());
    if (selectedFilters.status) params.set("status", selectedFilters.status);
    if (selectedFilters.beneficiary)
      params.set("beneficiary", selectedFilters.beneficiary);
    if (selectedPeriod.start)
      params.set("start_datetime", selectedPeriod.start);
    if (selectedPeriod.end) params.set("end_datetime", selectedPeriod.end);
    return `sales/?${params}`;
  }
  function syncUrl(selectedPeriod: PeriodValue, selectedFilters: SalesFilters) {
    const params = new URLSearchParams();
    if (selectedFilters.number.trim())
      params.set("number", selectedFilters.number.trim());
    if (selectedFilters.search.trim())
      params.set("search", selectedFilters.search.trim());
    if (selectedFilters.status) params.set("status", selectedFilters.status);
    if (selectedFilters.beneficiary)
      params.set("beneficiary", selectedFilters.beneficiary);
    if (selectedPeriod.start)
      params.set("start_datetime", selectedPeriod.start);
    if (selectedPeriod.end) params.set("end_datetime", selectedPeriod.end);
    window.history.replaceState(
      null,
      "",
      `${window.location.pathname}${params.size ? `?${params}` : ""}`,
    );
  }
  async function load(
    path?: string,
    context = contextRef.current,
    selectedPeriod = period,
    selectedFilters = appliedFilters,
  ) {
    const requestId = ++requestRef.current;
    if (!currentBranch) {
      setData(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    setData(null);
    if (!path) {
      setAppliedFilters(selectedFilters);
      syncUrl(selectedPeriod, selectedFilters);
    }
    try {
      const response = await http.get<Paginated<Sale>>(
        path || query(selectedPeriod, selectedFilters),
      );
      if (contextRef.current === context && requestRef.current === requestId)
        setData(response);
    } catch (caught) {
      if (contextRef.current === context && requestRef.current === requestId)
        setError(
          caught instanceof ApiError
            ? caught.message
            : "Não foi possível carregar as operações.",
        );
    } finally {
      if (contextRef.current === context && requestRef.current === requestId)
        setLoading(false);
    }
  }
  function clearFilters() {
    setSearch("");
    setNumber("");
    setStatus("");
    setBeneficiary("");
    const clearedPeriod = { start: "", end: "" };
    const clearedFilters = emptyFilters();
    setPeriod(clearedPeriod);
    void load(undefined, contextRef.current, clearedPeriod, clearedFilters);
  }
  useEffect(() => {
    const context = contextRef.current;
    const queryParams = new URLSearchParams(window.location.search);
    const initialPeriod = {
      start: queryParams.get("start_datetime") || "",
      end: queryParams.get("end_datetime") || "",
    };
    const initialFilters = {
      search: queryParams.get("search") || "",
      number: queryParams.get("number") || "",
      status: queryParams.get("status") || "",
      beneficiary: queryParams.get("beneficiary") || "",
    };
    setData(null);
    setError("");
    setSearch(initialFilters.search);
    setNumber(initialFilters.number);
    setStatus(initialFilters.status);
    setBeneficiary(initialFilters.beneficiary);
    setPeriod(initialPeriod);
    setAppliedFilters(initialFilters);
    setBeneficiaries([]);
    void load(undefined, context, initialPeriod, initialFilters);
    if (consumption && canLoadBeneficiaries)
      http
        .getAll<SaleBeneficiary>("sales/beneficiaries/")
        .then((items) => {
          if (contextRef.current === context) setBeneficiaries(items);
        })
        .catch(() => undefined);
  }, [currentCompany?.id, currentBranch?.id, operation]);

  return (
    <>
      <PageHeader
        title={consumption ? "Consumações" : "Vendas"}
        description={`Histórico da filial ${currentBranch?.name || "não selecionada"}. Valores e produtos refletem o registro da operação.`}
      />
      <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        {error && <Alert message={error} />}
        <form
          className="card grid gap-3 p-4 md:grid-cols-2 xl:grid-cols-[10rem_minmax(13rem,1fr)_10rem_12rem_auto_auto]"
          onSubmit={(event) => {
            event.preventDefault();
            const nextFilters = { search, number, status, beneficiary };
            void load(undefined, contextRef.current, period, nextFilters);
          }}
        >
          <Field label="Número">
            <Input
              value={number}
              onChange={(event) => setNumber(event.target.value)}
              placeholder="V000001"
            />
          </Field>
          <Field label="Busca ampla">
            <div className="relative">
              <Search className="absolute left-3 top-3 size-4 text-slate-400" />
              <Input
                className="pl-9"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Item, código ou pessoa"
              />
            </div>
          </Field>
          <Field label="Status">
            <Select
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="">Todos</option>
              <option value="finalized">Finalizadas</option>
              <option value="cancelled">Canceladas</option>
            </Select>
          </Field>
          {consumption && canLoadBeneficiaries ? (
            <Field label="Beneficiário">
              <Select
                value={beneficiary}
                onChange={(event) => setBeneficiary(event.target.value)}
              >
                <option value="">Todos</option>
                {beneficiaries.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </Select>
            </Field>
          ) : (
            <div />
          )}
          <Button className="self-end" type="submit">
            Aplicar
          </Button>
          <Button
            className="self-end"
            type="button"
            variant="secondary"
            onClick={clearFilters}
          >
            Limpar
          </Button>
          <PeriodFilter
            className="md:col-span-2 xl:col-span-full"
            value={period}
            onChange={setPeriod}
            onApply={(next) => {
              setPeriod(next);
              void load(undefined, contextRef.current, next, appliedFilters);
            }}
            showActions={false}
          />
        </form>
        <section className="card overflow-hidden">
          <div className="card-header">
            <div>
              <h2 className="text-sm font-bold">
                {consumption ? "Consumações registradas" : "Vendas comerciais"}
              </h2>
              <p className="mt-1 text-[11px] text-slate-500">
                Ordenação mais recente primeiro
              </p>
            </div>
            <ClipboardList className="size-5 text-slate-300" />
          </div>
          {loading ? (
            <TableLoading columns={6} />
          ) : data?.results.length ? (
            <>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Número</th>
                      <th>Data</th>
                      <th>{consumption ? "Cobrado / referência" : "Total"}</th>
                      <th>Status</th>
                      <th>Operador</th>
                      {consumption && <th>Beneficiário</th>}
                      <th className="text-right">Detalhe</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.results.map((item) => (
                      <tr key={item.id}>
                        <td className="font-bold">{item.sale_number}</td>
                        <td>{formatDate(item.created_at)}</td>
                        <td>
                          <strong>{formatBRL(item.total)}</strong>
                          {consumption && (
                            <span className="block text-[10px] text-slate-400">
                              Ref. {formatBRL(item.subtotal)}
                            </span>
                          )}
                        </td>
                        <td>
                          <SaleStatusBadge status={item.status} />
                        </td>
                        <td>{item.created_by_name}</td>
                        {consumption && (
                          <td>{item.beneficiary_user_name || "-"}</td>
                        )}
                        <td>
                          <div className="flex justify-end">
                            <Link
                              className="icon-button"
                              aria-label={`Abrir ${item.sale_number}`}
                              href={`/${consumption ? "consumacoes" : "vendas"}/${item.id}`}
                            >
                              <ExternalLink className="size-4" />
                            </Link>
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
              title={`Nenhuma ${consumption ? "consumação" : "venda"} encontrada`}
              description="Ajuste os filtros ou registre uma nova operação nesta filial."
            />
          )}
        </section>
      </div>
    </>
  );
}
