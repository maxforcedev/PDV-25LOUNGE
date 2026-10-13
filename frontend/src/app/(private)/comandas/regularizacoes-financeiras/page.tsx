"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Eye, ShieldCheck } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, Field, Input, Modal, MoneyInput, Select, Spinner, Textarea } from "@/components/ui";
import { formatDate, formatDecimalBRL, formatPercent } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type {
  CommandFinancialRegularizationDetail,
  FinancialRegularizationItem,
  ItemFinancialRegularizationPreview,
  ItemFinancialRegularizationResult,
  LegacyServiceFeeRegularizationCommand,
} from "@/types";

type ItemForm = {
  promotionMode: "" | "none" | "promotion";
  promotionId: string;
  promotionName: string;
  promotionDiscountType: "" | "percentage" | "fixed_amount";
  promotionDiscountValue: string;
  promotionBenefit: string;
  manualDiscountType: "" | "amount" | "percentage";
  manualDiscountValue: string;
  manualDiscount: string;
  netSubtotal: string;
  participatesInServiceFee: "" | "true" | "false";
  participatesInCommission: "" | "true" | "false";
};

function valueOf(value: unknown) {
  return typeof value === "string" || typeof value === "number" ? String(value) : "";
}

function initialItemForm(item: FinancialRegularizationItem): ItemForm {
  const snapshot = item.financial_snapshot;
  const promotion = snapshot?.promotion;
  return {
    promotionMode: promotion === null ? "none" : typeof promotion === "number" ? "promotion" : "",
    promotionId: typeof promotion === "number" ? String(promotion) : "",
    promotionName: valueOf(snapshot?.promotion_name),
    promotionDiscountType: snapshot?.promotion_discount_type || "",
    promotionDiscountValue: valueOf(snapshot?.promotion_discount_value),
    promotionBenefit: valueOf(snapshot?.promotion_benefit),
    manualDiscountType: snapshot?.manual_discount_intent?.type || "",
    manualDiscountValue: valueOf(snapshot?.manual_discount_intent?.value),
    manualDiscount: valueOf(snapshot?.manual_discount),
    netSubtotal: valueOf(snapshot?.net_subtotal),
    participatesInServiceFee: typeof snapshot?.participates_in_service_fee === "boolean" ? String(snapshot.participates_in_service_fee) as "true" | "false" : "",
    participatesInCommission: typeof snapshot?.participates_in_commission === "boolean" ? String(snapshot.participates_in_commission) as "true" | "false" : "",
  };
}

function pendingType(command: LegacyServiceFeeRegularizationCommand) {
  const itemPending = command.financial_status.item_ids.length > 0;
  const feePending = command.service_fee_rate_snapshot === null;
  if (itemPending && feePending) return "Múltiplas pendências";
  if (itemPending) return "Condições financeiras dos itens";
  if (feePending) return "Taxa de serviço histórica";
  return "Regularização financeira";
}

function FinancialRegularizationsPage() {
  const { currentBranch, hasPermission, supportSession } = useAuth();
  const readOnly = supportSession?.mode === "READ_ONLY";
  const canRegularizeItems = hasPermission(permissions.regularizeCommandItemFinancials) && !readOnly;
  const canRegularizeFee = hasPermission(permissions.regularizeCommandServiceFee) && !readOnly;
  const [commands, setCommands] = useState<LegacyServiceFeeRegularizationCommand[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [selected, setSelected] = useState<LegacyServiceFeeRegularizationCommand | null>(null);
  const [detail, setDetail] = useState<CommandFinancialRegularizationDetail | null>(null);
  const [itemForms, setItemForms] = useState<Record<number, ItemForm>>({});
  const [preview, setPreview] = useState<ItemFinancialRegularizationPreview | null>(null);
  const [rate, setRate] = useState("");
  const [justification, setJustification] = useState("");
  const [evidenceReference, setEvidenceReference] = useState("");
  const [itemConfirmed, setItemConfirmed] = useState(false);
  const [feeConfirmed, setFeeConfirmed] = useState(false);
  const [itemIdempotencyKey, setItemIdempotencyKey] = useState("");
  const [feeIdempotencyKey, setFeeIdempotencyKey] = useState("");
  const context = useRef("");
  context.current = String(currentBranch?.id || "");

  async function load(token: string) {
    if (!currentBranch) { setCommands([]); setLoading(false); return; }
    setLoading(true); setError("");
    try {
      const result = await http.get<LegacyServiceFeeRegularizationCommand[]>("attendance-commands/legacy-service-fee-regularizations/");
      if (context.current === token) setCommands(result);
    } catch (caught) {
      if (context.current === token) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as regularizações pendentes.");
    } finally {
      if (context.current === token) setLoading(false);
    }
  }

  const loadRef = useRef(load);
  loadRef.current = load;
  useEffect(() => { setCommands([]); void loadRef.current(String(currentBranch?.id || "")); }, [currentBranch?.id]);

  async function loadDetail(command: LegacyServiceFeeRegularizationCommand) {
    setLoadingDetail(true); setError("");
    try {
      const result = await http.get<CommandFinancialRegularizationDetail>(`attendance-commands/${command.id}/financial-regularization/`);
      setDetail(result);
      setItemForms(Object.fromEntries(result.items.map((item) => [item.id, initialItemForm(item)])));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar os detalhes da comanda.");
    } finally { setLoadingDetail(false); }
  }

  function openRegularization(command: LegacyServiceFeeRegularizationCommand) {
    setSelected(command); setDetail(null); setRate(""); setJustification(""); setEvidenceReference("");
    setPreview(null); setFields({}); setError(""); setItemConfirmed(false); setFeeConfirmed(false);
    setItemIdempotencyKey(crypto.randomUUID()); setFeeIdempotencyKey(crypto.randomUUID());
    void loadDetail(command);
  }

  function updateItemForm(itemId: number, patch: Partial<ItemForm>) {
    setItemForms((current) => ({ ...current, [itemId]: { ...current[itemId], ...patch } }));
    setPreview(null);
  }

  function itemPayload() {
    if (!detail) return null;
    const items = [];
    for (const item of detail.items) {
      const form = itemForms[item.id];
      if (!form || !form.promotionMode || !form.manualDiscountType || !form.promotionBenefit || !form.manualDiscountValue || !form.manualDiscount || !form.netSubtotal || !form.participatesInServiceFee || !form.participatesInCommission) {
        setError("Preencha todas as condições históricas comprovadas para cada item antes de continuar.");
        return null;
      }
      if (form.promotionMode === "promotion" && (!form.promotionId || !form.promotionName || !form.promotionDiscountType || !form.promotionDiscountValue)) {
        setError("Informe todos os dados da promoção histórica comprovada.");
        return null;
      }
      items.push({
        item: item.id,
        financial_snapshot: {
          promotion: form.promotionMode === "promotion" ? Number(form.promotionId) : null,
          promotion_name: form.promotionMode === "promotion" ? form.promotionName.trim() : null,
          promotion_discount_type: form.promotionMode === "promotion" ? form.promotionDiscountType : null,
          promotion_discount_value: form.promotionMode === "promotion" ? form.promotionDiscountValue.replace(",", ".") : null,
          promotion_benefit: form.promotionBenefit.replace(",", "."),
          manual_discount_intent: { type: form.manualDiscountType, value: form.manualDiscountValue.replace(",", ".") },
          manual_discount: form.manualDiscount.replace(",", "."),
          net_subtotal: form.netSubtotal.replace(",", "."),
          participates_in_service_fee: form.participatesInServiceFee === "true",
          participates_in_commission: form.participatesInCommission === "true",
        },
      });
    }
    return items;
  }

  async function requestPreview() {
    if (!selected) return;
    const items = itemPayload();
    if (!items) return;
    setSaving(true); setError(""); setFields({});
    try {
      const result = await http.post<ItemFinancialRegularizationPreview>(`attendance-commands/${selected.id}/item-financial-regularization/`, {
        items, justification: justification.trim(), evidence_reference: evidenceReference.trim(), preview: true,
      });
      setPreview(result);
    } catch (caught) {
      if (caught instanceof ApiError) { setError(caught.message); setFields(caught.fields || {}); }
      else setError("Não foi possível gerar a prévia financeira.");
    } finally { setSaving(false); }
  }

  async function regularizeItems() {
    if (!selected || !itemConfirmed) return;
    const items = itemPayload();
    if (!items) return;
    if (!preview) { setError("Gere a prévia antes de confirmar a regularização."); return; }
    setSaving(true); setError(""); setFields({});
    try {
      const result = await http.post<ItemFinancialRegularizationResult>(`attendance-commands/${selected.id}/item-financial-regularization/`, {
        items, justification: justification.trim(), evidence_reference: evidenceReference.trim(), idempotency_key: itemIdempotencyKey,
      });
      setSuccess(result.preview_available ? "Condições históricas dos itens regularizadas." : "Itens regularizados. A taxa de serviço histórica ainda precisa ser recuperada.");
      setPreview(null); setItemConfirmed(false);
      await Promise.all([loadDetail(selected), load(String(currentBranch?.id || ""))]);
    } catch (caught) {
      if (caught instanceof ApiError) { setError(caught.message); setFields(caught.fields || {}); }
      else setError("Não foi possível concluir a regularização dos itens.");
    } finally { setSaving(false); }
  }

  async function regularizeFee() {
    if (!selected || !feeConfirmed) return;
    setSaving(true); setError(""); setFields({});
    try {
      await http.post(`attendance-commands/${selected.id}/service-fee-regularization/`, {
        service_fee_rate: rate.replace(",", "."), justification: justification.trim(),
        evidence_reference: evidenceReference.trim(), idempotency_key: feeIdempotencyKey,
      });
      setSuccess("Taxa histórica regularizada."); setFeeConfirmed(false);
      await Promise.all([loadDetail(selected), load(String(currentBranch?.id || ""))]);
    } catch (caught) {
      if (caught instanceof ApiError) { setError(caught.message); setFields(caught.fields || {}); }
      else setError("Não foi possível concluir a regularização da taxa.");
    } finally { setSaving(false); }
  }

  if (!currentBranch) return <div className="p-6"><Alert message="Selecione uma filial." /></div>;

  const itemPending = !!detail?.items.length;
  const feePending = detail?.service_fee_rate_regularization_required === true;
  return (
    <>
      <PageHeader title="Regularizações financeiras" description="Recupere informações históricas comprovadas sem alterar pagamentos já realizados." action={<Link href="/comandas" className="btn btn-secondary"><ArrowLeft className="size-4" />Voltar</Link>} />
      <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        <section className="card border-danger/30 p-4 text-sm"><strong className="block">Ação excepcional e auditada</strong><p className="mt-1 text-muted">Use somente evidências históricas. A regularização não modifica pagamentos, estornos, estoque, CMV ou vendedor.</p></section>
        {error && <Alert message={error} />}
        {success && <Alert message={success} type="success" />}
        {loading ? <Spinner /> : commands.length ? <section className="card overflow-hidden"><div className="table-wrap"><table className="data-table"><thead><tr><th>Comanda</th><th>Aberta em</th><th>Filial</th><th>Pagamentos</th><th>Pendência</th><th>Estado</th><th>Ação</th></tr></thead><tbody>{commands.map((command) => <tr key={command.id}><td><strong>{command.identifier || command.number}</strong>{command.identifier ? <small className="ml-2 text-muted">{command.number}</small> : null}</td><td>{formatDate(command.created_at)}</td><td>{command.branch_name || "-"}</td><td>{command.payment_count}</td><td>{pendingType(command)}</td><td>{command.financial_status.state === "REGULARIZATION_REQUIRED" ? "Pendente" : command.financial_status.state}</td><td><Button variant="secondary" onClick={() => openRegularization(command)}><Eye className="size-4" />Consultar</Button></td></tr>)}</tbody></table></div></section> : <section className="card p-5 text-sm text-muted">Não há comandas com pendências financeiras nesta filial.</section>}
      </div>
      <Modal open={!!selected} title="Regularização financeira histórica" description={selected ? `Comanda ${selected.identifier || selected.number}. Pagamentos anteriores não serão modificados.` : undefined} onClose={() => !saving && setSelected(null)}>
        <div className="space-y-5 p-5">
          {loadingDetail ? <Spinner /> : detail ? <>
            <section className="rounded-md border border-subtle p-3 text-sm"><strong>{detail.command.identifier || detail.command.number}</strong><div className="mt-2 grid gap-1 text-muted sm:grid-cols-2"><span>Status: {detail.command.status}</span><span>Aberta em: {formatDate(detail.command.created_at)}</span><span>Filial: {detail.command.branch_name || "-"}</span><span>Integridade: {itemPending || feePending ? "regularização necessária" : "regularizada"}</span></div>{detail.financial_status.message && <p className="mt-2 text-muted">{detail.financial_status.message}</p>}</section>
            {itemPending && <section className="space-y-4"><div><h3 className="font-semibold">Condições financeiras dos itens</h3><p className="text-sm text-muted">Preencha apenas dados comprovados. Campos não comprovados não devem ser estimados.</p></div>{detail.items.map((item) => { const form = itemForms[item.id]; if (!form) return null; return <div key={item.id} className="rounded-md border border-subtle p-4"><div className="mb-3 text-sm"><strong>{item.product_name}</strong><div className="mt-1 text-muted">Qtd. {item.quantity} · Unitário {formatDecimalBRL(item.unit_price)} · Bruto {formatDecimalBRL(item.gross_subtotal)} · Confirmado {formatDate(item.confirmed_at || item.created_at)}</div><div className="mt-1 text-danger">{item.issue === "missing" ? "Snapshot ausente" : "Snapshot inconsistente"}{item.missing_financial_fields.length ? `: ${item.missing_financial_fields.join(", ")}` : ""}</div></div><div className="grid gap-3 sm:grid-cols-2">
              <Field label="Promoção histórica"><Select value={form.promotionMode} onChange={(event) => updateItemForm(item.id, { promotionMode: event.target.value as ItemForm["promotionMode"] })} disabled={saving}><option value="">Selecione conforme a evidência</option><option value="none">Não houve promoção comprovada</option><option value="promotion">Houve promoção comprovada</option></Select></Field>
              <Field label="Benefício promocional"><MoneyInput value={form.promotionBenefit} onValueChange={(value) => updateItemForm(item.id, { promotionBenefit: value })} disabled={saving} placeholder="0,00" /></Field>
              {form.promotionMode === "promotion" && <><Field label="ID da promoção"><Input value={form.promotionId} onChange={(event) => updateItemForm(item.id, { promotionId: event.target.value })} disabled={saving} inputMode="numeric" /></Field><Field label="Nome da promoção"><Input value={form.promotionName} onChange={(event) => updateItemForm(item.id, { promotionName: event.target.value })} disabled={saving} /></Field><Field label="Tipo do desconto promocional"><Select value={form.promotionDiscountType} onChange={(event) => updateItemForm(item.id, { promotionDiscountType: event.target.value as ItemForm["promotionDiscountType"] })} disabled={saving}><option value="">Selecione</option><option value="percentage">Percentual</option><option value="fixed_amount">Valor fixo</option></Select></Field><Field label="Valor da promoção"><MoneyInput value={form.promotionDiscountValue} onValueChange={(value) => updateItemForm(item.id, { promotionDiscountValue: value })} disabled={saving} /></Field></>}
              <Field label="Tipo do desconto manual"><Select value={form.manualDiscountType} onChange={(event) => updateItemForm(item.id, { manualDiscountType: event.target.value as ItemForm["manualDiscountType"] })} disabled={saving}><option value="">Selecione conforme a evidência</option><option value="amount">Valor</option><option value="percentage">Percentual</option></Select></Field><Field label="Valor do desconto manual"><MoneyInput value={form.manualDiscountValue} onValueChange={(value) => updateItemForm(item.id, { manualDiscountValue: value })} disabled={saving} placeholder="0,00" /></Field><Field label="Desconto manual calculado"><MoneyInput value={form.manualDiscount} onValueChange={(value) => updateItemForm(item.id, { manualDiscount: value })} disabled={saving} placeholder="0,00" /></Field><Field label="Subtotal líquido"><MoneyInput value={form.netSubtotal} onValueChange={(value) => updateItemForm(item.id, { netSubtotal: value })} disabled={saving} /></Field><Field label="Participa da taxa de serviço"><Select value={form.participatesInServiceFee} onChange={(event) => updateItemForm(item.id, { participatesInServiceFee: event.target.value as ItemForm["participatesInServiceFee"] })} disabled={saving}><option value="">Selecione conforme a evidência</option><option value="true">Sim</option><option value="false">Não</option></Select></Field><Field label="Participa da comissão"><Select value={form.participatesInCommission} onChange={(event) => updateItemForm(item.id, { participatesInCommission: event.target.value as ItemForm["participatesInCommission"] })} disabled={saving}><option value="">Selecione conforme a evidência</option><option value="true">Sim</option><option value="false">Não</option></Select></Field>
            </div></div>; })}</section>}
            {(itemPending || feePending) && <section className="grid gap-3 sm:grid-cols-2"><Field label="Justificativa" error={fields.justification?.[0]}><Textarea value={justification} onChange={(event) => { setJustification(event.target.value); setPreview(null); }} disabled={saving} rows={4} placeholder="Explique a evidência que fundamenta esta recuperação." /></Field><Field label="Referência da evidência" error={fields.evidence_reference?.[0]}><Textarea value={evidenceReference} onChange={(event) => { setEvidenceReference(event.target.value); setPreview(null); }} disabled={saving} rows={4} placeholder="Documento, relatório ou comprovante arquivado." /></Field></section>}
            {itemPending && <section className="space-y-3 rounded-md border border-subtle p-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><strong>Prévia financeira</strong><p className="text-sm text-muted">A prévia não confirma a operação.</p></div>{canRegularizeItems && <Button variant="secondary" loading={saving} onClick={() => void requestPreview()}>Gerar prévia</Button>}</div>{preview && (preview.preview_available ? <div className="grid gap-1 text-sm sm:grid-cols-2"><span>Subtotal: {formatDecimalBRL(preview.subtotal)}</span><span>Benefícios: {formatDecimalBRL(preview.promotion_discount)}</span><span>Descontos: {formatDecimalBRL(preview.manual_discount)}</span><span>Taxa: {formatPercent(preview.service_fee_rate)} ({formatDecimalBRL(preview.service_fee)})</span>{preview.commission_rate !== undefined && <span>Comissão: {formatPercent(preview.commission_rate)} ({formatDecimalBRL(preview.commission_amount)})</span>}<span>Total devido: {formatDecimalBRL(preview.total_due)}</span><span>Total pago: {formatDecimalBRL(preview.paid_total)}</span><span>Saldo: {formatDecimalBRL(preview.remaining_balance)}</span>{preview.payment_exceeds_total && <strong className="text-danger">Há pagamento excedente.</strong>}</div> : <Alert message={preview.reason || "A prévia consolidada não está disponível."} />)}{canRegularizeItems && <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={itemConfirmed} onChange={(event) => setItemConfirmed(event.target.checked)} disabled={saving || !preview} /><span>Confirmo que os snapshots acima são comprovados e que esta regularização excepcional não altera pagamentos anteriores.</span></label>} {canRegularizeItems ? <Button loading={saving} disabled={!preview || !itemConfirmed} onClick={() => void regularizeItems()}><ShieldCheck className="size-4" />Confirmar itens</Button> : <p className="text-sm text-muted">Você não possui permissão para regularizar os itens históricos.</p>}</section>}
            {feePending && <section className="space-y-3 rounded-md border border-subtle p-4"><div><h3 className="font-semibold">Taxa de serviço histórica</h3>{itemPending && <p className="text-sm text-muted">Recupere primeiro os itens quando a evidência permitir; esta taxa permanece uma operação independente.</p>}</div><Field label="Percentual histórico de serviço" error={fields.service_fee_rate?.[0]}><MoneyInput value={rate} onValueChange={setRate} disabled={saving} placeholder="Ex.: 10,00" /></Field>{canRegularizeFee && <><label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={feeConfirmed} onChange={(event) => setFeeConfirmed(event.target.checked)} disabled={saving} /><span>Confirmo que a taxa foi comprovada pela evidência informada.</span></label><Button loading={saving} disabled={!feeConfirmed} onClick={() => void regularizeFee()}><ShieldCheck className="size-4" />Confirmar taxa</Button></>}{!canRegularizeFee && <p className="text-sm text-muted">Você não possui permissão para regularizar a taxa histórica.</p>}</section>}
            {detail.payments_visible && <section className="rounded-md border border-subtle p-4"><h3 className="font-semibold">Pagamentos</h3>{detail.payments.length ? <div className="mt-2 space-y-1 text-sm">{detail.payments.map((payment) => <div key={payment.id} className="flex justify-between gap-3"><span>{payment.payment_method__name} · {formatDate(payment.created_at)} · {payment.status === "reversed" ? `Estornado${payment.reversal_of_id ? ` do pagamento #${payment.reversal_of_id}` : ""}` : "Aplicado"}</span><strong>{formatDecimalBRL(payment.amount)}</strong></div>)}</div> : <p className="mt-2 text-sm text-muted">Nenhum pagamento histórico encontrado.</p>}</section>}
            {!detail.payments_visible && <p className="text-sm text-muted">O histórico de pagamentos não está disponível para a sua permissão.</p>}
          </> : null}
          {error && <Alert message={error} />}
          <div className="flex justify-end border-t border-subtle pt-4"><Button variant="secondary" onClick={() => setSelected(null)} disabled={saving}>Fechar</Button></div>
        </div>
      </Modal>
    </>
  );
}

export default function FinancialRegularizationsPageWrapper() {
  return <AdminGuard requiredPermissions={[permissions.viewCommands]} requiredFeatures={["commands"]}><FinancialRegularizationsPage /></AdminGuard>;
}
