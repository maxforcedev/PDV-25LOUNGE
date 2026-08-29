"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRightLeft, Ban, CheckCircle2, Combine, Plus, RotateCcw, Scissors, ShoppingCart, WalletCards, XCircle } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { ModifierPicker } from "@/components/modifier-picker";
import { CustomerQuickPicker } from "@/components/customer-quick-picker";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, Field, Input, Modal, Select, Spinner } from "@/components/ui";
import { formatBRL, formatDate, formatQuantity, fieldError } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { CheckoutOptions, Command, CommandPayment, CommandPaymentSummary, Customer, ModifierSelection, OrderItem, Product, SalePreview, SaleUserOption, Table } from "@/types";

function CommandDetail() {
  const id = String(useParams<{ id: string }>().id);
  const { hasFeature, hasPermission, supportSession, user } = useAuth();
  const readOnly = supportSession?.mode === "READ_ONLY";
  const canAddItems = hasPermission(permissions.addCommandItems) && !readOnly;
  const canCancelItems = hasPermission(permissions.cancelCommandItems) && !readOnly;
  const canFinalize = hasPermission(permissions.finalizeCommand) && !readOnly;
  const canSetCustomer = hasPermission(permissions.openCommand) && !readOnly;
  const canViewPayments = hasPermission(permissions.viewCommandPayments);
  const canRecordPayments = hasPermission(permissions.recordCommandPayment) && !readOnly;
  const canReversePayments = hasPermission(permissions.reverseCommandPayment) && !readOnly;
  const usesTables = hasFeature("tables");
  const canTransfer = hasFeature("commands") && usesTables && hasPermission(permissions.transferCommand) && !readOnly;
  const canTransferItems = hasFeature("commands") && hasPermission(permissions.transferCommandItems) && !readOnly;
  const canMerge = hasFeature("commands") && hasPermission(permissions.mergeCommands) && !readOnly;
  const canSplit = hasFeature("commands") && hasPermission(permissions.splitCommand) && !readOnly;
  const canDiscount = hasPermission(permissions.applyDiscount);
  const canWaiveServiceFee = hasPermission(permissions.waiveServiceFee);
  const [command, setCommand] = useState<Command | null>(null);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [customerSaving, setCustomerSaving] = useState(false);
  const [items, setItems] = useState<OrderItem[]>([]);
  const [paymentSummary, setPaymentSummary] = useState<CommandPaymentSummary | null>(null);
  const [commandPayments, setCommandPayments] = useState<CommandPayment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [products, setProducts] = useState<Product[]>([]);
  const [modifierProduct, setModifierProduct] = useState<Product | null>(null);
  const [productId, setProductId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [saving, setSaving] = useState(false);
  const [cancelItem, setCancelItem] = useState<OrderItem | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [finalizeOpen, setFinalizeOpen] = useState(false);
  const [paymentOpen, setPaymentOpen] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState("");
  const [paymentAmount, setPaymentAmount] = useState("");
  const [paymentReceivedAmount, setPaymentReceivedAmount] = useState("");
  const [paymentCashSession, setPaymentCashSession] = useState("");
  const [reversePayment, setReversePayment] = useState<CommandPayment | null>(null);
  const [reverseReason, setReverseReason] = useState("");
  const [cashSessions, setCashSessions] = useState<CheckoutOptions["cash_sessions"]>([]);
  const [cashSession, setCashSession] = useState("");
  const [paymentRows, setPaymentRows] = useState([{ method: "", amount: "", received_amount: "" }]);
  const [paymentMethods, setPaymentMethods] = useState<Array<{ id: number; name: string; code: string }>>([]);
  const [preview, setPreview] = useState<SalePreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [sellers, setSellers] = useState<SaleUserOption[]>([]);
  const [authorizers, setAuthorizers] = useState<SaleUserOption[]>([]);
  const [serviceFeeAuthorizers, setServiceFeeAuthorizers] = useState<SaleUserOption[]>([]);
  const [seller, setSeller] = useState("");
  const [discount, setDiscount] = useState("0.00");
  const [discountAuthorizer, setDiscountAuthorizer] = useState("");
  const [discountPassword, setDiscountPassword] = useState("");
  const [serviceFeeWaived, setServiceFeeWaived] = useState(false);
  const [serviceFeeAuthorizer, setServiceFeeAuthorizer] = useState("");
  const [serviceFeePassword, setServiceFeePassword] = useState("");
  const [operation, setOperation] = useState<"transfer" | "items" | "merge" | "split" | null>(null);
  const [operationCommands, setOperationCommands] = useState<Command[]>([]);
  const [operationTables, setOperationTables] = useState<Table[]>([]);
  const [destinationCommand, setDestinationCommand] = useState("");
  const [destinationTable, setDestinationTable] = useState("");
  const [splitIdentifier, setSplitIdentifier] = useState("");
  const [itemQuantities, setItemQuantities] = useState<Record<number, string>>({});
  const context = useRef("");
  const hasAppliedPayments = Number(paymentSummary?.paid_total || "0") > 0;

  async function load() {
    setLoading(true); setError("");
    try {
      const [cmd, orderItems, summary, payments] = await Promise.all([
        http.get<Command>(`commands/${id}/`),
        http.getAll<OrderItem>(`order-items/?order__command=${id}`),
        canViewPayments ? http.get<CommandPaymentSummary>(`commands/${id}/payment-summary/`) : Promise.resolve(null),
        canViewPayments ? http.get<CommandPayment[]>(`commands/${id}/payments/`) : Promise.resolve([]),
      ]);
      setCommand(cmd);
      if (cmd.customer) {
        http.get<Customer>(`customers/${cmd.customer}/`).then(setCustomer).catch(() => setCustomer(null));
      } else setCustomer(null);
      setItems(orderItems);
      setPaymentSummary(summary);
      setCommandPayments(payments);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar a comanda.");
    } finally { setLoading(false); }
  }

  const loadRef = useRef(load);
  loadRef.current = load;
  useEffect(() => { setCommand(null); void loadRef.current(); }, [id]);

  async function openAdd() {
    setProductId(""); setQuantity("1"); setFields({});
    try {
      const prods = await http.getAll<Product>("sales/catalog/?operation_type=sale&channel=command");
      setProducts(prods);
    } catch { setProducts([]); }
    setAddOpen(true);
  }

  async function changeCustomer(next: Customer | null) {
    if (!command || customerSaving) return;
    setCustomerSaving(true); setError("");
    try {
      await http.post(`commands/${command.id}/set-customer/`, { customer: next?.id || null });
      setCustomer(next);
      await load();
    } catch (caught) { setError(caught instanceof ApiError ? caught.message : "Não foi possível alterar o cliente."); }
    finally { setCustomerSaving(false); }
  }

  async function addItem(modifiers: ModifierSelection[] = []) {
    if (!command) return;
    setSaving(true); setError(""); setFields({});
    try {
      await http.post(`commands/${command.id}/add-item/`, { product: Number(productId), quantity: quantity.replace(",", "."), modifiers });
      setAddOpen(false);
      await load();
    } catch (caught) {
      if (caught instanceof ApiError) { setError(caught.message); setFields(caught.fields || {}); }
      else setError("Não foi possível adicionar o item.");
    } finally { setSaving(false); }
  }

  function requestAddItem() {
    const product = products.find((item) => item.id === Number(productId));
    if (!product) {
      setError("Selecione um produto.");
      return;
    }
    if ((product.modifier_groups || []).some((group) => group.status === "active")) {
      setAddOpen(false);
      setModifierProduct(product);
      return;
    }
    void addItem();
  }

  async function confirmItem(item: OrderItem) {
    setError(""); setSuccess("");
    try {
      await http.post(`order-items/${item.id}/confirm/`, { idempotency_key: crypto.randomUUID() });
      await load();
      setSuccess("Item confirmado com baixa de estoque.");
    } catch (caught) { setError(caught instanceof ApiError ? caught.message : "Não foi possível confirmar o item."); }
  }

  async function doCancel() {
    if (!cancelItem || !command) return;
    setSaving(true); setError("");
    try {
      await http.post(`order-items/${cancelItem.id}/cancel/`, { idempotency_key: crypto.randomUUID(), reason: cancelReason });
      setCancelItem(null); setCancelReason("");
      await load();
    } catch (caught) { setError(caught instanceof ApiError ? caught.message : "Não foi possível cancelar o item."); }
    finally { setSaving(false); }
  }

  async function openOperation(next: "transfer" | "items" | "merge" | "split") {
    setError(""); setFields({}); setDestinationCommand(""); setDestinationTable(""); setSplitIdentifier("");
    setItemQuantities(Object.fromEntries(items.filter((item) => item.status !== "cancelled").map((item) => [item.id, item.quantity])));
    try {
      const [commands, tables] = await Promise.all([
        http.getAll<Command>("commands/open-list/"),
        usesTables ? http.getAll<Table>("tables/") : Promise.resolve([]),
      ]);
      setOperationCommands(commands.filter((item) => item.id !== command?.id));
      setOperationTables(tables.filter((item) => item.status === "active"));
      setOperation(next);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as opções da operação.");
    }
  }

  function selectedOperationItems() {
    return items.flatMap((item) => {
      const quantity = itemQuantities[item.id]?.trim().replace(",", ".");
      return item.status !== "cancelled" && quantity && Number(quantity) > 0 ? [{ item: item.id, quantity }] : [];
    });
  }

  async function executeOperation() {
    if (!command || !operation) return;
    const key = crypto.randomUUID();
    const selectedItems = selectedOperationItems();
    if ((operation === "items" || operation === "split") && !selectedItems.length) {
      setError("Informe a quantidade de pelo menos um item.");
      return;
    }
    if ((operation === "items" || operation === "merge") && !destinationCommand) {
      setError("Selecione a comanda de destino.");
      return;
    }
    setSaving(true); setError(""); setFields({});
    try {
      if (operation === "transfer") {
        await http.post(`commands/${command.id}/transfer/`, { table: destinationTable ? Number(destinationTable) : null, idempotency_key: key });
      } else if (operation === "items") {
        await http.post(`commands/${command.id}/transfer-items/`, { command: Number(destinationCommand), items: selectedItems, idempotency_key: key });
      } else if (operation === "merge") {
        await http.post(`commands/${command.id}/merge/`, { command: Number(destinationCommand), idempotency_key: key });
      } else {
        await http.post(`commands/${command.id}/split/`, { items: selectedItems, table: destinationTable ? Number(destinationTable) : null, identifier: splitIdentifier.trim(), idempotency_key: key });
      }
      const message = operation === "transfer" ? "Mesa da comanda transferida." : operation === "items" ? "Itens transferidos com sucesso." : operation === "merge" ? "Comandas mescladas com sucesso." : "Nova comanda criada com os itens selecionados.";
      setOperation(null);
      await load();
      setSuccess(message);
    } catch (caught) {
      if (caught instanceof ApiError) { setError(caught.message); setFields(caught.fields || {}); }
      else setError("Não foi possível concluir a operação.");
    } finally { setSaving(false); }
  }

  async function requestPreview(options?: { seller?: string; discount?: string; serviceFeeWaived?: boolean }) {
    setPreviewLoading(true);
    try {
      const result = await http.post<SalePreview>(`commands/${id}/calculate/`, {
        ...((options?.seller ?? seller) ? { seller_user: Number(options?.seller ?? seller) } : {}),
        discount: options?.discount ?? discount,
        service_fee_waived: options?.serviceFeeWaived ?? serviceFeeWaived,
      });
      setPreview(result);
      return result;
    } catch (caught) {
      setPreview(null);
      setError(caught instanceof ApiError ? caught.message : "Não foi possível calcular o fechamento.");
      return null;
    } finally { setPreviewLoading(false); }
  }

  async function openFinalize() {
    setError("");
    try {
      const [options, sellerOptions, discountOptions, feeOptions, summary] = await Promise.all([
        http.get<CheckoutOptions>("commands/checkout-options/"),
        http.get<SaleUserOption[]>("commands/sellers/"),
        http.get<SaleUserOption[]>("commands/discount-authorizers/"),
        http.get<SaleUserOption[]>("commands/service-fee-authorizers/"),
        http.get<CommandPaymentSummary>(`commands/${id}/payment-summary/`),
      ]);
      setPaymentSummary(summary);
      setPaymentMethods(options.payment_methods.map((method) => ({ id: method.id, name: method.name, code: method.code })));
      setCashSessions(options.cash_sessions);
      setCashSession(options.cash_sessions.length === 1 ? String(options.cash_sessions[0].id) : "");
      setSellers(sellerOptions); setAuthorizers(discountOptions); setServiceFeeAuthorizers(feeOptions);
      const defaultSeller = sellerOptions.find((item) => item.id === user?.id) || sellerOptions[0];
      setSeller(defaultSeller ? String(defaultSeller.id) : "");
      setDiscount("0.00"); setDiscountAuthorizer(""); setDiscountPassword("");
      setServiceFeeWaived(false); setServiceFeeAuthorizer(""); setServiceFeePassword("");
      if (defaultSeller) await requestPreview({ seller: String(defaultSeller.id), discount: "0.00", serviceFeeWaived: false });
      else setError("Não há atendente habilitado para vendas nesta filial.");
    } catch {
      setPaymentMethods([]);
      setCashSessions([]);
      setCashSession("");
      setError("Não foi possível carregar uma sessão de Caixa aberta.");
    }
    setPaymentRows([{ method: "", amount: "", received_amount: "" }]);
    setFinalizeOpen(true);
  }

  async function openPayment() {
    setError(""); setFields({});
    try {
      const options = await http.get<CheckoutOptions>("commands/checkout-options/");
      setPaymentMethods(options.payment_methods.map((method) => ({ id: method.id, name: method.name, code: method.code })));
      setCashSessions(options.cash_sessions);
      setPaymentCashSession(options.cash_sessions.length === 1 ? String(options.cash_sessions[0].id) : "");
      setPaymentMethod(""); setPaymentAmount(""); setPaymentReceivedAmount("");
      setPaymentOpen(true);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as opções de pagamento.");
    }
  }

  async function recordPayment() {
    if (!command) return;
    const method = paymentMethods.find((item) => item.id === Number(paymentMethod));
    if (!method || Number(paymentAmount.replace(",", ".")) <= 0) {
      setError("Informe a forma e o valor aplicado.");
      return;
    }
    if (method.code === "cash" && !paymentCashSession) {
      setError("Selecione uma sessão de Caixa aberta para pagamento em dinheiro.");
      return;
    }
    setSaving(true); setError(""); setFields({});
    try {
      const discountAuthorization = !canDiscount && Number(discount.replace(",", ".")) > 0
        ? { user: Number(discountAuthorizer), method: "password", credential: discountPassword }
        : undefined;
      const feeAuthorization = !canWaiveServiceFee && serviceFeeWaived
        ? { user: Number(serviceFeeAuthorizer), method: "password", credential: serviceFeePassword }
        : undefined;
      await http.post(`commands/${command.id}/record-payment/`, {
        payment_method: method.id,
        amount: paymentAmount.replace(",", "."),
        ...(method.code === "cash" ? {
          received_amount: (paymentReceivedAmount || paymentAmount).replace(",", "."),
          cash_session: Number(paymentCashSession),
        } : {}),
        discount: discount.replace(",", "."),
        service_fee_waived: serviceFeeWaived,
        ...(discountAuthorization ? { discount_authorization: discountAuthorization } : {}),
        ...(feeAuthorization ? { service_fee_authorization: feeAuthorization } : {}),
        idempotency_key: crypto.randomUUID(),
      });
      setPaymentOpen(false);
      await load();
      setSuccess("Pagamento registrado.");
    } catch (caught) {
      if (caught instanceof ApiError) { setError(caught.message); setFields(caught.fields || {}); }
      else setError("Não foi possível registrar o pagamento.");
    } finally { setSaving(false); }
  }

  async function doReversePayment() {
    if (!command || !reversePayment) return;
    setSaving(true); setError(""); setFields({});
    try {
      await http.post(`commands/${command.id}/payments/${reversePayment.id}/reverse/`, {
        idempotency_key: crypto.randomUUID(), reason: reverseReason,
      });
      setReversePayment(null); setReverseReason("");
      await load();
      setSuccess("Pagamento estornado.");
    } catch (caught) {
      if (caught instanceof ApiError) { setError(caught.message); setFields(caught.fields || {}); }
      else setError("Não foi possível estornar o pagamento.");
    } finally { setSaving(false); }
  }

  async function finalize() {
    if (!command) return;
    setSaving(true); setError("");
    if (!cashSession) {
      setError("Selecione uma sessão de Caixa aberta para finalizar a comanda.");
      setSaving(false);
      return;
    }
    if (!seller) {
      setError("Selecione o atendente responsável pela venda.");
      setSaving(false);
      return;
    }
    if (Number(discount.replace(",", ".")) > 0 && !canDiscount && (!discountAuthorizer || !discountPassword)) {
      setError("Informe o autorizador e a senha para aplicar o desconto.");
      setSaving(false);
      return;
    }
    if (serviceFeeWaived && !canWaiveServiceFee && (!serviceFeeAuthorizer || !serviceFeePassword)) {
      setError("Informe o autorizador e a senha para retirar a taxa de serviço.");
      setSaving(false);
      return;
    }
    const [latestPreview, latestSummary] = await Promise.all([
      requestPreview(),
      canViewPayments ? http.get<CommandPaymentSummary>(`commands/${command.id}/payment-summary/`) : Promise.resolve(null),
    ]);
    if (!latestPreview || !latestSummary) { setSaving(false); return; }
    setPaymentSummary(latestSummary);
    const payments = paymentRows.filter((row) => row.method && Number(row.amount) > 0).map((row) => {
      const amount = row.amount.replace(",", ".");
      return {
        payment_method: Number(row.method),
        amount,
        ...(paymentMethods.find((method) => method.id === Number(row.method))?.code === "cash" ? { received_amount: (row.received_amount || amount).replace(",", ".") } : {}),
      };
    });
    const tendered = payments.reduce((sum, row) => sum + Number(row.amount), 0);
    const remaining = Number(latestSummary.remaining_total);
    if (Math.abs(tendered - remaining) > 0.01) {
      setError(`Informe apenas o saldo restante (${formatBRL(latestSummary.remaining_total)}). Valor informado: ${formatBRL(String(tendered))}.`);
      setSaving(false);
      return;
    }
    try {
      const discountAuthorization = !canDiscount && Number(discount.replace(",", ".")) > 0
        ? { user: Number(discountAuthorizer), method: "password", credential: discountPassword }
        : undefined;
      const feeAuthorization = serviceFeeWaived && !canWaiveServiceFee
        ? { user: Number(serviceFeeAuthorizer), method: "password", credential: serviceFeePassword }
        : undefined;
      await http.post(`commands/${command.id}/finalize/`, {
        idempotency_key: crypto.randomUUID(), cash_session: Number(cashSession), payments,
        seller_user: Number(seller), discount: discount.replace(",", "."),
        service_fee_waived: serviceFeeWaived,
        ...(discountAuthorization ? { discount_authorization: discountAuthorization } : {}),
        ...(feeAuthorization ? { service_fee_authorization: feeAuthorization } : {}),
      });
      setFinalizeOpen(false);
      await load();
      setSuccess("Comanda fechada com venda criada.");
    } catch (caught) { setError(caught instanceof ApiError ? caught.message : "Não foi possível fechar a comanda."); }
    finally { setSaving(false); }
  }

  const confirmedItems = items.filter((item) => item.status === "confirmed");
  const pendingItems = items.filter((item) => item.status === "pending");
  const cancelledItems = items.filter((item) => item.status === "cancelled");
  const confirmedTotal = confirmedItems.reduce((sum, item) => sum + Number(item.unit_price) * Number(item.quantity), 0);

  if (loading) return <div className="p-6"><Spinner /></div>;
  if (error && !command) return <div className="p-6"><Alert message={error} /><Link href="/comandas" className="btn btn-secondary mt-4"><ArrowLeft className="size-4" />Voltar</Link></div>;
  if (!command) return null;

  return (
    <>
        <PageHeader title={`Comanda ${command.identifier || command.command_number}`} description={command.identifier ? `${command.command_number} · ${command.status === "open" ? "Aberta" : "Fechada"}` : command.status === "open" ? "Aberta" : "Fechada"} action={<Link href="/comandas" className="btn btn-secondary"><ArrowLeft className="size-4" />Voltar</Link>} />
      <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        {error && <Alert message={error} />}
        {success && <Alert message={success} type="success" />}
          <section className="card p-5"><div className="grid gap-4 sm:grid-cols-3"><div><strong className="block text-sm">Mesa</strong><span>{command.table_name || "Sem mesa"}</span></div><div><strong className="block text-sm">Itens confirmados</strong><span>{confirmedItems.length}</span></div><div><strong className="block text-sm">Subtotal dos itens</strong><span className="text-lg font-bold">{formatBRL(String(confirmedTotal))}</span></div></div>{command.status === "open" && canSetCustomer ? <div className="mt-4 max-w-md border-t border-subtle pt-4"><strong className="mb-2 block text-sm">Cliente</strong><CustomerQuickPicker value={customer} onChange={(next) => void changeCustomer(next)} disabled={customerSaving} /></div> : customer ? <div className="mt-4 border-t border-subtle pt-4 text-sm"><strong>Cliente: </strong>{customer.name}{customer.phone ? ` · ${customer.phone}` : ""}</div> : null}</section>

        {command.status === "open" && canRecordPayments && !canViewPayments && <section className="card p-4"><Button onClick={() => void openPayment()}><WalletCards className="size-4" />Registrar pagamento</Button></section>}
        {canViewPayments && <section className="card overflow-hidden"><div className="card-header flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-sm font-bold">Pagamentos</h2><p className="mt-1 text-sm text-muted">Valores apurados pelo servidor.</p></div>{command.status === "open" && canRecordPayments && <Button onClick={() => void openPayment()}><WalletCards className="size-4" />Registrar pagamento</Button>}</div><div className="grid gap-px bg-subtle sm:grid-cols-3"><div className="bg-card p-4"><span className="block text-xs font-medium text-muted">TOTAL</span><strong className="mt-1 block text-lg">{formatBRL(paymentSummary?.command_total || "0")}</strong></div><div className="bg-card p-4"><span className="block text-xs font-medium text-muted">PAGO</span><strong className="mt-1 block text-lg text-success">{formatBRL(paymentSummary?.paid_total || "0")}</strong></div><div className="bg-card p-4"><span className="block text-xs font-medium text-muted">SALDO</span><strong className="mt-1 block text-lg">{formatBRL(paymentSummary?.remaining_total || "0")}</strong></div></div><div className="divide-y divide-subtle">{commandPayments.map((payment) => { const reversed = payment.status === "reversed"; const hasReversal = commandPayments.some((item) => item.reversal_of === payment.id); return <div key={payment.id} className="flex flex-wrap items-center justify-between gap-3 p-4 text-sm"><div><div className="flex flex-wrap items-center gap-2"><strong>{reversed ? "Estorno" : payment.payment_method_name}</strong><span className={reversed ? "text-danger" : "text-muted"}>{reversed ? "Estornado" : "Aplicado"}</span></div><p className="mt-1 text-xs text-muted">{formatDate(payment.created_at)}{payment.received_amount ? ` · Recebido: ${formatBRL(payment.received_amount)}` : ""}{payment.change_amount ? ` · Troco: ${formatBRL(payment.change_amount)}` : ""}{payment.reversal_reason ? ` · Motivo: ${payment.reversal_reason}` : ""}</p></div><div className="flex items-center gap-3"><strong className={reversed ? "text-danger" : ""}>{reversed ? "- " : ""}{formatBRL(payment.amount)}</strong>{!reversed && !hasReversal && command.status === "open" && canReversePayments && <Button variant="secondary" onClick={() => { setReversePayment(payment); setReverseReason(""); }}><RotateCcw className="size-4" />Estornar</Button>}</div></div>; })}{!commandPayments.length && <div className="p-4 text-center text-sm text-muted">Nenhum pagamento registrado.</div>}</div></section>}

        {command.status === "open" && (
          <section className="card p-4 sm:p-5">
            <h2 className="text-sm font-bold">Operações da comanda</h2>
            <p className="mt-1 text-sm text-muted">As alterações são aplicadas somente em comandas abertas.</p>
            <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
              {canTransfer && <Button variant="secondary" onClick={() => void openOperation("transfer")}><ArrowRightLeft className="size-4" />Transferir mesa</Button>}
              {canTransferItems && <Button variant="secondary" disabled={hasAppliedPayments} title={hasAppliedPayments ? "Estorne os pagamentos antes de transferir itens." : undefined} onClick={() => void openOperation("items")}><ArrowRightLeft className="size-4" />Transferir itens</Button>}
              {canMerge && <Button variant="secondary" disabled={hasAppliedPayments} title={hasAppliedPayments ? "Estorne os pagamentos antes de mesclar comandas." : undefined} onClick={() => void openOperation("merge")}><Combine className="size-4" />Mesclar comanda</Button>}
              {canSplit && <Button variant="secondary" disabled={hasAppliedPayments} title={hasAppliedPayments ? "Estorne os pagamentos antes de dividir a comanda." : undefined} onClick={() => void openOperation("split")}><Scissors className="size-4" />Dividir comanda</Button>}
            </div>
          </section>
        )}

        {command.status === "open" && (
          <section className="card overflow-hidden">
            <div className="card-header flex items-center justify-between"><h2 className="text-sm font-bold">Itens</h2>{canAddItems && <Button variant="secondary" onClick={() => void openAdd()}><Plus className="size-4" />Adicionar item</Button>}</div>
            <div className="divide-y divide-subtle">
              {pendingItems.map((item) => (
                <div key={item.id} className="flex items-center justify-between p-4"><div><strong className="block">{item.product_name}</strong><small className="text-muted">{formatQuantity(item.quantity)} {item.unit.toUpperCase()} · {formatBRL(item.unit_price)}</small></div>
                  <div className="flex gap-2">{canAddItems && <Button variant="secondary" onClick={() => void confirmItem(item)}><CheckCircle2 className="size-4" />Confirmar</Button>}{canCancelItems && <button className="icon-button" title="Cancelar" onClick={() => { setCancelItem(item); setCancelReason(""); }}><Ban className="size-4" /></button>}</div>
                </div>
              ))}
              {confirmedItems.map((item) => (
                  <div key={item.id} className="flex items-center justify-between p-4 opacity-80"><div><strong className="block">{item.product_name}</strong><small className="text-muted">{formatQuantity(item.quantity)} {item.unit.toUpperCase()} · {formatBRL(item.unit_price)} · Confirmado</small>{item.modifier_snapshot?.length ? <small className="mt-1 block text-muted">{item.modifier_snapshot.map((modifier) => `${modifier.option_name}${modifier.selected_quantity !== "1" ? ` × ${modifier.selected_quantity}` : ""}`).join(" · ")}</small> : null}</div>{canCancelItems && <button className="icon-button" title="Cancelar" onClick={() => { setCancelItem(item); setCancelReason(""); }}><Ban className="size-4" /></button>}</div>
              ))}
              {cancelledItems.map((item) => (
                <div key={item.id} className="flex items-center justify-between p-4 opacity-50"><div><strong className="block line-through">{item.product_name}</strong><small className="text-muted">{formatQuantity(item.quantity)} {item.unit.toUpperCase()} · Cancelado</small></div></div>
              ))}
              {!items.length && <div className="p-4 text-center text-muted text-sm">Nenhum item adicionado.</div>}
            </div>
            {canFinalize && command.status === "open" && confirmedItems.length > 0 && (
              <div className="border-t border-subtle p-4"><Button onClick={() => void openFinalize()}><ShoppingCart className="size-4" />Fechar comanda</Button></div>
            )}
          </section>
        )}

        {command.sale && command.status === "closed" && (
          <section className="card p-5"><strong className="block text-sm">Venda gerada</strong><Link href={`/vendas/${command.sale}`} className="text-primary hover:underline">Ver venda #{command.sale}</Link></section>
        )}
      </div>

      <Modal open={addOpen} title="Adicionar item" onClose={() => setAddOpen(false)}>
        <div className="space-y-4 p-5">
          <Field label="Produto" error={fieldError(fields, "product")}><Select value={productId} onChange={(e) => setProductId(e.target.value)} disabled={saving}><option value="">Selecione</option>{products.map((prod) => <option key={prod.id} value={prod.id}>{prod.name}</option>)}</Select></Field>
          <Field label="Quantidade" error={fieldError(fields, "quantity")}><Input value={quantity} onChange={(e) => setQuantity(e.target.value)} disabled={saving} inputMode="decimal" /></Field>
          {error && <Alert message={error} />}
          <div className="flex justify-end gap-2 border-t border-subtle pt-4"><Button variant="secondary" onClick={() => setAddOpen(false)}>Cancelar</Button><Button loading={saving} onClick={requestAddItem}>Adicionar</Button></div>
        </div>
      </Modal>
      {modifierProduct && <ModifierPicker product={modifierProduct} onClose={() => { setModifierProduct(null); setAddOpen(true); }} onConfirm={(selections) => { setModifierProduct(null); void addItem(selections); }} />}

      <Modal open={!!cancelItem} title="Cancelar item" onClose={() => setCancelItem(null)}>
        <div className="space-y-4 p-5">
          <p className="text-sm text-muted">{cancelItem ? `${cancelItem.product_name} × ${cancelItem.quantity}` : ""}</p>
          <Field label="Motivo do cancelamento" error={fieldError(fields, "reason")}><Input value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} disabled={saving} /></Field>
          {error && <Alert message={error} />}
          <div className="flex justify-end gap-2 border-t border-subtle pt-4"><Button variant="secondary" onClick={() => setCancelItem(null)}>Voltar</Button><Button loading={saving} onClick={() => void doCancel()}>Cancelar item</Button></div>
        </div>
      </Modal>

      <Modal open={paymentOpen} title="Registrar pagamento" onClose={() => setPaymentOpen(false)}>
        <div className="space-y-4 p-5">
          <div className="grid gap-3 rounded-md bg-surface p-3 text-sm sm:grid-cols-3"><div><span className="block text-xs text-muted">Total</span><strong>{formatBRL(paymentSummary?.command_total || "0")}</strong></div><div><span className="block text-xs text-muted">Pago</span><strong>{formatBRL(paymentSummary?.paid_total || "0")}</strong></div><div><span className="block text-xs text-muted">Saldo</span><strong>{formatBRL(paymentSummary?.remaining_total || "0")}</strong></div></div>
          <Field label="Forma de pagamento" error={fieldError(fields, "payment_method")}><Select value={paymentMethod} onChange={(event) => setPaymentMethod(event.target.value)} disabled={saving}><option value="">Selecione</option>{paymentMethods.map((method) => <option key={method.id} value={method.id}>{method.name}</option>)}</Select></Field>
          <Field label="Valor aplicado" error={fieldError(fields, "amount")}><Input value={paymentAmount} onChange={(event) => setPaymentAmount(event.target.value)} disabled={saving} inputMode="decimal" placeholder="0,00" /></Field>
          {paymentMethods.find((method) => method.id === Number(paymentMethod))?.code === "cash" && <><Field label="Sessão de Caixa" error={fieldError(fields, "cash_session")}><Select value={paymentCashSession} onChange={(event) => setPaymentCashSession(event.target.value)} disabled={saving}><option value="">Selecione uma sessão aberta</option>{cashSessions.map((session) => <option key={session.id} value={session.id}>{session.register_name} · {session.opened_by_name}</option>)}</Select></Field><Field label="Valor recebido" error={fieldError(fields, "received_amount")}><Input value={paymentReceivedAmount} onChange={(event) => setPaymentReceivedAmount(event.target.value)} disabled={saving} inputMode="decimal" placeholder="0,00" /></Field>{paymentReceivedAmount && Number(paymentReceivedAmount.replace(",", ".")) >= Number(paymentAmount.replace(",", ".")) ? <p className="text-sm text-muted">Troco: <strong>{formatBRL(String(Number(paymentReceivedAmount.replace(",", ".")) - Number(paymentAmount.replace(",", "."))))}</strong></p> : null}</>}
          {error && <Alert message={error} />}<div className="flex justify-end gap-2 border-t border-subtle pt-4"><Button variant="secondary" onClick={() => setPaymentOpen(false)} disabled={saving}>Cancelar</Button><Button loading={saving} onClick={() => void recordPayment()}>Registrar pagamento</Button></div>
        </div>
      </Modal>

      <Modal open={!!reversePayment} title="Estornar pagamento" onClose={() => setReversePayment(null)}>
        <div className="space-y-4 p-5"><p className="text-sm text-muted">{reversePayment ? `${reversePayment.payment_method_name} · ${formatBRL(reversePayment.amount)}` : ""}</p><Field label="Motivo do estorno" error={fieldError(fields, "reason")}><Input value={reverseReason} onChange={(event) => setReverseReason(event.target.value)} disabled={saving} /></Field>{error && <Alert message={error} />}<div className="flex justify-end gap-2 border-t border-subtle pt-4"><Button variant="secondary" onClick={() => setReversePayment(null)} disabled={saving}>Cancelar</Button><Button loading={saving} onClick={() => void doReversePayment()}>Estornar pagamento</Button></div></div>
      </Modal>

      <Modal open={finalizeOpen} title="Fechar comanda" onClose={() => setFinalizeOpen(false)}>
        <div className="space-y-4 p-5">
          <div className="rounded-md bg-surface p-3 text-sm">
            <div className="flex justify-between"><span>Subtotal</span><strong>{formatBRL(preview?.subtotal || "0")}</strong></div>
            {preview && Number(preview.promotion_discount_total) > 0 ? <div className="mt-1 flex justify-between text-success"><span>Promoções</span><span>- {formatBRL(preview.promotion_discount_total)}</span></div> : null}
            {preview && Number(preview.discount) > 0 ? <div className="mt-1 flex justify-between text-success"><span>Desconto</span><span>- {formatBRL(preview.discount)}</span></div> : null}
            {preview && Number(preview.service_fee_amount) > 0 ? <div className="mt-1 flex justify-between"><span>Taxa de serviço ({preview.service_fee_rate}%)</span><span>{formatBRL(preview.service_fee_amount)}</span></div> : null}
            <div className="mt-2 flex justify-between border-t border-subtle pt-2 text-base"><strong>Total final</strong><strong>{previewLoading ? "Calculando..." : formatBRL(preview?.total || "0")}</strong></div>
          </div>
          <div className="grid gap-2 rounded-md border border-subtle p-3 text-sm sm:grid-cols-3"><div><span className="block text-xs text-muted">Total da comanda</span><strong>{formatBRL(paymentSummary?.command_total || "0")}</strong></div><div><span className="block text-xs text-muted">Já pago</span><strong>{formatBRL(paymentSummary?.paid_total || "0")}</strong></div><div><span className="block text-xs text-muted">Saldo a receber</span><strong>{formatBRL(paymentSummary?.remaining_total || "0")}</strong></div></div>
          {preview?.items.length ? <div className="max-h-32 space-y-1 overflow-y-auto text-xs text-muted">{preview.items.map((item, index) => <div key={`${item.product}-${item.product_name}-${index}`}><span>{item.product_name} · {item.quantity} · {formatBRL(item.subtotal)}</span>{item.modifier_snapshot?.length ? <span> · {item.modifier_snapshot.map((modifier) => modifier.option_name).join(", ")}</span> : null}</div>)}</div> : null}
          <Field label="Atendente"><Select value={seller} onChange={(event) => { setSeller(event.target.value); void requestPreview({ seller: event.target.value }); }} disabled={saving}><option value="">Selecione</option>{sellers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>
          <Field label="Desconto na conta"><Input value={discount} onChange={(event) => setDiscount(event.target.value)} onBlur={() => void requestPreview()} disabled={saving} inputMode="decimal" /></Field>
          {Number(discount.replace(",", ".")) > 0 && !canDiscount ? <div className="grid gap-3 sm:grid-cols-2"><Field label="Autorizador"><Select value={discountAuthorizer} onChange={(event) => setDiscountAuthorizer(event.target.value)} disabled={saving}><option value="">Selecione</option>{authorizers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field><Field label="Senha do autorizador"><Input type="password" value={discountPassword} onChange={(event) => setDiscountPassword(event.target.value)} disabled={saving} /></Field></div> : null}
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={serviceFeeWaived} onChange={(event) => { setServiceFeeWaived(event.target.checked); void requestPreview({ serviceFeeWaived: event.target.checked }); }} disabled={saving} />Retirar taxa de serviço</label>
          {serviceFeeWaived && !canWaiveServiceFee ? <div className="grid gap-3 sm:grid-cols-2"><Field label="Autorizador"><Select value={serviceFeeAuthorizer} onChange={(event) => setServiceFeeAuthorizer(event.target.value)} disabled={saving}><option value="">Selecione</option>{serviceFeeAuthorizers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field><Field label="Senha do autorizador"><Input type="password" value={serviceFeePassword} onChange={(event) => setServiceFeePassword(event.target.value)} disabled={saving} /></Field></div> : null}
          <Field label="Sessão de Caixa"><Select value={cashSession} onChange={(e) => setCashSession(e.target.value)} disabled={saving}><option value="">Selecione uma sessão aberta</option>{cashSessions.map((session) => <option key={session.id} value={session.id}>{session.register_name} · {session.opened_by_name}</option>)}</Select></Field>
          <p className="text-xs text-muted">Informe somente o saldo a receber. Se o saldo estiver zerado, deixe os pagamentos vazios.</p>
          {paymentRows.map((row, index) => (
            <div key={index} className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_0.7fr_0.7fr_auto]">
              <Select value={row.method} onChange={(e) => setPaymentRows((rows) => rows.map((r, i) => i === index ? { ...r, method: e.target.value } : r))} disabled={saving}><option value="">Forma</option>{paymentMethods.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</Select>
              <Input placeholder="Valor" value={row.amount} onChange={(e) => setPaymentRows((rows) => rows.map((r, i) => i === index ? { ...r, amount: e.target.value } : r))} disabled={saving} inputMode="decimal" />
              {paymentMethods.find((method) => method.id === Number(row.method))?.code === "cash" ? <Input placeholder="Recebido" value={row.received_amount} onChange={(e) => setPaymentRows((rows) => rows.map((r, i) => i === index ? { ...r, received_amount: e.target.value } : r))} disabled={saving} inputMode="decimal" /> : <span />}
              {paymentRows.length > 1 && <button className="icon-button" onClick={() => setPaymentRows((rows) => rows.filter((_, i) => i !== index))} disabled={saving}><XCircle className="size-4" /></button>}
            </div>
          ))}
          <Button variant="secondary" onClick={() => setPaymentRows((rows) => [...rows, { method: "", amount: "", received_amount: "" }])} disabled={saving}><Plus className="size-4" />Adicionar pagamento</Button>
          {error && <Alert message={error} />}
          <div className="flex justify-end gap-2 border-t border-subtle pt-4"><Button variant="secondary" onClick={() => setFinalizeOpen(false)}>Cancelar</Button><Button loading={saving} onClick={() => void finalize()}>Fechar comanda</Button></div>
        </div>
      </Modal>

      <Modal open={!!operation} title={operation === "transfer" ? "Transferir mesa" : operation === "items" ? "Transferir itens" : operation === "merge" ? "Mesclar comanda" : "Dividir comanda"} description={operation === "transfer" ? "Altere a mesa vinculada a esta comanda." : operation === "items" ? "Informe a comanda de destino e as quantidades a transferir." : operation === "merge" ? "Todos os pedidos da comanda escolhida serão incorporados a esta comanda." : "Uma nova comanda será criada com os itens e quantidades informados."} onClose={() => setOperation(null)} size="lg">
        <div className="space-y-4 p-5 sm:p-6">
          {operation === "transfer" && <Field label="Mesa de destino"><Select value={destinationTable} onChange={(event) => setDestinationTable(event.target.value)} disabled={saving}><option value="">Sem mesa</option>{operationTables.map((table) => <option key={table.id} value={table.id}>{table.name}</option>)}</Select></Field>}
          {(operation === "items" || operation === "merge") && <Field label={operation === "merge" ? "Comanda de origem" : "Comanda de destino"} error={fieldError(fields, "command")}><Select value={destinationCommand} onChange={(event) => setDestinationCommand(event.target.value)} disabled={saving}><option value="">Selecione uma comanda aberta</option>{operationCommands.map((item) => <option key={item.id} value={item.id}>{item.identifier || item.command_number}{item.identifier ? ` · ${item.command_number}` : ""}{item.table_name ? ` · Mesa ${item.table_name}` : ""}</option>)}</Select></Field>}
          {operation === "split" && <><Field label="Identificação da nova comanda" optional><Input value={splitIdentifier} onChange={(event) => setSplitIdentifier(event.target.value)} disabled={saving} placeholder="Ex.: Cliente 2" /></Field>{usesTables && <Field label="Mesa da nova comanda" optional><Select value={destinationTable} onChange={(event) => setDestinationTable(event.target.value)} disabled={saving}><option value="">Sem mesa</option>{operationTables.map((table) => <option key={table.id} value={table.id}>{table.name}</option>)}</Select></Field>}</>}
          {(operation === "items" || operation === "split") && <div><strong className="mb-2 block text-sm">Itens e quantidades</strong><div className="max-h-64 divide-y divide-subtle overflow-y-auto rounded-md border border-subtle">{items.filter((item) => item.status !== "cancelled").map((item) => <div key={item.id} className="grid grid-cols-[1fr_7rem] items-center gap-3 p-3"><div><strong className="block text-sm">{item.product_name}</strong><span className="text-xs text-muted">Disponível: {formatQuantity(item.quantity)} {item.unit.toUpperCase()}{item.status === "confirmed" ? " · Confirmado: somente quantidade total" : ""}</span></div><Input value={itemQuantities[item.id] || ""} onChange={(event) => setItemQuantities((current) => ({ ...current, [item.id]: event.target.value }))} disabled={saving || item.status === "confirmed"} inputMode="decimal" aria-label={`Quantidade de ${item.product_name}`} /></div>)}</div><p className="mt-2 text-xs text-muted">Deixe a quantidade em branco ou zero para não transferir o item.</p></div>}
          {operation === "transfer" && <div className="rounded-md bg-surface p-3 text-sm"><strong>Prévia</strong><p className="mt-1 text-muted">Comanda {command.identifier || command.command_number} será vinculada a {destinationTable ? operationTables.find((table) => table.id === Number(destinationTable))?.name || "a mesa selecionada" : "sem mesa"}.</p></div>}
          {operation === "merge" && <div className="rounded-md bg-surface p-3 text-sm text-muted">A comanda selecionada será fechada após a transferência de todos os pedidos para esta comanda.</div>}
          {error && <Alert message={error} />}
          <div className="flex flex-col-reverse gap-2 border-t border-subtle pt-4 sm:flex-row sm:justify-end"><Button variant="secondary" onClick={() => setOperation(null)} disabled={saving}>Cancelar</Button><Button loading={saving} onClick={() => void executeOperation()}>{operation === "transfer" ? "Transferir mesa" : operation === "items" ? "Transferir itens" : operation === "merge" ? "Mesclar comandas" : "Criar comanda"}</Button></div>
        </div>
      </Modal>
    </>
  );
}

export default function CommandDetailPage() {
  return <AdminGuard requiredPermissions={[permissions.viewCommands]} requiredFeatures={["commands"]}><CommandDetail /></AdminGuard>;
}
