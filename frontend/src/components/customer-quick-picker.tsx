"use client";

import { useEffect, useState } from "react";
import { Plus, Search, X } from "lucide-react";
import { Alert, Button, Field, Input, Modal, Select, Spinner } from "@/components/ui";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { Customer } from "@/types";

export function CustomerQuickPicker({ value, onChange, disabled = false }: { value: Customer | null; onChange: (customer: Customer | null) => void; disabled?: boolean }) {
  const { currentCompany, hasPermission, supportSession } = useAuth();
  const canView = hasPermission(permissions.viewCustomer);
  const canAdd = hasPermission(permissions.addCustomer) && supportSession?.mode !== "READ_ONLY";
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => { setQuery(""); setResults([]); setError(""); }, [currentCompany?.id]);
  useEffect(() => {
    if (!canView || !currentCompany || query.trim().length < 2) { setResults([]); return; }
    const timer = window.setTimeout(() => {
      setLoading(true); setError("");
      http.get<{ results: Customer[] }>(`customers/search/?company=${currentCompany.id}&q=${encodeURIComponent(query.trim())}&limit=20&status=active`)
        .then((response) => setResults(response.results))
        .catch((caught) => setError(caught instanceof ApiError ? caught.message : "Não foi possível buscar clientes."))
        .finally(() => setLoading(false));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [canView, currentCompany, query]);

  async function create() {
    if (!currentCompany || !name.trim()) return;
    setSaving(true); setError("");
    try {
      const customer = await http.post<Customer>("customers/", { company: currentCompany.id, name: name.trim(), phone });
      onChange(customer); setCreateOpen(false); setName(""); setPhone(""); setQuery(""); setResults([]);
    } catch (caught) { setError(caught instanceof ApiError ? caught.message : "Não foi possível criar o cliente."); }
    finally { setSaving(false); }
  }

  if (!canView) return null;
  return <div className="space-y-2">
    {value ? <div className="flex items-center justify-between gap-2 rounded-md border border-primary/20 bg-primary/5 p-2 text-xs"><span><strong>{value.name}</strong>{value.phone ? ` · ${value.phone}` : ""}</span>{!disabled && <button type="button" className="icon-button size-7" onClick={() => onChange(null)} aria-label="Remover cliente"><X className="size-3.5" /></button>}</div> : <>
      <div className="flex gap-2"><div className="relative flex-1"><Search className="absolute left-2.5 top-2.5 size-4 text-muted" /><Input className="h-9 pl-8" value={query} onChange={(event) => setQuery(event.target.value)} disabled={disabled} placeholder="Buscar cliente" /></div>{canAdd && <Button type="button" variant="secondary" className="h-9" disabled={disabled} onClick={() => { setError(""); setCreateOpen(true); }}><Plus className="size-4" />Novo</Button>}</div>
      {loading && <div className="flex items-center gap-2 text-xs text-muted"><Spinner />Buscando clientes...</div>}
      {results.length > 0 && <Select className="h-9" value="" disabled={disabled} onChange={(event) => { const customer = results.find((item) => item.id === Number(event.target.value)); if (customer) onChange(customer); }}><option value="">Selecionar cliente</option>{results.map((customer) => <option key={customer.id} value={customer.id}>{customer.name}{customer.phone ? ` · ${customer.phone}` : ""}</option>)}</Select>}
    </>}
    {error && <Alert message={error} />}
    <Modal open={createOpen} title="Novo cliente" description="Cadastre sem sair da operação." onClose={() => setCreateOpen(false)}><div className="space-y-4 p-5"><Field label="Nome"><Input autoFocus value={name} onChange={(event) => setName(event.target.value)} disabled={saving} /></Field><Field label="Telefone"><Input value={phone} onChange={(event) => setPhone(event.target.value)} disabled={saving} inputMode="tel" /></Field>{error && <Alert message={error} />}<div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setCreateOpen(false)}>Cancelar</Button><Button type="button" loading={saving} onClick={() => void create()}>Criar e selecionar</Button></div></div></Modal>
  </div>;
}
