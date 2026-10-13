"use client";

import { CalendarRange, RefreshCw } from "lucide-react";
import { Button, Field, Select } from "@/components/ui";
import type { PeriodValue } from "@/lib/period";

type Category = { id: number; name: string };

export function DashboardToolbar({
  period,
  draftPeriod,
  presets,
  customOpen,
  category,
  categories,
  loading,
  updatedAt,
  onPreset,
  onToggleCustom,
  onDraftChange,
  onApplyCustom,
  onCategoryChange,
  onRefresh,
}: {
  period: PeriodValue;
  draftPeriod: PeriodValue;
  presets: ReadonlyArray<readonly [string, PeriodValue]>;
  customOpen: boolean;
  category: string;
  categories: Category[];
  loading: boolean;
  updatedAt?: string;
  onPreset: (value: PeriodValue) => void;
  onToggleCustom: () => void;
  onDraftChange: (value: PeriodValue) => void;
  onApplyCustom: () => void;
  onCategoryChange: (value: string) => void;
  onRefresh: () => void;
}) {
  const customSelected = !presets.some(
    ([, value]) => value.start === period.start && value.end === period.end,
  );

  return (
    <section className="card overflow-hidden">
      <div className="flex flex-col gap-5 p-5 sm:p-6 xl:flex-row xl:items-center xl:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-primary">
            <CalendarRange className="size-4" />
            <p className="text-[10px] font-extrabold uppercase tracking-[0.16em]">
              Filtros de análise
            </p>
          </div>
          <p className="mt-2 text-sm font-semibold text-fg">
            Período selecionado: {period.start.slice(0, 10).split("-").reverse().join("/")} a {period.end.slice(0, 10).split("-").reverse().join("/")}
          </p>
          <p className="mt-1 text-xs text-muted">
            {updatedAt ? `Dados operacionais atualizados em ${updatedAt}.` : "Atualize os dados para consultar o estado mais recente da filial."}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="rounded-full border border-subtle bg-surface-muted px-3 py-2 text-xs font-bold text-muted transition hover:border-focus/40 hover:text-link focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/20"
            onClick={onToggleCustom}
            aria-expanded={customOpen}
          >
            Personalizar período
          </button>
          <Button variant="secondary" onClick={onRefresh} loading={loading}>
            {!loading && <RefreshCw className="size-3.5" />}
            Atualizar
          </Button>
        </div>
      </div>
      <div className="border-t border-subtle bg-surface-muted/60 px-5 py-4 sm:px-6">
        <div className="flex flex-wrap items-center gap-2">
          {presets.map(([label, value]) => {
            const selected = value.start === period.start && value.end === period.end;
            return (
              <button
                key={label}
                type="button"
                aria-pressed={selected}
                className={`rounded-full px-3.5 py-2 text-xs font-bold transition focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/20 ${selected ? "bg-primary text-white shadow-sm" : "border border-subtle bg-surface text-muted hover:border-focus/40 hover:text-link"}`}
                onClick={() => onPreset(value)}
              >
                {label}
              </button>
            );
          })}
          <button
            type="button"
            aria-pressed={customOpen || customSelected}
            className={`rounded-full px-3.5 py-2 text-xs font-bold transition focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/20 ${customOpen || customSelected ? "bg-primary text-white shadow-sm" : "border border-subtle bg-surface text-muted hover:border-focus/40 hover:text-link"}`}
            onClick={onToggleCustom}
          >
            Personalizado
          </button>
          <div className="ml-auto min-w-48 max-sm:w-full">
            <Select
              aria-label="Filtrar por categoria"
              value={category}
              onChange={(event) => onCategoryChange(event.target.value)}
            >
              <option value="">Todas as categorias</option>
              {categories.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </Select>
          </div>
        </div>
        {customOpen && (
          <div className="mt-4 grid gap-3 border-t border-subtle pt-4 md:grid-cols-[1fr_1fr_auto] md:items-end">
            <Field label="Data/hora inicial">
              <input className="input" step="1" type="datetime-local" value={draftPeriod.start} onChange={(event) => onDraftChange({ ...draftPeriod, start: event.target.value })} />
            </Field>
            <Field label="Data/hora final">
              <input className="input" step="1" type="datetime-local" value={draftPeriod.end} onChange={(event) => onDraftChange({ ...draftPeriod, end: event.target.value })} />
            </Field>
            <Button onClick={onApplyCustom}>Aplicar período</Button>
          </div>
        )}
      </div>
    </section>
  );
}
