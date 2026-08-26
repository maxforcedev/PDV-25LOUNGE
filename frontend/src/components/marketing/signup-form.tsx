"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { CheckCircle2, Clock3, Eye, EyeOff, ShieldCheck } from "lucide-react";
import { Alert, Button, Field, Input, Select, Spinner } from "@/components/ui";
import { ApiError, http } from "@/lib/http";
import { fieldError } from "@/lib/format";
import type { ProvisioningResult, PublicPlan } from "@/types";

interface SignupValues {
  plan_version: string;
  trade_name: string;
  legal_name: string;
  owner_email: string;
  owner_password: string;
}

const EMPTY_VALUES: SignupValues = {
  plan_version: "",
  trade_name: "",
  legal_name: "",
  owner_email: "",
  owner_password: "",
};

function createIdempotencyKey() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return `signup-${crypto.randomUUID()}`;
  return `signup-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function SignupForm() {
  const searchParams = useSearchParams();
  const [plans, setPlans] = useState<PublicPlan[]>([]);
  const [values, setValues] = useState(EMPTY_VALUES);
  const [loadingPlans, setLoadingPlans] = useState(true);
  const [plansError, setPlansError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [result, setResult] = useState<ProvisioningResult | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const replayRef = useRef<{ fingerprint: string; key: string } | null>(null);

  useEffect(() => {
    let active = true;
    http.getPublic<PublicPlan[]>("public/plans/")
      .then((items) => {
        if (!active) return;
        setPlans(items);
        const requested = searchParams.get("plano");
        const selected = items.some((item) => String(item.id) === requested) ? requested! : String(items[0]?.id || "");
        setValues((current) => ({ ...current, plan_version: current.plan_version || selected }));
      })
      .catch((caught) => active && setPlansError(caught instanceof Error ? caught.message : "Não foi possível carregar os planos."))
      .finally(() => active && setLoadingPlans(false));
    return () => { active = false; };
  }, [searchParams]);

  function update(name: keyof SignupValues, value: string) {
    setValues((current) => ({ ...current, [name]: value }));
    setFields((current) => ({ ...current, [name]: [] }));
    setError("");
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setFields({});
    const payload = {
      plan_version: Number(values.plan_version),
      trade_name: values.trade_name.trim(),
      legal_name: values.legal_name.trim(),
      owner_email: values.owner_email.trim().toLowerCase(),
      owner_password: values.owner_password,
    };
    const fingerprint = JSON.stringify(payload);
    if (!replayRef.current || replayRef.current.fingerprint !== fingerprint) {
      replayRef.current = { fingerprint, key: createIdempotencyKey() };
    }
    try {
      const created = await http.postPublic<ProvisioningResult>("public/signup/", {
        ...payload,
        idempotency_key: replayRef.current.key,
      });
      setResult(created);
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setFields(caught.fields);
      } else setError("Não foi possível concluir o cadastro.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loadingPlans) return <div className="flex min-h-96 items-center justify-center text-primary"><Spinner className="size-7" /><span className="sr-only">Preparando cadastro</span></div>;

  if (result) {
    const pending = result.approval_status === "PENDING";
    return (
      <div className="card mx-auto max-w-xl overflow-hidden text-center">
        <div className={`px-6 py-10 ${pending ? "bg-warning-surface text-warning-strong" : "bg-success-surface text-success-strong"}`}>
          <span className="mx-auto flex size-16 items-center justify-center rounded-full bg-surface shadow-sm">{pending ? <Clock3 className="size-8" /> : <CheckCircle2 className="size-8" />}</span>
          <h1 className="mt-5 text-2xl font-black tracking-tight">{pending ? "Cadastro recebido para aprovação" : "Sua conta foi criada"}</h1>
        </div>
        <div className="p-6 sm:p-8">
          <p className="text-sm leading-7 text-muted">{pending ? "A equipe responsável analisará o cadastro. O acesso operacional será liberado após a aprovação." : "A empresa, a matriz e sua assinatura foram preparadas. Use o e-mail e a senha informados para acessar."}</p>
          <p className="mt-4 text-xs text-muted">Referência do cadastro: #{result.id}</p>
          <div className="mt-7 flex flex-col justify-center gap-3 sm:flex-row">
            {!pending && <Link href="/login" className="btn btn-primary h-11">Acessar minha conta</Link>}
            <Link href="/ajuda" className="btn btn-secondary h-11">Central de Ajuda</Link>
          </div>
        </div>
      </div>
    );
  }

  if (plansError || !plans.length) {
    return <div className="mx-auto max-w-xl"><Alert message={plansError || "Nenhum plano público está disponível para cadastro."} /><Link href="/planos" className="btn btn-secondary mt-4">Voltar aos planos</Link></div>;
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[0.72fr_1.28fr] lg:items-start">
      <aside className="lg:sticky lg:top-24">
        <p className="marketing-eyebrow">Autoatendimento</p>
        <h1 className="mt-4 text-3xl font-black tracking-[-0.04em] text-fg sm:text-4xl">Comece com os dados essenciais.</h1>
        <p className="mt-4 text-sm leading-7 text-muted">Crie a conta Owner, sua empresa e a matriz em um único fluxo. Informações complementares ficam para depois.</p>
        <div className="mt-7 space-y-3 text-xs text-muted">
          <p className="flex items-center gap-2"><ShieldCheck className="size-4 text-success-strong" />Sem cartão e sem cobrança online</p>
          <p className="flex items-center gap-2"><ShieldCheck className="size-4 text-success-strong" />Senha protegida e validação no servidor</p>
          <p className="flex items-center gap-2"><ShieldCheck className="size-4 text-success-strong" />Aprovação automática ou análise, conforme a política vigente</p>
        </div>
      </aside>

      <form onSubmit={submit} className="card p-5 sm:p-8">
        <div className="mb-7 border-b border-subtle pb-5"><h2 className="text-xl font-bold text-fg">Dados da conta e empresa</h2><p className="mt-1 text-xs leading-5 text-muted">Todos os campos abaixo são necessários para preparar o acesso inicial.</p></div>
        <div className="space-y-5">
          {error && <Alert message={error} />}
          <Field label="Plano" error={fieldError(fields, "plan_version")}><Select required value={values.plan_version} onChange={(event) => update("plan_version", event.target.value)} aria-invalid={Boolean(fieldError(fields, "plan_version"))} disabled={submitting}>{plans.map((plan) => <option key={plan.id} value={plan.id}>{plan.name}{plan.trial_days ? ` · ${plan.trial_days} dias para experimentar` : ""}</option>)}</Select></Field>
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Nome da empresa" error={fieldError(fields, "trade_name")}><Input required maxLength={150} autoComplete="organization" value={values.trade_name} onChange={(event) => update("trade_name", event.target.value)} placeholder="Como sua empresa é conhecida" aria-invalid={Boolean(fieldError(fields, "trade_name"))} disabled={submitting} /></Field>
            <Field label="Razão social" error={fieldError(fields, "legal_name")}><Input required maxLength={200} value={values.legal_name} onChange={(event) => update("legal_name", event.target.value)} placeholder="Nome empresarial" aria-invalid={Boolean(fieldError(fields, "legal_name"))} disabled={submitting} /></Field>
          </div>
          <Field label="E-mail do Owner" error={fieldError(fields, "owner_email")}><Input required type="email" autoComplete="email" value={values.owner_email} onChange={(event) => update("owner_email", event.target.value)} placeholder="voce@empresa.com.br" aria-invalid={Boolean(fieldError(fields, "owner_email"))} disabled={submitting} /><span className="mt-1.5 block text-[11px] text-muted">Este e-mail será usado para entrar e administrar a assinatura.</span></Field>
          <Field label="Senha" error={fieldError(fields, "owner_password")}><div className="relative"><Input required type={showPassword ? "text" : "password"} autoComplete="new-password" value={values.owner_password} onChange={(event) => update("owner_password", event.target.value)} className="pr-11" aria-invalid={Boolean(fieldError(fields, "owner_password"))} disabled={submitting} /><button type="button" className="icon-button absolute right-0.5 top-1/2 -translate-y-1/2" onClick={() => setShowPassword((current) => !current)} aria-label={showPassword ? "Ocultar senha" : "Exibir senha"}>{showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}</button></div><span className="mt-1.5 block text-[11px] leading-5 text-muted">Use uma senha forte, diferente do e-mail e de dados fáceis de identificar.</span></Field>
        </div>
        <div className="mt-7 flex flex-col-reverse gap-3 border-t border-subtle pt-6 sm:flex-row sm:items-center sm:justify-between">
          <Link href="/planos" className="text-center text-xs font-semibold text-muted hover:text-fg">Comparar planos</Link>
          <Button type="submit" loading={submitting} className="h-11 sm:min-w-48">Criar minha conta</Button>
        </div>
      </form>
    </div>
  );
}
