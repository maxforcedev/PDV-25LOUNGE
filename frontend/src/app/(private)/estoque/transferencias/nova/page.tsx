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
import { contentUnitLabel, isUnitQuantityValid, physicalQuantityDisplay, quantityInputMode } from "@/lib/inventory";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { StockTransfer, TransferWorkflowOptions } from "@/types";

type Row = { product: string; quantity: string };

function NewTransfer() {
  const router = useRouter();
  const { currentBranch, supportSession } = useAuth();
  const [options, setOptions] = useState<TransferWorkflowOptions | null>(null);
  const [destination, setDestination] = useState("");
  const [notes, setNotes] = useState("");
  const [rows, setRows] = useState<Row[]>([{ product: "", quantity: "" }]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const [saving, setSaving] = useState(false);
  const branchId = currentBranch?.id;
  const readOnly = supportSession?.mode === "READ_ONLY";
  const destinations = options?.destination_branches ?? [];

  useEffect(() => {
    let active = true;
    setOptions(null);
    setDestination("");
    setRows([{ product: "", quantity: "" }]);
    setNotes("");
    setError("");
    if (!branchId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    void http
      .get<TransferWorkflowOptions>("stock-transfers/options/")
      .then((response) => active && setOptions(response))
      .catch((caught) => active && setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as opções da transferência."))
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
      if (product && !isUnitQuantityValid(row.quantity, tracked ? "un" : product.unit)) {
        clientFields[`items.${index}.quantity`] = [tracked ? "Informe um número inteiro de embalagens fechadas." : product.unit.toLowerCase() === "un" ? "Informe uma quantidade inteira de unidades." : "Informe uma quantidade positiva com até 3 casas decimais."];
      }
    });
    if (Object.keys(clientFields).length) {
      setFields(clientFields);
      setError("Revise as quantidades informadas.");
      return;
    }
    setSaving(true);
    setError("");
    setFields({});
    try {
      const transfer = await http.post<StockTransfer>("stock-transfers/", {
        origin_branch: currentBranch.id,
        destination_branch: Number(destination),
        notes,
        items: rows.map((row) => ({ product: Number(row.product), quantity: row.quantity.replace(",", ".") })),
      });
      router.push(`/estoque/transferencias/${transfer.id}`);
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setFields(caught.fields);
      } else setError("Não foi possível criar a transferência.");
      setSaving(false);
    }
  }

  return <>
    <PageHeader title="Nova transferência" description={`${currentBranch?.name || "Selecione uma filial"} será a origem.`} action={<Link href="/estoque/transferencias" className="btn btn-secondary"><ArrowLeft className="size-4" />Voltar</Link>} />
    <InventoryNav />
    <div className="p-4 sm:p-6 lg:p-8">
      <form className="mx-auto max-w-4xl space-y-4" onSubmit={submit}>
        {error && <Alert message={error} />}
        <section className="card p-5 sm:p-6">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Origem"><Input readOnly value={options?.origin_branch.name || currentBranch?.name || "Sem filial ativa"} /></Field>
            <Field label="Destino" error={fieldError(fields, "destination_branch")}>
              <Select required value={destination} onChange={(event) => setDestination(event.target.value)} disabled={readOnly || loading}>
                <option value="">Selecione uma filial elegível</option>
                {destinations.map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}
              </Select>
            </Field>
          </div>
          <div className="mt-4"><Field label="Observações" optional error={fieldError(fields, "notes")}><Textarea value={notes} onChange={(event) => setNotes(event.target.value)} disabled={readOnly} /></Field></div>
        </section>
        <section className="card overflow-hidden">
          <div className="card-header"><div><h2 className="text-sm font-bold">Produtos</h2><p className="mt-1 text-[11px] text-muted">Transferências aceitam somente embalagens fechadas inteiras para produtos em UN; conteúdo residual permanece na origem.</p></div><Button type="button" variant="secondary" onClick={() => setRows((value) => [...value, { product: "", quantity: "" }])} disabled={readOnly || loading}><Plus className="size-4" />Adicionar</Button></div>
          <div className="space-y-3 p-4 sm:p-6">
            {rows.map((row, index) => {
              const product = options?.stocks.find((item) => String(item.product) === row.product);
              const tracked = product?.current_content != null && product.package_content && product.content_unit;
              const balance = product ? physicalQuantityDisplay({ quantity: product.current_quantity, unit: product.unit, content: product.current_content, packageContent: product.package_content, contentUnit: product.content_unit, completePackages: product.complete_packages, residualContent: product.residual_content }) : null;
              return <div key={index} className="grid gap-3 rounded-lg border border-subtle p-3 sm:grid-cols-[1fr_180px_auto]">
                <Field label={`Produto ${index + 1}`} error={fieldError(fields, `items.${index}.product`)}>
                  <Select required value={row.product} onChange={(event) => update(index, { product: event.target.value, quantity: "" })} disabled={readOnly || loading}>
                    <option value="">Selecione</option>
                    {options?.stocks.filter((item) => !rows.some((other, position) => position !== index && other.product === String(item.product))).map((item) => <option key={item.stock} value={item.product}>{item.product_name} ({item.internal_code})</option>)}
                  </Select>
                </Field>
                <Field label={tracked ? "Embalagens fechadas" : `Quantidade${product ? ` (${product.unit.toUpperCase()})` : ""}`} error={fieldError(fields, `items.${index}.quantity`)}>
                  <Input required inputMode={quantityInputMode(tracked ? "un" : product?.unit)} pattern={tracked ? "\d+" : undefined} step={tracked || product?.unit.toLowerCase() === "un" ? "1" : "0.001"} min={tracked ? "1" : "0.001"} value={row.quantity} onChange={(event) => update(index, { quantity: tracked ? event.target.value.replace(/\D/g, "") : event.target.value })} disabled={readOnly} />
                   {balance && <span className="mt-1 block text-[10px] text-muted">Saldo na origem: {balance}</span>}
                   {tracked && <span className="mt-1 block text-[10px] font-semibold text-warning-strong">Somente embalagens fechadas de {formatQuantity(product.package_content)} {contentUnitLabel(product.content_unit)}. O residual permanece na origem.</span>}
                </Field>
                <button type="button" className="icon-button self-end" title="Remover" disabled={rows.length === 1 || readOnly} onClick={() => setRows((value) => value.filter((_, position) => position !== index))}><Trash2 className="size-4" /></button>
              </div>;
            })}
          </div>
        </section>
        <div className="flex justify-end gap-2"><Link href="/estoque/transferencias" className="btn btn-secondary">Cancelar</Link><Button type="submit" loading={saving} disabled={readOnly || loading || !destination || rows.some((row) => !row.product || !row.quantity)}>Criar rascunho</Button></div>
      </form>
    </div>
  </>;
}

export default function NewTransferPage() {
  return <AdminGuard requiredPermissions={[permissions.createTransfer]}><NewTransfer /></AdminGuard>;
}
