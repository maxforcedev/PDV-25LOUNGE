"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Plus, SlidersHorizontal, Trash2 } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { InventoryNav } from "@/components/inventory-nav";
import { PageHeader } from "@/components/page-header";
import { PeriodFilter, type PeriodValue } from "@/components/period-filter";
import { Alert, Button, EmptyState, Field, Input, Modal, Select, TableLoading, Textarea } from "@/components/ui";
import { fieldError, formatDate, formatDecimalBRL, formatQuantity } from "@/lib/format";
import { contentUnitLabel, enrichFractionStockOptions, isExactContentValid, isUnitQuantityValid, lossReasonLabels, physicalQuantityDisplay } from "@/lib/inventory";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { InventoryWorkflowOptions, LossReason, LossRecord } from "@/types";

type Filters = { reason: string; product: string; responsible: string; period: PeriodValue };
const empty = (): Filters => ({ reason: "", product: "", responsible: "", period: { start: "", end: "" } });

function Losses() {
  const { currentBranch, hasPermission, supportSession } = useAuth();
  const canView = hasPermission(permissions.viewAdvancedInventory);
  const canCreate = hasPermission(permissions.recordLoss) && supportSession?.mode !== "READ_ONLY";
  const [items, setItems] = useState<LossRecord[]>([]);
  const [options, setOptions] = useState<InventoryWorkflowOptions | null>(null);
  const [draft, setDraft] = useState<Filters>(empty);
  const [open, setOpen] = useState(false);
  const [product, setProduct] = useState("");
  const [quantity, setQuantity] = useState("");
  const [quantityMode, setQuantityMode] = useState<"packages" | "content">("packages");
  const [reason, setReason] = useState<LossReason>("BREAKAGE");
  const [observation, setObservation] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const key = useRef("");
  const context = useRef("");
  context.current = String(currentBranch?.id || "");
  const selectedProduct = options?.stocks.find((item) => String(item.product) === product);
  const lossQuantity = (item: LossRecord) => physicalQuantityDisplay({ quantity: item.quantity, content: item.content_quantity, packageContent: item.package_content_snapshot, contentUnit: item.content_unit, completePackages: item.complete_packages, residualContent: item.residual_content });

  async function load(filters = draft, token = context.current) {
    if (!currentBranch || !canView) {
      setItems([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    const query = new URLSearchParams();
    if (filters.reason) query.set("reason", filters.reason);
    if (filters.product) query.set("product", filters.product);
    if (filters.responsible) query.set("responsible", filters.responsible);
    if (filters.period.start) query.set("start_datetime", filters.period.start);
    if (filters.period.end) query.set("end_datetime", filters.period.end);
    try {
      const response = await http.getAll<LossRecord>(`loss-records/?${query}`);
      if (context.current === token) setItems(response);
    } catch (caught) {
      if (context.current === token) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as perdas.");
    } finally {
      if (context.current === token) setLoading(false);
    }
  }

  const loadRef = useRef(load);
  loadRef.current = load;
  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const filters = { ...empty(), reason: query.get("reason") || "", product: query.get("product") || "", responsible: query.get("responsible") || "", period: { start: query.get("start_datetime") || "", end: query.get("end_datetime") || "" } };
    setDraft(filters);
    setItems([]);
    setOptions(null);
    setSuccess("");
    const token = context.current;
    void loadRef.current(filters, token);
    if (currentBranch && canCreate) {
      void http.get<InventoryWorkflowOptions>("loss-records/options/").then(async (response) => ({ ...response, stocks: await enrichFractionStockOptions(response.stocks) })).then((response) => { if (context.current === token) setOptions(response); }).catch((caught) => { if (context.current === token) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as opções de perda."); });
    }
  }, [currentBranch, canView, canCreate]);

  function openCreate() {
    setProduct(options?.stocks[0] ? String(options.stocks[0].product) : "");
    setQuantity("");
    setQuantityMode("packages");
    setReason("BREAKAGE");
    setObservation("");
    setError("");
    setFields({});
    key.current = crypto.randomUUID();
    setOpen(true);
  }

  function changed(callback: () => void) {
    callback();
    key.current = crypto.randomUUID();
  }

  async function create(event: React.FormEvent) {
    event.preventDefault();
    if (!currentBranch || !selectedProduct) return;
    const exact = quantityMode === "content" && selectedProduct.fraction_config?.tracking_active;
    if (exact ? !isExactContentValid(quantity) : !isUnitQuantityValid(quantity, selectedProduct.unit)) {
      setFields({ [exact ? "content_quantity" : "quantity"]: [exact ? "Informe conteúdo positivo com até 9 casas decimais." : selectedProduct.unit.toLowerCase() === "un" ? "Informe uma quantidade inteira de embalagens." : "Informe uma quantidade positiva com até 3 casas decimais."] });
      setError("Revise a quantidade informada.");
      return;
    }
    setSaving(true);
    setError("");
    setFields({});
    try {
      const loss = await http.post<LossRecord>("loss-records/", { idempotency_key: key.current, branch: currentBranch.id, product: Number(product), ...(exact ? { content_quantity: quantity.replace(",", ".") } : { quantity: quantity.replace(",", ".") }), reason, observation });
      setOpen(false);
      setSuccess(`Perda de ${loss.content_quantity ? physicalQuantityDisplay({ content: loss.content_quantity, packageContent: loss.package_content_snapshot || selectedProduct.fraction_config?.package_content, contentUnit: loss.content_unit || selectedProduct.fraction_config?.content_unit, completePackages: loss.complete_packages, residualContent: loss.residual_content }) : `${formatQuantity(loss.quantity)} ${selectedProduct.unit.toUpperCase()}`} de ${loss.product_name} registrada.`);
      if (canView) await load();
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setFields(caught.fields);
      } else setError("Não foi possível registrar a perda.");
    } finally {
      setSaving(false);
    }
  }

  return <>
    <PageHeader title="Perdas de estoque" description={`${currentBranch?.name || "Selecione uma filial"} · baixas conhecidas, justificadas e auditadas.`} action={canCreate && <Button onClick={openCreate} disabled={!currentBranch || !options}><Plus className="size-4" />Registrar perda</Button>} />
    <InventoryNav />
    <div className="space-y-4 p-4 sm:p-6 lg:p-8">
      {error && !open && <Alert message={error} />}
      {success && <Alert message={success} type="success" />}
      {canView ? <>
        <form className="card grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-3" onSubmit={(event) => { event.preventDefault(); void load(); }}>
          <Select aria-label="Motivo" value={draft.reason} onChange={(event) => setDraft((value) => ({ ...value, reason: event.target.value }))}><option value="">Todos os motivos</option>{Object.entries(lossReasonLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select>
          <Input aria-label="Produto" inputMode="numeric" placeholder="ID do produto" value={draft.product} onChange={(event) => setDraft((value) => ({ ...value, product: event.target.value.replace(/\D/g, "") }))} />
          <Input aria-label="Responsável" inputMode="numeric" placeholder="ID do responsável" value={draft.responsible} onChange={(event) => setDraft((value) => ({ ...value, responsible: event.target.value.replace(/\D/g, "") }))} />
          <PeriodFilter className="sm:col-span-2 xl:col-span-3" value={draft.period} onChange={(period) => setDraft((value) => ({ ...value, period }))} />
          <div className="flex justify-end gap-2 sm:col-span-2 xl:col-span-3"><Button type="button" variant="secondary" onClick={() => { const filters = empty(); setDraft(filters); void load(filters); }}>Limpar</Button><Button type="submit"><SlidersHorizontal className="size-4" />Aplicar</Button></div>
        </form>
        <section className="card overflow-hidden">
          <div className="card-header"><div><h2 className="text-sm font-bold">Registros de perda</h2><p className="mt-1 text-[11px] text-muted">Snapshots de custo permanecem ocultos sem a permissão correspondente.</p></div><Trash2 className="size-5 text-muted" /></div>
          {loading ? <TableLoading columns={7} /> : items.length ? <>
            <div className="divide-y divide-subtle md:hidden">{items.map((item) => <article key={item.id} className="p-4"><div className="flex justify-between gap-3"><div><strong>{item.product_name}</strong><p className="mt-1 text-xs text-muted">{lossReasonLabels[item.reason]} · {formatDate(item.recorded_at)}</p></div><strong>{lossQuantity(item)}</strong></div><p className="mt-3 text-xs text-muted">{item.observation}</p><dl className="mt-3 grid grid-cols-2 gap-2 text-xs"><div><dt className="text-muted">Venda potencial</dt><dd>{formatDecimalBRL(item.potential_sale_value)}</dd></div>{item.cost_impact !== undefined && <div><dt className="text-muted">Impacto de custo</dt><dd>{formatDecimalBRL(item.cost_impact)}</dd></div>}</dl><Link href={`/estoque/movimentacoes?operation_reference=${item.id}&domain_origin=LOSS`} className="mt-3 inline-block text-xs font-semibold text-link">Ver movimentação de perda</Link></article>)}</div>
            <div className="table-wrap hidden md:block"><table className="data-table"><thead><tr><th>Data do evento</th><th>Produto</th><th>Quantidade exata</th><th>Motivo</th><th>Responsável</th><th>Impactos</th><th>Movimento</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td>{formatDate(item.recorded_at)}</td><td><strong>{item.product_name}</strong><small className="block max-w-72 text-muted">{item.observation}</small></td><td className="font-bold">{lossQuantity(item)}</td><td>{lossReasonLabels[item.reason]}</td><td>#{item.recorded_by}</td><td><span className="block">Venda: {formatDecimalBRL(item.potential_sale_value)}</span>{item.cost_impact !== undefined && <small className="text-muted">Custo: {formatDecimalBRL(item.cost_impact)}</small>}</td><td><Link href={`/estoque/movimentacoes?operation_reference=${item.id}&domain_origin=LOSS`} className="font-semibold text-link">Abrir</Link></td></tr>)}</tbody></table></div>
          </> : <EmptyState title="Nenhuma perda" description="Não há registros para os filtros aplicados." />}
        </section>
      </> : <section className="card"><EmptyState title="Histórico restrito" description="Sua permissão permite registrar a perda, mas não consultar o histórico ou seus impactos." /></section>}
    </div>
    <Modal open={open} title="Registrar perda" description="A confirmação baixa o saldo e captura os valores históricos no servidor." onClose={() => !saving && setOpen(false)}>
      <form onSubmit={create}>
        <div className="space-y-4 p-5 sm:p-6">
          {error && <Alert message={error} />}
          <Field label="Filial"><Input readOnly value={options?.branch.name || currentBranch?.name || ""} /></Field>
          <Field label="Produto" error={fieldError(fields, "product")}><Select required value={product} onChange={(event) => changed(() => { const next = options?.stocks.find((item) => String(item.product) === event.target.value); setProduct(event.target.value); setQuantity(""); setQuantityMode(next?.fraction_config?.tracking_active ? "content" : "packages"); })}><option value="">Selecione</option>{options?.stocks.map((item) => <option key={item.stock} value={item.product}>{item.product_name} ({item.internal_code})</option>)}</Select></Field>
          {selectedProduct?.fraction_config?.tracking_active && <fieldset><legend className="label">Forma da baixa</legend><div className="grid grid-cols-2 gap-2"><label className={`rounded-md border p-3 text-xs ${quantityMode === "content" ? "border-primary bg-primary/5" : "border-subtle"}`}><input className="mr-2" type="radio" checked={quantityMode === "content"} onChange={() => changed(() => { setQuantityMode("content"); setQuantity(""); })} />Conteúdo exato</label><label className={`rounded-md border p-3 text-xs ${quantityMode === "packages" ? "border-primary bg-primary/5" : "border-subtle"}`}><input className="mr-2" type="radio" checked={quantityMode === "packages"} onChange={() => changed(() => { setQuantityMode("packages"); setQuantity(""); })} />Embalagens fechadas</label></div></fieldset>}
          <div className="grid gap-4 sm:grid-cols-2"><Field label={quantityMode === "content" && selectedProduct?.fraction_config ? `Conteúdo perdido (${contentUnitLabel(selectedProduct.fraction_config.content_unit)})` : `Quantidade${selectedProduct ? ` (${selectedProduct.unit.toUpperCase()})` : ""}`} error={fieldError(fields, quantityMode === "content" ? "content_quantity" : "quantity")}><Input required inputMode="decimal" step={quantityMode === "content" ? "0.000000001" : selectedProduct?.unit.toLowerCase() === "un" ? "1" : "0.001"} min={quantityMode === "content" ? "0.000000001" : "0.001"} value={quantity} onChange={(event) => changed(() => setQuantity(event.target.value))} />{quantityMode === "content" && selectedProduct?.fraction_config && <span className="mt-1 block text-[10px] text-muted">Embalagem canônica: {formatQuantity(selectedProduct.fraction_config.package_content)} {contentUnitLabel(selectedProduct.fraction_config.content_unit)}</span>}</Field><Field label="Motivo" error={fieldError(fields, "reason")}><Select value={reason} onChange={(event) => changed(() => setReason(event.target.value as LossReason))}>{Object.entries(lossReasonLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select></Field></div>
          <Field label="Observação" error={fieldError(fields, "observation")}><Textarea required minLength={3} value={observation} onChange={(event) => changed(() => setObservation(event.target.value))} /></Field>
        </div>
        <div className="flex justify-end gap-2 border-t border-subtle px-5 py-4"><Button type="button" variant="secondary" disabled={saving} onClick={() => setOpen(false)}>Cancelar</Button><Button type="submit" loading={saving} disabled={!selectedProduct}>Confirmar baixa</Button></div>
      </form>
    </Modal>
  </>;
}

export default function LossesPage() {
  return <AdminGuard requiredPermissions={[permissions.viewAdvancedInventory, permissions.recordLoss]}><Losses /></AdminGuard>;
}
