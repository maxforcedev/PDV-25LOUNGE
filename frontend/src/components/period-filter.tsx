"use client";

import { useEffect, useState } from "react";
import { Button, Field, Input } from "@/components/ui";
import {
  businessPeriodPreset,
  type PeriodPreset,
  type PeriodValue,
} from "@/lib/period";

export type { PeriodValue } from "@/lib/period";

interface PeriodFilterProps {
  value: PeriodValue;
  onApply?: (value: PeriodValue) => void;
  onClear?: (value: PeriodValue) => void;
  onChange?: (value: PeriodValue) => void;
  showActions?: boolean;
  className?: string;
}

export function PeriodFilter({
  value,
  onApply,
  onClear,
  onChange,
  showActions = true,
  className = "",
}: PeriodFilterProps) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value.start, value.end]);

  function update(next: PeriodValue) {
    setDraft(next);
    onChange?.(next);
  }

  function choose(preset: PeriodPreset) {
    update(businessPeriodPreset(preset));
  }

  const presets: Array<[PeriodPreset, string]> = [
    ["today", "Hoje"],
    ["yesterday", "Ontem"],
    ["week", "Últimos 7 dias"],
    ["fortnight", "Últimos 15 dias"],
    ["month", "Últimos 30 dias"],
  ];
  const selectedPreset = presets.find(([key]) => {
    const preset = businessPeriodPreset(key);
    return preset.start === draft.start && preset.end === draft.end;
  })?.[0];

  return (
    <div className={`space-y-3 ${className}`}>
      <div className="flex flex-wrap gap-2">
        {presets.map(([key, label]) => (
          <button
            type="button"
            key={key}
            aria-pressed={selectedPreset === key}
            className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/20 ${selectedPreset === key ? "border-info/40 bg-info-surface text-info-strong" : "border-subtle bg-surface-muted text-muted hover:border-focus/40 hover:text-link"}`}
            onClick={() => choose(key)}
          >
            {label}
          </button>
        ))}
        <button
          type="button"
          aria-pressed={!selectedPreset}
          className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/20 ${!selectedPreset ? "border-info/40 bg-info-surface text-info-strong" : "border-subtle bg-surface-muted text-muted hover:border-focus/40 hover:text-fg"}`}
          onClick={() => update(value)}
        >
          Personalizado
        </button>
      </div>
      <div
        className={`grid gap-3 sm:items-end ${showActions ? "sm:grid-cols-[1fr_1fr_auto_auto]" : "sm:grid-cols-2"}`}
      >
        <Field label="Início">
          <Input
            type="datetime-local"
            step="1"
            value={draft.start}
            onChange={(event) =>
              update({ ...draft, start: event.target.value })
            }
          />
        </Field>
        <Field label="Fim">
          <Input
            type="datetime-local"
            step="1"
            value={draft.end}
            onChange={(event) => update({ ...draft, end: event.target.value })}
          />
        </Field>
        {showActions && (
          <>
            <Button
              type="button"
              variant="secondary"
              onClick={() => onApply?.(draft)}
            >
              Aplicar
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                const reset = businessPeriodPreset("today");
                update(reset);
                (onClear || onApply)?.(reset);
              }}
            >
              Limpar
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
