"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Building2, Check, RefreshCw, Users } from "lucide-react";
import { Alert, Spinner } from "@/components/ui";
import { formatBRL } from "@/lib/format";
import { http } from "@/lib/http";
import type { PublicPlan } from "@/types";

function limitLabel(limit: PublicPlan["limits"]["users"], singular: string, plural: string) {
  if (limit.unlimited) return `${plural} ilimitados`;
  return `${limit.value ?? 0} ${(limit.value ?? 0) === 1 ? singular : plural}`;
}

export function PlansCatalog() {
  const [plans, setPlans] = useState<PublicPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  function load() {
    setLoading(true);
    setError("");
    http.getPublic<PublicPlan[]>("public/plans/")
      .then(setPlans)
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Não foi possível carregar os planos."))
      .finally(() => setLoading(false));
  }

  useEffect(() => load(), []);

  if (loading) {
    return <div className="flex min-h-72 items-center justify-center text-primary"><Spinner className="size-7" /><span className="sr-only">Carregando planos</span></div>;
  }

  if (error) {
    return <div className="mx-auto max-w-xl py-12"><Alert message={error} /><button type="button" className="btn btn-secondary mx-auto mt-4 flex" onClick={load}><RefreshCw className="size-4" />Tentar novamente</button></div>;
  }

  if (!plans.length) {
    return <div className="card mx-auto max-w-xl p-8 text-center"><h2 className="text-lg font-bold text-fg">Novas adesões temporariamente indisponíveis</h2><p className="mt-2 text-sm leading-6 text-muted">Nenhum plano público está disponível neste momento. Consulte a Central de Ajuda para outros canais de contato.</p><Link href="/ajuda" className="btn btn-secondary mt-6">Abrir Central de Ajuda</Link></div>;
  }

  return (
    <div className={`grid gap-5 ${plans.length > 2 ? "lg:grid-cols-3" : "mx-auto max-w-4xl md:grid-cols-2"}`}>
      {plans.map((plan, index) => (
        <article key={plan.id} className={`card relative flex flex-col overflow-hidden p-6 sm:p-7 ${index === 0 ? "border-primary/35 shadow-[0_18px_50px_rgba(52,84,209,0.10)]" : ""}`}>
          {index === 0 && <span className="absolute right-0 top-0 rounded-bl-xl bg-primary px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-wider text-white">Disponível</span>}
          <div className="pr-16">
            <p className="marketing-eyebrow">{plan.code}</p>
            <h2 className="mt-3 text-2xl font-black tracking-tight text-fg">{plan.name}</h2>
          </div>
          <p className="mt-4 min-h-12 text-[13px] leading-6 text-muted">{plan.description || "Controle operacional conectado para sua empresa."}</p>
          <div className="mt-6 border-y border-subtle py-5">
            <div className="flex items-end gap-2"><strong className="text-3xl font-black tracking-[-0.04em] text-fg">{formatBRL(plan.price)}</strong><span className="pb-1 text-xs text-muted">/{plan.billing_period_months === 1 ? "mês" : `${plan.billing_period_months} meses`}</span></div>
            {plan.trial_days > 0 && <p className="mt-2 text-xs font-semibold text-success-strong">{plan.trial_days} dias para experimentar, sem cartão</p>}
          </div>
          <ul className="mt-6 flex-1 space-y-3 text-sm text-fg">
            <li className="flex items-center gap-3"><span className="flex size-7 items-center justify-center rounded-full bg-info-surface text-info-strong"><Users className="size-3.5" /></span>{limitLabel(plan.limits.users, "usuário", "usuários")}</li>
            <li className="flex items-center gap-3"><span className="flex size-7 items-center justify-center rounded-full bg-info-surface text-info-strong"><Building2 className="size-3.5" /></span>{limitLabel(plan.limits.branches, "filial", "filiais")}</li>
            <li className="flex items-center gap-3"><span className="flex size-7 items-center justify-center rounded-full bg-success-surface text-success-strong"><Check className="size-3.5" /></span>Cadastro sem cartão ou gateway</li>
          </ul>
          <Link href={`/cadastro?plano=${plan.id}`} className="btn btn-primary mt-7 h-12 w-full rounded-xl">Escolher {plan.name}<ArrowRight className="size-4" /></Link>
        </article>
      ))}
    </div>
  );
}
