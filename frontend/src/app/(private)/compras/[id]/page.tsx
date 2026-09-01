"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useEffectEvent, useRef, useState } from "react";
import {
  ArrowLeft,
  Check,
  ClipboardCheck,
  Download,
  FileUp,
  Pencil,
  Plus,
  XCircle,
} from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import {
  Alert,
  Button,
  EmptyState,
  Field,
  Input,
  Modal,
  MoneyInput,
  Spinner,
  Textarea,
} from "@/components/ui";
import {
  formatDecimalBRL as formatBRL,
  formatDate,
  formatDecimalBRL,
  formatEditableDecimal,
  formatQuantity,
} from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import {
  centsText,
  compareDecimal,
  decimalToScaled,
  ensureReceiptKey,
  moneyCents,
  purchaseStatusLabels,
  purchaseTypeLabels,
  purchaseBaseEquivalent,
  purchasePresentationLabel,
  readReceiptKeys,
  receiptPayloadFingerprint,
  reconcileReceiptKeys,
  removeReceiptKey,
  updateReceiptKeyState,
  validatePurchaseAttachmentFile,
} from "@/lib/purchases";
import { useAuth } from "@/providers/auth-provider";
import type {
  PayableInstallment,
  PurchaseOrder,
  PurchaseReceipt,
  PurchaseOrderStatus,
} from "@/types";

type ReasonAction = "cancel" | "close-partial";
type InstallmentDraft = { amount: string; due_date: string; notes: string };
const statusTone: Record<PurchaseOrderStatus, string> = {
  DRAFT: "bg-warning/15 text-warning-strong",
  PLACED: "bg-info-surface text-info-strong",
  PARTIALLY_RECEIVED: "bg-warning/15 text-warning-strong",
  RECEIVED: "bg-success/10 text-success-strong",
  CANCELLED: "bg-danger/10 text-danger-strong",
  CLOSED_PARTIAL: "bg-surface-muted text-muted",
};
function quantityText(value: bigint) {
  const negative = value < BigInt(0);
  const absolute = negative ? -value : value;
  const whole = absolute / BigInt(1_000_000);
  const fraction = String(absolute % BigInt(1_000_000))
    .padStart(6, "0")
    .replace(/0+$/, "");
  return `${negative ? "-" : ""}${whole}${fraction ? `.${fraction}` : ""}`;
}

function PurchaseDetail() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const id = pathname.split("/").filter(Boolean).at(-1)!;
  const returnHref =
    searchParams.get("origin") === "payables" ? "/contas-a-pagar" : "/compras";
  const { currentBranch, hasPermission, supportSession } = useAuth();
  const branchId = currentBranch?.id;
  const readOnly = supportSession?.mode === "READ_ONLY";
  const canCosts = hasPermission(permissions.viewPurchaseCosts);
  const canCreate = hasPermission(permissions.createPurchase) && !readOnly;
  const canPlace = hasPermission(permissions.placePurchase) && !readOnly;
  const canReceive = hasPermission(permissions.receivePurchase) && !readOnly;
  const canClose = hasPermission(permissions.closePurchase) && !readOnly;
  const canPayables =
    hasPermission(permissions.managePurchasePayables) && !readOnly;
  const [order, setOrder] = useState<PurchaseOrder | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [acting, setActing] = useState(false);
  const [reasonAction, setReasonAction] = useState<ReasonAction | null>(null);
  const [reason, setReason] = useState("");
  const [receiptOpen, setReceiptOpen] = useState(false);
  const [received, setReceived] = useState<Record<number, string>>({});
  const [receiptReason, setReceiptReason] = useState("");
  const [receiptNotes, setReceiptNotes] = useState("");
  const [receiptKey, setReceiptKey] = useState("");
  const [receiptUncertain, setReceiptUncertain] = useState(false);
  const [reconcilingReceipt, setReconcilingReceipt] = useState(false);
  const autoReceiptOpened = useRef(false);
  const [installmentOpen, setInstallmentOpen] = useState(false);
  const [installments, setInstallments] = useState<InstallmentDraft[]>([]);
  const [editOpen, setEditOpen] = useState(false);
  const [attachmentFile, setAttachmentFile] = useState<File | null>(null);
  const [attachmentInputKey, setAttachmentInputKey] = useState(0);
  const [attachmentError, setAttachmentError] = useState("");
  const [attachmentBusy, setAttachmentBusy] = useState<
    "upload" | "download" | "remove" | ""
  >("");
  const [edit, setEdit] = useState({
    global_discount: "",
    freight_total: "",
    other_expenses_total: "",
    document_number: "",
    document_key: "",
    document_series: "",
    document_date: "",
    notes: "",
  });

  async function load(showLoading = true) {
    if (!currentBranch) {
      setLoading(false);
      return;
    }
    if (showLoading) setLoading(true);
    setError("");
    try {
      const item = await http.get<PurchaseOrder>(`purchase-orders/${id}/`);
      setOrder(item);
      reconcileReceiptKeys(
        item.id,
        item.receipts.map((receipt) => receipt.idempotency_key),
      );
      const query = new URLSearchParams(window.location.search);
      if (query.get("attachment") === "failed") {
        setAttachmentError(
          "A compra foi criada, mas o anexo não foi enviado. Selecione o arquivo novamente.",
        );
        query.delete("attachment");
      }
      if (
        !autoReceiptOpened.current &&
        query.get("receive") === "1" &&
        item.order_type === "DIRECT" &&
        item.status === "DRAFT" &&
        canReceive
      ) {
        autoReceiptOpened.current = true;
        initializeReceipt(item);
        query.delete("receive");
      }
      window.history.replaceState(
        null,
        "",
        `${window.location.pathname}${query.size ? `?${query}` : ""}`,
      );
      return item;
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível carregar a compra.",
      );
      return null;
    } finally {
      setLoading(false);
    }
  }
  const loadRef = useRef(load);
  loadRef.current = load;
  useEffect(() => {
    setOrder(null);
    setSuccess("");
    autoReceiptOpened.current = false;
    void loadRef.current();
  }, [id, branchId]);

  function receiptPayload(
    current: PurchaseOrder,
    quantities = received,
    reasonText = receiptReason,
    notesText = receiptNotes,
  ) {
    const rows = receiptRows(current, quantities);
    return {
      items: rows.map((row) => ({
        purchase_order_item: row.item.id,
        received_stock_quantity: quantityText(decimalToScaled(row.now, 6)),
        divergence_reason:
          row.divergence !== BigInt(0) ? reasonText.trim() : "",
      })),
      notes: notesText.trim(),
      divergence_reason: reasonText.trim(),
    };
  }
  function initializeReceipt(current: PurchaseOrder) {
    if (!current) return;
    const quantities = Object.fromEntries(
      current.items.map((item) => [
        item.id,
        formatEditableDecimal(item.pending_stock_quantity),
      ]),
    );
    setReceived(quantities);
    setReceiptReason("");
    setReceiptNotes("");
    setError("");
    const fingerprint = receiptPayloadFingerprint(
      receiptPayload(current, quantities, "", ""),
    );
    const key = ensureReceiptKey(current.id, fingerprint, "ready");
    const record = readReceiptKeys(current.id).find(
      (item) => item.fingerprint === fingerprint,
    );
    setReceiptKey(key);
    setReceiptUncertain(
      record?.state === "ambiguous" || record?.state === "pending",
    );
    setReceiptOpen(true);
  }
  async function openReceipt() {
    if (!order || reconcilingReceipt) return;
    setReconcilingReceipt(true);
    setError("");
    const fresh = await load(false);
    if (fresh) initializeReceipt(fresh);
    setReconcilingReceipt(false);
  }
  function receiptRows(current: PurchaseOrder, quantities = received) {
    return current.items.map((item) => {
      const now = quantities[item.id] || "0";
      const ordered = decimalToScaled(item.ordered_stock_quantity, 6);
      const previous = decimalToScaled(item.received_stock_quantity, 6);
      const currentValue = decimalToScaled(now, 6);
      const accumulated = previous + currentValue;
      return {
        item,
        now,
        ordered,
        previous,
        accumulated,
        pending: ordered > accumulated ? ordered - accumulated : BigInt(0),
        divergence:
          currentValue - (ordered > previous ? ordered - previous : BigInt(0)),
      };
    });
  }

  const syncReceiptKey = useEffectEvent(() => {
    if (!receiptOpen || !order) return;
    const fingerprint = receiptPayloadFingerprint(receiptPayload(order));
    const existing = readReceiptKeys(order.id).find(
      (item) => item.fingerprint === fingerprint,
    );
    const key = ensureReceiptKey(order.id, fingerprint, "ready");
    setReceiptKey(key);
    setReceiptUncertain(
      existing?.state === "ambiguous" || existing?.state === "pending",
    );
  });
  useEffect(() => {
    syncReceiptKey();
  }, [receiptOpen, received, receiptReason, receiptNotes, order]);

  async function place() {
    if (!order || !canPlace) return;
    setActing(true);
    setError("");
    setSuccess("");
    try {
      const next = await http.post<PurchaseOrder>(
        `purchase-orders/${order.id}/place/`,
        { exclusive_supplier_override: order.exclusive_supplier_override },
      );
      setOrder(next);
      setSuccess("Pedido realizado com sucesso.");
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível realizar o pedido.",
      );
    } finally {
      setActing(false);
    }
  }

  async function submitReceipt(event: React.FormEvent) {
    event.preventDefault();
    if (!order || !canReceive) return;
    const rows = receiptRows(order);
    if (
      rows.some(
        (row) =>
          row.pending < BigInt(0) || decimalToScaled(row.now, 6) < BigInt(0),
      )
    ) {
      setError(
        "A quantidade recebida deve estar entre zero e a pendência atual.",
      );
      return;
    }
    if (!rows.some((row) => decimalToScaled(row.now, 6) > BigInt(0))) {
      setError("Informe quantidade positiva para ao menos um item.");
      return;
    }
    if (
      rows.some((row) => row.divergence !== BigInt(0)) &&
      receiptReason.trim().length < 3
    ) {
      setError("Informe o motivo do recebimento parcial ou divergente.");
      return;
    }
    const payload = receiptPayload(order);
    const fingerprint = receiptPayloadFingerprint(payload);
    const idempotencyKey = ensureReceiptKey(order.id, fingerprint, "pending");
    setReceiptKey(idempotencyKey);
    setReceiptUncertain(true);
    setActing(true);
    setError("");
    setSuccess("");
    try {
      await http.post<PurchaseReceipt>(`purchase-orders/${order.id}/receive/`, {
        idempotency_key: idempotencyKey,
        ...payload,
      });
      removeReceiptKey(order.id, fingerprint);
      setReceiptOpen(false);
      setReceiptKey("");
      setReceiptUncertain(false);
      setSuccess("Recebimento confirmado com sucesso.");
      await load(false);
    } catch (caught) {
      const ambiguous =
        !(caught instanceof ApiError) ||
        caught.status === 0 ||
        caught.status >= 500;
      updateReceiptKeyState(
        order.id,
        fingerprint,
        ambiguous ? "ambiguous" : "ready",
      );
      setReceiptUncertain(ambiguous);
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível confirmar o recebimento. A mesma chave será usada na nova tentativa.",
      );
    } finally {
      setActing(false);
    }
  }

  async function closeReceipt() {
    if (!order || acting || reconcilingReceipt) return;
    const payload = receiptPayload(order);
    const fingerprint = receiptPayloadFingerprint(payload);
    ensureReceiptKey(
      order.id,
      fingerprint,
      receiptUncertain ? "ambiguous" : "ready",
    );
    if (!receiptUncertain) {
      setReceiptOpen(false);
      return;
    }
    if (
      !window.confirm(
        "O resultado do recebimento ainda é incerto. Recarregar a compra antes de fechar?",
      )
    )
      return;
    setReconcilingReceipt(true);
    setError("");
    const fresh = await load(false);
    if (!fresh) {
      setError(
        "Não foi possível conferir o recebimento. Mantenha esta janela aberta e tente novamente.",
      );
      setReconcilingReceipt(false);
      return;
    }
    const committed = fresh.receipts.some(
      (receipt) => receipt.idempotency_key === receiptKey,
    );
    if (committed) {
      removeReceiptKey(order.id, fingerprint);
      setSuccess("O recebimento já havia sido confirmado pelo servidor.");
    } else {
      updateReceiptKeyState(order.id, fingerprint, "ready");
    }
    setReceiptUncertain(false);
    setReceiptOpen(false);
    setReconcilingReceipt(false);
  }

  async function submitReason(event: React.FormEvent) {
    event.preventDefault();
    if (!order || !reasonAction || !canClose || reason.trim().length < 3)
      return;
    setActing(true);
    setError("");
    setSuccess("");
    try {
      const next = await http.post<PurchaseOrder>(
        `purchase-orders/${order.id}/${reasonAction}/`,
        { reason: reason.trim() },
      );
      setOrder(next);
      setReasonAction(null);
      setSuccess(
        reasonAction === "cancel"
          ? "Compra cancelada."
          : "Pendência parcial encerrada.",
      );
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível concluir a ação.",
      );
    } finally {
      setActing(false);
    }
  }

  function openEdit() {
    if (!order) return;
    setEdit({
       global_discount: formatEditableDecimal(order.global_discount || "0"),
       freight_total: formatEditableDecimal(order.freight_total || "0"),
       other_expenses_total: formatEditableDecimal(order.other_expenses_total || "0"),
      document_number: order.document_number,
      document_key: order.document_key,
      document_series: order.document_series,
      document_date: order.document_date || "",
      notes: order.notes,
    });
    setEditOpen(true);
  }
  async function submitEdit(event: React.FormEvent) {
    event.preventDefault();
    if (!order || !canCreate) return;
    setActing(true);
    setError("");
    try {
      const next = await http.patch<PurchaseOrder>(
        `purchase-orders/${order.id}/`,
        {
          ...(canCosts
            ? {
                global_discount: centsText(moneyCents(edit.global_discount)),
                freight_total: centsText(moneyCents(edit.freight_total)),
                other_expenses_total: centsText(
                  moneyCents(edit.other_expenses_total),
                ),
              }
            : {}),
          document_number: edit.document_number.trim(),
          document_key: edit.document_key.trim(),
          document_series: edit.document_series.trim(),
          document_date: edit.document_date || null,
          notes: edit.notes.trim(),
        },
      );
      setOrder(next);
      setEditOpen(false);
      setSuccess("Dados da compra atualizados.");
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível atualizar a compra.",
      );
    } finally {
      setActing(false);
    }
  }

  function openInstallments() {
    if (!order) return;
    setInstallments([
       { amount: formatEditableDecimal(order.payable_total || ""), due_date: "", notes: "" },
    ]);
    setInstallmentOpen(true);
  }
  async function submitInstallments(event: React.FormEvent) {
    event.preventDefault();
    if (!order || !canPayables) return;
    const total = installments.reduce(
      (sum, item) => sum + moneyCents(item.amount),
      BigInt(0),
    );
    if (total !== moneyCents(order.payable_total || "0")) {
      setError(
         `A soma das parcelas deve ser ${formatDecimalBRL(order.payable_total)}.`,
      );
      return;
    }
    setActing(true);
    setError("");
    try {
      await http.post<PayableInstallment[]>(
        `purchase-orders/${order.id}/installments/`,
        {
          installments: installments.map((item) => ({
            ...item,
            amount: centsText(moneyCents(item.amount)),
            notes: item.notes.trim(),
          })),
        },
      );
      setInstallmentOpen(false);
      setSuccess("Parcelas definidas com sucesso.");
      await load(false);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível definir as parcelas.",
      );
    } finally {
      setActing(false);
    }
  }

  async function chooseAttachment(file: File | null) {
    setAttachmentFile(null);
    setAttachmentError("");
    if (!file) return;
    const validation = await validatePurchaseAttachmentFile(file);
    if (validation) {
      setAttachmentError(validation);
      return;
    }
    setAttachmentFile(file);
  }

  async function uploadAttachment() {
    if (!order || !attachmentFile || !canCreate) return;
    setAttachmentBusy("upload");
    setAttachmentError("");
    const body = new FormData();
    body.append("attachment", attachmentFile);
    try {
      const next = await http.postForm<PurchaseOrder>(
        `purchase-orders/${order.id}/attachments/`,
        body,
      );
      setOrder(next);
      setAttachmentFile(null);
      setAttachmentInputKey((value) => value + 1);
      setSuccess("Anexo enviado com sucesso.");
    } catch (caught) {
      setAttachmentError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível enviar o anexo.",
      );
    } finally {
      setAttachmentBusy("");
    }
  }

  async function downloadAttachment(attachment: NonNullable<PurchaseOrder["attachments"]>[number]) {
    setAttachmentBusy("download");
    setAttachmentError("");
    try {
      const result = await http.download(attachment.download_url);
      const url = URL.createObjectURL(result.blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = result.filename || attachment.name;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (caught) {
      setAttachmentError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível baixar o anexo.",
      );
    } finally {
      setAttachmentBusy("");
    }
  }

  async function removeAttachment(attachmentId: number) {
    if (!order || !canCreate) return;
    setAttachmentBusy("remove");
    setAttachmentError("");
    try {
      const next = await http.post<PurchaseOrder>(
        `purchase-orders/${order.id}/attachments/${attachmentId}/remove/`,
        {},
      );
      setOrder(next);
      setSuccess("Anexo removido com sucesso.");
    } catch (caught) {
      setAttachmentError(
        caught instanceof ApiError ? caught.message : "Não foi possível remover o anexo.",
      );
    } finally {
      setAttachmentBusy("");
    }
  }

  if (loading)
    return (
      <div className="flex min-h-[50vh] items-center justify-center text-primary">
        <Spinner className="size-7" />
      </div>
    );
  if (!order)
    return (
      <div className="p-6">
        {error ? (
          <Alert message={error} />
        ) : (
          <EmptyState
            title="Compra não encontrada"
            description="A compra não existe ou não pertence à filial atual."
          />
        )}
      </div>
    );
  const receiveAllowed =
    (order.order_type === "DIRECT" && order.status === "DRAFT") ||
    (order.order_type === "ORDER" &&
      ["PLACED", "PARTIALLY_RECEIVED"].includes(order.status));
  const rows = receiptRows(order);

  return (
    <>
      <PageHeader
        title={`Compra ${order.order_number}`}
        description={`${order.branch_name} · ${purchaseTypeLabels[order.order_type]}`}
        action={
          <div className="flex flex-wrap gap-2">
            <Link href={returnHref} className="btn btn-secondary">
              <ArrowLeft className="size-4" />
              Voltar
            </Link>
            {order.status === "DRAFT" && canCreate && (
              <Button variant="secondary" onClick={openEdit}>
                <Pencil className="size-4" />
                Editar dados
              </Button>
            )}
            {order.order_type === "ORDER" &&
              order.status === "DRAFT" &&
              canPlace && (
                <Button onClick={() => void place()} loading={acting}>
                  <Check className="size-4" />
                  Realizar pedido
                </Button>
              )}
            {receiveAllowed && canReceive && (
              <Button
                onClick={() => void openReceipt()}
                disabled={acting || reconcilingReceipt}
                loading={reconcilingReceipt}
              >
                <ClipboardCheck className="size-4" />
                Receber
              </Button>
            )}
            {order.status === "PARTIALLY_RECEIVED" && canClose && (
              <Button
                variant="secondary"
                onClick={() => {
                  setReason("");
                  setReasonAction("close-partial");
                }}
              >
                Encerrar parcial
              </Button>
            )}
            {["DRAFT", "PLACED"].includes(order.status) && canClose && (
              <Button
                variant="danger"
                onClick={() => {
                  setReason("");
                  setReasonAction("cancel");
                }}
              >
                <XCircle className="size-4" />
                Cancelar
              </Button>
            )}
          </div>
        }
      />
      <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        {error &&
          !receiptOpen &&
          !reasonAction &&
          !editOpen &&
          !installmentOpen && <Alert message={error} />}
        {success && <Alert type="success" message={success} />}
        {readOnly && (
          <div className="rounded-md border border-warning/30 bg-warning-surface p-3 text-xs text-warning-strong">
            Sessão de suporte somente leitura. As ações estão desabilitadas.
          </div>
        )}
        <section className="card grid gap-5 p-5 sm:grid-cols-2 xl:grid-cols-4">
          <div>
            <span className="label">Status</span>
            <span
              className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-semibold ${statusTone[order.status]}`}
            >
              {purchaseStatusLabels[order.status]}
            </span>
          </div>
          <div>
            <span className="label">Fornecedor</span>
            <strong className="text-sm">{order.supplier_name}</strong>
          </div>
          <div>
            <span className="label">Criada em</span>
            <span className="text-sm">{formatDate(order.created_at)}</span>
          </div>
          <div>
            <span className="label">Documento</span>
            <span className="text-sm">
              {order.document_number || "Não informado"}
              {order.document_series ? ` · série ${order.document_series}` : ""}
            </span>
          </div>
        </section>
        <div className="grid gap-4 xl:grid-cols-[1fr_22rem]">
          <section className="card overflow-hidden">
            <div className="card-header">
              <div>
                <h2 className="text-sm font-bold">Itens da compra</h2>
                <p className="mt-1 text-[11px] text-muted">
                  Quantidades na apresentação comercial.
                </p>
              </div>
            </div>
            <div className="table-wrap">
              <table className="data-table min-w-200">
                <thead>
                  <tr>
                    <th># / Produto</th>
                    <th>Apresentação</th>
                    <th>Pedido</th>
                    <th>Recebido</th>
                    <th>Pendente</th>
                    {canCosts && (
                      <>
                        <th>Preço</th>
                        <th>Total efetivo</th>
                      </>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {order.items.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <strong>
                          {item.line_number}. {item.product_name}
                        </strong>
                        <small className="block text-muted">
                          {item.product_internal_code}
                        </small>
                      </td>
                      <td>
                        {purchasePresentationLabel(
                          item.presentation_unit_code,
                          item.presentation_description,
                        )}
                        <small className="block text-muted">
                          {purchaseBaseEquivalent(
                            item.ordered_stock_quantity,
                            item.conversion_factor,
                            item.presentation_description,
                            item.product_stock_unit,
                          )}
                        </small>
                      </td>
                      <td>{formatQuantity(item.ordered_quantity)}</td>
                      <td>
                        {formatQuantity(item.received_quantity)}
                        <small className="block text-muted">
                          {formatQuantity(
                            item.received_stock_quantity,
                            item.product_stock_unit,
                          )}
                        </small>
                      </td>
                      <td className="font-bold">
                        {formatQuantity(item.pending_quantity)}
                        <small className="block text-muted">
                          {formatQuantity(
                            item.pending_stock_quantity,
                            item.product_stock_unit,
                          )}
                        </small>
                      </td>
                      {canCosts && (
                        <>
                          <td>{formatDecimalBRL(item.purchase_unit_price)}</td>
                          <td>{formatBRL(item.effective_total)}</td>
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          {canCosts && (
            <section className="card space-y-3 p-5">
              <h2 className="text-sm font-bold">Totais</h2>
              <dl className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <dt className="text-muted">Bruto</dt>
                  <dd>{formatBRL(order.gross_total)}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-muted">Desconto</dt>
                  <dd>- {formatBRL(order.global_discount)}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-muted">Frete</dt>
                  <dd>{formatBRL(order.freight_total)}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-muted">Despesas</dt>
                  <dd>{formatBRL(order.other_expenses_total)}</dd>
                </div>
                <div className="flex justify-between border-t border-subtle pt-3 text-base font-extrabold">
                  <dt>A pagar</dt>
                  <dd>{formatBRL(order.payable_total)}</dd>
                </div>
              </dl>
            </section>
          )}
        </div>
        <section className="card grid gap-4 p-5 sm:grid-cols-2 xl:grid-cols-4">
          <div>
            <span className="label">Chave do documento</span>
            <p className="break-all text-xs">{order.document_key || "-"}</p>
          </div>
          <div>
            <span className="label">Data do documento</span>
            <p className="text-xs">
              {order.document_date
                ? new Date(
                    `${order.document_date}T12:00:00`,
                  ).toLocaleDateString("pt-BR")
                : "-"}
            </p>
          </div>
          <div className="space-y-2 xl:col-span-2">
            <span className="label">Anexos</span>
            {order.attachments.length ? (
              <div className="space-y-2">
                {order.attachments.map((attachment) => (
                  <div key={attachment.id} className="flex flex-wrap items-center gap-2">
                    <span className="min-w-0 flex-1 truncate text-xs font-semibold">
                      {attachment.name}
                    </span>
                    <Button
                      type="button"
                      variant="secondary"
                      loading={attachmentBusy === "download"}
                      disabled={!!attachmentBusy}
                      onClick={() => void downloadAttachment(attachment)}
                    >
                      <Download className="size-4" /> Baixar
                    </Button>
                    {canCreate && (
                      <Button
                        type="button"
                        variant="danger"
                        loading={attachmentBusy === "remove"}
                        disabled={!!attachmentBusy}
                        onClick={() => void removeAttachment(attachment.id)}
                      >
                        Remover
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted">Nenhum anexo.</p>
            )}
            {canCreate && (
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                <Input
                  key={attachmentInputKey}
                  type="file"
                  accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
                  disabled={!!attachmentBusy}
                  onChange={(event) =>
                    void chooseAttachment(event.target.files?.[0] || null)
                  }
                />
                <Button
                  type="button"
                  loading={attachmentBusy === "upload"}
                  disabled={!attachmentFile || !!attachmentBusy}
                  onClick={() => void uploadAttachment()}
                >
                  <FileUp className="size-4" />
                  Enviar
                </Button>
              </div>
            )}
            <p className="text-[10px] text-muted">
              PDF, JPG ou PNG, nome seguro e até 10 MB.
            </p>
            {attachmentError && (
              <p className="field-error" role="alert">
                {attachmentError}
              </p>
            )}
          </div>
          <div>
            <span className="label">Observações</span>
            <p className="whitespace-pre-wrap text-xs">{order.notes || "-"}</p>
          </div>
          {order.closure_reason && (
            <div className="sm:col-span-2 xl:col-span-4">
              <span className="label">Motivo do encerramento</span>
              <p className="text-xs">{order.closure_reason}</p>
            </div>
          )}
        </section>
        {canPayables && (
          <section className="card overflow-hidden">
            <div className="card-header">
              <div>
                <h2 className="text-sm font-bold">Contas a pagar</h2>
                <p className="mt-1 text-[11px] text-muted">
                  Parcelas exclusivas desta compra.
                </p>
              </div>
              {order.status === "DRAFT" && order.installments?.length === 0 && (
                <Button variant="secondary" onClick={openInstallments}>
                  <Plus className="size-4" />
                  Definir parcelas
                </Button>
              )}
            </div>
            {order.installments?.length ? (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Parcela</th>
                      <th>Vencimento</th>
                      <th>Valor</th>
                      <th>Status</th>
                      <th>Observação</th>
                    </tr>
                  </thead>
                  <tbody>
                    {order.installments.map((item) => (
                      <tr key={item.id}>
                        <td>{item.installment_number}</td>
                        <td>
                          {new Date(
                            `${item.due_date}T12:00:00`,
                          ).toLocaleDateString("pt-BR")}
                        </td>
                        <td>{formatBRL(item.amount)}</td>
                        <td>
                          {item.status === "PENDING"
                            ? "Pendente"
                            : item.status === "PAID"
                              ? "Paga"
                              : "Cancelada"}
                        </td>
                        <td>{item.notes || item.cancellation_reason || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="p-5 text-xs text-muted">
                Nenhuma parcela definida.
              </p>
            )}
          </section>
        )}
        <section className="card overflow-hidden">
          <div className="card-header">
            <div>
              <h2 className="text-sm font-bold">Recebimentos</h2>
              <p className="mt-1 text-[11px] text-muted">
                Histórico imutável de confirmações.
              </p>
            </div>
          </div>
          {order.receipts.length ? (
            <div className="space-y-4 p-4">
              {order.receipts.map((receipt) => (
                <article
                  key={receipt.id}
                  className="overflow-hidden rounded-lg border border-subtle"
                >
                  <div className="flex flex-wrap justify-between gap-2 bg-surface-muted p-3 text-xs">
                    <strong>{formatDate(receipt.confirmed_at)}</strong>
                    <span className="font-mono text-[10px] text-muted">
                      {receipt.id}
                    </span>
                  </div>
                  <div className="table-wrap">
                    <table className="data-table min-w-225">
                      <thead>
                        <tr>
                          <th>Produto</th>
                          <th>Pedido</th>
                          <th>Anterior</th>
                          <th>Agora</th>
                          <th>Acumulado</th>
                           <th>Pendente</th>
                           <th>Divergência</th>
                           {canCosts && <th>Financeiro</th>}
                        </tr>
                      </thead>
                      <tbody>
                        {receipt.items.map((item) => (
                          <tr key={item.id}>
                            <td>
                              <strong>{item.product_name_snapshot}</strong>
                              <small className="block text-muted">
                                {item.presentation_snapshot.replace(" - ", " — ")}
                              </small>
                            </td>
                            <td>
                              {formatQuantity(item.ordered_stock_quantity)}
                            </td>
                            <td>
                              {formatQuantity(item.previously_received_stock_quantity)}
                            </td>
                            <td>{formatQuantity(item.stock_quantity)}</td>
                            <td>{formatQuantity(item.accumulated_stock_quantity)}</td>
                            <td>{formatQuantity(item.pending_stock_quantity)}</td>
                            <td
                              className={
                                compareDecimal(item.divergence_stock_quantity, "0")
                                  ? "font-bold text-warning-strong"
                                  : ""
                              }
                            >
                              {formatQuantity(item.divergence_stock_quantity)}
                              {item.divergence_reason && (
                                <small className="block text-muted">
                                  {item.divergence_reason}
                                </small>
                              )}
                            </td>
                            {canCosts && (
                              <td className="text-xs">
                                <span className="block">
                                  Pedido: {formatBRL(item.ordered_total)}
                                </span>
                                <span className="block">
                                  Recebido: {formatBRL(item.received_total)}
                                </span>
                                <span className="block text-muted">
                                  Diferença: {formatBRL(item.difference_total)}
                                </span>
                              </td>
                            )}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {(receipt.notes || receipt.divergence_reason) && (
                    <p className="border-t border-subtle p-3 text-xs text-muted">
                      {receipt.divergence_reason || receipt.notes}
                    </p>
                  )}
                </article>
              ))}
            </div>
          ) : (
            <p className="p-5 text-xs text-muted">
              Nenhum recebimento confirmado.
            </p>
          )}
        </section>
      </div>

      <Modal
        open={receiptOpen}
        title="Confirmar recebimento"
        description={`Compra ${order.order_number} · a confirmação movimentará o estoque.`}
        onClose={() => void closeReceipt()}
        size="xl"
      >
        <form onSubmit={submitReceipt}>
          <div className="space-y-4 p-5">
            {error && <Alert message={error} />}
            {receiptUncertain && (
              <div className="rounded-md border border-warning/30 bg-warning-surface p-3 text-xs text-warning-strong">
                O resultado da última tentativa é incerto. Reenvie sem alterar
                os dados para usar a mesma chave, ou use Voltar para recarregar
                e conferir o servidor.
              </div>
            )}
            <div className="table-wrap rounded-lg border border-subtle">
              <table className="data-table min-w-225">
                <thead>
                  <tr>
                    <th>Produto</th>
                    <th>Pedido (base)</th>
                    <th>Anterior</th>
                    <th>Quantidade recebida</th>
                    <th>Acumulado</th>
                    <th>Pendente</th>
                    <th>Divergência</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map(
                    ({
                      item,
                      ordered,
                      previous,
                      accumulated,
                      pending,
                      divergence,
                    }) => (
                      <tr key={item.id}>
                        <td>
                          <strong>{item.product_name}</strong>
                          <small className="block text-muted">
                            {purchasePresentationLabel(
                              item.presentation_unit_code,
                              item.presentation_description,
                            )}
                          </small>
                        </td>
                        <td>
                          {formatQuantity(
                            quantityText(ordered),
                            item.product_stock_unit,
                          )}
                        </td>
                        <td>
                          {formatQuantity(
                            quantityText(previous),
                            item.product_stock_unit,
                          )}
                        </td>
                        <td>
                          <Input
                            className="w-28"
                            required
                            inputMode="decimal"
                            pattern="\d+([.,]\d{1,6})?"
                            value={received[item.id] || ""}
                            onChange={(event) =>
                              setReceived((value) => ({
                                ...value,
                                [item.id]: event.target.value.replace(",", "."),
                              }))
                            }
                            disabled={
                              acting ||
                              reconcilingReceipt ||
                              receiptUncertain ||
                              order.order_type === "DIRECT"
                            }
                          />
                          <small className="mt-1 block text-muted">
                            Equivalente: {purchaseBaseEquivalent(
                              received[item.id] || "0",
                              item.conversion_factor,
                              item.presentation_description,
                              item.product_stock_unit,
                            )}
                          </small>
                        </td>
                        <td>
                          {formatQuantity(
                            quantityText(accumulated),
                            item.product_stock_unit,
                          )}
                        </td>
                        <td
                          className={
                            pending
                              ? "font-bold text-warning-strong"
                              : "font-bold text-success-strong"
                          }
                        >
                          {formatQuantity(
                            quantityText(pending),
                            item.product_stock_unit,
                          )}
                        </td>
                        <td
                          className={
                            divergence ? "font-bold text-warning-strong" : ""
                          }
                        >
                          {formatQuantity(
                            quantityText(divergence),
                            item.product_stock_unit,
                          )}
                        </td>
                      </tr>
                    ),
                  )}
                </tbody>
              </table>
            </div>
            <Field
              label="Motivo da divergência"
              optional={!rows.some((row) => row.divergence !== BigInt(0))}
            >
              <Textarea
                minLength={3}
                required={rows.some((row) => row.divergence !== BigInt(0))}
                value={receiptReason}
                onChange={(event) => setReceiptReason(event.target.value)}
                disabled={acting || reconcilingReceipt || receiptUncertain}
                placeholder="Obrigatório para recebimento parcial ou divergente"
              />
            </Field>
            <Field label="Observações" optional>
              <Textarea
                value={receiptNotes}
                onChange={(event) => setReceiptNotes(event.target.value)}
                disabled={acting || reconcilingReceipt || receiptUncertain}
              />
            </Field>
            <p className="text-[10px] text-muted">
              Chave idempotente mantida nas tentativas do mesmo conteúdo:{" "}
              <span className="font-mono">{receiptKey}</span>
            </p>
          </div>
          <div className="flex justify-end gap-2 border-t border-subtle p-4">
            <Button
              type="button"
              variant="secondary"
              onClick={() => void closeReceipt()}
              disabled={acting || reconcilingReceipt}
            >
              Voltar
            </Button>
            <Button
              type="submit"
              loading={acting}
              disabled={reconcilingReceipt}
            >
              Confirmar recebimento
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        open={!!reasonAction}
        title={
          reasonAction === "cancel"
            ? "Cancelar compra"
            : "Encerrar recebimento parcial"
        }
        description="A ação será auditada e exige justificativa."
        onClose={() => !acting && setReasonAction(null)}
        size="md"
      >
        <form onSubmit={submitReason}>
          <div className="space-y-4 p-5">
            {error && <Alert message={error} />}
            <Field label="Motivo">
              <Textarea
                required
                minLength={3}
                maxLength={2000}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                disabled={acting}
              />
            </Field>
          </div>
          <div className="flex justify-end gap-2 border-t border-subtle p-4">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setReasonAction(null)}
              disabled={acting}
            >
              Voltar
            </Button>
            <Button
              type="submit"
              variant={reasonAction === "cancel" ? "danger" : "primary"}
              loading={acting}
            >
              Confirmar
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        open={installmentOpen}
        title="Definir parcelas"
        description={`A soma deve ser ${formatBRL(order.payable_total)}.`}
        onClose={() => !acting && setInstallmentOpen(false)}
        size="lg"
      >
        <form onSubmit={submitInstallments}>
          <div className="space-y-3 p-5">
            {error && <Alert message={error} />}
            {installments.map((item, index) => (
              <div
                key={index}
                className="grid gap-3 rounded-md border border-subtle p-3 sm:grid-cols-[8rem_10rem_1fr_auto] sm:items-end"
              >
                <Field label={`Valor ${index + 1}`}>
                  <MoneyInput
                    required
                    value={item.amount}
                    onValueChange={(amount) =>
                      setInstallments((current) =>
                        current.map((value, position) =>
                          position === index ? { ...value, amount } : value,
                        ),
                      )
                    }
                  />
                </Field>
                <Field label="Vencimento">
                  <Input
                    required
                    type="date"
                    value={item.due_date}
                    onChange={(event) =>
                      setInstallments((current) =>
                        current.map((value, position) =>
                          position === index
                            ? { ...value, due_date: event.target.value }
                            : value,
                        ),
                      )
                    }
                  />
                </Field>
                <Field label="Observação" optional>
                  <Input
                    value={item.notes}
                    onChange={(event) =>
                      setInstallments((current) =>
                        current.map((value, position) =>
                          position === index
                            ? { ...value, notes: event.target.value }
                            : value,
                        ),
                      )
                    }
                  />
                </Field>
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`Remover parcela ${index + 1}`}
                  disabled={installments.length === 1}
                  onClick={() =>
                    setInstallments((current) =>
                      current.filter((_, position) => position !== index),
                    )
                  }
                >
                  <XCircle className="size-4" />
                </button>
              </div>
            ))}
            <Button
              type="button"
              variant="secondary"
              onClick={() =>
                setInstallments((current) => [
                  ...current,
                  { amount: "", due_date: "", notes: "" },
                ])
              }
            >
              <Plus className="size-4" />
              Parcela
            </Button>
          </div>
          <div className="flex justify-end gap-2 border-t border-subtle p-4">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setInstallmentOpen(false)}
              disabled={acting}
            >
              Voltar
            </Button>
            <Button type="submit" loading={acting}>
              Definir parcelas
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        open={editOpen}
        title="Editar dados da compra"
        description="Somente compras em rascunho podem ter valores comerciais alterados."
        onClose={() => !acting && setEditOpen(false)}
        size="xl"
      >
        <form onSubmit={submitEdit}>
          <div className="grid gap-4 p-5 sm:grid-cols-3">
            {error && (
              <div className="sm:col-span-3">
                <Alert message={error} />
              </div>
            )}
            {canCosts && (
              <>
                <Field label="Desconto global">
                  <MoneyInput
                    value={edit.global_discount}
                    onValueChange={(value) =>
                      setEdit((current) => ({
                        ...current,
                        global_discount: value,
                      }))
                    }
                  />
                </Field>
                <Field label="Frete">
                  <MoneyInput
                    value={edit.freight_total}
                    onValueChange={(value) =>
                      setEdit((current) => ({
                        ...current,
                        freight_total: value,
                      }))
                    }
                  />
                </Field>
                <Field label="Outras despesas">
                  <MoneyInput
                    value={edit.other_expenses_total}
                    onValueChange={(value) =>
                      setEdit((current) => ({
                        ...current,
                        other_expenses_total: value,
                      }))
                    }
                  />
                </Field>
              </>
            )}
            <Field label="Número" optional>
              <Input
                value={edit.document_number}
                onChange={(event) =>
                  setEdit((current) => ({
                    ...current,
                    document_number: event.target.value,
                  }))
                }
              />
            </Field>
            <Field label="Série" optional>
              <Input
                value={edit.document_series}
                onChange={(event) =>
                  setEdit((current) => ({
                    ...current,
                    document_series: event.target.value,
                  }))
                }
              />
            </Field>
            <Field label="Data" optional>
              <Input
                type="date"
                value={edit.document_date}
                onChange={(event) =>
                  setEdit((current) => ({
                    ...current,
                    document_date: event.target.value,
                  }))
                }
              />
            </Field>
            <div className="sm:col-span-2">
              <Field label="Chave" optional>
                <Input
                  value={edit.document_key}
                  onChange={(event) =>
                    setEdit((current) => ({
                      ...current,
                      document_key: event.target.value,
                    }))
                  }
                />
              </Field>
            </div>
            <div className="sm:col-span-3">
              <Field label="Observações" optional>
                <Textarea
                  value={edit.notes}
                  onChange={(event) =>
                    setEdit((current) => ({
                      ...current,
                      notes: event.target.value,
                    }))
                  }
                />
              </Field>
            </div>
          </div>
          <div className="flex justify-end gap-2 border-t border-subtle p-4">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setEditOpen(false)}
              disabled={acting}
            >
              Voltar
            </Button>
            <Button type="submit" loading={acting}>
              Salvar
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
}

export default function PurchaseDetailPage() {
  return (
    <AdminGuard requiredPermissions={[permissions.viewPurchase]}>
      <PurchaseDetail />
    </AdminGuard>
  );
}
