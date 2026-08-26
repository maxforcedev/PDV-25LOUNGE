"use client";

import { Headphones, Plus } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { SupportAccessActions, SupportSessionCreated } from "@/components/support-access";
import { CriticalFields, Empty, ErrorBlock, LoadingBlock, Modal, Notice, Status } from "@/components/ui";
import { api } from "@/lib/api";
import { dateTime } from "@/lib/format";
import type { SupportSession } from "@/lib/types";
import { useAuth } from "@/providers/auth-provider";

export default function SupportPage() {
  const { can } = useAuth();
  const allowed = can("platform.support.manage");
  const [sessions, setSessions] = useState<SupportSession[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [company, setCompany] = useState("");
  const [impersonatedUser, setImpersonatedUser] = useState("");
  const [mode, setMode] = useState("READ_ONLY");
  const [reason, setReason] = useState("");
  const [password, setPassword] = useState("");
  const [created, setCreated] = useState<SupportSession | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!allowed) return;
    let active = true;
    api.list<SupportSession>("platform/support-sessions/")
      .then((value) => { if (active) { setSessions(value); setError(null); } })
      .catch((value) => { if (active) setError(value); });
    return () => { active = false; };
  }, [allowed, reload]);

  function openCreate() {
    setCompany(""); setImpersonatedUser(""); setMode("READ_ONLY"); setReason(""); setPassword(""); setActionError(null); setCreating(true);
  }

  async function create(event: FormEvent) {
    event.preventDefault(); setSaving(true); setActionError(null);
    try {
      const session = await api.post<SupportSession>("platform/support-sessions/", { company: Number(company), impersonated_user: impersonatedUser ? Number(impersonatedUser) : null, mode, reason, current_password: password });
      setCreated(session); setCreating(false); setNotice(`Support Session #${session.id} criada.`); setReload((value) => value + 1);
    } catch (value) { setActionError(value); } finally { setSaving(false); }
  }

  async function end(sessionId: number) {
    try { await api.post(`platform/support-sessions/${sessionId}/end/`); setNotice(`Support Session #${sessionId} encerrada.`); setReload((value) => value + 1); } catch (value) { setError(value); }
  }

  if (!allowed) return <ErrorBlock error={new Error("Seu perfil nao possui acesso a Support Sessions.")} />;
  if (error) return <ErrorBlock error={error} retry={() => { setError(null); setSessions(null); setReload((value) => value + 1); }} />;
  if (!sessions) return <LoadingBlock label="Carregando Support Sessions" />;

  return <div className="enter space-y-6"><div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="eyebrow">Acesso temporario</p><h1 className="mt-2 text-3xl font-black tracking-tight sm:text-4xl">Support Sessions</h1><p className="mt-2 text-sm text-steel/65">Abertura, acesso ao Backoffice e encerramento auditado por tenant.</p></div><button className="btn btn-signal" onClick={openCreate}><Plus size={15} />Iniciar sessao</button></div>{notice && <Notice message={notice} />}{created && <SupportSessionCreated session={created} />}<section className="panel"><div className="panel-head"><div><p className="eyebrow">Historico global</p><h2 className="mt-1 font-bold">Sessoes</h2></div><Headphones size={18} className="text-steel/45" /></div>{sessions.length === 0 ? <Empty title="Sem sessoes de suporte" detail="Inicie uma sessao informando o ID do tenant alvo." /> : <div className="divide-y divide-line">{sessions.map((session) => { const active = !session.ended_at && new Date(session.expires_at) > new Date(); return <div className="grid gap-4 p-5 lg:grid-cols-[1fr_auto] lg:items-center" key={session.id}><div><div className="flex flex-wrap items-center gap-2"><Status value={active ? "ACTIVE" : session.ended_at ? "ENDED" : "EXPIRED"} /><span className="font-mono text-[10px] font-bold uppercase">{session.mode.replace("_", " ")}</span><span className="font-mono text-[10px] text-steel/50">TENANT #{session.company}</span></div><p className="mt-3 text-sm">{session.reason}</p><p className="mt-2 text-xs text-steel/55">{session.actor_email} / expira {dateTime(session.expires_at)}</p></div>{active && <div className="flex flex-wrap gap-2"><SupportAccessActions sessionId={session.id} /><button className="btn btn-danger" onClick={() => void end(session.id)}>Encerrar</button></div>}</div>; })}</div>}</section>
    {creating && <Modal title="Iniciar Support Session" description="Informe o tenant diretamente; nenhuma consulta de tenants sera feita sem permissao." onClose={() => setCreating(false)}><form onSubmit={create}><div className="grid gap-4 p-5 sm:grid-cols-2"><Field label="ID do tenant"><input className="input" type="number" min="1" value={company} onChange={(event) => setCompany(event.target.value)} required /></Field><Field label="Modo"><select className="input" value={mode} onChange={(event) => setMode(event.target.value)}><option value="READ_ONLY">Somente leitura</option><option value="READ_WRITE">Leitura e escrita</option></select></Field><Field label="ID do usuario impersonado (opcional)"><input className="input" type="number" min="1" value={impersonatedUser} onChange={(event) => setImpersonatedUser(event.target.value)} /></Field></div>{actionError ? <div className="px-5 pb-4"><ErrorBlock error={actionError} /></div> : null}<CriticalFields reason={reason} password={password} onReason={setReason} onPassword={setPassword} error={actionError} /><div className="flex justify-end gap-2 p-5"><button type="button" className="btn btn-quiet" onClick={() => setCreating(false)}>Cancelar</button><button className="btn btn-signal" disabled={saving || !company || !reason || !password}>{saving ? "Iniciando..." : "Criar sessao"}</button></div></form></Modal>}
  </div>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) { return <div className="field"><label>{label}</label>{children}</div>; }
