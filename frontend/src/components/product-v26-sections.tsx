"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Boxes, Check, Copy, Factory, GripVertical, PackageOpen, Pencil, Plus, Power, RotateCcw, Store, Truck } from "lucide-react";
import { Alert, Button, ConfirmDialog, Field, Input, Modal, Select } from "@/components/ui";
import { fieldError, formatDecimalBRL, formatQuantity } from "@/lib/format";
import { contentUnitLabel, packageContentDisplay } from "@/lib/inventory";
import { ApiError, http } from "@/lib/http";
import type {
  EmbeddedProductSupplier,
  EmbeddedProductSupplierUnit,
  ModifierGroup,
  Product,
  ProductBranchConfig,
  ProductModifierGroup,
  PresentationPreset,
  PresentationType,
  ProductionDestination,
  Supplier,
  UserBranch,
} from "@/types";

type Permissions = {
  branch: boolean;
  fraction: boolean;
  destinations: boolean;
  duplicate: boolean;
  viewModifiers: boolean;
  changeModifiers: boolean;
  viewSuppliers: boolean;
  changeSuppliers: boolean;
};

type Props = {
  product: Product;
  companyId: number;
  currentBranchId: number;
  branches: UserBranch[];
  permissions: Permissions;
  onReload: () => Promise<void>;
  onDuplicated: (product: Product) => void;
};

type RelationForm = {
  supplier: string;
  supplier_code: string;
  is_preferred: boolean;
  is_exclusive: boolean;
};
type UnitForm = {
  unit_code: string;
  description: string;
  conversion_factor: string;
  barcode: string;
  is_default: boolean;
  presentation_preset: string;
  presentation_type: PresentationType;
  custom_code: string;
  custom_name: string;
  save_as_preset: boolean;
};

const emptyRelation = (): RelationForm => ({ supplier: "", supplier_code: "", is_preferred: false, is_exclusive: false });
const emptyUnit = (): UnitForm => ({ unit_code: "", description: "", conversion_factor: "1.000000", barcode: "", is_default: false, presentation_preset: "", presentation_type: "UN", custom_code: "", custom_name: "", save_as_preset: false });
const channelLabels = { counter: "Balcão", table: "Mesa", command: "Comanda" } as const;
const presentationTypeLabels: Record<PresentationType, string> = {
  UN: "Unidade", CX: "Caixa", FD: "Fardo", PK: "Pack", PCT: "Pacote",
  ENG: "Engradado", DSP: "Display", BDJ: "Bandeja", SC: "Saco", KIT: "Kit", OTHER: "Outro",
};

function apiError(caught: unknown, fallback: string) {
  return caught instanceof ApiError
    ? `${caught.message} ${Object.values(caught.fields).flat().join(" ")}`.trim()
    : fallback;
}

function AuditNote() {
  return <p className="mt-2 text-[10px] text-muted">Alterações desta seção são registradas na auditoria.</p>;
}

export function ProductV26Sections({ product, companyId, currentBranchId, branches, permissions, onReload, onDuplicated }: Props) {
  const [branchConfig, setBranchConfig] = useState<ProductBranchConfig | null>(null);
  const [destinations, setDestinations] = useState<ProductionDestination[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [presentationPresets, setPresentationPresets] = useState<PresentationPreset[]>([]);
  const [modifierGroups, setModifierGroups] = useState<ModifierGroup[]>([]);
  const [modifierLinks, setModifierLinks] = useState<ProductModifierGroup[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const [fractionContent, setFractionContent] = useState(product.fraction_config?.package_content || "");
  const [fractionUnit, setFractionUnit] = useState<"ml" | "g">(product.fraction_config?.content_unit || "ml");
  const [activateFraction, setActivateFraction] = useState(false);

  const [destinationOpen, setDestinationOpen] = useState(false);
  const [editingDestination, setEditingDestination] = useState<ProductionDestination | null>(null);
  const [destinationName, setDestinationName] = useState("");
  const [destinationCode, setDestinationCode] = useState("");
  const [selectedDestinations, setSelectedDestinations] = useState<number[]>(product.production_destinations?.map((item) => item.id) || []);

  const [copyOpen, setCopyOpen] = useState<"product" | "category" | null>(null);
  const [copySource, setCopySource] = useState(String(currentBranchId));
  const [copyTargets, setCopyTargets] = useState<number[]>([]);
  const [duplicateOpen, setDuplicateOpen] = useState(false);
  const [duplicateOptions, setDuplicateOptions] = useState({ composition: false, fraction: false, branch_config: false, destinations: false, suppliers: false });

  const [relationOpen, setRelationOpen] = useState(false);
  const [editingRelation, setEditingRelation] = useState<EmbeddedProductSupplier | null>(null);
  const [relationForm, setRelationForm] = useState<RelationForm>(emptyRelation);
  const [unitOpen, setUnitOpen] = useState(false);
  const [unitRelation, setUnitRelation] = useState<EmbeddedProductSupplier | null>(null);
  const [editingUnit, setEditingUnit] = useState<EmbeddedProductSupplierUnit | null>(null);
  const [unitForm, setUnitForm] = useState<UnitForm>(emptyUnit);
  const [fields, setFields] = useState<Record<string, string[]>>({});

  useEffect(() => {
    let active = true;
    setError("");
    setNotice("");
    setSelectedDestinations(product.production_destinations?.map((item) => item.id) || []);
    setFractionContent(product.fraction_config?.package_content || "");
    setFractionUnit(product.fraction_config?.content_unit || "ml");
    const requests: Promise<void>[] = [
      http.get<ProductBranchConfig>(`products/${product.id}/branch-config/`).then((value) => { if (active) setBranchConfig(value); }),
      http.getAll<ProductionDestination>("production-destinations/").then((value) => { if (active) setDestinations(value); }),
    ];
    if (permissions.viewSuppliers) {
      requests.push(http.getAll<Supplier>(`suppliers/?company=${companyId}`).then((value) => { if (active) setSuppliers(value); }));
      requests.push(http.getAll<PresentationPreset>(`presentation-presets/?company=${companyId}`).then((value) => { if (active) setPresentationPresets(value); }));
    }
    if (permissions.viewModifiers) {
      requests.push(http.getAll<ModifierGroup>(`modifier-groups/?company=${companyId}`).then((value) => { if (active) setModifierGroups(value); }));
      requests.push(http.getAll<ProductModifierGroup>(`product-modifier-groups/?product=${product.id}`).then((value) => { if (active) setModifierLinks(value); }));
    }
    void Promise.allSettled(requests).then((results) => {
      if (active && results.some((item) => item.status === "rejected")) setError("Parte das configurações não pôde ser carregada para a filial atual.");
    });
    return () => { active = false; };
  }, [companyId, currentBranchId, permissions.viewModifiers, permissions.viewSuppliers, product]);

  async function run(action: () => Promise<unknown>, success: string, reload = true) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      setNotice(success);
      if (reload) await onReload();
      return true;
    } catch (caught) {
      setError(apiError(caught, "Não foi possível salvar a configuração."));
      if (caught instanceof ApiError) setFields(caught.fields);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function saveBranchConfig() {
    if (!branchConfig) return;
    await run(
      async () => setBranchConfig(await http.put<ProductBranchConfig>(`products/${product.id}/branch-config/`, {
        is_available: branchConfig.is_available,
        available_counter: branchConfig.available_counter,
        available_table: branchConfig.available_table,
        available_command: branchConfig.available_command,
      })),
      "Disponibilidade e canais da filial salvos.",
    );
  }

  async function saveFraction() {
    await run(
      () => http.put(`products/${product.id}/fraction-config/`, { package_content: fractionContent.replace(",", "."), content_unit: fractionUnit }),
      "Conteúdo da embalagem salvo.",
    );
  }

  async function confirmFractionActivation() {
    setActivateFraction(false);
    await run(() => http.post(`products/${product.id}/fraction-config/activate/`), "Rastreamento exato ativado. Conteúdo e unidade agora são imutáveis.");
  }

  function openDestination(item?: ProductionDestination) {
    setEditingDestination(item || null);
    setDestinationName(item?.name || "");
    setDestinationCode(item?.code || "");
    setDestinationOpen(true);
    setFields({});
  }

  async function saveDestination(event: React.FormEvent) {
    event.preventDefault();
    const saved = await run(
      () => editingDestination
        ? http.patch(`production-destinations/${editingDestination.id}/`, { name: destinationName, code: destinationCode })
        : http.post("production-destinations/", { branch: currentBranchId, name: destinationName, code: destinationCode }),
      editingDestination ? "Destino atualizado." : "Destino criado.",
      false,
    );
    if (saved) {
      setDestinationOpen(false);
      setDestinations(await http.getAll<ProductionDestination>("production-destinations/"));
    }
  }

  async function saveDestinationLinks() {
    await run(() => http.put(`products/${product.id}/production-destinations/`, { destinations: selectedDestinations }), "Destinos do produto salvos.");
  }

  async function toggleDestinationStatus(destination: ProductionDestination) {
    const action = destination.status === "active" ? "deactivate" : "activate";
    await run(
      () => http.post<ProductionDestination>(`production-destinations/${destination.id}/${action}/`).then((updated) => setDestinations((items) => items.map((item) => item.id === updated.id ? updated : item))),
      `Destino ${action === "activate" ? "ativado" : "inativado"}.`,
      false,
    );
  }

  async function toggleModifierGroup(group: ModifierGroup) {
    const link = modifierLinks.find((item) => item.modifier_group === group.id);
    const saved = await run(
      () => link
        ? http.post(`product-modifier-groups/${link.id}/${link.status === "active" ? "deactivate" : "activate"}/`, {})
        : http.post("product-modifier-groups/", { product: product.id, modifier_group: group.id }),
      link?.status === "active" ? "Grupo de modificador desvinculado." : "Grupo de modificador vinculado.",
      false,
    );
    if (saved) setModifierLinks(await http.getAll<ProductModifierGroup>(`product-modifier-groups/?product=${product.id}`));
  }

  async function moveModifierLink(link: ProductModifierGroup, targetId: number) {
    const previous = modifierLinks; const next = [...modifierLinks];
    const index = next.findIndex((item) => item.id === link.id);
    const target = next.findIndex((item) => item.id === targetId);
    if (index < 0 || target < 0 || index === target) return;
    next.splice(target, 0, next.splice(index, 1)[0]); setModifierLinks(next);
    const saved = await run(
      () => http.post("product-modifier-groups/reorder/", { product: product.id, link_ids: next.map((item) => item.id) }),
      "Ordem dos modificadores atualizada.", false,
    );
    if (!saved) setModifierLinks(previous);
  }

  async function copyConfiguration() {
    if (!copyOpen) return;
    const payload = { source_branch: Number(copySource), target_branches: copyTargets };
    const copied = await run(
      () => copyOpen === "category"
        ? http.post("products/copy-category-config/", { ...payload, category: product.category })
        : http.post(`products/${product.id}/copy-branch-config/`, payload),
      copyOpen === "category" ? "Configuração da categoria copiada para as filiais selecionadas." : "Configuração do produto copiada para as filiais selecionadas.",
      false,
    );
    if (copied) setCopyOpen(null);
  }

  async function duplicate() {
    setBusy(true);
    setError("");
    try {
      const created = await http.post<Product>(`products/${product.id}/duplicate/`, duplicateOptions);
      setDuplicateOpen(false);
      onDuplicated(created);
    } catch (caught) {
      setError(apiError(caught, "Não foi possível duplicar o produto."));
    } finally {
      setBusy(false);
    }
  }

  function openRelation(relation?: EmbeddedProductSupplier) {
    setEditingRelation(relation || null);
    setRelationForm(relation ? {
      supplier: String(relation.supplier), supplier_code: relation.supplier_code,
      is_preferred: relation.is_preferred, is_exclusive: relation.is_exclusive,
    } : emptyRelation());
    setFields({});
    setRelationOpen(true);
  }

  async function saveRelation(event: React.FormEvent) {
    event.preventDefault();
    setFields({});
    const payload = {
      company: companyId, product: product.id, supplier: Number(relationForm.supplier),
      supplier_code: relationForm.supplier_code, is_preferred: relationForm.is_preferred,
      is_exclusive: relationForm.is_exclusive,
    };
    const saved = await run(
      () => editingRelation ? http.patch(`product-suppliers/${editingRelation.id}/`, payload) : http.post("product-suppliers/", payload),
      editingRelation ? "Vínculo de fornecedor atualizado." : "Fornecedor vinculado ao produto.",
    );
    if (saved) setRelationOpen(false);
  }

  function openUnit(relation: EmbeddedProductSupplier, unit?: EmbeddedProductSupplierUnit) {
    setUnitRelation(relation);
    setEditingUnit(unit || null);
    setUnitForm(unit ? {
      ...emptyUnit(),
      unit_code: unit.unit_code, description: unit.description, conversion_factor: unit.conversion_factor,
      barcode: unit.barcode, is_default: unit.is_default,
    } : emptyUnit());
    setFields({});
    setUnitOpen(true);
  }

  async function saveUnit(event: React.FormEvent) {
    event.preventDefault();
    if (!unitRelation) return;
    const commonPayload = {
      company: companyId, product_supplier: unitRelation.id, barcode: unitForm.barcode,
      is_default: unitForm.is_default,
    };
    const payload = editingUnit
      ? {
        ...commonPayload, unit_code: unitForm.unit_code, description: unitForm.description,
        conversion_factor: unitForm.conversion_factor.replace(",", "."),
      }
      : unitForm.presentation_preset
        ? { ...commonPayload, presentation_preset: Number(unitForm.presentation_preset) }
        : {
          ...commonPayload, presentation_type: unitForm.presentation_type,
          conversion_factor: unitForm.conversion_factor.replace(",", "."),
          ...(unitForm.presentation_type === "OTHER" ? {
            custom_code: unitForm.custom_code.trim().toUpperCase(), custom_name: unitForm.custom_name.trim(),
          } : {}),
          save_as_preset: unitForm.save_as_preset,
        };
    const saved = await run(
      () => editingUnit ? http.patch(`product-supplier-units/${editingUnit.id}/`, payload) : http.post("product-supplier-units/", payload),
      editingUnit ? "Apresentação atualizada." : "Apresentação adicionada.",
    );
    if (saved) setUnitOpen(false);
  }

  async function toggleRelationStatus(relation: EmbeddedProductSupplier) {
    const action = relation.status === "active" ? "deactivate" : "activate";
    await run(
      () => http.post(`product-suppliers/${relation.id}/${action}/`),
      `Vínculo de fornecedor ${action === "activate" ? "ativado" : "inativado"}.`,
    );
  }

  async function toggleUnitStatus(unit: EmbeddedProductSupplierUnit) {
    const action = unit.status === "active" ? "deactivate" : "activate";
    await run(
      () => http.post(`product-supplier-units/${unit.id}/${action}/`),
      `Apresentação ${action === "activate" ? "ativada" : "inativada"}.`,
    );
  }

  const stock = product.branch_stock;
  const exactStock = stock?.current_content != null && product.fraction_config;
  const targetBranches = branches.filter((branch) => String(branch.id) !== copySource);

  return <div className="space-y-5 border-t border-subtle p-5 sm:p-6">
    {error && <Alert message={error} />}
    {notice && <Alert type="success" message={notice} />}

    <section className="rounded-xl border border-subtle bg-surface-muted/40 p-4">
      <div className="flex items-start gap-3"><Boxes className="mt-0.5 size-5 text-primary" /><div className="min-w-0 flex-1"><h3 className="text-sm font-bold">Estoque na filial atual</h3>
        {!stock || !stock.applicable ? <p className="mt-2 text-xs text-muted">Não se aplica: este produto não controla estoque.</p> : stock.semantic === "components" ? <><p className="mt-2 text-xl font-bold">{formatQuantity(stock.current_quantity)} {stock.unit?.toUpperCase()}</p><p className="text-xs text-muted">Disponibilidade resolvida pela capacidade dos componentes, não por saldo próprio.</p></> : <><p className="mt-2 text-xl font-bold">{exactStock ? packageContentDisplay(stock.current_content, product.fraction_config) : `${formatQuantity(stock.current_quantity)} ${stock.unit?.toUpperCase()}`}</p><p className="text-xs text-muted">Saldo físico direto desta filial.</p>{exactStock && <p className="mt-2 text-xs text-muted">Total exato: {formatQuantity(stock.current_content)} {contentUnitLabel(stock.content_unit || product.fraction_config?.content_unit)}</p>}</>}
        {stock?.unit_cost !== undefined && <p className="mt-2 text-xs text-muted">Custo atual: {formatDecimalBRL(stock.unit_cost)}</p>}
      </div></div>
    </section>

    <section className="rounded-xl border border-subtle p-4">
      <div className="mb-4 flex items-start justify-between gap-3"><div><h3 className="flex items-center gap-2 text-sm font-bold"><Store className="size-4 text-primary" />Disponibilidade na filial</h3><p className="mt-1 text-[11px] text-muted">Preço efetivo: {formatDecimalBRL(branchConfig?.effective_sale_price || product.branch_configuration?.sale_price)}. O preço por filial continua no fluxo dedicado.</p></div><Link href="/produtos/precos" className="btn btn-secondary">Preços</Link></div>
      {branchConfig && <div className="space-y-3"><label className="flex items-center gap-2 text-xs font-semibold"><input type="checkbox" checked={branchConfig.is_available} disabled={!permissions.branch} onChange={(event) => setBranchConfig((value) => value && ({ ...value, is_available: event.target.checked }))} />Produto disponível nesta filial</label><div className="grid gap-3 sm:grid-cols-3">{(Object.keys(channelLabels) as Array<keyof typeof channelLabels>).map((channel) => <Field key={channel} label={channelLabels[channel]}><Select disabled={!permissions.branch} value={String(branchConfig[`available_${channel}`])} onChange={(event) => setBranchConfig((value) => value && ({ ...value, [`available_${channel}`]: event.target.value === "null" ? null : event.target.value === "true" }))}><option value="null">Herdar global ({product[`available_${channel}`] ? "disponível" : "indisponível"})</option><option value="true">Disponível nesta filial</option><option value="false">Indisponível nesta filial</option></Select><span className="mt-1 block text-[10px] text-muted">Efetivo: {branchConfig.effective_channels[channel] ? "disponível" : "indisponível"}</span></Field>)}</div>{permissions.branch && <div className="flex justify-end"><Button type="button" loading={busy} onClick={() => void saveBranchConfig()}>Salvar filial</Button></div>}</div>}
      <AuditNote />
    </section>

    {permissions.viewModifiers && <section className="rounded-xl border border-subtle p-4">
      <div><h3 className="text-sm font-bold">Grupos de modificadores</h3><p className="mt-1 text-[11px] text-muted">Vincule grupos reutilizáveis a este produto. As regras de obrigatório, mínimo e máximo são definidas no grupo.</p></div>
      <div className="mt-4 grid gap-2 sm:grid-cols-2">{modifierGroups.map((group) => {
        const link = modifierLinks.find((item) => item.modifier_group === group.id);
        const linked = link?.status === "active";
        return <div key={group.id} draggable={Boolean(link && linked && permissions.changeModifiers)} onDragStart={(event) => link && event.dataTransfer.setData("text/plain", String(link.id))} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { const source = Number(event.dataTransfer.getData("text/plain")); if (link && source) void moveModifierLink(modifierLinks.find((item) => item.id === source)!, link.id); }} className="flex items-center gap-3 rounded-md border border-subtle p-3 text-xs"><span className="cursor-grab active:cursor-grabbing"><GripVertical className="size-4 text-muted" /></span><input type="checkbox" checked={linked} disabled={!permissions.changeModifiers || group.status !== "active"} onChange={() => void toggleModifierGroup(group)} /><div className="min-w-0 flex-1"><strong className="block">{group.name}</strong><span className="text-[10px] text-muted">{group.status === "active" ? `${group.is_required ? "Obrigatório" : "Opcional"} · ${group.min_selections}/${group.max_selections ?? "∞"}` : "Grupo inativo"}</span></div></div>;
      })}</div>
      {!modifierGroups.length && <p className="mt-3 rounded-md bg-surface-muted p-3 text-xs text-muted">Cadastre grupos em Modificadores antes de vinculá-los ao produto.</p>}<AuditNote />
    </section>}

    {product.inventory_behavior === "direct" && product.unit === "un" && <section className="rounded-xl border border-subtle p-4">
      <h3 className="flex items-center gap-2 text-sm font-bold"><PackageOpen className="size-4 text-primary" />Conteúdo fracionável</h3><p className="mt-1 text-[11px] text-muted">A embalagem é expressa somente em unidade canônica de conteúdo (mL ou g).</p>
      <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_140px_auto]"><Field label="Conteúdo por embalagem"><Input inputMode="decimal" min="0.000000001" step="0.000000001" value={fractionContent} disabled={!permissions.fraction || product.fraction_config?.tracking_active} onChange={(event) => setFractionContent(event.target.value)} /></Field><Field label="Unidade canônica"><Select value={fractionUnit} disabled={!permissions.fraction || product.fraction_config?.tracking_active} onChange={(event) => setFractionUnit(event.target.value as "ml" | "g")}><option value="ml">mL</option><option value="g">g</option></Select></Field><div className="flex items-end"><Button type="button" loading={busy} disabled={!permissions.fraction || !fractionContent || product.fraction_config?.tracking_active} onClick={() => void saveFraction()}>Salvar</Button></div></div>
      {product.fraction_config?.tracking_active ? <p className="mt-3 flex items-center gap-2 text-xs font-semibold text-success-strong"><Check className="size-4" />Rastreamento exato ativo e configuração imutável.</p> : product.fraction_config && permissions.fraction && <Button type="button" variant="secondary" className="mt-3" onClick={() => setActivateFraction(true)}>Ativar rastreamento exato</Button>}
      <AuditNote />
    </section>}

    <section className="rounded-xl border border-subtle p-4">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="flex items-center gap-2 text-sm font-bold"><Factory className="size-4 text-primary" />Destinos de produção</h3><p className="mt-1 text-[11px] text-muted">Somente configuração. Não envia impressão e não executa KDS.</p></div>{permissions.destinations && <Button type="button" variant="secondary" onClick={() => openDestination()}><Plus className="size-4" />Novo destino</Button>}</div>
      <div className="mt-4 grid gap-2 sm:grid-cols-2">{destinations.map((item) => <label key={item.id} className="flex items-center gap-3 rounded-md border border-subtle p-3 text-xs"><input type="checkbox" checked={selectedDestinations.includes(item.id)} disabled={!permissions.destinations || (item.status !== "active" && !selectedDestinations.includes(item.id))} onChange={(event) => setSelectedDestinations((value) => event.target.checked ? [...value, item.id] : value.filter((id) => id !== item.id))} /><span className="min-w-0 flex-1"><strong className="block">{item.name}</strong><span className="text-muted">{item.code}{item.status !== "active" ? " · inativo" : ""}</span></span>{permissions.destinations && <div className="flex gap-1"><button type="button" className="icon-button" title="Editar destino" onClick={(event) => { event.preventDefault(); openDestination(item); }}><Pencil className="size-3.5" /></button><button type="button" className="icon-button" title={item.status === "active" ? "Inativar destino" : "Ativar destino"} onClick={(event) => { event.preventDefault(); void toggleDestinationStatus(item); }}><Power className="size-3.5" /></button></div>}</label>)}</div>
      {permissions.destinations && <div className="mt-3 flex justify-end"><Button type="button" loading={busy} onClick={() => void saveDestinationLinks()}>Salvar vínculos</Button></div>}<AuditNote />
    </section>

    <section className="rounded-xl border border-subtle p-4">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="flex items-center gap-2 text-sm font-bold"><Copy className="size-4 text-primary" />Copiar entre filiais</h3><p className="mt-1 text-[11px] text-muted">Comando atômico: disponibilidade, canais, preço por filial e destinos. Estoque e histórico nunca são copiados.</p></div>{permissions.branch && <div className="flex gap-2"><Button type="button" variant="secondary" onClick={() => { setCopyOpen("product"); setCopyTargets([]); }}>Produto</Button><Button type="button" variant="secondary" onClick={() => { setCopyOpen("category"); setCopyTargets([]); }}>Categoria</Button></div>}</div><AuditNote />
    </section>

    {permissions.viewSuppliers && <section className="rounded-xl border border-subtle p-4">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="flex items-center gap-2 text-sm font-bold"><Truck className="size-4 text-primary" />Fornecedores e apresentações</h3><p className="mt-1 text-[11px] text-muted">Vínculos existentes de ProductSupplier e ProductSupplierUnit.</p></div>{permissions.changeSuppliers && <Button type="button" variant="secondary" onClick={() => openRelation()}><Plus className="size-4" />Vincular</Button>}</div>
      <div className="mt-4 space-y-3">{product.suppliers?.length ? product.suppliers.map((relation) => <article key={relation.id} className="rounded-lg border border-subtle p-3"><div className="flex items-start justify-between gap-3"><div><strong className="text-xs">{relation.supplier_name}</strong><p className="text-[10px] text-muted">Código: {relation.supplier_code || "não informado"}{relation.is_exclusive ? " · exclusivo" : relation.is_preferred ? " · preferencial" : ""}{relation.status !== "active" ? " · inativo" : ""}</p></div>{permissions.changeSuppliers && <div className="flex gap-1"><button type="button" className="icon-button" title="Editar vínculo" onClick={() => openRelation(relation)}><Pencil className="size-3.5" /></button><button type="button" className="icon-button" title="Adicionar apresentação" onClick={() => openUnit(relation)}><Plus className="size-3.5" /></button><button type="button" className="icon-button" title={relation.status === "active" ? "Inativar vínculo" : "Ativar vínculo"} onClick={() => void toggleRelationStatus(relation)}><Power className="size-3.5" /></button></div>}</div><div className="mt-2 grid gap-2 sm:grid-cols-2">{relation.units.map((unit) => <div key={unit.id} className="flex items-center gap-1 rounded-md bg-surface-muted p-2"><button type="button" disabled={!permissions.changeSuppliers} onClick={() => openUnit(relation, unit)} className="min-w-0 flex-1 text-left text-[11px] disabled:cursor-default"><strong>{unit.unit_code}</strong> · {unit.description || "Sem descrição"}<span className="block text-muted">{formatQuantity(unit.conversion_factor)} {product.unit.toUpperCase()}{unit.is_default ? " · padrão" : ""}{unit.status !== "active" ? " · inativa" : ""}</span></button>{permissions.changeSuppliers && <button type="button" className="icon-button shrink-0" title={unit.status === "active" ? "Inativar apresentação" : "Ativar apresentação"} onClick={() => void toggleUnitStatus(unit)}><Power className="size-3.5" /></button>}</div>)}</div></article>) : <p className="rounded-md bg-surface-muted p-4 text-xs text-muted">Nenhum fornecedor vinculado.</p>}</div><AuditNote />
    </section>}

    {permissions.duplicate && <section className="flex flex-col gap-3 rounded-xl border border-subtle p-4 sm:flex-row sm:items-center sm:justify-between"><div><h3 className="flex items-center gap-2 text-sm font-bold"><RotateCcw className="size-4 text-primary" />Duplicar produto</h3><p className="mt-1 text-[11px] text-muted">O servidor gera novo nome e código interno; SKU e código de barras ficam vazios para evitar colisões.</p></div><Button type="button" variant="secondary" onClick={() => setDuplicateOpen(true)}>Duplicar</Button></section>}

    <ConfirmDialog open={activateFraction} title="Ativar rastreamento exato" message="Depois da ativação, o conteúdo por embalagem e a unidade canônica não poderão ser alterados. O saldo passará a rastrear conteúdo exato." confirmLabel="Ativar definitivamente" loading={busy} onClose={() => setActivateFraction(false)} onConfirm={() => void confirmFractionActivation()} />

    <Modal open={destinationOpen} title={editingDestination ? "Editar destino" : "Novo destino"} description="Configuração da filial atual; sem execução de impressão ou KDS." onClose={() => setDestinationOpen(false)} size="md"><form onSubmit={saveDestination}><div className="space-y-4 p-5"><Field label="Nome" error={fieldError(fields, "name")}><Input required value={destinationName} onChange={(event) => setDestinationName(event.target.value)} /></Field><Field label="Código" error={fieldError(fields, "code")}><Input required value={destinationCode} onChange={(event) => setDestinationCode(event.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-"))} /></Field></div><div className="flex justify-end gap-2 border-t border-subtle px-5 py-4"><Button type="button" variant="secondary" onClick={() => setDestinationOpen(false)}>Cancelar</Button><Button type="submit" loading={busy}>Salvar destino</Button></div></form></Modal>

    <Modal open={!!copyOpen} title={copyOpen === "category" ? "Copiar configuração da categoria" : "Copiar configuração do produto"} description="Selecione a origem e uma ou mais filiais de destino." onClose={() => setCopyOpen(null)}><div className="space-y-4 p-5"><Field label="Filial de origem"><Select value={copySource} onChange={(event) => { setCopySource(event.target.value); setCopyTargets((value) => value.filter((id) => String(id) !== event.target.value)); }}>{branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}</Select></Field><fieldset><legend className="label">Filiais de destino</legend><div className="grid gap-2 sm:grid-cols-2">{targetBranches.map((branch) => <label key={branch.id} className="flex items-center gap-2 rounded-md border border-subtle p-3 text-xs"><input type="checkbox" checked={copyTargets.includes(branch.id)} onChange={(event) => setCopyTargets((value) => event.target.checked ? [...value, branch.id] : value.filter((id) => id !== branch.id))} />{branch.name}</label>)}</div></fieldset><fieldset><legend className="label">Seções do comando atual</legend><div className="grid gap-2 sm:grid-cols-2">{["Disponibilidade e canais", "Preços por filial", "Destinos de produção"].map((label) => <label key={label} className="flex items-center gap-2 text-xs"><input type="checkbox" checked readOnly />{label}</label>)}<label className="flex items-center gap-2 text-xs text-muted"><input type="checkbox" checked={false} readOnly />Estoque (nunca copiado)</label></div><p className="mt-2 text-[10px] text-muted">O serializer V2.6 executa estas seções como uma única operação auditada; não aceita cópia parcial.</p></fieldset></div><div className="flex justify-end gap-2 border-t border-subtle px-5 py-4"><Button variant="secondary" onClick={() => setCopyOpen(null)}>Cancelar</Button><Button loading={busy} disabled={!copyTargets.length} onClick={() => void copyConfiguration()}>Copiar configuração</Button></div></Modal>

    <Modal open={duplicateOpen} title="Duplicar produto" description="Escolha apenas as relações que devem acompanhar a cópia." onClose={() => setDuplicateOpen(false)}><div className="grid gap-3 p-5 sm:grid-cols-2">{Object.entries({ composition: "Composição", fraction: "Configuração fracionável", branch_config: "Configuração e preços das filiais", destinations: "Destinos de produção", suppliers: "Fornecedores e apresentações" }).map(([key, label]) => <label key={key} className="flex items-center gap-3 rounded-md border border-subtle p-3 text-xs"><input type="checkbox" checked={duplicateOptions[key as keyof typeof duplicateOptions]} disabled={(key === "composition" && product.inventory_behavior !== "components") || (key === "fraction" && !product.fraction_config) || (key === "suppliers" && !permissions.changeSuppliers)} onChange={(event) => setDuplicateOptions((value) => ({ ...value, [key]: event.target.checked }))} />{label}</label>)}</div><div className="flex justify-end gap-2 border-t border-subtle px-5 py-4"><Button variant="secondary" onClick={() => setDuplicateOpen(false)}>Cancelar</Button><Button loading={busy} onClick={() => void duplicate()}>Criar cópia segura</Button></div></Modal>

    <Modal open={relationOpen} title={editingRelation ? "Editar fornecedor do produto" : "Vincular fornecedor"} onClose={() => setRelationOpen(false)}><form onSubmit={saveRelation}><div className="space-y-4 p-5"><Field label="Fornecedor" error={fieldError(fields, "supplier")}><Select required value={relationForm.supplier} disabled={!!editingRelation} onChange={(event) => setRelationForm((value) => ({ ...value, supplier: event.target.value }))}><option value="">Selecione</option>{suppliers.map((item) => <option key={item.id} value={item.id}>{item.trade_name || item.legal_name}</option>)}</Select></Field><Field label="Código no fornecedor" optional error={fieldError(fields, "supplier_code")}><Input value={relationForm.supplier_code} onChange={(event) => setRelationForm((value) => ({ ...value, supplier_code: event.target.value }))} /></Field><div className="grid gap-3 sm:grid-cols-2"><label className="flex items-center gap-2 text-xs font-semibold"><input type="checkbox" checked={relationForm.is_preferred} onChange={(event) => setRelationForm((value) => ({ ...value, is_preferred: event.target.checked }))} />Preferencial</label><label className="flex items-center gap-2 text-xs font-semibold"><input type="checkbox" checked={relationForm.is_exclusive} onChange={(event) => setRelationForm((value) => ({ ...value, is_exclusive: event.target.checked, is_preferred: event.target.checked || value.is_preferred }))} />Exclusivo</label></div></div><div className="flex justify-end gap-2 border-t border-subtle px-5 py-4"><Button type="button" variant="secondary" onClick={() => setRelationOpen(false)}>Cancelar</Button><Button type="submit" loading={busy}>Salvar vínculo</Button></div></form></Modal>

    <Modal open={unitOpen} title={editingUnit ? "Editar apresentação" : "Nova apresentação"} description={unitRelation?.supplier_name} onClose={() => setUnitOpen(false)}><form onSubmit={saveUnit}><div className="grid gap-4 p-5 sm:grid-cols-2">
      <div className="sm:col-span-2 rounded-md bg-surface-muted p-3 text-[11px] text-muted">Estoque: {product.unit.toUpperCase()}. A quantidade informa quantas unidades de estoque esta apresentação representa.</div>
      {editingUnit ? <>
        <Field label="Código da unidade" error={fieldError(fields, "unit_code")}><Input required value={unitForm.unit_code} onChange={(event) => setUnitForm((value) => ({ ...value, unit_code: event.target.value.toUpperCase() }))} /></Field>
        <Field label="Quantidade na unidade de estoque" error={fieldError(fields, "conversion_factor")}><Input required inputMode="decimal" min="0.000001" step="0.000001" value={unitForm.conversion_factor} onChange={(event) => setUnitForm((value) => ({ ...value, conversion_factor: event.target.value }))} /></Field>
        <Field label="Descrição da apresentação" error={fieldError(fields, "description")}><Input required maxLength={200} value={unitForm.description} onChange={(event) => setUnitForm((value) => ({ ...value, description: event.target.value }))} /></Field>
        <p className="self-end text-[11px] text-muted">Esta apresentação existente permanece editável sem exigir a migração para um preset.</p>
      </> : <>
        <Field label="Apresentação da empresa" error={fieldError(fields, "presentation_preset")}><Select value={unitForm.presentation_preset} onChange={(event) => setUnitForm((value) => ({ ...value, presentation_preset: event.target.value }))}><option value="">Criar nova apresentação</option>{presentationPresets.filter((preset) => preset.status === "active").map((preset) => <option key={preset.id} value={preset.id}>{preset.code} · {preset.name}</option>)}</Select></Field>
        {unitForm.presentation_preset ? <p className="self-end text-[11px] text-muted">O preset define o código, a descrição e a conversão desta apresentação.</p> : <>
          <Field label="Tipo de apresentação" error={fieldError(fields, "presentation_type")}><Select value={unitForm.presentation_type} onChange={(event) => setUnitForm((value) => ({ ...value, presentation_type: event.target.value as PresentationType }))}>{(Object.keys(presentationTypeLabels) as PresentationType[]).map((type) => <option key={type} value={type}>{type} · {presentationTypeLabels[type]}</option>)}</Select></Field>
          <Field label="Quantidade na unidade de estoque" error={fieldError(fields, "conversion_factor")}><Input required inputMode="decimal" min="0.000001" step="0.000001" value={unitForm.conversion_factor} onChange={(event) => setUnitForm((value) => ({ ...value, conversion_factor: event.target.value }))} /></Field>
          {unitForm.presentation_type === "OTHER" && <><Field label="Código personalizado" error={fieldError(fields, "custom_code")}><Input required maxLength={20} value={unitForm.custom_code} onChange={(event) => setUnitForm((value) => ({ ...value, custom_code: event.target.value.toUpperCase() }))} /></Field><Field label="Nome personalizado" error={fieldError(fields, "custom_name")}><Input required maxLength={100} value={unitForm.custom_name} onChange={(event) => setUnitForm((value) => ({ ...value, custom_name: event.target.value }))} /></Field></>}
          <label className="flex items-center gap-2 text-xs font-semibold sm:col-span-2"><input type="checkbox" checked={unitForm.save_as_preset} onChange={(event) => setUnitForm((value) => ({ ...value, save_as_preset: event.target.checked }))} />Salvar como preset da empresa</label>
        </>}
        <div className="rounded-md bg-surface-muted p-3 text-[11px] sm:col-span-2"><strong>Prévia:</strong> {unitForm.presentation_preset ? (() => { const preset = presentationPresets.find((item) => item.id === Number(unitForm.presentation_preset)); return `${preset?.code || "-"} · ${preset?.description || preset?.name || "-"} · conversão ${formatQuantity(preset?.conversion_factor || "1")} ${product.unit.toUpperCase()}`; })() : `${unitForm.presentation_type === "OTHER" ? unitForm.custom_code || "código" : unitForm.presentation_type} · ${unitForm.presentation_type === "OTHER" ? unitForm.custom_name || "nome" : presentationTypeLabels[unitForm.presentation_type]} · conversão ${formatQuantity(unitForm.conversion_factor || "0")} ${product.unit.toUpperCase()}`}</div>
      </>}
      <Field label="Código de barras" optional error={fieldError(fields, "barcode")}><Input value={unitForm.barcode} onChange={(event) => setUnitForm((value) => ({ ...value, barcode: event.target.value }))} /></Field>
      <label className="flex items-center gap-2 self-end text-xs font-semibold"><input type="checkbox" checked={unitForm.is_default} onChange={(event) => setUnitForm((value) => ({ ...value, is_default: event.target.checked }))} />Apresentação padrão</label>
    </div><div className="flex justify-end gap-2 border-t border-subtle px-5 py-4"><Button type="button" variant="secondary" onClick={() => setUnitOpen(false)}>Cancelar</Button><Button type="submit" loading={busy}>Salvar apresentação</Button></div></form></Modal>
  </div>;
}
