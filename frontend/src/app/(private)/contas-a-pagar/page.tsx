"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Banknote, Eye, Search, SlidersHorizontal, WalletCards, XCircle } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import { PeriodFilter, type PeriodValue } from "@/components/period-filter";
import { Alert, Button, EmptyState, Field, Input, Modal, Select, TableLoading, Textarea } from "@/components/ui";
import { formatBRL, formatDate } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { centsText, inDatePeriod, moneyCents, payableStatusLabels } from "@/lib/purchases";
import { useAuth } from "@/providers/auth-provider";
import type { PayableInstallment, PayableInstallmentStatus, Supplier } from "@/types";

type Filters = { supplier: string; status: string; purchase: string; period: PeriodValue };
const emptyFilters = (): Filters => ({ supplier: "", status: "", purchase: "", period: { start: "", end: "" } });

function PayableBadge({ status }: { status: PayableInstallmentStatus }) {
  const tone = status === "PAID" ? "bg-success/10 text-success-strong" : status === "CANCELLED" ? "bg-danger/10 text-danger-strong" : "bg-warning/15 text-warning-strong";
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-semibold ${tone}`}>{payableStatusLabels[status]}</span>;
}

function PurchasePayables() {
  const { currentBranch, currentCompany, supportSession } = useAuth();
  const companyId = currentCompany?.id;
  const branchId = currentBranch?.id;
  const readOnly = supportSession?.mode === "READ_ONLY";
  const [items, setItems] = useState<PayableInstallment[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [draft, setDraft] = useState<Filters>(emptyFilters);
  const [applied, setApplied] = useState<Filters>(emptyFilters);
  const [selected, setSelected] = useState<PayableInstallment | null>(null);
  const [action, setAction] = useState<"pay" | "cancel" | null>(null);
  const [text, setText] = useState("");
  const [paymentMethod, setPaymentMethod] = useState("PIX");
  const [paidAmount, setPaidAmount] = useState("");
  const [paidDate, setPaidDate] = useState("");
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const context = useRef("");
  context.current = `${currentCompany?.id || ""}:${currentBranch?.id || ""}`;

  async function load(selectedFilters = applied, key = context.current) {
    if (!currentBranch) { setItems([]); setLoading(false); return; }
    setLoading(true); setError("");
    const params = new URLSearchParams();
    if (selectedFilters.supplier) params.set("supplier", selectedFilters.supplier);
    if (selectedFilters.status) params.set("status", selectedFilters.status);
    try {
      const result = await http.getAll<PayableInstallment>(`payable-installments/?${params}`);
      const purchase = selectedFilters.purchase.trim().toLocaleLowerCase("pt-BR");
      if (context.current === key) setItems(result.filter((item) => (!purchase || item.order_number.toLocaleLowerCase("pt-BR").includes(purchase)) && inDatePeriod(`${item.due_date}T12:00:00`, selectedFilters.period.start, selectedFilters.period.end)));
    } catch (caught) { if (context.current === key) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as contas a pagar."); }
    finally { if (context.current === key) setLoading(false); }
  }
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    const key = context.current; const selectedFilters = emptyFilters();
    setDraft(selectedFilters); setApplied(selectedFilters); setItems([]); setSuppliers([]); setError(""); setSuccess("");
    if (!branchId || !companyId) { setLoading(false); return; }
    void loadRef.current(selectedFilters, key);
    let active = true;
    http.getAll<Supplier>(`suppliers/?company=${companyId}&status=active`).then((result) => { if (active && context.current === key) setSuppliers(result); }).catch(() => { if (active) setSuppliers([]); });
    return () => { active = false; };
  }, [branchId, companyId]);

  function apply(event: React.FormEvent) { event.preventDefault(); const next = { ...draft, period: { ...draft.period } }; setApplied(next); void load(next); }
  function clear() { const next = emptyFilters(); setDraft(next); setApplied(next); void load(next); }
  function open(item: PayableInstallment, next: "pay" | "cancel") { if (readOnly) return; setSelected(item); setAction(next); setText(""); setPaymentMethod("PIX"); setPaidAmount(item.amount); setPaidDate(new Date().toISOString().slice(0, 10)); setError(""); }
  async function submit(event: React.FormEvent) {
    event.preventDefault(); if (!selected || !action || readOnly) return;
    if (action === "cancel" && text.trim().length < 3) { setError("Informe um motivo com ao menos 3 caracteres."); return; }
    setActing(true); setError(""); setSuccess("");
    try {
      await http.post<PayableInstallment>(`payable-installments/${selected.id}/${action}/`, action === "pay" ? { payment_method: paymentMethod, paid_amount: paidAmount.replace(",", "."), paid_date: paidDate, notes: text.trim() } : { reason: text.trim() });
      setSelected(null); setAction(null); setSuccess(action === "pay" ? "Pagamento manual registrado." : "Parcela cancelada."); await load();
    } catch (caught) { setError(caught instanceof ApiError ? caught.message : "Não foi possível concluir a ação."); }
    finally { setActing(false); }
  }

  const pendingTotal = items.filter((item) => item.status === "PENDING").reduce((sum, item) => sum + moneyCents(item.amount), BigInt(0));
  return <>
    <PageHeader title="Contas a pagar" description={`${currentBranch?.name || "Selecione uma filial"} · somente parcelas originadas em compras.`} />
    <div className="space-y-4 p-4 sm:p-6 lg:p-8">
      {error && !action && <Alert message={error} />}{success && <Alert type="success" message={success} />}
      {readOnly && <div className="rounded-md border border-warning/30 bg-warning-surface p-3 text-xs text-warning-strong">Sessão de suporte somente leitura. Pagamentos e cancelamentos estão desabilitados.</div>}
      <section className="card flex flex-wrap items-center justify-between gap-4 p-5"><div><span className="text-xs text-muted">Pendente nos resultados</span><strong className="mt-1 block text-xl">{formatBRL(centsText(pendingTotal))}</strong></div><WalletCards className="size-8 text-primary" /></section>
      <form className="card grid gap-3 p-4 md:grid-cols-2 xl:grid-cols-4" onSubmit={apply}>
        <Select aria-label="Fornecedor" value={draft.supplier} onChange={(event) => setDraft((value) => ({ ...value, supplier: event.target.value }))}><option value="">Todos os fornecedores</option>{suppliers.map((supplier) => <option key={supplier.id} value={supplier.id}>{supplier.trade_name}</option>)}</Select>
        <Select aria-label="Status" value={draft.status} onChange={(event) => setDraft((value) => ({ ...value, status: event.target.value }))}><option value="">Todos os status</option>{Object.entries(payableStatusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select>
        <div className="relative md:col-span-2"><Search className="pointer-events-none absolute left-3 top-3 size-4 text-muted" /><Input className="pl-9" placeholder="Número da compra" value={draft.purchase} onChange={(event) => setDraft((value) => ({ ...value, purchase: event.target.value }))} /></div>
        <PeriodFilter className="md:col-span-2 xl:col-span-4" value={draft.period} onChange={(period) => setDraft((value) => ({ ...value, period }))} />
        <div className="flex justify-end gap-2 md:col-span-2 xl:col-span-4"><Button type="button" variant="secondary" onClick={clear}>Limpar</Button><Button type="submit"><SlidersHorizontal className="size-4" />Aplicar</Button></div>
      </form>
      <section className="card overflow-hidden"><div className="card-header"><div><h2 className="text-sm font-bold">Parcelas de compras</h2><p className="mt-1 text-[11px] text-muted">{items.length} {items.length === 1 ? "parcela" : "parcelas"}</p></div><Banknote className="size-5 text-muted" /></div>{loading ? <TableLoading columns={7} /> : items.length ? <>
        <div className="divide-y divide-subtle md:hidden">{items.map((item) => <article key={item.id} className="space-y-3 p-4"><div className="flex justify-between gap-3"><div><Link href={`/compras/${item.purchase_order}?origin=payables`} className="font-bold text-link">{item.order_number}</Link><p className="mt-1 text-xs text-muted">{item.supplier_name} · parcela {item.installment_number}</p></div><PayableBadge status={item.status} /></div><div className="flex items-end justify-between"><div><span className="text-[10px] text-muted">Vencimento</span><strong className="block text-xs">{new Date(`${item.due_date}T12:00:00`).toLocaleDateString("pt-BR")}</strong></div><strong>{formatBRL(item.amount)}</strong></div>{item.status === "PENDING" && <div className="flex justify-end gap-2 border-t border-subtle pt-3"><Button variant="secondary" onClick={() => open(item, "cancel")} disabled={readOnly}><XCircle className="size-4" />Cancelar</Button><Button onClick={() => open(item, "pay")} disabled={readOnly}><Banknote className="size-4" />Pagar</Button></div>}</article>)}</div>
        <div className="table-wrap hidden md:block"><table className="data-table min-w-225"><thead><tr><th>Compra</th><th>Fornecedor</th><th>Parcela</th><th>Vencimento</th><th>Valor</th><th>Status</th><th>Baixa</th><th className="text-right">Ações</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td><Link href={`/compras/${item.purchase_order}?origin=payables`} className="font-bold text-link">{item.order_number}</Link></td><td>{item.supplier_name}</td><td>{item.installment_number}</td><td>{new Date(`${item.due_date}T12:00:00`).toLocaleDateString("pt-BR")}</td><td className="font-bold">{formatBRL(item.amount)}</td><td><PayableBadge status={item.status} /></td><td>{item.paid_at ? formatDate(item.paid_at) : item.cancelled_at ? formatDate(item.cancelled_at) : "-"}</td><td><div className="flex justify-end gap-1"><Link className="icon-button" href={`/compras/${item.purchase_order}?origin=payables`} title="Ver compra"><Eye className="size-4" /></Link>{item.status === "PENDING" && <><button className="icon-button" title="Registrar pagamento" onClick={() => open(item, "pay")} disabled={readOnly}><Banknote className="size-4" /></button><button className="icon-button" title="Cancelar parcela" onClick={() => open(item, "cancel")} disabled={readOnly}><XCircle className="size-4" /></button></>}</div></td></tr>)}</tbody></table></div>
      </> : <EmptyState title="Nenhuma parcela encontrada" description="Não há contas de compras para os filtros informados." />}</section>
    </div>
    <Modal open={!!action && !!selected} title={action === "pay" ? "Registrar pagamento manual" : "Cancelar parcela"} description={selected ? `${selected.order_number} · parcela ${selected.installment_number} · ${formatBRL(selected.amount)}` : ""} onClose={() => !acting && setAction(null)} size="md"><form onSubmit={submit}><div className="space-y-4 p-5">{error && <Alert message={error} />}{action === "pay" && <div className="grid gap-4 sm:grid-cols-2"><Field label="Forma efetivamente paga"><Select value={paymentMethod} onChange={(event) => setPaymentMethod(event.target.value)}><option>PIX</option><option>Transferência</option><option>Boleto</option><option>Dinheiro</option><option>Cartão</option><option>Outro</option></Select></Field><Field label="Data do pagamento"><Input required type="date" value={paidDate} onChange={(event) => setPaidDate(event.target.value)} /></Field><Field label="Valor pago"><Input required inputMode="decimal" value={paidAmount} onChange={(event) => setPaidAmount(event.target.value)} /></Field></div>}<Field label={action === "pay" ? "Observação" : "Motivo"} optional={action === "pay"}><Textarea required={action === "cancel"} minLength={action === "cancel" ? 3 : undefined} value={text} onChange={(event) => setText(event.target.value)} disabled={acting} /></Field>{action === "pay" && <p className="text-xs text-warning-strong">A baixa, forma efetiva, data e valor ficam registrados na parcela de fornecedor.</p>}</div><div className="flex justify-end gap-2 border-t border-subtle p-4"><Button type="button" variant="secondary" onClick={() => setAction(null)} disabled={acting}>Voltar</Button><Button type="submit" variant={action === "cancel" ? "danger" : "primary"} loading={acting}>{action === "pay" ? "Confirmar pagamento" : "Cancelar parcela"}</Button></div></form></Modal>
  </>;
}

export default function PurchasePayablesPage() { return <AdminGuard requiredPermissions={[permissions.managePurchasePayables]}><PurchasePayables /></AdminGuard>; }
