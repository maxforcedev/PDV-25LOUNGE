import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { CheckCircle2, CircleAlert, Radio } from "lucide-react";
import type { OperationalAttentionSummary } from "@/lib/operational-attention";

export function OperationalAttention({
  summary,
  alerts,
}: {
  summary?: OperationalAttentionSummary;
  alerts?: OperationalAttentionSummary;
  asOf?: string;
  coverage?: string;
}) {
  const query = useSearchParams();
  const summaryValue = summary ?? alerts;
  const active = summaryValue?.active_count ?? 0;
  const critical = summaryValue?.by_severity.critical ?? 0;
  const attention = summaryValue?.by_severity.attention ?? 0;
  const availableCategories = summaryValue?.available_categories ?? [];
  const period = new URLSearchParams();
  for (const key of ["start_datetime", "end_datetime"]) {
    const value = query.get(key);
    if (value) period.set(key, value);
  }
  const href = `/atencao-operacional${period.size ? `?${period}` : ""}`;
  return (
    <section className="card overflow-hidden">
      <div className="card-header">
        <div>
          <div className="flex items-center gap-2">
            <Radio className="size-4 text-primary" />
            <h2 className="text-sm font-bold">Central de Atenção</h2>
          </div>
          <p className="mt-1 text-xs text-muted">Exceções ativas de estoque, recebimentos, comandas e impressão. Operações abertas normais não geram alerta.</p>
        </div>
        {active ? <span className="rounded-full bg-warning/10 px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-wide text-warning-strong">{active} {active === 1 ? "alerta" : "alertas"}</span> : null}
      </div>
      {active ? (
        <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap gap-2 text-xs"><span className="rounded-full bg-danger/10 px-2.5 py-1 font-bold text-danger-strong">{critical} crítico(s)</span><span className="rounded-full bg-warning/10 px-2.5 py-1 font-bold text-warning-strong">{attention} em atenção</span></div>
          <Link href={href} className="btn btn-secondary self-start text-xs sm:self-auto"><CircleAlert className="size-4" />Abrir central</Link>
        </div>
      ) : !availableCategories.length ? (
        <div className="flex items-start gap-3 px-5 py-4 text-sm text-muted">
          <CircleAlert className="mt-0.5 size-5 shrink-0" />
          <span><strong className="block">Indicadores operacionais indisponíveis para este perfil.</strong><small className="mt-1 block text-xs text-muted">A Central não confirma normalidade quando os módulos necessários não estão acessíveis.</small></span>
        </div>
      ) : (
        <div className="flex items-start gap-3 px-5 py-4 text-sm text-success-strong">
          <CheckCircle2 className="mt-0.5 size-5 shrink-0" />
          <span><strong className="block">Nenhuma situação ativa identificada.</strong><small className="mt-1 block text-xs text-muted">A central acompanha somente condições que exigem intervenção.</small></span>
        </div>
      )}
    </section>
  );
}
