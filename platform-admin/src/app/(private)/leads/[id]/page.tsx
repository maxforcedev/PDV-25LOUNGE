"use client";

import Link from "next/link";
import { ArrowLeft, BriefcaseBusiness } from "lucide-react";
import { useParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { ErrorBlock, LoadingBlock, Notice } from "@/components/ui";
import { api } from "@/lib/api";
import { dateTime } from "@/lib/format";
import type { CommercialLead, CommercialLeadStatus } from "@/lib/types";
import { useAuth } from "@/providers/auth-provider";

const statusLabels: Record<CommercialLeadStatus, string> = {
  NEW: "Novo",
  CONTACTED: "Contatado",
  QUALIFIED: "Qualificado",
  CONVERTED: "Convertido",
  LOST: "Perdido",
};

export default function LeadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const allowed = can("platform.leads.manage");
  const [lead, setLead] = useState<CommercialLead | null>(null);
  const [selectedStatus, setSelectedStatus] = useState<CommercialLeadStatus | "">("");
  const [error, setError] = useState<unknown>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!allowed) return;
    let active = true;
    api.get<CommercialLead>(`platform/leads/${id}/`)
      .then((value) => { if (active) { setLead(value); setSelectedStatus(value.status); setError(null); } })
      .catch((value) => { if (active) setError(value); });
    return () => { active = false; };
  }, [allowed, id, reload]);

  async function changeStatus(event: FormEvent) {
    event.preventDefault();
    if (!lead || !selectedStatus || selectedStatus === lead.status) return;
    setSaving(true); setActionError(null);
    try {
      const updated = await api.post<CommercialLead>(`platform/leads/${lead.id}/status/`, { status: selectedStatus });
      setLead(updated); setSelectedStatus(updated.status); setNotice("Status do lead atualizado e auditado.");
    } catch (value) { setActionError(value); } finally { setSaving(false); }
  }

  if (!allowed) return <ErrorBlock error={new Error("Seu perfil nao possui acesso aos leads comerciais.")} />;
  if (error) return <ErrorBlock error={error} retry={() => { setError(null); setLead(null); setReload((value) => value + 1); }} />;
  if (!lead) return <LoadingBlock label="Carregando lead" />;
  return <div className="enter space-y-6">
    <Link href="/leads" className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-steel/65 hover:text-ink"><ArrowLeft size={15} />Todos os leads</Link>
    <header className="border border-ink bg-ink p-5 text-white sm:p-7"><div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end"><div><div className="flex items-center gap-3"><span className="flex size-10 items-center justify-center bg-signal text-ink"><BriefcaseBusiness size={19} /></span><div><p className="font-mono text-[9px] uppercase tracking-[.15em] text-white/45">Lead #{lead.id}</p><h1 className="text-2xl font-black tracking-tight sm:text-3xl">{lead.name}</h1></div></div><p className="mt-4 text-sm text-white/55">{lead.company_name} / recebido em {dateTime(lead.created_at)}</p></div><span className="status border-white/15 bg-white/10 text-white">{statusLabels[lead.status]}</span></div></header>
    {notice && <Notice message={notice} />}
    <div className="grid gap-6 xl:grid-cols-[1fr_360px]"><div className="space-y-6"><section className="panel"><div className="panel-head"><div><p className="eyebrow">Contato</p><h2 className="mt-1 font-bold">Dados do interessado</h2></div></div><div className="grid gap-px bg-line sm:grid-cols-2"><Datum label="Empresa" value={lead.company_name} /><Datum label="Segmento" value={lead.segment} /><Datum label="WhatsApp" value={lead.whatsapp} /><Datum label="E-mail" value={lead.email} /><Datum label="Plano de interesse" value={lead.plan_interest} /><Datum label="Pagina de origem" value={lead.source_path} /></div></section><section className="panel"><div className="panel-head"><div><p className="eyebrow">Mensagem</p><h2 className="mt-1 font-bold">Contexto enviado</h2></div></div><p className="whitespace-pre-wrap p-5 text-sm leading-6 text-steel/80">{lead.message || "Nenhuma mensagem informada."}</p></section><section className="panel"><div className="panel-head"><div><p className="eyebrow">Atribuicao</p><h2 className="mt-1 font-bold">UTMs</h2></div></div><div className="grid gap-px bg-line sm:grid-cols-3"><Datum label="Source" value={lead.utm_source} /><Datum label="Medium" value={lead.utm_medium} /><Datum label="Campaign" value={lead.utm_campaign} /></div></section></div>
      <aside className="panel self-start"><div className="panel-head"><div><p className="eyebrow">Funil comercial</p><h2 className="mt-1 font-bold">Status</h2></div></div><form className="space-y-4 p-5" onSubmit={changeStatus}><div className="field"><label htmlFor="lead-status">Status atual</label><select id="lead-status" className="input" value={selectedStatus} onChange={(event) => setSelectedStatus(event.target.value as CommercialLeadStatus)}>{(Object.keys(statusLabels) as CommercialLeadStatus[]).map((value) => <option value={value} key={value}>{statusLabels[value]}</option>)}</select></div>{actionError ? <ErrorBlock error={actionError} /> : null}<button className="btn btn-signal w-full" disabled={saving || selectedStatus === lead.status}>{saving ? "Atualizando..." : "Atualizar status"}</button><p className="text-xs text-steel/60">Cada alteracao de status e registrada no trilho de auditoria.</p></form></aside>
    </div>
  </div>;
}

function Datum({ label, value }: { label: string; value: string }) {
  return <div className="bg-paper p-5"><p className="eyebrow">{label}</p><p className="mt-2 break-words text-sm font-semibold">{value || "-"}</p></div>;
}
