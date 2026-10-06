"use client";

import Link from "next/link";
import { ArrowRight, Search, UsersRound } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { Empty, ErrorBlock, LoadingBlock } from "@/components/ui";
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

export default function LeadsPage() {
  const { can } = useAuth();
  const allowed = can("platform.leads.manage");
  const [leads, setLeads] = useState<CommercialLead[] | null>(null);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<"" | CommercialLeadStatus>("");
  const [filters, setFilters] = useState({ search: "", status: "" });
  const [error, setError] = useState<unknown>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!allowed) return;
    let active = true;
    const params = new URLSearchParams();
    if (filters.search) params.set("search", filters.search);
    if (filters.status) params.set("status", filters.status);
    const suffix = params.toString() ? `?${params}` : "";
    api.get<CommercialLead[]>(`platform/leads/${suffix}`)
      .then((value) => { if (active) { setLeads(value); setError(null); } })
      .catch((value) => { if (active) setError(value); });
    return () => { active = false; };
  }, [allowed, filters, reload]);

  function applyFilters(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setLeads(null);
    setFilters({ search: search.trim(), status });
  }

  if (!allowed) return <ErrorBlock error={new Error("Seu perfil nao possui acesso aos leads comerciais.")} />;
  return <div className="enter space-y-6">
    <div><p className="eyebrow">Operacao comercial</p><h1 className="mt-2 text-3xl font-black tracking-tight sm:text-4xl">Leads</h1><p className="mt-2 text-sm text-steel/65">Contatos recebidos pelo site e acompanhamento do funil comercial.</p></div>
    <section className="panel"><div className="panel-head"><form className="flex w-full flex-col gap-2 sm:flex-row" onSubmit={applyFilters}><div className="relative flex-1"><Search className="absolute left-3 top-3 text-steel/45" size={16} /><input className="input pl-9" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Nome, empresa, e-mail ou WhatsApp" aria-label="Pesquisar leads" /></div><select className="input sm:max-w-44" value={status} onChange={(event) => setStatus(event.target.value as "" | CommercialLeadStatus)} aria-label="Filtrar por status"><option value="">Todos os status</option>{(Object.keys(statusLabels) as CommercialLeadStatus[]).map((value) => <option value={value} key={value}>{statusLabels[value]}</option>)}</select><button className="btn btn-primary">Filtrar</button></form><span className="hidden items-center gap-2 font-mono text-[10px] uppercase text-steel/50 lg:flex"><UsersRound size={15} />{leads?.length ?? "-"} registros</span></div>
      {error ? <div className="p-5"><ErrorBlock error={error} retry={() => { setError(null); setLeads(null); setReload((value) => value + 1); }} /></div> : !leads ? <LoadingBlock label="Consultando leads" /> : leads.length === 0 ? <Empty title="Nenhum lead encontrado" detail="Revise os filtros aplicados ou aguarde novos contatos pelo site." /> : <div className="table-wrap"><table className="data-table"><thead><tr><th>Nome</th><th>Empresa</th><th>WhatsApp</th><th>E-mail</th><th>Segmento</th><th>Plano</th><th>Origem</th><th>Data</th><th>Status</th><th /></tr></thead><tbody>{leads.map((lead) => <tr key={lead.id}><td className="font-bold">{lead.name}</td><td>{lead.company_name}</td><td>{lead.whatsapp}</td><td>{lead.email}</td><td>{lead.segment}</td><td>{lead.plan_interest || "-"}</td><td className="max-w-36 truncate" title={lead.source_path}>{lead.source_path || "-"}</td><td className="whitespace-nowrap text-xs">{dateTime(lead.created_at)}</td><td><span className="status border-line bg-[#e8ebe7] text-steel">{statusLabels[lead.status]}</span></td><td className="text-right"><Link href={`/leads/${lead.id}`} className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-wider hover:underline">Abrir <ArrowRight size={15} /></Link></td></tr>)}</tbody></table></div>}
    </section>
  </div>;
}
