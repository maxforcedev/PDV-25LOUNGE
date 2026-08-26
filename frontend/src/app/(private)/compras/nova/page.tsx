"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Plus, Trash2 } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import {
  Alert,
  Button,
  Field,
  Input,
  MoneyInput,
  Select,
  Textarea,
} from "@/components/ui";
import { formatBRL } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import {
  centsText,
  lineTotalCents,
  moneyCents,
  purchaseTypeLabels,
  validatePurchaseAttachmentFile,
} from "@/lib/purchases";
import { useAuth } from "@/providers/auth-provider";
import type {
  ProductSupplier,
  ProductSupplierUnit,
  PurchaseOrder,
  PurchaseOrderType,
  Supplier,
} from "@/types";

type Line = { unit: string; quantity: string; price: string };
type Installment = { amount: string; due_date: string; notes: string };
const emptyLine = (): Line => ({ unit: "", quantity: "1", price: "" });

function NewPurchase() {
  const router = useRouter();
  const { currentBranch, currentCompany, hasPermission, supportSession } =
    useAuth();
  const companyId = currentCompany?.id;
  const branchId = currentBranch?.id;
  const readOnly = supportSession?.mode === "READ_ONLY";
  const canManagePayables =
    hasPermission(permissions.managePurchasePayables) && !readOnly;
  const [supplier, setSupplier] = useState("");
  const [type, setType] = useState<PurchaseOrderType>("ORDER");
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [relations, setRelations] = useState<ProductSupplier[]>([]);
  const [units, setUnits] = useState<ProductSupplierUnit[]>([]);
  const [lines, setLines] = useState<Line[]>([emptyLine()]);
  const [discount, setDiscount] = useState("0.00");
  const [freight, setFreight] = useState("0.00");
  const [expenses, setExpenses] = useState("0.00");
  const [documentNumber, setDocumentNumber] = useState("");
  const [documentKey, setDocumentKey] = useState("");
  const [documentSeries, setDocumentSeries] = useState("");
  const [documentDate, setDocumentDate] = useState("");
  const [attachmentFile, setAttachmentFile] = useState<File | null>(null);
  const [attachmentError, setAttachmentError] = useState("");
  const [notes, setNotes] = useState("");
  const [installments, setInstallments] = useState<Installment[]>([]);
  const [loadingOptions, setLoadingOptions] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const context = useRef("");
  context.current = `${currentCompany?.id || ""}:${currentBranch?.id || ""}`;

  const relationById = useMemo(
    () => new Map(relations.map((item) => [item.id, item])),
    [relations],
  );
  const grossCents = lines.reduce(
    (total, line) => total + lineTotalCents(line.quantity, line.price),
    BigInt(0),
  );
  const payableCents =
    grossCents -
    moneyCents(discount) +
    moneyCents(freight) +
    moneyCents(expenses);
  const installmentCents = installments.reduce(
    (total, item) => total + moneyCents(item.amount),
    BigInt(0),
  );

  useEffect(() => {
    const key = context.current;
    setSupplier("");
    setRelations([]);
    setUnits([]);
    setLines([emptyLine()]);
    setError("");
    if (!companyId || !branchId) {
      setLoadingOptions(false);
      return;
    }
    setLoadingOptions(true);
    http
      .getAll<Supplier>(`suppliers/?company=${companyId}&status=active`)
      .then((items) => {
        if (context.current === key) setSuppliers(items);
      })
      .catch((caught) => {
        if (context.current === key)
          setError(
            caught instanceof ApiError
              ? caught.message
              : "Não foi possível carregar os fornecedores.",
          );
      })
      .finally(() => {
        if (context.current === key) setLoadingOptions(false);
      });
  }, [companyId, branchId]);

  useEffect(() => {
    const key = context.current;
    setRelations([]);
    setUnits([]);
    setLines([emptyLine()]);
    if (!supplier || !companyId) return;
    setLoadingOptions(true);
    Promise.all([
      http.getAll<ProductSupplier>(
        `product-suppliers/?company=${companyId}&supplier=${supplier}&status=active`,
      ),
      http.getAll<ProductSupplierUnit>(
        `product-supplier-units/?company=${companyId}&supplier=${supplier}&status=active`,
      ),
    ])
      .then(([nextRelations, nextUnits]) => {
        if (context.current === key) {
          setRelations(nextRelations);
          setUnits(
            nextUnits.filter((unit) =>
              nextRelations.some(
                (relation) => relation.id === unit.product_supplier,
              ),
            ),
          );
        }
      })
      .catch((caught) => {
        if (context.current === key)
          setError(
            caught instanceof ApiError
              ? caught.message
              : "Não foi possível carregar as apresentações do fornecedor.",
          );
      })
      .finally(() => {
        if (context.current === key) setLoadingOptions(false);
      });
  }, [supplier, companyId]);

  function updateLine(index: number, patch: Partial<Line>) {
    setLines((current) =>
      current.map((line, position) =>
        position === index ? { ...line, ...patch } : line,
      ),
    );
  }
  function addInstallment() {
    setInstallments((current) => [
      ...current,
      {
        amount: current.length
          ? ""
          : centsText(payableCents > BigInt(0) ? payableCents : BigInt(0)),
        due_date: "",
        notes: "",
      },
    ]);
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

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!currentBranch || readOnly) return;
    const selectedUnits = lines.map((line) => Number(line.unit));
    if (new Set(selectedUnits).size !== selectedUnits.length) {
      setError("Não repita a mesma apresentação na compra.");
      return;
    }
    if (payableCents < BigInt(0)) {
      setError("O desconto não pode exceder o valor bruto.");
      return;
    }
    if (installments.length && installmentCents !== payableCents) {
      setError(
        `A soma das parcelas deve ser ${formatBRL(centsText(payableCents))}.`,
      );
      return;
    }
    setSaving(true);
    setError("");
    try {
      const order = await http.post<PurchaseOrder>("purchase-orders/", {
        branch: currentBranch.id,
        supplier: Number(supplier),
        order_type: type,
        items: lines.map((line) => {
          const unit = units.find((item) => item.id === Number(line.unit))!;
          return {
            product: relationById.get(unit.product_supplier)?.product,
            product_supplier_unit: unit.id,
            ordered_quantity: line.quantity,
            purchase_unit_price: line.price,
          };
        }),
        global_discount: centsText(moneyCents(discount)),
        freight_total: centsText(moneyCents(freight)),
        other_expenses_total: centsText(moneyCents(expenses)),
        document_number: documentNumber.trim(),
        document_key: documentKey.trim(),
        document_series: documentSeries.trim(),
        document_date: documentDate || null,
        notes: notes.trim(),
        ...(installments.length
          ? {
              installments: installments.map((item) => ({
                ...item,
                amount: centsText(moneyCents(item.amount)),
                notes: item.notes.trim(),
              })),
            }
          : {}),
      });
      let attachmentFailed = false;
      if (attachmentFile) {
        const body = new FormData();
        body.append("attachment", attachmentFile);
        try {
          await http.postForm<PurchaseOrder>(
            `purchase-orders/${order.id}/attachment/`,
            body,
          );
        } catch {
          attachmentFailed = true;
        }
      }
      const query = new URLSearchParams();
      if (type === "DIRECT") query.set("receive", "1");
      if (attachmentFailed) query.set("attachment", "failed");
      router.push(`/compras/${order.id}${query.size ? `?${query}` : ""}`);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Não foi possível criar a compra.",
      );
      setSaving(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Nova compra"
        description={`${currentBranch?.name || "Selecione uma filial"} · os itens serão snapshotados pelo backend.`}
        action={
          <Link href="/compras" className="btn btn-secondary">
            <ArrowLeft className="size-4" />
            Voltar
          </Link>
        }
      />
      <form className="space-y-4 p-4 sm:p-6 lg:p-8" onSubmit={submit}>
        {error && <Alert message={error} />}
        <section className="card grid gap-4 p-5 sm:grid-cols-2">
          <Field label="Filial">
            <Input value={currentBranch?.name || "Sem filial ativa"} readOnly />
          </Field>
          <Field label="Tipo">
            <Select
              value={type}
              onChange={(event) =>
                setType(event.target.value as PurchaseOrderType)
              }
              disabled={saving || readOnly}
            >
              {Object.entries(purchaseTypeLabels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Fornecedor">
            <Select
              required
              value={supplier}
              onChange={(event) => setSupplier(event.target.value)}
              disabled={saving || loadingOptions || readOnly}
            >
              <option value="">Selecione um fornecedor ativo</option>
              {suppliers.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.trade_name}
                </option>
              ))}
            </Select>
          </Field>
          <div className="rounded-md bg-info-surface p-3 text-xs text-info-strong">
            {type === "DIRECT"
              ? "A entrada direta será criada em rascunho e seguirá para o mesmo fluxo de recebimento integral."
              : "O pedido deverá ser realizado antes de receber mercadorias."}
          </div>
        </section>

        <section className="card overflow-hidden">
          <div className="card-header">
            <div>
              <h2 className="text-sm font-bold">Itens</h2>
              <p className="mt-1 text-[11px] text-muted">
                Somente relações e apresentações ativas do fornecedor.
              </p>
            </div>
            <Button
              type="button"
              variant="secondary"
              onClick={() => setLines((current) => [...current, emptyLine()])}
              disabled={!supplier || !units.length || saving}
            >
              <Plus className="size-4" />
              Item
            </Button>
          </div>
          <div className="space-y-3 p-4">
            {lines.map((line, index) => {
              const selected = units.find(
                (item) => item.id === Number(line.unit),
              );
              return (
                <div
                  key={index}
                  className="grid gap-3 rounded-lg border border-subtle p-3 md:grid-cols-[minmax(15rem,1fr)_9rem_10rem_8rem_auto] md:items-end"
                >
                  <Field label={`Apresentação ${index + 1}`}>
                    <Select
                      required
                      value={line.unit}
                      onChange={(event) =>
                        updateLine(index, { unit: event.target.value })
                      }
                      disabled={!supplier || loadingOptions || saving}
                    >
                      <option value="">Selecione</option>
                      {units.map((unit) => (
                        <option
                          key={unit.id}
                          value={unit.id}
                          disabled={lines.some(
                            (other, position) =>
                              position !== index &&
                              other.unit === String(unit.id),
                          )}
                        >
                          {unit.product_name} · {unit.unit_code} /{" "}
                          {unit.description} ({unit.conversion_factor} un.)
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field label="Quantidade">
                    <Input
                      required
                      inputMode="decimal"
                      pattern="\d+([.,]\d{1,6})?"
                      value={line.quantity}
                      onChange={(event) =>
                        updateLine(index, {
                          quantity: event.target.value.replace(",", "."),
                        })
                      }
                      disabled={saving}
                    />
                  </Field>
                  <Field label="Preço de compra">
                    <Input
                      required
                      inputMode="decimal"
                      pattern="\d+([.,]\d{1,6})?"
                      value={line.price}
                      onChange={(event) =>
                        updateLine(index, {
                          price: event.target.value.replace(",", "."),
                        })
                      }
                      disabled={saving}
                    />
                  </Field>
                  <div>
                    <span className="label">Subtotal</span>
                    <strong className="block h-10 rounded-md bg-surface-muted px-3 py-2.5 text-sm">
                      {formatBRL(
                        centsText(lineTotalCents(line.quantity, line.price)),
                      )}
                    </strong>
                  </div>
                  <button
                    type="button"
                    className="icon-button"
                    aria-label={`Remover item ${index + 1}`}
                    onClick={() =>
                      setLines((current) =>
                        current.filter((_, position) => position !== index),
                      )
                    }
                    disabled={lines.length === 1 || saving}
                  >
                    <Trash2 className="size-4" />
                  </button>
                  {selected && (
                    <p className="text-[10px] text-muted md:col-span-5">
                      Conversão: {selected.conversion_factor} unidades de
                      estoque por {selected.unit_code}.
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </section>

        <div className="grid gap-4 xl:grid-cols-[1fr_24rem]">
          <section className="card grid gap-4 p-5 sm:grid-cols-3">
            <Field label="Número do documento" optional>
              <Input
                maxLength={100}
                value={documentNumber}
                onChange={(event) => setDocumentNumber(event.target.value)}
                disabled={saving}
              />
            </Field>
            <Field label="Série" optional>
              <Input
                maxLength={30}
                value={documentSeries}
                onChange={(event) => setDocumentSeries(event.target.value)}
                disabled={saving}
              />
            </Field>
            <Field label="Data do documento" optional>
              <Input
                type="date"
                value={documentDate}
                onChange={(event) => setDocumentDate(event.target.value)}
                disabled={saving}
              />
            </Field>
            <Field label="Chave do documento" optional>
              <Input
                className="sm:col-span-2"
                maxLength={100}
                value={documentKey}
                onChange={(event) => setDocumentKey(event.target.value)}
                disabled={saving}
              />
            </Field>
            <div className="sm:col-span-2">
              <Field label="Anexo" optional error={attachmentError}>
                <Input
                  type="file"
                  accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
                  disabled={saving}
                  onChange={(event) =>
                    void chooseAttachment(event.target.files?.[0] || null)
                  }
                />
                <span className="mt-1 block text-[10px] text-muted">
                  PDF, JPG ou PNG, nome seguro e até 10 MB. O envio ocorre após
                  a criação da compra.
                </span>
              </Field>
            </div>
            <div className="sm:col-span-3">
              <Field label="Observações" optional>
                <Textarea
                  rows={3}
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                  disabled={saving}
                />
              </Field>
            </div>
          </section>
          <section className="card space-y-4 p-5">
            <h2 className="text-sm font-bold">Totais exatos</h2>
            <Field label="Desconto global">
              <MoneyInput
                value={discount}
                onValueChange={setDiscount}
                disabled={saving}
              />
            </Field>
            <Field label="Frete">
              <MoneyInput
                value={freight}
                onValueChange={setFreight}
                disabled={saving}
              />
            </Field>
            <Field label="Outras despesas">
              <MoneyInput
                value={expenses}
                onValueChange={setExpenses}
                disabled={saving}
              />
            </Field>
            <dl className="space-y-2 border-t border-subtle pt-4 text-sm">
              <div className="flex justify-between">
                <dt className="text-muted">Bruto</dt>
                <dd>{formatBRL(centsText(grossCents))}</dd>
              </div>
              <div className="flex justify-between text-base font-extrabold">
                <dt>Total a pagar</dt>
                <dd>{formatBRL(centsText(payableCents))}</dd>
              </div>
            </dl>
          </section>
        </div>

        {canManagePayables && (
          <section className="card overflow-hidden">
            <div className="card-header">
              <div>
                <h2 className="text-sm font-bold">Parcelas</h2>
                <p className="mt-1 text-[11px] text-muted">
                  Opcional. A soma deve reconciliar exatamente com o total a
                  pagar.
                </p>
              </div>
              <Button
                type="button"
                variant="secondary"
                onClick={addInstallment}
                disabled={saving}
              >
                <Plus className="size-4" />
                Parcela
              </Button>
            </div>
            <div className="space-y-3 p-4">
              {installments.length ? (
                installments.map((item, index) => (
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
                      onClick={() =>
                        setInstallments((current) =>
                          current.filter((_, position) => position !== index),
                        )
                      }
                    >
                      <Trash2 className="size-4" />
                    </button>
                  </div>
                ))
              ) : (
                <p className="text-xs text-muted">
                  Nenhuma parcela será criada.
                </p>
              )}{" "}
              {installments.length > 0 && (
                <p
                  className={`text-right text-xs font-bold ${installmentCents === payableCents ? "text-success-strong" : "text-danger-strong"}`}
                >
                  Parcelas: {formatBRL(centsText(installmentCents))} de{" "}
                  {formatBRL(centsText(payableCents))}
                </p>
              )}
            </div>
          </section>
        )}
        <div className="flex justify-end gap-2">
          <Link href="/compras" className="btn btn-secondary">
            Cancelar
          </Link>
          <Button
            type="submit"
            loading={saving}
            disabled={
              !currentBranch ||
              !supplier ||
              !units.length ||
              payableCents < BigInt(0) ||
              readOnly
            }
          >
            Criar compra
          </Button>
        </div>
      </form>
    </>
  );
}

export default function NewPurchasePage() {
  return (
    <AdminGuard requiredPermissions={[permissions.createPurchase]}>
      <NewPurchase />
    </AdminGuard>
  );
}
