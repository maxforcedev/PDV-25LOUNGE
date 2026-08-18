"use client";

import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Inbox,
  LoaderCircle,
  X,
} from "lucide-react";

export function Spinner({ className = "size-4" }: { className?: string }) {
  return (
    <LoaderCircle aria-hidden="true" className={`${className} animate-spin`} />
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger";
  loading?: boolean;
};
export function Button({
  variant = "primary",
  loading,
  children,
  className = "",
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      className={`btn btn-${variant} ${className}`}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <Spinner />}
      {children}
    </button>
  );
}

interface FieldProps {
  label: string;
  error?: string;
  optional?: boolean;
  children: React.ReactNode;
}
export function Field({ label, error, optional, children }: FieldProps) {
  return (
    <label className="block">
      <span className="label">
        {label}
        {optional && (
          <span className="ml-1 font-normal text-muted">(opcional)</span>
        )}
      </span>
      {children}
      {error && <span className="field-error block">{error}</span>}
    </label>
  );
}

export function Input({
  className = "",
  ...props
}: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`input ${className}`} />;
}

function sanitizeMoney(raw: string) {
  return raw.replace(/[^\d,.]/g, "").replace(/,/g, ".");
}

export function MoneyInput({
  value,
  onValueChange,
  className = "",
  ...props
}: Omit<InputHTMLAttributes<HTMLInputElement>, "onChange" | "value"> & {
  value: string;
  onValueChange: (next: string) => void;
}) {
  return (
    <input
      type="text"
      inputMode="decimal"
      autoComplete="off"
      {...props}
      value={value}
      onChange={(event) => onValueChange(sanitizeMoney(event.target.value))}
      className={`input ${className}`}
    />
  );
}

export function IntegerInput({
  value,
  onValueChange,
  className = "",
  ...props
}: Omit<InputHTMLAttributes<HTMLInputElement>, "onChange" | "value"> & {
  value: string;
  onValueChange: (next: string) => void;
}) {
  return (
    <input
      type="text"
      inputMode="numeric"
      autoComplete="off"
      {...props}
      value={value}
      onChange={(event) =>
        onValueChange(event.target.value.replace(/[^\d]/g, ""))
      }
      className={`input ${className}`}
    />
  );
}

export function Select({
  className = "",
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`input select-control ${className}`} />;
}

export function Textarea({
  className = "",
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={`textarea ${className}`} />;
}

export function Alert({
  message,
  type = "error",
}: {
  message: string;
  type?: "error" | "success";
}) {
  const success = type === "success";
  return (
    <div
      role={success ? "status" : "alert"}
      className={`animate-enter flex items-start gap-2.5 rounded-md border px-3.5 py-3 text-[13px] ${success ? "border-success/30 bg-success-surface text-success-strong" : "border-danger/30 bg-danger-surface text-danger-strong"}`}
    >
      {success ? (
        <CheckCircle2 className="mt-0.5 size-4 shrink-0" />
      ) : (
        <AlertCircle className="mt-0.5 size-4 shrink-0" />
      )}
      <span>{message}</span>
    </div>
  );
}

export function EmptyState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="flex flex-col items-center px-6 py-16 text-center">
      <div className="mb-4 flex size-14 items-center justify-center rounded-full bg-surface-muted text-muted">
        <Inbox className="size-6" />
      </div>
      <h3 className="text-sm font-semibold text-fg">{title}</h3>
      <p className="mt-1 max-w-sm text-xs leading-5 text-muted">
        {description}
      </p>
    </div>
  );
}

export function TableLoading({ columns = 5 }: { columns?: number }) {
  return (
    <div className="p-5" aria-label="Carregando dados">
      {[0, 1, 2, 3].map((row) => (
        <div key={row} className="flex gap-6 border-b border-subtle py-4">
          {Array.from({ length: columns }).map((_, col) => (
            <div
              key={col}
              className="h-3 flex-1 animate-pulse rounded bg-surface-muted"
            />
          ))}
        </div>
      ))}
    </div>
  );
}

export function StatusBadge({ active }: { active: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${active ? "border-success/30 bg-success-surface text-success-strong" : "border-subtle bg-surface-muted text-muted"}`}
    >
      <span
        className={`size-1.5 rounded-full ${active ? "bg-success" : "bg-disabled"}`}
      />
      {active ? "Ativo" : "Inativo"}
    </span>
  );
}

export function Tooltip({
  content,
  children,
}: {
  content: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className="group relative inline-block max-w-full rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-focus/30"
      tabIndex={0}
    >
      {children}
      <span
        role="tooltip"
        className="pointer-events-none invisible absolute bottom-full left-1/2 z-30 mb-2 w-max max-w-72 -translate-x-1/2 rounded-md bg-chart-tooltip px-3 py-2 text-left text-[11px] font-medium leading-4 text-chart-tooltip-fg opacity-0 shadow-xl ring-1 ring-subtle transition group-hover:visible group-hover:opacity-100 group-focus:visible group-focus:opacity-100"
      >
        {content}
      </span>
    </span>
  );
}

export function Pagination({
  count,
  next,
  previous,
  onPage,
}: {
  count: number;
  next: string | null;
  previous: string | null;
  onPage: (url: string) => void;
}) {
  if (!next && !previous)
    return (
      <div className="px-5 py-4 text-xs text-muted">
        {count} {count === 1 ? "registro" : "registros"}
      </div>
    );
  return (
    <div className="flex items-center justify-between gap-4 px-5 py-4 text-xs text-muted">
      <span>{count} registros</span>
      <div className="flex gap-2">
        <button
          className="icon-button border border-subtle"
          aria-label="Página anterior"
          disabled={!previous}
          onClick={() => previous && onPage(previous)}
        >
          <ChevronLeft className="size-4" />
        </button>
        <button
          className="icon-button border border-subtle"
          aria-label="Próxima página"
          disabled={!next}
          onClick={() => next && onPage(next)}
        >
          <ChevronRight className="size-4" />
        </button>
      </div>
    </div>
  );
}

export function Modal({
  open,
  title,
  description,
  children,
  onClose,
  size = "lg",
}: {
  open: boolean;
  title: string;
  description?: string;
  children: React.ReactNode;
  onClose: () => void;
  size?: "md" | "lg" | "xl";
}) {
  if (!open) return null;
  const sizes = { md: "max-w-md", lg: "max-w-2xl", xl: "max-w-4xl" };
  return (
    <div
      className="modal-backdrop fixed inset-0 z-50 flex items-end justify-center p-0 backdrop-blur-[1px] sm:items-center sm:p-5"
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <div
        className={`modal-panel animate-enter max-h-[92vh] w-full overflow-y-auto rounded-t-xl shadow-2xl sm:rounded-xl ${sizes[size]}`}
      >
        <div className="modal-header sticky top-0 z-10 flex items-start justify-between gap-4 border-b px-5 py-4 sm:px-6">
          <div>
            <h2 id="modal-title" className="text-base font-bold text-fg">
              {title}
            </h2>
            {description && (
              <p className="mt-1 text-xs text-muted">{description}</p>
            )}
          </div>
          <button
            type="button"
            className="icon-button -mr-2 -mt-1"
            aria-label="Fechar"
            onClick={onClose}
          >
            <X className="size-4" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  danger,
  loading,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  danger?: boolean;
  loading?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Modal open={open} title={title} onClose={onClose} size="md">
      <div className="p-5 sm:p-6">
        <p className="text-[13px] leading-6 text-muted">{message}</p>
      </div>
      <div className="flex justify-end gap-2 border-t border-subtle px-5 py-4 sm:px-6">
        <Button variant="secondary" onClick={onClose} disabled={loading}>
          Cancelar
        </Button>
        <Button
          variant={danger ? "danger" : "primary"}
          loading={loading}
          onClick={onConfirm}
        >
          {confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}
