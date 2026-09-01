"use client";

import { useState } from "react";
import { Alert, Button, Field, Input, Modal } from "@/components/ui";
import { decimalIsZero, formatDecimalBRL, formatQuantity } from "@/lib/format";
import { centsToDecimal, modifierContributionCents, quantityToThousandths, thousandthsToDecimal } from "@/lib/sales";
import type { ModifierGroup, ModifierSelection, Product } from "@/types";

type Props = {
  product: Product;
  onClose: () => void;
  onConfirm: (selections: ModifierSelection[]) => void;
};

export function ModifierPicker({ product, onClose, onConfirm }: Props) {
  const groups = (product.modifier_groups || []).filter((group) => group.status === "active");
  const [quantities, setQuantities] = useState<Record<number, string>>({});
  const [error, setError] = useState("");

  function selectedFor(group: ModifierGroup) {
    return (group.options || []).filter((option) => quantities[option.id] !== undefined);
  }

  function selectedTotal(group: ModifierGroup) {
    let total = BigInt(0);
    for (const option of selectedFor(group)) {
      const quantity = quantityToThousandths(quantities[option.id]);
      if (quantity === null) return null;
      total += quantity;
    }
    return total;
  }

  function selectedCount(group: ModifierGroup) {
    return selectedFor(group).length;
  }

  function toggle(optionId: number, checked: boolean) {
    setError("");
    setQuantities((current) => {
      const next = { ...current };
      if (checked) next[optionId] = "1";
      else delete next[optionId];
      return next;
    });
  }

  function confirm() {
    for (const group of groups) {
      if (selectedFor(group).some((option) => {
        const quantity = quantityToThousandths(quantities[option.id]);
        return quantity === null || quantity <= BigInt(0);
      })) {
        setError(`Informe uma quantidade positiva para as opções de ${group.name}.`);
        return;
      }
      const total = selectedTotal(group);
      const count = selectedCount(group);
      if (group.is_required && !count) {
        setError(`${group.name} é obrigatório.`);
        return;
      }
      if (group.required_quantity != null) {
        const required = quantityToThousandths(group.required_quantity);
        if (total === null || required === null || total !== required) {
          setError(
            `${group.name} exige ${formatQuantity(group.required_quantity)} unidade(s); recebido ${total === null ? "-" : formatQuantity(thousandthsToDecimal(total))}.`,
          );
          return;
        }
      } else {
        if (group.min_selections && count < group.min_selections) {
          setError(`${group.name} exige no mínimo ${group.min_selections} opções distintas.`);
          return;
        }
        if (group.max_selections !== null && count > group.max_selections) {
          setError(`${group.name} permite no máximo ${group.max_selections} opções distintas.`);
          return;
        }
        if (group.allow_option_quantity) {
          const minimumTotal = quantityToThousandths(group.min_total_quantity);
          const maximumTotal = group.max_total_quantity === null
            ? null
            : quantityToThousandths(group.max_total_quantity);
          if (total === null || minimumTotal === null || (minimumTotal > BigInt(0) && total < minimumTotal)) {
            setError(`${group.name} exige quantidade total mínima de ${formatQuantity(group.min_total_quantity)}.`);
            return;
          }
          if (
            group.max_total_quantity !== null
            && (maximumTotal === null || total === null || total > maximumTotal)
          ) {
            setError(`${group.name} permite quantidade total máxima de ${formatQuantity(group.max_total_quantity!)}.`);
            return;
          }
        }
      }
    }
    onConfirm(
      groups.flatMap((group) => selectedFor(group).map((option) => ({
        option: option.id,
        quantity: quantities[option.id].replace(",", "."),
      }))),
    );
  }

  const additional = groups.flatMap((group) => selectedFor(group)).reduce<bigint | null>(
    (total, option) => {
      if (total === null) return null;
      const contribution = modifierContributionCents(
        option.additional_price, quantities[option.id],
      );
      return contribution === null ? null : total + contribution;
    },
    BigInt(0),
  );

  return <Modal open title={`Configurar ${product.name}`} description="O valor final é confirmado pelo servidor." onClose={onClose} size="lg">
    <div className="max-h-[65vh] space-y-4 overflow-y-auto p-5">
      {groups.map((group) => {
        const distinctRule = group.min_selections || group.max_selections !== null
          ? `${group.min_selections ? `Mínimo ${group.min_selections} opções distintas` : "Opções distintas livres"}${group.max_selections !== null ? ` · Máximo ${group.max_selections} opções distintas` : ""}`
          : "";
        const totalRule = group.allow_option_quantity && (
          !decimalIsZero(group.min_total_quantity) || group.max_total_quantity !== null
        )
          ? `${!decimalIsZero(group.min_total_quantity) ? `Mínimo total ${formatQuantity(group.min_total_quantity)}` : "Total livre"}${group.max_total_quantity !== null ? ` · Máximo total ${formatQuantity(group.max_total_quantity)}` : ""}`
          : "";
        const rule = group.required_quantity
          ? `Distribua exatamente ${formatQuantity(group.required_quantity)} unidades`
          : [distinctRule, totalRule].filter(Boolean).join(" · ") || "Opcional";
        return <section key={group.id} className="rounded-lg border border-subtle p-4">
          <div className="mb-3 flex items-start justify-between gap-3"><div><h3 className="text-sm font-bold">{group.name}</h3><p className="mt-1 text-[11px] text-muted">{rule}{group.is_required ? " · Obrigatório" : ""}</p></div><span className="text-xs font-semibold text-primary">{selectedTotal(group) === null ? "-" : formatQuantity(thousandthsToDecimal(selectedTotal(group)!))}{group.required_quantity ? `/${formatQuantity(group.required_quantity)}` : ""}</span></div>
          <div className="space-y-2">{(group.options || []).filter((option) => option.status === "active").map((option) => {
            const selected = quantities[option.id] !== undefined;
            return <div key={option.id} className="flex items-center gap-3 rounded-md border border-subtle p-3"><input type="checkbox" className="size-4 accent-primary" checked={selected} onChange={(event) => toggle(option.id, event.target.checked)} /><div className="min-w-0 flex-1"><strong className="block text-xs">{option.name}</strong><span className="text-[11px] text-muted">{option.option_type === "observation" ? "Observação" : option.option_type === "remove" ? "Remover" : "Adicionar"}{!decimalIsZero(option.additional_price) ? ` · +${formatDecimalBRL(option.additional_price)}` : ""}</span></div>{selected && group.allow_option_quantity && <Field label="Qtd."><Input className="h-8 w-20 text-center" inputMode="decimal" value={quantities[option.id]} onChange={(event) => { setError(""); setQuantities((current) => ({ ...current, [option.id]: event.target.value })); }} /></Field>}</div>;
          })}</div>
        </section>;
      })}
      {error && <Alert message={error} />}
    </div>
    <div className="flex items-center justify-between gap-3 border-t border-subtle px-5 py-4"><div className="text-xs text-muted">Adicionais: <strong className="text-fg">{additional === null ? "-" : formatDecimalBRL(centsToDecimal(additional))}</strong></div><div className="flex gap-2"><Button variant="secondary" onClick={onClose}>Cancelar</Button><Button onClick={confirm}>Adicionar ao carrinho</Button></div></div>
  </Modal>;
}
