"use client";

import { useEffect, useState } from "react";
import { Button, Field, Input } from "@/components/ui";

export interface PeriodValue { start: string; end: string }

function localValue(date: Date) {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function dayStart(date: Date) { const value = new Date(date); value.setHours(0, 0, 0, 0); return value; }
function dayEnd(date: Date) { const value = new Date(date); value.setHours(23, 59, 59, 0); return value; }

function presetValue(preset: string): PeriodValue {
  const now = new Date();
  if (preset === "today") return { start: localValue(dayStart(now)), end: localValue(dayEnd(now)) };
  if (preset === "yesterday") { const date = new Date(now); date.setDate(date.getDate() - 1); return { start: localValue(dayStart(date)), end: localValue(dayEnd(date)) }; }
  if (preset === "week") { const start = dayStart(now); start.setDate(start.getDate() - 6); return { start: localValue(start), end: localValue(dayEnd(now)) }; }
  const days = preset === "fortnight" ? 14 : 29;
  const start = dayStart(now);
  start.setDate(start.getDate() - days);
  return { start: localValue(start), end: localValue(dayEnd(now)) };
}

export function PeriodFilter({ value, onApply, onClear, className = "" }: { value: PeriodValue; onApply: (value: PeriodValue) => void; onClear?: (value: PeriodValue) => void; className?: string }) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value.start, value.end]);
  function choose(preset: string) { setDraft(presetValue(preset)); }
  return <div className={`space-y-3 ${className}`}>
    <div className="flex flex-wrap gap-2">
      {[["today", "Hoje"], ["yesterday", "Ontem"], ["week", "Últimos 7 dias"], ["fortnight", "Últimos 15 dias"], ["month", "Últimos 30 dias"]].map(([key, label]) => <button type="button" key={key} className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-primary/10 hover:text-primary" onClick={() => choose(key)}>{label}</button>)}
      <button type="button" className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-600" onClick={() => setDraft(value)}>Personalizado</button>
    </div>
    <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto_auto] sm:items-end">
      <Field label="Início"><Input type="datetime-local" step="1" value={draft.start} onChange={(event) => setDraft((current) => ({ ...current, start: event.target.value }))} /></Field>
      <Field label="Fim"><Input type="datetime-local" step="1" value={draft.end} onChange={(event) => setDraft((current) => ({ ...current, end: event.target.value }))} /></Field>
      <Button type="button" variant="secondary" onClick={() => onApply(draft)}>Aplicar</Button>
      <Button type="button" variant="secondary" onClick={() => { const reset = presetValue("today"); setDraft(reset); (onClear || onApply)(reset); }}>Limpar</Button>
    </div>
  </div>;
}
