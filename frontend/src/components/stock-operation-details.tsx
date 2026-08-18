"use client";

import { useState } from "react";
import { Copy, ListFilter } from "lucide-react";

export function StockOperationDetails({ reference, count }: { reference: string; count: number }) {
  const [copied, setCopied] = useState(false);

  async function copyReference() {
    try {
      await navigator.clipboard.writeText(reference);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  return (
    <details className="mt-2 text-[11px] text-muted">
      <summary className="cursor-pointer font-semibold">Detalhes da operação</summary>
      <div className="mt-2 space-y-2 rounded-md border border-subtle bg-surface-muted p-2.5">
        <div>
          <span className="block text-[10px] uppercase tracking-wide">Referência técnica</span>
          <code className="break-all text-[10px]">{reference}</code>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn btn-secondary px-2 py-1 text-[10px]" onClick={() => void copyReference()}>
            <Copy className="size-3" />{copied ? "Copiada" : "Copiar referência"}
          </button>
          <a className="btn btn-secondary px-2 py-1 text-[10px]" href={`/estoque/movimentacoes?operation_reference=${encodeURIComponent(reference)}`}>
            <ListFilter className="size-3" />Ver {count} {count === 1 ? "movimento" : "movimentos"}
          </a>
        </div>
      </div>
    </details>
  );
}
