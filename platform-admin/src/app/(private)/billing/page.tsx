"use client";

import Link from "next/link";
import { ArrowRight, CreditCard } from "lucide-react";
import { useEffect, useState } from "react";
import { Empty, ErrorBlock, LoadingBlock } from "@/components/ui";
import { api } from "@/lib/api";
import { dateTime, money } from "@/lib/format";
import type { Payment, Subscription } from "@/lib/types";
import { useAuth } from "@/providers/auth-provider";

export default function BillingPage() {
  const { can } = useAuth();
  const allowed = can("platform.billing.manage");
  const [payments, setPayments] = useState<Payment[] | null>(null);
  const [subscriptions, setSubscriptions] = useState<Subscription[] | null>(null);
  const [paymentsError, setPaymentsError] = useState<unknown>(null);
  const [subscriptionsError, setSubscriptionsError] = useState<unknown>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!allowed) return;
    let active = true;
    api.list<Payment>("platform/payments/")
      .then((value) => { if (active) { setPayments(value); setPaymentsError(null); } })
      .catch((value) => { if (active) setPaymentsError(value); });
    return () => { active = false; };
  }, [allowed, reload]);

  useEffect(() => {
    if (!allowed) return;
    let active = true;
    api.list<Subscription>("platform/subscriptions/")
      .then((value) => { if (active) { setSubscriptions(value); setSubscriptionsError(null); } })
      .catch((value) => { if (active) setSubscriptionsError(value); });
    return () => { active = false; };
  }, [allowed, reload]);

  if (!allowed) return <ErrorBlock error={new Error("Seu perfil nao possui acesso a cobranca.")} />;

  return <div className="enter space-y-6"><div><p className="eyebrow">Operacao financeira</p><h1 className="mt-2 text-3xl font-black tracking-tight sm:text-4xl">Cobranca</h1><p className="mt-2 text-sm text-steel/65">Assinaturas e historico financeiro sem acesso aos dados de gestao do tenant.</p></div><section className="panel"><div className="panel-head"><div><p className="eyebrow">Contratos correntes e historicos</p><h2 className="mt-1 font-bold">Assinaturas</h2></div><div className="flex items-center gap-2 font-mono text-[10px] uppercase text-steel/50"><CreditCard size={15} />{subscriptions?.length ?? "-"} registros</div></div>{subscriptionsError ? <div className="p-5"><ErrorBlock error={subscriptionsError} retry={() => { setSubscriptionsError(null); setSubscriptions(null); setReload((value) => value + 1); }} /></div> : !subscriptions ? <LoadingBlock label="Carregando assinaturas" /> : subscriptions.length === 0 ? <Empty title="Nenhuma assinatura encontrada" detail="Nao existem contratos acessiveis para cobranca." /> : <div className="table-wrap"><table className="data-table"><thead><tr><th>Assinatura</th><th>Tenant</th><th>Plano</th><th>Estado</th><th>Periodo</th><th /></tr></thead><tbody>{subscriptions.map((subscription) => <tr key={subscription.id}><td className="font-mono text-xs">#{subscription.id}</td><td className="font-mono text-xs">Tenant #{subscription.company}</td><td><p className="font-bold">{subscription.plan_name}</p><p className="text-xs text-steel/50">v{subscription.plan_version_number} / {subscription.billing_mode}</p></td><td>{subscription.status.replaceAll("_", " ")}</td><td><span className="text-xs">{dateTime(subscription.current_period_start)}</span><br /><span className="text-xs text-steel/50">ate {dateTime(subscription.current_period_end)}</span></td><td className="text-right"><Link className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-wider hover:underline" href={`/billing/subscriptions/${subscription.id}`}>Abrir cobranca <ArrowRight size={14} /></Link></td></tr>)}</tbody></table></div>}</section><section className="panel"><div className="panel-head"><div><p className="eyebrow">Registros confirmados</p><h2 className="mt-1 font-bold">Pagamentos</h2></div><div className="flex items-center gap-2 font-mono text-[10px] uppercase text-steel/50"><CreditCard size={15} />{payments?.length ?? "-"} registros</div></div>{paymentsError ? <div className="p-5"><ErrorBlock error={paymentsError} retry={() => { setPaymentsError(null); setPayments(null); setReload((value) => value + 1); }} /></div> : !payments ? <LoadingBlock label="Carregando historico financeiro" /> : payments.length === 0 ? <Empty title="Nenhum pagamento registrado" detail="Os pagamentos confirmados aparecerao aqui." /> : <div className="table-wrap"><table className="data-table"><thead><tr><th>Pagamento</th><th>Assinatura</th><th>Competencia exata</th><th>Metodo</th><th>Operador</th></tr></thead><tbody>{payments.map((payment) => <tr key={payment.id}><td><p className="font-black">{money(payment.amount)}</p><p className="text-xs text-steel/55">{dateTime(payment.paid_at)}</p></td><td><Link className="font-mono text-xs font-bold hover:underline" href={`/billing/subscriptions/${payment.subscription}`}>#{payment.subscription}</Link></td><td><span className="text-xs">{dateTime(payment.competency_start)}</span><br /><span className="text-xs text-steel/50">ate {dateTime(payment.competency_end)}</span></td><td>{payment.payment_method}</td><td className="text-xs">{payment.actor_email}</td></tr>)}</tbody></table></div>}</section></div>;
}
