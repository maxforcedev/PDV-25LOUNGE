"use client";

import { useState } from "react";
import { ChevronDown, Download } from "lucide-react";
import { http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import { Button } from "@/components/ui";

type ExportFormat = "pdf" | "csv" | "xlsx";

export function ReportExportAction({
  path,
  query,
}: {
  path: string;
  query: URLSearchParams;
}) {
  const { hasPermission } = useAuth();
  const [status, setStatus] = useState("");
  const [downloading, setDownloading] = useState(false);

  if (!hasPermission(permissions.exportReports)) return null;

  async function download(format: ExportFormat) {
    setDownloading(true);
    setStatus("Preparando relatório...");
    try {
      const exportQuery = new URLSearchParams(query);
      exportQuery.set("export", format);
      const { blob, filename } = await http.download(
        `${path}?${exportQuery.toString()}`,
      );
      if (!blob.size) {
        setStatus("O arquivo gerado está vazio para o recorte aplicado.");
        return;
      }
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setStatus("Arquivo baixado com sucesso.");
    } catch (caught) {
      setStatus(
        caught instanceof Error
          ? caught.message
          : "Não foi possível exportar o relatório.",
      );
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <details className="relative" onToggle={(event) => downloading && (event.currentTarget.open = false)}>
        <summary className="btn btn-secondary cursor-pointer list-none [&::-webkit-details-marker]:hidden">
          {downloading ? <Download className="size-4 animate-pulse" /> : <Download className="size-4" />}
          Exportar
          <ChevronDown className="size-4" />
        </summary>
        <div className="absolute right-0 z-20 mt-2 min-w-40 overflow-hidden rounded-lg border border-subtle bg-surface p-1 shadow-lg">
          {(["xlsx", "pdf", "csv"] as ExportFormat[]).map((format) => (
            <button key={format} type="button" disabled={downloading} className="flex w-full items-center rounded-md px-3 py-2 text-left text-xs font-semibold text-fg hover:bg-surface-muted disabled:opacity-50" onClick={(event) => {
              event.currentTarget.closest("details")?.removeAttribute("open");
              void download(format);
            }}>
              {format === "xlsx" ? "Excel (.xlsx)" : format.toUpperCase()}
            </button>
          ))}
        </div>
      </details>
      {status && (
        <span className="basis-full text-right text-xs text-muted" role="status">
          {status}
        </span>
      )}
    </div>
  );
}
