"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Ban, CheckCircle2, PackageCheck, Send } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { InventoryNav } from "@/components/inventory-nav";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, ConfirmDialog, Field, Input, Modal, Spinner, Textarea } from "@/components/ui";
import { fieldError, formatDate, formatDecimalBRL, formatQuantity } from "@/lib/format";
import { contentUnitLabel, inventoryTone, isUnitQuantityValid, quantityInputMode, transferStatusLabels } from "@/lib/inventory";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { StockTransfer, StockTransferReceipt, TransferReceiveOptions } from "@/types";

const detailPermissions = [permissions.viewTransfers, permissions.createTransfer, permissions.dispatchTransfer, permissions.receiveTransfer] as const;

function TransferDetail() {
  const id = String(useParams<{ id: string }>().id);
  const { currentBranch, hasPermission, supportSession } = useAuth();
  const readOnly = supportSession?.mode === "READ_ONLY";
  const canViewHistory = hasPermission(permissions.viewTransfers);
  const canCreate = hasPermission(permissions.createTransfer);
  const canDispatchAction = hasPermission(permissions.dispatchTransfer);
  const canReceiveAction = hasPermission(permissions.receiveTransfer);
  const canLoadTransfer = canViewHistory || canCreate || canDispatchAction || canReceiveAction;
  const [transfer, setTransfer] = useState<StockTransfer | null>(null);
  const [receiveOptions, setReceiveOptions] = useState<TransferReceiveOptions | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [dispatchOpen, setDispatchOpen] = useState(false);
  const [receiptOpen, setReceiptOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notes, setNotes] = useState("");
  const [finalize, setFinalize] = useState(false);
  const [confirmEmptyFinalize, setConfirmEmptyFinalize] = useState(false);
  const [quantities, setQuantities] = useState<Record<number, string>>({});
  const [reason, setReason] = useState("");
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const receiptKey = useRef("");
  const dispatchKey = useRef("");
  const branchId = currentBranch?.id;

  async function load() {
    setLoading(true);
    setError("");
    try {
      if (canLoadTransfer) {
        setTransfer(await http.get<StockTransfer>(`stock-transfers/${id}/`));
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar a transferência.");
    } finally {
      setLoading(false);
    }
  }

  const loadRef = useRef(load);
  loadRef.current = load;
  useEffect(() => {
    setTransfer(null);
    setSuccess("");
    dispatchKey.current = "";
    void loadRef.current();
  }, [id, branchId]);

  const atOrigin = transfer?.origin_branch === branchId;
  const atDestination = transfer?.destination_branch === branchId;
  const canDispatch = canDispatchAction && !readOnly && !!atOrigin && transfer?.status === "DRAFT";
  const canCancel = canCreate && !readOnly && !!atOrigin && transfer?.status === "DRAFT";
  const canReceive = canReceiveAction && !readOnly && (receiveOptions ? receiveOptions.destination_branch === branchId : !!atDestination && ["IN_TRANSIT", "PARTIALLY_RECEIVED"].includes(transfer?.status || ""));

  function changeReceiptPayload(callback: () => void) {
    callback();
    receiptKey.current = crypto.randomUUID();
  }

  async function openReceipt() {
    receiptKey.current = crypto.randomUUID();
    setNotes("");
    setFinalize(false);
    setConfirmEmptyFinalize(false);
    setFields({});
    setError("");
    try {
      const options = await http.get<TransferReceiveOptions>(`stock-transfers/${id}/receive-options/`);
      setReceiveOptions(options);
      setQuantities(Object.fromEntries(options.items.filter((item) => Number(item.pending_quantity) > 0).map((item) => [item.transfer_item, item.pending_quantity])));
      setReceiptOpen(true);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as opções de recebimento.");
    }
  }

  async function dispatchTransfer() {
    if (!dispatchKey.current) dispatchKey.current = crypto.randomUUID();
    setSaving(true);
    setError("");
    try {
      setTransfer(await http.post<StockTransfer>(`stock-transfers/${id}/dispatch/`, { idempotency_key: dispatchKey.current }));
      dispatchKey.current = "";
      setDispatchOpen(false);
      setSuccess("Transferência despachada. A baixa foi registrada uma única vez na origem.");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível despachar.");
    } finally {
      setSaving(false);
    }
  }

  async function receive(event: React.FormEvent) {
    event.preventDefault();
    if (!receiveOptions) return;
    setError("");
    setFields({});
    const items = receiveOptions.items.flatMap((item) => Number(String(quantities[item.transfer_item] || "").replace(",", ".")) > 0 ? [{ transfer_item: item.transfer_item, quantity: quantities[item.transfer_item].replace(",", ".") }] : []);
    const clientFields: Record<string, string[]> = {};
    items.forEach((entry, index) => {
      const transferItem = receiveOptions.items.find((item) => item.transfer_item === entry.transfer_item);
      if (transferItem && !isUnitQuantityValid(entry.quantity, transferItem.unit)) {
        clientFields[`items.${index}.quantity`] = [transferItem.unit.toLowerCase() === "un" ? "Informe uma quantidade inteira de unidades." : "Informe uma quantidade positiva com até 3 casas decimais."];
      }
    });
    if (!items.length && !finalize) {
      setError("Informe ao menos uma quantidade recebida ou finalize explicitamente a conferência.");
      return;
    }
    if (!items.length && finalize && !confirmEmptyFinalize) {
      setError("Confirme que nenhum item foi recebido e que todo o saldo pendente deve virar divergência.");
      return;
    }
    if (Object.keys(clientFields).length) {
      setFields(clientFields);
      setError("Revise as quantidades informadas.");
      return;
    }
    setSaving(true);
    try {
      const receipt = await http.post<StockTransferReceipt>(`stock-transfers/${id}/receive/`, { idempotency_key: receiptKey.current, finalize, notes, items });
      setReceiptOpen(false);
      setSuccess(items.length ? `Recebimento ${finalize ? "final" : "parcial"} confirmado em ${formatDate(receipt.received_at)}.` : `Conferência finalizada sem itens recebidos em ${formatDate(receipt.received_at)}. As pendências foram registradas como divergência.`);
      await load();
      if (finalize) setReceiveOptions(null);
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setFields(caught.fields);
      } else setError("Não foi possível confirmar o recebimento.");
    } finally {
      setSaving(false);
    }
  }

  async function cancel(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setFields({});
    try {
      setTransfer(await http.post<StockTransfer>(`stock-transfers/${id}/cancel/`, { reason }));
      setCancelOpen(false);
      setSuccess("Rascunho cancelado.");
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setFields(caught.fields);
      } else setError("Não foi possível cancelar.");
    } finally {
      setSaving(false);
    }
  }

  if (loading && !transfer && !receiveOptions) return <div className="flex min-h-96 items-center justify-center text-primary"><Spinner className="size-7" /></div>;

  return <>
    <PageHeader title={transfer ? `Transferência ${transfer.id.slice(0, 8).toUpperCase()}` : `Transferência ${id.slice(0, 8).toUpperCase()}`} description={transfer ? `${transfer.origin_branch_name} → ${transfer.destination_branch_name}` : "Dados mínimos da ação autorizada"} action={<div className="flex flex-wrap gap-2"><Link href="/estoque/transferencias" className="btn btn-secondary"><ArrowLeft className="size-4" />Voltar</Link>{canCancel && <Button variant="danger" onClick={() => { setReason(""); setCancelOpen(true); }}><Ban className="size-4" />Cancelar</Button>}{canDispatch && <Button onClick={() => { if (!dispatchKey.current) dispatchKey.current = crypto.randomUUID(); setDispatchOpen(true); }}><Send className="size-4" />Despachar</Button>}{canReceive && <Button onClick={() => void openReceipt()}><PackageCheck className="size-4" />Receber</Button>}</div>} />
    <InventoryNav />
    <div className="space-y-4 p-4 sm:p-6 lg:p-8">
      {error && !receiptOpen && !cancelOpen && <Alert message={error} />}
      {success && <Alert message={success} type="success" />}
      {!transfer && receiveOptions && <section className="card p-5"><strong className="text-sm">Recebimento autorizado</strong><p className="mt-1 text-xs text-muted">Somente os itens e saldos necessários à conferência são disponibilizados.</p></section>}
      {transfer && <>
        <section className="card p-5 sm:p-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"><div><span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${inventoryTone(transfer.status)}`}>{transferStatusLabels[transfer.status]}</span><p className="mt-4 text-sm font-bold">{transfer.origin_branch_name} → {transfer.destination_branch_name}</p>{canViewHistory && <p className="mt-1 text-xs text-muted">Criada em {formatDate(transfer.created_at)} · responsável #{transfer.created_by}</p>}{transfer.notes && <p className="mt-3 max-w-2xl text-sm text-muted">{transfer.notes}</p>}</div>{canViewHistory && <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs"><div><dt className="text-muted">Despacho</dt><dd>{formatDate(transfer.dispatched_at || "")}</dd></div><div><dt className="text-muted">Recebimentos</dt><dd>{transfer.receipts.length}</dd></div></dl>}</div>
          {transfer.status === "CANCELLED" && <div className="mt-4 rounded-md bg-danger-surface p-3 text-xs text-danger-strong"><strong>Motivo do cancelamento:</strong> {transfer.cancellation_reason}</div>}
        </section>
        <section className="card overflow-hidden">
          <div className="card-header"><div><h2 className="text-sm font-bold">Itens da transferência</h2><p className="mt-1 text-[11px] text-muted">Produtos fracionáveis transitam somente em embalagens fechadas; os snapshots de conteúdo preservam a unidade canônica.</p></div></div>
          <div className="divide-y divide-subtle md:hidden">{transfer.items.map((item) => <article className="p-4" key={item.id}><strong className="text-sm">{item.product_name_snapshot}</strong><p className="text-[11px] text-muted">{item.product_internal_code_snapshot}</p><dl className="mt-3 grid grid-cols-2 gap-2 text-xs"><div><dt className="text-muted">Solicitado</dt><dd>{formatQuantity(item.requested_quantity)} {item.product_unit_snapshot.toUpperCase()}</dd></div><div><dt className="text-muted">Despachado</dt><dd>{formatQuantity(item.dispatched_quantity)}</dd></div><div><dt className="text-muted">Recebido</dt><dd>{formatQuantity(item.received_quantity)}</dd></div><div><dt className="text-muted">Pendente</dt><dd className="font-bold">{formatQuantity(item.pending_quantity)}</dd></div>{canViewHistory && item.origin_unit_cost_snapshot !== undefined && <div><dt className="text-muted">Custo na origem</dt><dd>{formatDecimalBRL(item.origin_unit_cost_snapshot)}</dd></div>}</dl>{canViewHistory && item.movement_ids.length > 0 && <Link className="mt-3 inline-block text-xs font-semibold text-link" href={`/estoque/movimentacoes?operation_reference=${transfer.id}&domain_origin=TRANSFER_DISPATCH`}>Ver despacho</Link>}</article>)}</div>
           <div className="table-wrap hidden md:block"><table className="data-table"><thead><tr><th>Produto</th><th>Solicitado</th><th>Despachado</th><th>Recebido</th><th>Pendente</th>{canViewHistory && transfer.items.some((item) => item.origin_unit_cost_snapshot !== undefined) && <th>Custo na origem</th>}</tr></thead><tbody>{transfer.items.map((item) => <tr key={item.id}><td><strong>{item.product_name_snapshot}</strong><small className="block text-muted">{item.product_internal_code_snapshot}</small>{item.package_content_snapshot && <small className="block font-semibold text-warning-strong">Embalagem fechada: {formatQuantity(item.package_content_snapshot)} {contentUnitLabel(item.content_unit_snapshot)}</small>}</td><td>{formatQuantity(item.requested_quantity)} {item.product_unit_snapshot.toUpperCase()}</td><td>{formatQuantity(item.dispatched_quantity)}</td><td>{formatQuantity(item.received_quantity)}</td><td className="font-bold">{formatQuantity(item.pending_quantity)}</td>{canViewHistory && transfer.items.some((row) => row.origin_unit_cost_snapshot !== undefined) && <td>{formatDecimalBRL(item.origin_unit_cost_snapshot)}</td>}</tr>)}</tbody></table></div>
        </section>
        {canViewHistory && <section className="card overflow-hidden"><div className="card-header"><div><h2 className="text-sm font-bold">Recebimentos no destino</h2><p className="mt-1 text-[11px] text-muted">Histórico imutável de eventos de recebimento.</p></div><CheckCircle2 className="size-5 text-muted" /></div>{transfer.receipts.length ? <div className="divide-y divide-subtle">{transfer.receipts.map((receipt) => <article key={receipt.id} className="p-4 sm:p-5"><div className="flex flex-col gap-2 sm:flex-row sm:justify-between"><div><strong className="text-sm">{receipt.finalize ? "Recebimento final" : "Recebimento parcial"}</strong><p className="mt-1 text-xs text-muted">{formatDate(receipt.received_at)} · responsável #{receipt.received_by}</p></div><Link href={`/estoque/movimentacoes?operation_reference=${receipt.id}&domain_origin=TRANSFER_RECEIPT`} className="text-xs font-semibold text-link">Ver movimentos</Link></div>{receipt.notes && <p className="mt-2 text-xs text-muted">{receipt.notes}</p>}{receipt.items.length ? <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">{receipt.items.map((item) => { const product = transfer.items.find((row) => row.id === item.transfer_item); return <div key={item.id} className="rounded-md bg-surface-muted p-3 text-xs"><strong>{product?.product_name_snapshot || `Item ${item.transfer_item}`}</strong><p className="mt-1">Recebido: {formatQuantity(item.received_quantity)} · acumulado: {formatQuantity(item.accumulated_quantity)}</p>{item.unit_cost_snapshot !== undefined && <p className="mt-1 text-muted">Custo: {formatDecimalBRL(item.unit_cost_snapshot)}</p>}</div>; })}</div> : <p className="mt-3 rounded-md bg-warning-surface p-3 text-xs text-warning-strong">Conferência finalizada sem quantidade recebida.</p>}</article>)}</div> : <p className="p-6 text-center text-xs text-muted">Nenhum recebimento registrado.</p>}</section>}
      </>}
    </div>
    <ConfirmDialog open={dispatchOpen} title="Despachar transferência" message="O despacho baixa integralmente as quantidades na filial de origem. Repetições desta confirmação usam a mesma chave e não podem gerar uma segunda baixa." confirmLabel="Confirmar despacho" loading={saving} onClose={() => setDispatchOpen(false)} onConfirm={() => void dispatchTransfer()} />
    <Modal open={receiptOpen} title="Receber no destino" description="Informe somente o que foi fisicamente conferido nesta etapa." onClose={() => !saving && setReceiptOpen(false)} size="lg">
      <form onSubmit={receive}>
        <div className="space-y-4 p-5 sm:p-6">
          {error && <Alert message={error} />}
           {receiveOptions?.items.filter((item) => Number(item.pending_quantity) > 0).map((item, index) => <div key={item.transfer_item} className="grid gap-2 rounded-md border border-subtle p-3 sm:grid-cols-[1fr_180px]"><div><strong className="text-sm">{item.product_name}</strong><p className="mt-1 text-xs text-muted">Pendente: {formatQuantity(item.pending_quantity)} {item.unit.toUpperCase()}</p>{transfer?.items.find((row) => row.id === item.transfer_item)?.package_content_snapshot && <p className="mt-1 text-[10px] font-semibold text-warning-strong">Receba somente embalagens fechadas.</p>}</div><Field label="Recebido agora" error={fieldError(fields, `items.${index}.quantity`)}><Input inputMode={quantityInputMode(item.unit)} step={item.unit.toLowerCase() === "un" ? "1" : "0.001"} min="0" value={quantities[item.transfer_item] || ""} onChange={(event) => changeReceiptPayload(() => setQuantities((value) => ({ ...value, [item.transfer_item]: event.target.value })))} /></Field></div>)}
          <Field label="Observações" optional error={fieldError(fields, "notes")}><Textarea value={notes} onChange={(event) => changeReceiptPayload(() => setNotes(event.target.value))} /></Field>
          <label className="flex items-start gap-3 rounded-md border border-warning/30 bg-warning-surface p-3 text-xs"><input type="checkbox" className="mt-0.5" checked={finalize} onChange={(event) => changeReceiptPayload(() => { setFinalize(event.target.checked); setConfirmEmptyFinalize(false); })} /><span><strong className="block text-warning-strong">Finalizar conferência</strong><span className="text-muted">Quantidades pendentes serão divergências finalizadas, não itens em trânsito.</span></span></label>
          {finalize && !receiveOptions?.items.some((item) => Number(String(quantities[item.transfer_item] || "").replace(",", ".")) > 0) && <label className="flex items-start gap-3 rounded-md border border-danger/30 bg-danger-surface p-3 text-xs"><input type="checkbox" className="mt-0.5" checked={confirmEmptyFinalize} onChange={(event) => changeReceiptPayload(() => setConfirmEmptyFinalize(event.target.checked))} /><span><strong className="block text-danger-strong">Confirmo recebimento zero</strong><span className="text-muted">Nenhum item foi recebido. Todo o saldo pendente será convertido em divergência explícita.</span></span></label>}
        </div>
        <div className="flex justify-end gap-2 border-t border-subtle px-5 py-4"><Button type="button" variant="secondary" disabled={saving} onClick={() => setReceiptOpen(false)}>Cancelar</Button><Button type="submit" loading={saving}>{finalize ? "Confirmar e finalizar" : "Confirmar parcial"}</Button></div>
      </form>
    </Modal>
    <Modal open={cancelOpen} title="Cancelar rascunho" description="Somente transferências ainda não despachadas podem ser canceladas." onClose={() => !saving && setCancelOpen(false)} size="md"><form onSubmit={cancel}><div className="space-y-4 p-5">{error && <Alert message={error} />}<Field label="Motivo" error={fieldError(fields, "reason")}><Textarea required minLength={3} value={reason} onChange={(event) => setReason(event.target.value)} /></Field></div><div className="flex justify-end gap-2 border-t border-subtle px-5 py-4"><Button type="button" variant="secondary" onClick={() => setCancelOpen(false)} disabled={saving}>Voltar</Button><Button type="submit" variant="danger" loading={saving}>Cancelar transferência</Button></div></form></Modal>
  </>;
}

export default function TransferDetailPage() {
  return <AdminGuard requiredPermissions={detailPermissions}><TransferDetail /></AdminGuard>;
}
