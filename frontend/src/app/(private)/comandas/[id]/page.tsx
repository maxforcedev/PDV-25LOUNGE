"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Ban, CheckCircle2, Plus, ShoppingCart, XCircle } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { ModifierPicker } from "@/components/modifier-picker";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, Field, Input, Modal, Select, Spinner } from "@/components/ui";
import { formatBRL, formatQuantity, fieldError } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { CheckoutOptions, Command, ModifierSelection, OrderItem, Product, SalePreview, SaleUserOption } from "@/types";

function CommandDetail() {
  const id = String(useParams<{ id: string }>().id);
  const { hasPermission, supportSession, user } = useAuth();
  const readOnly = supportSession?.mode === "READ_ONLY";
  const canAddItems = hasPermission(permissions.addCommandItems) && !readOnly;
  const canCancelItems = hasPermission(permissions.cancelCommandItems) && !readOnly;
  const canFinalize = hasPermission(permissions.finalizeCommand) && !readOnly;
  const canDiscount = hasPermission(permissions.applyDiscount);
  const canWaiveServiceFee = hasPermission(permissions.waiveServiceFee);
  const [command, setCommand] = useState<Command | null>(null);
  const [items, setItems] = useState<OrderItem[]>([]);
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
  const context = useRef("");

  async function load() {
    setLoading(true); setError("");
    try {
      const cmd = await http.get<Command>(`commands/${id}/`);
      setCommand(cmd);
      const orderItems = await http.getAll<OrderItem>(`order-items/?order__command=${id}`);
      setItems(orderItems);
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
      const [options, sellerOptions, discountOptions, feeOptions] = await Promise.all([
        http.get<CheckoutOptions>("commands/checkout-options/"),
        http.get<SaleUserOption[]>("commands/sellers/"),
        http.get<SaleUserOption[]>("commands/discount-authorizers/"),
        http.get<SaleUserOption[]>("commands/service-fee-authorizers/"),
      ]);
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
    const latestPreview = await requestPreview();
    if (!latestPreview) { setSaving(false); return; }
    const total = Number(latestPreview.total);
    const payments = paymentRows.filter((row) => row.method && Number(row.amount) > 0).map((row) => {
      const amount = row.amount.replace(",", ".");
      return {
        payment_method: Number(row.method),
        amount,
        ...(paymentMethods.find((method) => method.id === Number(row.method))?.code === "cash" ? { received_amount: (row.received_amount || amount).replace(",", ".") } : {}),
      };
    });
    const paid = payments.reduce((sum, row) => sum + Number(row.amount), 0);
    if (Math.abs(paid - total) > 0.01) {
      setError(`O pagamento deve quitar 100% do total (${formatBRL(String(total))}). Pago: ${formatBRL(String(paid))}.`);
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
          <section className="card p-5"><div className="grid gap-4 sm:grid-cols-3"><div><strong className="block text-sm">Mesa</strong><span>{command.table_name || "Sem mesa"}</span></div><div><strong className="block text-sm">Itens confirmados</strong><span>{confirmedItems.length}</span></div><div><strong className="block text-sm">Subtotal dos itens</strong><span className="text-lg font-bold">{formatBRL(String(confirmedTotal))}</span></div></div></section>

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

      <Modal open={finalizeOpen} title="Fechar comanda" onClose={() => setFinalizeOpen(false)}>
        <div className="space-y-4 p-5">
          <div className="rounded-md bg-surface p-3 text-sm">
            <div className="flex justify-between"><span>Subtotal</span><strong>{formatBRL(preview?.subtotal || "0")}</strong></div>
            {preview && Number(preview.promotion_discount_total) > 0 ? <div className="mt-1 flex justify-between text-success"><span>Promoções</span><span>- {formatBRL(preview.promotion_discount_total)}</span></div> : null}
            {preview && Number(preview.discount) > 0 ? <div className="mt-1 flex justify-between text-success"><span>Desconto</span><span>- {formatBRL(preview.discount)}</span></div> : null}
            {preview && Number(preview.service_fee_amount) > 0 ? <div className="mt-1 flex justify-between"><span>Taxa de serviço ({preview.service_fee_rate}%)</span><span>{formatBRL(preview.service_fee_amount)}</span></div> : null}
            <div className="mt-2 flex justify-between border-t border-subtle pt-2 text-base"><strong>Total final</strong><strong>{previewLoading ? "Calculando..." : formatBRL(preview?.total || "0")}</strong></div>
          </div>
          {preview?.items.length ? <div className="max-h-32 space-y-1 overflow-y-auto text-xs text-muted">{preview.items.map((item, index) => <div key={`${item.product}-${item.product_name}-${index}`}><span>{item.product_name} · {item.quantity} · {formatBRL(item.subtotal)}</span>{item.modifier_snapshot?.length ? <span> · {item.modifier_snapshot.map((modifier) => modifier.option_name).join(", ")}</span> : null}</div>)}</div> : null}
          <Field label="Atendente"><Select value={seller} onChange={(event) => { setSeller(event.target.value); void requestPreview({ seller: event.target.value }); }} disabled={saving}><option value="">Selecione</option>{sellers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field>
          <Field label="Desconto na conta"><Input value={discount} onChange={(event) => setDiscount(event.target.value)} onBlur={() => void requestPreview()} disabled={saving} inputMode="decimal" /></Field>
          {Number(discount.replace(",", ".")) > 0 && !canDiscount ? <div className="grid gap-3 sm:grid-cols-2"><Field label="Autorizador"><Select value={discountAuthorizer} onChange={(event) => setDiscountAuthorizer(event.target.value)} disabled={saving}><option value="">Selecione</option>{authorizers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field><Field label="Senha do autorizador"><Input type="password" value={discountPassword} onChange={(event) => setDiscountPassword(event.target.value)} disabled={saving} /></Field></div> : null}
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={serviceFeeWaived} onChange={(event) => { setServiceFeeWaived(event.target.checked); void requestPreview({ serviceFeeWaived: event.target.checked }); }} disabled={saving} />Retirar taxa de serviço</label>
          {serviceFeeWaived && !canWaiveServiceFee ? <div className="grid gap-3 sm:grid-cols-2"><Field label="Autorizador"><Select value={serviceFeeAuthorizer} onChange={(event) => setServiceFeeAuthorizer(event.target.value)} disabled={saving}><option value="">Selecione</option>{serviceFeeAuthorizers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></Field><Field label="Senha do autorizador"><Input type="password" value={serviceFeePassword} onChange={(event) => setServiceFeePassword(event.target.value)} disabled={saving} /></Field></div> : null}
          <Field label="Sessão de Caixa"><Select value={cashSession} onChange={(e) => setCashSession(e.target.value)} disabled={saving}><option value="">Selecione uma sessão aberta</option>{cashSessions.map((session) => <option key={session.id} value={session.id}>{session.register_name} · {session.opened_by_name}</option>)}</Select></Field>
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
    </>
  );
}

export default function CommandDetailPage() {
  return <AdminGuard requiredPermissions={[permissions.viewCommands]}><CommandDetail /></AdminGuard>;
}
