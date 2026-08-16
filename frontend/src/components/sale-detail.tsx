"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Ban, Building2, CreditCard, PackageCheck, ReceiptText, UserRound } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, Modal, Spinner, Textarea } from "@/components/ui";
import { formatBRL, formatDate, formatQuantity } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { Sale, SaleOperation } from "@/types";

function Status({ status }: { status: Sale["status"] }) { return <span className={`rounded-full px-3 py-1 text-xs font-bold ${status === "finalized" ? "bg-success/10 text-emerald-700" : "bg-danger/10 text-red-700"}`}>{status === "finalized" ? "Finalizada" : "Cancelada"}</span>; }
function DataPoint({ label, value }: { label: string; value: React.ReactNode }) { return <div><dt className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{label}</dt><dd className="mt-1 text-sm font-semibold text-dark">{value || "-"}</dd></div>; }

export function SaleDetail({ expectedOperation }: { expectedOperation: SaleOperation }) {
  const { id } = useParams<{ id: string }>();
  const { currentCompany, currentBranch, hasPermission } = useAuth();
  const contextRef = useRef(""); contextRef.current = `${currentCompany?.id || ""}:${currentBranch?.id || ""}:${id}`;
  const [sale, setSale] = useState<Sale | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [cancelOpen, setCancelOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [cancelling, setCancelling] = useState(false);

  async function load(context = contextRef.current) {
    if (!currentBranch || !id) { setLoading(false); return; }
    setLoading(true); setError("");
    try {
      const response = await http.get<Sale>(`sales/${id}/`);
      if (contextRef.current !== context) return;
      if (response.operation_type !== expectedOperation) { setSale(null); setError(`Esta operação é uma ${response.operation_type === "consumption" ? "consumação" : "venda comercial"}. Abra-a pela listagem correta.`); return; }
      setSale(response);
    } catch (caught) { if (contextRef.current === context) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar a operação."); }
    finally { if (contextRef.current === context) setLoading(false); }
  }
  useEffect(() => { const context = contextRef.current; setSale(null); setError(""); setCancelOpen(false); void load(context); }, [currentCompany?.id, currentBranch?.id, id]);

  async function cancel() {
    if (!sale) return;
    setCancelling(true); setError("");
    try { const updated = await http.post<Sale>(`sales/${sale.id}/cancel/`, { reason }); setSale(updated); setCancelOpen(false); setReason(""); }
    catch (caught) { setError(caught instanceof ApiError ? `${caught.message} ${Object.values(caught.fields).flat().join(" ")}`.trim() : "Não foi possível cancelar. Nenhuma alteração deve ser presumida; recarregue o detalhe."); setCancelOpen(false); }
    finally { setCancelling(false); }
  }

  if (loading) return <div className="flex min-h-[calc(100vh-4.5rem)] items-center justify-center gap-2 text-primary"><Spinner className="size-7" />Carregando operação...</div>;
  if (!sale) return <><PageHeader title="Detalhe da operação" description="Consulta histórica da filial atual." /><div className="p-4 sm:p-6 lg:p-8"><Alert message={error || "Operação não encontrada."} /><Link className="btn btn-secondary mt-4" href={expectedOperation === "consumption" ? "/consumacoes" : "/vendas"}><ArrowLeft className="size-4" />Voltar à listagem</Link></div></>;
  const consumption = sale.operation_type === "consumption";
  const hasUnitCosts = sale.items.every((item) => item.unit_cost !== undefined);
  const canCancel = sale.status === "finalized" && hasPermission(consumption ? permissions.cancelConsumption : permissions.cancelSale);
  return <><PageHeader title={`${consumption ? "Consumação" : "Venda"} ${sale.sale_number}`} description={`Registro imutável criado em ${formatDate(sale.created_at)}.`} action={<div className="flex gap-2"><Link className="btn btn-secondary" href={consumption ? "/consumacoes" : "/vendas"}><ArrowLeft className="size-4" />Voltar</Link>{canCancel && <Button variant="danger" onClick={() => setCancelOpen(true)}><Ban className="size-4" />Cancelar</Button>}</div>} />
    <div className="space-y-4 p-4 sm:p-6 lg:p-8">{error && <Alert message={error} />}
      <section className="card overflow-hidden"><div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-100 p-5 sm:p-6"><div><p className="text-[10px] font-bold uppercase tracking-[.18em] text-primary">{consumption ? "Consumo interno" : "Operação comercial"}</p><h2 className="mt-1 text-2xl font-bold">{sale.sale_number}</h2></div><Status status={sale.status} /></div><dl className="grid gap-6 p-5 sm:grid-cols-2 sm:p-6 lg:grid-cols-4"><DataPoint label="Filial" value={sale.branch_name} /><DataPoint label="Empresa" value={sale.company_name} /><DataPoint label="Operador" value={sale.created_by_name} /><DataPoint label="Beneficiário" value={sale.beneficiary_user_name} /><DataPoint label="Criada em" value={formatDate(sale.created_at)} /><DataPoint label="Atualizada em" value={formatDate(sale.updated_at)} /><DataPoint label="Sessão de caixa" value={sale.cash_session ? `#${sale.cash_session}` : "Não utilizada"} /><DataPoint label="Tipo" value={consumption ? "Consumação" : "Venda"} /></dl></section>
      <div className="grid gap-4 lg:grid-cols-[1.35fr_.65fr]"><section className="card overflow-hidden"><div className="card-header"><div><h2 className="flex items-center gap-2 text-sm font-bold"><PackageCheck className="size-4 text-primary" />Itens registrados</h2><p className="mt-1 text-[11px] text-slate-500">Snapshots da operação, sem consulta ao produto atual.</p></div></div><div className="table-wrap"><table className="data-table"><thead><tr><th>Produto no momento da operação</th><th>Quantidade</th>{hasUnitCosts && <th>Custo unit.</th>}<th>Preço unit.</th><th className="text-right">Subtotal</th></tr></thead><tbody>{sale.items.map((item) => <tr key={item.id}><td><strong className="block">{item.product_name}</strong><span className="text-[11px] text-slate-400">{item.internal_code} · {item.unit.toUpperCase()}</span>{item.promotion_name && <span className="mt-1 block text-[10px] font-bold text-emerald-700">{item.promotion_name} · benefício {formatBRL(item.promotion_benefit)}</span>}</td><td>{formatQuantity(item.quantity)} {item.unit.toUpperCase()}</td>{hasUnitCosts && <td>{formatBRL(item.unit_cost)}</td>}<td>{formatBRL(item.unit_price)}</td><td className="text-right"><strong className={item.promotion_name ? "text-slate-400 line-through" : ""}>{formatBRL(item.subtotal)}</strong>{item.promotion_name && <strong className="block text-emerald-700">{formatBRL(item.net_subtotal)}</strong>}</td></tr>)}</tbody></table></div></section>
        <section className="card self-start overflow-hidden"><div className="card-header"><h2 className="flex items-center gap-2 text-sm font-bold"><ReceiptText className="size-4 text-primary" />Valores</h2></div><div className="space-y-3 p-5"><div className="flex justify-between text-sm text-slate-500"><span>{consumption ? "Referência" : "Subtotal bruto"}</span><span>{formatBRL(sale.subtotal)}</span></div>{!consumption && sale.promotion_discount_total !== "0.00" && <div className="flex justify-between text-sm text-emerald-700"><span>Promoções</span><span>- {formatBRL(sale.promotion_discount_total)}</span></div>}{!consumption && <div className="flex justify-between text-sm text-slate-500"><span>Desconto manual</span><span>- {formatBRL(sale.discount)}</span></div>}{consumption && <div className="flex justify-between text-sm text-slate-500"><span>Valor cobrado</span><span>{formatBRL(sale.charged_amount || "0.00")}</span></div>}<div className="flex justify-between border-t border-slate-100 pt-3 text-lg font-bold"><span>Total</span><span>{formatBRL(sale.total)}</span></div></div></section></div>
      <section className="card overflow-hidden"><div className="card-header"><div><h2 className="flex items-center gap-2 text-sm font-bold"><CreditCard className="size-4 text-primary" />Pagamentos</h2><p className="mt-1 text-[11px] text-slate-500">Nomes e códigos preservados mesmo que o método tenha sido inativado.</p></div></div>{sale.payments.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Forma registrada</th><th>Valor</th><th>Recebido</th><th>Troco</th><th>Data</th></tr></thead><tbody>{sale.payments.map((payment) => <tr key={payment.id}><td><strong className="block">{payment.payment_method_name}</strong><code className="text-[10px] text-slate-400">{payment.payment_method_code}</code></td><td>{formatBRL(payment.amount)}</td><td>{payment.received_amount ? formatBRL(payment.received_amount) : "-"}</td><td>{payment.change_amount ? formatBRL(payment.change_amount) : "-"}</td><td>{formatDate(payment.created_at)}</td></tr>)}</tbody></table></div> : <div className="p-6 text-sm text-slate-500">Sem pagamentos: consumação registrada com cobrança zero.</div>}</section>
      {sale.status === "cancelled" && <section className="rounded-lg border border-danger/20 bg-danger/5 p-5"><h2 className="flex items-center gap-2 text-sm font-bold text-red-700"><Ban className="size-4" />Cancelamento</h2><dl className="mt-4 grid gap-4 sm:grid-cols-3"><DataPoint label="Cancelada em" value={formatDate(sale.cancelled_at || "")} /><DataPoint label="Responsável" value={sale.cancelled_by_name} /><DataPoint label="Motivo" value={sale.cancellation_reason || "Não informado"} /></dl></section>}
    </div>
    <Modal open={cancelOpen} title={`Cancelar ${consumption ? "consumação" : "venda"} ${sale.sale_number}`} description="Ação destrutiva e não repetível." onClose={() => !cancelling && setCancelOpen(false)} size="md"><div className="space-y-4 p-5 sm:p-6"><div className="rounded-lg border border-warning/30 bg-warning/10 p-4 text-xs leading-5 text-amber-900"><strong className="block">O estoque será revertido pelos movimentos originais.</strong>O cancelamento no sistema não confirma nem executa estorno externo de PIX ou cartão. Confira esse reembolso diretamente com o provedor do pagamento.</div><label className="block"><span className="label">Motivo <span className="font-normal text-slate-400">(opcional)</span></span><Textarea maxLength={500} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Contexto para auditoria" /></label></div><div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-4"><Button variant="secondary" disabled={cancelling} onClick={() => setCancelOpen(false)}>Manter operação</Button><Button variant="danger" loading={cancelling} onClick={() => void cancel()}>Confirmar cancelamento</Button></div></Modal>
  </>;
}
