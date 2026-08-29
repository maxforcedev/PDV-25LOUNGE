"use client";

import { useState } from "react";
import { Download } from "lucide-react";
import { http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import { Button, Select } from "@/components/ui";

type ExportFormat = "pdf" | "csv" | "xlsx";

export function ReportExportAction({
  path,
  query,
}: {
  path: string;
  query: URLSearchParams;
}) {
  const { hasPermission } = useAuth();
  const [format, setFormat] = useState<ExportFormat>("pdf");
  const [status, setStatus] = useState("");
  const [downloading, setDownloading] = useState(false);

  if (!hasPermission(permissions.exportReports)) return null;

  async function download() {
    setDownloading(true);
    setStatus("Gerando arquivo...");
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
      <Select
        aria-label="Formato de exportação"
        className="w-24"
        value={format}
        onChange={(event) => setFormat(event.target.value as ExportFormat)}
      >
        <option value="pdf">PDF</option>
        <option value="csv">CSV</option>
        <option value="xlsx">Excel</option>
      </Select>
      <Button
        variant="secondary"
        loading={downloading}
        onClick={() => void download()}
      >
        <Download className="size-4" />
        Exportar
      </Button>
      {status && (
        <span className="basis-full text-right text-xs text-muted" role="status">
          {status}
        </span>
      )}
    </div>
  );
}
