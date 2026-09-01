"use client";

import { useEffect, useRef, useState } from "react";
import { Search, X } from "lucide-react";
import { Spinner } from "@/components/ui";
import { ApiError, http } from "@/lib/http";
import type { Paginated, Product } from "@/types";

type ProductAutocompleteProps = {
  companyId?: number;
  branchId?: number;
  value: Product | null;
  onChange: (product: Product | null) => void;
  disabled?: boolean;
  placeholder?: string;
  onError?: (message: string) => void;
  optionsEndpoint?: string;
};

export function ProductAutocomplete({
  companyId,
  branchId,
  value,
  onChange,
  disabled = false,
  placeholder = "Buscar por nome, código, SKU ou código de barras",
  onError,
  optionsEndpoint,
}: ProductAutocompleteProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Product[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const requestRef = useRef(0);

  useEffect(() => {
    const term = query.trim();
    if (!term || !companyId || !branchId) {
      setResults([]);
      setNext(null);
      setLoading(false);
      return;
    }
    const requestId = ++requestRef.current;
    const timer = window.setTimeout(() => {
      setLoading(true);
      const params = new URLSearchParams({
        company: String(companyId),
        branch: String(branchId),
        inventory_behavior: "direct",
        status: "active",
        search: term,
        page: String(page),
        page_size: "20",
      });
      const request = optionsEndpoint
        ? http.get<{ products: Product[] }>(`${optionsEndpoint}?search=${encodeURIComponent(term)}`)
            .then((response) => ({ results: response.products, next: null }))
        : http.get<Paginated<Product>>(`products/?${params}`);
      void request
        .then((response) => {
          if (requestRef.current !== requestId) return;
          setResults((current) =>
            page === 1 ? response.results : [...current, ...response.results],
          );
          setNext(response.next);
        })
        .catch((caught) => {
          if (requestRef.current !== requestId) return;
          setResults([]);
          setNext(null);
          onError?.(
            caught instanceof ApiError
              ? caught.message
              : "Não foi possível pesquisar os produtos.",
          );
        })
        .finally(() => {
          if (requestRef.current === requestId) setLoading(false);
        });
    }, 300);
    return () => window.clearTimeout(timer);
  }, [branchId, companyId, onError, optionsEndpoint, page, query]);

  function search(value: string) {
    setQuery(value);
    setPage(1);
    setOpen(true);
  }

  return (
    <div className="relative">
      {value ? (
        <div className="flex min-h-10 items-center justify-between gap-3 rounded-md border border-subtle bg-surface px-3 py-2 text-sm">
          <span className="min-w-0">
            <strong className="block truncate">{value.name}</strong>
            <span className="block truncate text-[11px] text-muted">
              {value.internal_code}{value.sku ? ` · ${value.sku}` : ""}{value.barcode ? ` · ${value.barcode}` : ""}
            </span>
          </span>
          <button
            type="button"
            className="icon-button shrink-0"
            aria-label="Trocar produto"
            disabled={disabled}
            onClick={() => {
              onChange(null);
              setOpen(true);
            }}
          >
            <X className="size-4" />
          </button>
        </div>
      ) : (
        <>
          <Search className="pointer-events-none absolute left-3 top-3 size-4 text-muted" />
          <input
            className="input w-full pl-9"
            value={query}
            disabled={disabled}
            placeholder={placeholder}
            onFocus={() => setOpen(true)}
            onChange={(event) => search(event.target.value)}
          />
        </>
      )}
      {open && !value && (
        <div className="absolute z-30 mt-1 max-h-72 w-full overflow-y-auto rounded-md border border-subtle bg-surface shadow-lg">
          {!query.trim() ? (
            <p className="p-3 text-xs text-muted">Digite para pesquisar produtos sem carregar o catálogo completo.</p>
          ) : loading && !results.length ? (
            <div className="flex justify-center p-4"><Spinner className="size-5" /></div>
          ) : results.length ? (
            <>
              {results.map((product) => (
                <button
                  key={product.id}
                  type="button"
                  className="block w-full border-b border-subtle p-3 text-left last:border-b-0 hover:bg-surface-muted"
                  onClick={() => {
                    onChange(product);
                    setQuery("");
                    setResults([]);
                    setOpen(false);
                  }}
                >
                  <strong className="block text-sm">{product.name}</strong>
                  <span className="block text-[11px] text-muted">
                    {product.internal_code}{product.sku ? ` · ${product.sku}` : ""}{product.barcode ? ` · ${product.barcode}` : ""}
                  </span>
                </button>
              ))}
              {next && (
                <button
                  type="button"
                  className="w-full p-3 text-xs font-bold text-primary hover:bg-surface-muted"
                  disabled={loading}
                  onClick={() => setPage((current) => current + 1)}
                >
                  {loading ? "Carregando..." : "Mostrar mais produtos"}
                </button>
              )}
            </>
          ) : (
            <p className="p-3 text-xs text-muted">Nenhum produto encontrado.</p>
          )}
        </div>
      )}
    </div>
  );
}
