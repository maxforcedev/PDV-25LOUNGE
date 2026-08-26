"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { AdminGuard } from "@/components/admin-guard";
import { InventoryNav } from "@/components/inventory-nav";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, Field, Input, Select, Textarea } from "@/components/ui";
import { fieldError, formatQuantity } from "@/lib/format";
import { contentUnitLabel, isExactContentValid, isUnitQuantityValid, physicalQuantityDisplay, quantityInputMode } from "@/lib/inventory";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { InventoryCount, InventoryWorkflowOptions } from "@/types";

type Row = { product: string; counted_quantity: string; counted_complete_packages: string; counted_residual_content: string; counted_at: string; observation: string };
function localNow() {
  const date = new Date();
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 19);
}
function emptyRow(): Row {
  return { product: "", counted_quantity: "", counted_complete_packages: "", counted_residual_content: "", counted_at: localNow(), observation: "" };
}

function NewCount() {
  const router = useRouter();
  const { currentBranch, supportSession } = useAuth();
  const [options, setOptions] = useState<InventoryWorkflowOptions | null>(null);
  const [observation, setObservation] = useState("");
  const [rows, setRows] = useState<Row[]>([emptyRow()]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const branchId = currentBranch?.id;
  const readOnly = supportSession?.mode === "READ_ONLY";

  useEffect(() => {
    let active = true;
    setOptions(null);
    setRows([emptyRow()]);
    setObservation("");
    setError("");
    if (!branchId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    void http.get<InventoryWorkflowOptions>("inventory-counts/options/")
      .then((response) => active && setOptions(response))
      .catch((caught) => active && setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as opções do inventário."))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [branchId]);

  function update(index: number, value: Partial<Row>) {
    setRows((current) => current.map((row, position) => position === index ? { ...row, ...value } : row));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!currentBranch || !options) return;
    const clientFields: Record<string, string[]> = {};
    rows.forEach((row, index) => {
      const product = options.stocks.find((item) => String(item.product) === row.product);
      const tracked = product?.current_content != null && product.package_content && product.content_unit;
      if (tracked) {
        if (!/^\d+$/.test(row.counted_complete_packages)) clientFields[`items.${index}.counted_complete_packages`] = ["Informe um número inteiro de embalagens completas."];
        if (!isExactContentValid(row.counted_residual_content || "0", true) || Number(row.counted_residual_content.replace(",", ".") || 0) >= Number(product.package_content)) clientFields[`items.${index}.counted_residual_content`] = [`Informe um residual entre zero e menos de ${formatQuantity(product.package_content)} ${contentUnitLabel(product.content_unit)}.`];
      } else if (product && !isUnitQuantityValid(row.counted_quantity, product.unit, true)) {
        clientFields[`items.${index}.counted_quantity`] = [product.unit.toLowerCase() === "un" ? "Informe uma quantidade inteira de unidades." : "Informe zero ou uma quantidade com até 3 casas decimais."];
      }
    });
    if (Object.keys(clientFields).length) {
      setFields(clientFields);
      setError("Revise as quantidades contadas.");
      return;
    }
    setSaving(true);
    setError("");
    setFields({});
    try {
      const count = await http.post<InventoryCount>("inventory-counts/", {
        branch: currentBranch.id,
        observation,
        items: rows.map((row) => {
          const product = options.stocks.find((item) => String(item.product) === row.product);
          const exact = product?.current_content != null && product.package_content && product.content_unit;
          return { product: Number(row.product), ...(exact ? { counted_complete_packages: Number(row.counted_complete_packages), counted_residual_content: (row.counted_residual_content || "0").replace(",", ".") } : { counted_quantity: row.counted_quantity.replace(",", ".") }), counted_at: new Date(row.counted_at).toISOString(), observation: row.observation };
        }),
      });
      router.push(`/estoque/inventarios/${count.id}`);
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setFields(caught.fields);
      } else setError("Não foi possível capturar a contagem.");
      setSaving(false);
    }
  }

  return <>
    <PageHeader title="Nova contagem física" description={`${currentBranch?.name || "Selecione uma filial"} · capture quantidade e horário observados.`} action={<Link href="/estoque/inventarios" className="btn btn-secondary"><ArrowLeft className="size-4" />Voltar</Link>} />
    <InventoryNav />
    <div className="p-4 sm:p-6 lg:p-8">
      <form className="mx-auto max-w-5xl space-y-4" onSubmit={submit}>
        {error && <Alert message={error} />}
        <section className="card p-5 sm:p-6"><Field label="Observação geral" error={fieldError(fields, "observation")}><Textarea required minLength={3} value={observation} onChange={(event) => setObservation(event.target.value)} disabled={readOnly} placeholder="Ex.: contagem física do fechamento" /></Field></section>
        <section className="card overflow-hidden">
          <div className="card-header"><div><h2 className="text-sm font-bold">Produtos contados</h2><p className="mt-1 text-[11px] text-muted">O teórico exibido vem das opções do fluxo; o servidor captura o valor autoritativo no horário informado.</p></div><Button type="button" variant="secondary" disabled={readOnly || loading} onClick={() => setRows((value) => [...value, emptyRow()])}><Plus className="size-4" />Adicionar</Button></div>
          <div className="space-y-3 p-4 sm:p-6">
            {rows.map((row, index) => {
              const product = options?.stocks.find((item) => String(item.product) === row.product);
              const theoretical = product ? physicalQuantityDisplay({ quantity: product.current_quantity, unit: product.unit, content: product.current_content, packageContent: product.package_content, contentUnit: product.content_unit, completePackages: product.complete_packages, residualContent: product.residual_content }) : null;
              const tracked = product?.current_content != null && product.package_content && product.content_unit;
              return <div key={index} className="rounded-lg border border-subtle p-4">
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-[1fr_150px_210px_auto]">
                   <Field label={`Produto ${index + 1}`} error={fieldError(fields, `items.${index}.product`)}><Select required value={row.product} onChange={(event) => update(index, { product: event.target.value, counted_quantity: "", counted_complete_packages: "", counted_residual_content: "" })} disabled={readOnly || loading}><option value="">Selecione</option>{options?.stocks.filter((item) => !rows.some((other, position) => position !== index && other.product === String(item.product))).map((item) => <option key={item.stock} value={item.product}>{item.product_name} ({item.internal_code})</option>)}</Select>{theoretical && <span className="mt-1 block text-[10px] text-muted">Teórico atual: {theoretical}</span>}</Field>
                   {tracked ? <div className="grid grid-cols-2 gap-2"><Field label="Embalagens completas" error={fieldError(fields, `items.${index}.counted_complete_packages`)}><Input required inputMode="numeric" pattern="\d+" min="0" step="1" value={row.counted_complete_packages} onChange={(event) => update(index, { counted_complete_packages: event.target.value.replace(/\D/g, "") })} disabled={readOnly} /></Field><Field label={`Residual (${contentUnitLabel(product.content_unit)})`} error={fieldError(fields, `items.${index}.counted_residual_content`)}><Input required inputMode="decimal" min="0" max={product.package_content || undefined} step="0.000000001" value={row.counted_residual_content} onChange={(event) => update(index, { counted_residual_content: event.target.value })} disabled={readOnly} /><span className="mt-1 block text-[10px] text-muted">Cada embalagem: {formatQuantity(product.package_content)} {contentUnitLabel(product.content_unit)}</span></Field></div> : <Field label={`Contagem${product ? ` (${product.unit.toUpperCase()})` : ""}`} error={fieldError(fields, `items.${index}.counted_quantity`)}><Input required inputMode={quantityInputMode(product?.unit)} step={product?.unit.toLowerCase() === "un" ? "1" : "0.001"} min="0" value={row.counted_quantity} onChange={(event) => update(index, { counted_quantity: event.target.value })} disabled={readOnly} /></Field>}
                  <Field label="Contado em" error={fieldError(fields, `items.${index}.counted_at`)}><Input required type="datetime-local" step="1" max={localNow()} value={row.counted_at} onChange={(event) => update(index, { counted_at: event.target.value })} disabled={readOnly} /></Field>
                  <button type="button" className="icon-button self-end" disabled={readOnly || rows.length === 1} onClick={() => setRows((value) => value.filter((_, position) => position !== index))}><Trash2 className="size-4" /></button>
                </div>
                <div className="mt-3"><Field label="Observação do item" optional error={fieldError(fields, `items.${index}.observation`)}><Input value={row.observation} onChange={(event) => update(index, { observation: event.target.value })} disabled={readOnly} /></Field></div>
              </div>;
            })}
          </div>
        </section>
        <div className="flex justify-end gap-2"><Link href="/estoque/inventarios" className="btn btn-secondary">Cancelar</Link><Button type="submit" loading={saving} disabled={readOnly || loading || rows.some((row) => { const product = options?.stocks.find((item) => String(item.product) === row.product); const tracked = product?.current_content != null && product.package_content && product.content_unit; return !row.product || (tracked ? row.counted_complete_packages === "" || row.counted_residual_content === "" : row.counted_quantity === ""); })}>Capturar inventário</Button></div>
      </form>
    </div>
  </>;
}

export default function NewCountPage() {
  return <AdminGuard requiredPermissions={[permissions.performInventoryCount]}><NewCount /></AdminGuard>;
}
