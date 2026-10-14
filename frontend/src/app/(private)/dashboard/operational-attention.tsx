import Link from "next/link";
import { CheckCircle2, CircleAlert, Info, Radio } from "lucide-react";

export type OperationalAlert = {
  key: string;
  title: string;
  detail: string;
  href?: string;
  tone: "danger" | "warning" | "info";
  reference?: "current" | "period";
};

export type OperationalCoverage = "full" | "partial" | "none";

export function OperationalAttention({
  alerts,
  asOf,
  coverage,
}: {
  alerts: OperationalAlert[];
  asOf?: string;
  coverage: OperationalCoverage;
}) {
  const timestamp = asOf ? new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short", timeZone: "America/Sao_Paulo" }).format(new Date(asOf)) : null;
  const emptyState =
    coverage === "full"
      ? {
          icon: CheckCircle2,
          title: "Nenhuma ocorrência identificada nos indicadores monitorados.",
          description: "Estado atual e período selecionado verificados conforme cada indicador.",
          className: "text-success-strong",
        }
      : coverage === "partial"
        ? {
            icon: Info,
            title: "Nenhuma ocorrência identificada nos indicadores disponíveis para seu perfil.",
            description: "Alguns indicadores podem estar ocultos por configuração ou permissão.",
            className: "text-muted",
          }
        : {
            icon: Info,
            title: "Indicadores operacionais indisponíveis para este perfil.",
            description: "A configuração da filial ou suas permissões não disponibilizam indicadores operacionais.",
            className: "text-muted",
          };
  const EmptyIcon = emptyState.icon;
  return (
    <section className="card overflow-hidden">
      <div className="card-header">
        <div>
          <div className="flex items-center gap-2">
            <Radio className="size-4 text-primary" />
            <h2 className="text-sm font-bold">Atenção operacional</h2>
          </div>
          <p className="mt-1 text-xs text-muted">Estado atual da filial{timestamp ? ` em ${timestamp}` : ""}, com exceções financeiras do período quando houver.</p>
        </div>
        {alerts.length ? <span className="rounded-full bg-warning/10 px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-wide text-warning-strong">{alerts.length} {alerts.length === 1 ? "alerta" : "alertas"}</span> : null}
      </div>
      {alerts.length ? (
        <div className="grid gap-2.5 p-4 sm:grid-cols-2 xl:grid-cols-3">
          {alerts.map((alert) => {
            const tones = {
              danger: "border-danger/30 bg-danger/10 text-danger-strong",
              warning: "border-warning/30 bg-warning/10 text-warning-strong",
              info: "border-primary/25 bg-primary/5 text-primary",
            };
            const content = <><CircleAlert className="mt-0.5 size-4 shrink-0" /><span className="min-w-0"><strong className="block text-xs">{alert.title}</strong><small className="mt-1 block text-[11px] leading-4 opacity-85">{alert.detail}</small><small className="mt-1 block text-[10px] font-bold uppercase tracking-wide opacity-75">{alert.reference === "period" ? "Período selecionado" : "Estado atual"}</small></span></>;
            const className = `flex gap-2.5 rounded-lg border p-3 transition ${tones[alert.tone]} ${alert.href ? "hover:brightness-95 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/20" : ""}`;
            return alert.href ? <Link key={alert.key} href={alert.href} className={className}>{content}</Link> : <div key={alert.key} className={className}>{content}</div>;
          })}
        </div>
      ) : (
        <div className={`flex items-start gap-3 px-5 py-4 text-sm ${emptyState.className}`}>
          <EmptyIcon className="mt-0.5 size-5 shrink-0" />
          <span><strong className="block">{emptyState.title}</strong><small className="mt-1 block text-xs text-muted">{emptyState.description}</small></span>
        </div>
      )}
    </section>
  );
}
