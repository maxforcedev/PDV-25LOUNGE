"use client";

import Link from "next/link";
import { useEffect, useEffectEvent, useRef, useState } from "react";
import { ExternalLink, RefreshCw } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, EmptyState, Select, Spinner } from "@/components/ui";
import {
  operationalAttentionQuery,
  type AttentionCategory,
  type AttentionSeverity,
  type OperationalAttentionResponse,
} from "@/lib/operational-attention";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";

const categories: Array<[AttentionCategory, string]> = [
  ["inventory", "Estoque"], ["financial", "Financeiro"], ["commands", "Comandas"], ["printing", "Impressão"], ["cash", "Caixa"],
];
const severities: Array<[AttentionSeverity, string]> = [
  ["critical", "Crítico"], ["attention", "Atenção"], ["informational", "Informativo"],
];

function attentionError(caught: unknown) {
  if (!(caught instanceof ApiError) || caught.status === 0) return "Não foi possível conectar ao servidor. Tente novamente.";
  if (caught.status === 403) return "Seu perfil não possui acesso às ocorrências disponíveis nesta filial.";
  return caught.message || "Não foi possível carregar a Central de Atenção Operacional.";
}

function initialPeriod() {
  if (typeof window === "undefined") return { startDatetime: "", endDatetime: "" };
  const query = new URLSearchParams(window.location.search);
  return {
    startDatetime: query.get("start_datetime") || "",
    endDatetime: query.get("end_datetime") || "",
  };
}

function AttentionPage() {
  const { currentBranch } = useAuth();
  const branchId = currentBranch?.id || 0;
  const request = useRef(0);
  const period = useRef(initialPeriod());
  const [category, setCategory] = useState<"" | AttentionCategory>("");
  const [severity, setSeverity] = useState<"" | AttentionSeverity>("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<OperationalAttentionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load(nextPage = page) {
    if (!branchId) { setData(null); setError(""); setLoading(false); return; }
    const token = ++request.current;
    setData(null); setLoading(true); setError("");
    try {
      const query = operationalAttentionQuery({
        categories: category ? [category] : [], severities: severity ? [severity] : [], page: nextPage,
        ...period.current,
      });
      const result = await http.get<OperationalAttentionResponse>(`operational-attention/?${query}`);
      if (request.current === token) setData(result);
    } catch (caught) {
      if (request.current === token) setError(attentionError(caught));
    } finally {
      if (request.current === token) setLoading(false);
    }
  }

  const loadAttention = useEffectEvent(load);
  useEffect(() => {
    request.current += 1;
    setPage(1);
    void loadAttention(1);
  }, [branchId, category, severity]);

  useEffect(() => {
    if (data && category && !data.available_categories.includes(category)) setCategory("");
  }, [data, category]);

  const summary = data?.summary;
  const hasCoverage = (data?.available_categories.length ?? 0) > 0;
  return <>
    <PageHeader title="Atenção operacional" description="Situações ativas que exigem intervenção na filial selecionada." action={<Button variant="secondary" onClick={() => void load()} disabled={loading}><RefreshCw className="size-4" />Atualizar</Button>} />
    <main className="space-y-5 p-4 sm:p-6 lg:p-8">
      <section className="card grid gap-3 p-4 sm:grid-cols-[minmax(0,1fr)_12rem_12rem] sm:items-end">
        <div><strong className="text-sm">{hasCoverage ? `${summary?.active_count ?? 0} ocorrência(s) ativa(s)` : "Cobertura operacional indisponível"}</strong><p className="mt-1 text-xs text-muted">Condições são avaliadas ao consultar. Alertas corrigidos deixam de aparecer.</p></div>
        <label className="text-xs font-semibold text-muted">Categoria<Select value={category} onChange={(event) => setCategory(event.target.value as "" | AttentionCategory)} className="mt-1"><option value="">Todas</option>{categories.filter(([value]) => !data || data.available_categories.includes(value)).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select></label>
        <label className="text-xs font-semibold text-muted">Gravidade<Select value={severity} onChange={(event) => setSeverity(event.target.value as "" | AttentionSeverity)} className="mt-1"><option value="">Todas</option>{severities.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select></label>
      </section>
      {error && <Alert message={error} />}
      {loading ? <section className="card flex min-h-48 items-center justify-center"><Spinner /></section> : !error && data?.results.length ? <section className="space-y-3">{data.results.map((alert) => {
        const tone = alert.severity === "critical" ? "border-danger/35 bg-danger/5" : alert.severity === "attention" ? "border-warning/35 bg-warning/5" : "border-primary/25 bg-primary/5";
        const severityLabel = alert.severity === "critical" ? "Crítico" : alert.severity === "attention" ? "Atenção" : "Informativo";
        const categoryLabel = categories.find(([value]) => value === alert.category)?.[1] || alert.category;
        const occurredAt = alert.occurred_at ? new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(new Date(alert.occurred_at)) : null;
        return <article key={alert.identity} className={`card border p-4 ${tone}`}><div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><span className="rounded-full bg-surface px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wide">{severityLabel}</span><span className="text-[11px] font-semibold text-muted">{categoryLabel} · {alert.reference === "period" ? "Período selecionado" : "Estado atual"}</span></div><h2 className="mt-2 text-sm font-bold">{alert.title}</h2><p className="mt-1 text-sm text-muted">{alert.description}</p><p className="mt-3 text-xs"><strong>Filial:</strong> {alert.context.branch_name}{occurredAt ? <> · <strong>Referência:</strong> {occurredAt}</> : null}</p><p className="mt-1 text-xs"><strong>Entidade:</strong> {alert.entity.name} · <strong>Ação recomendada:</strong> {alert.recommended_action}</p></div>{alert.route && <Link href={alert.route} className="btn btn-secondary shrink-0 text-xs">Ver contexto<ExternalLink className="size-3.5" /></Link>}</div></article>;
      })}</section> : !error && !hasCoverage ? <section className="card"><EmptyState title="Indicadores indisponíveis" description="Seu perfil ou a configuração da filial não permite avaliar situações operacionais nesta central." /></section> : !error ? <section className="card"><EmptyState title="Nenhuma situação ativa" description="Não há exceções ativas dentro dos filtros e permissões disponíveis." /></section> : null}
      {data && (data.previous || data.next) && <div className="flex items-center justify-between"><Button variant="secondary" disabled={!data.previous || loading} onClick={() => { const next = Math.max(1, page - 1); setPage(next); void load(next); }}>Anterior</Button><span className="text-xs text-muted">Página {page}</span><Button variant="secondary" disabled={!data.next || loading} onClick={() => { const next = page + 1; setPage(next); void load(next); }}>Próxima</Button></div>}
    </main>
  </>;
}

export default function OperationalAttentionRoute() {
  return <AdminGuard requiredPermissions={[permissions.viewDashboard]} requiredFeatures={["reports"]}><AttentionPage /></AdminGuard>;
}
