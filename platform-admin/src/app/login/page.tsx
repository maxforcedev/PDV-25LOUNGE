"use client";

import { ArrowRight, LockKeyhole } from "lucide-react";
import { FormEvent, useState } from "react";
import { ErrorBlock } from "@/components/ui";
import { useAuth } from "@/providers/auth-provider";

export default function LoginPage() {
  const { login, loading, user } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(event: FormEvent) {
    event.preventDefault(); setSubmitting(true); setError(null);
    try { await login(email, password); } catch (value) { setError(value); } finally { setSubmitting(false); }
  }

  if (loading || user) return <div className="flex min-h-screen items-center justify-center bg-ink"><div className="spinner text-signal" /></div>;
  return <main className="grid min-h-screen bg-ink lg:grid-cols-[1.05fr_.95fr]">
    <section className="core-grid relative hidden overflow-hidden border-r border-white/10 p-12 text-white lg:flex lg:flex-col lg:justify-between"><div><div className="flex items-center gap-3"><span className="size-3 bg-signal" /><span className="text-2xl font-black tracking-tight">CORE</span></div><p className="mt-2 font-mono text-[10px] uppercase tracking-[.22em] text-white/45">Platform command system / V2.2</p></div><div className="max-w-xl"><p className="eyebrow !text-signal">Restricted operations</p><h1 className="mt-4 text-5xl font-black leading-[.98] tracking-[-.04em]">Controle da plataforma.<br />Sem atalhos.</h1><p className="mt-6 max-w-md text-sm leading-6 text-white/55">Provisionamento, governanca comercial, cobranca e suporte controlado em uma superficie separada do produto.</p></div><div className="grid grid-cols-3 border-y border-white/10 py-5 font-mono text-[9px] uppercase tracking-wider text-white/40"><span>Audit trail</span><span>CSRF enforced</span><span>Reauth required</span></div></section>
    <section className="flex items-center justify-center bg-canvas p-5 sm:p-10"><div className="w-full max-w-md"><div className="mb-10 lg:hidden"><div className="flex items-center gap-2"><span className="size-2.5 bg-signal outline outline-1 outline-ink" /><span className="text-xl font-black">CORE</span></div><p className="mt-1 font-mono text-[9px] uppercase tracking-[.2em] text-steel/55">Platform operations</p></div><div className="panel"><div className="border-b border-line p-6 sm:p-8"><div className="flex size-10 items-center justify-center bg-ink text-signal"><LockKeyhole size={19} /></div><p className="eyebrow mt-6">Identificacao de operador</p><h2 className="mt-2 text-2xl font-black tracking-tight">Acesso administrativo</h2><p className="mt-2 text-sm text-steel/65">Use exclusivamente sua credencial de plataforma.</p></div><form onSubmit={submit}><div className="grid gap-5 p-6 sm:p-8">{error ? <ErrorBlock error={error} /> : null}<div className="field"><label htmlFor="email">E-mail corporativo</label><input id="email" className="input" type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="username" required autoFocus /></div><div className="field"><label htmlFor="password">Senha</label><input id="password" className="input" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required /></div><button className="btn btn-signal mt-2 w-full" disabled={submitting}>{submitting ? <><span className="spinner" />Validando</> : <>Entrar no CORE <ArrowRight size={16} /></>}</button></div></form></div><p className="mt-5 text-center font-mono text-[9px] uppercase tracking-wider text-steel/50">Acoes administrativas sao registradas e auditaveis</p></div></section>
  </main>;
}
