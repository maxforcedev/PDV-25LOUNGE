"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Plus } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, Spinner } from "@/components/ui";
import { formatDate } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { Command, Table } from "@/types";

function CommandsPage() {
  const { currentBranch, hasPermission, hasFeature, supportSession } = useAuth();
  const readOnly = supportSession?.mode === "READ_ONLY";
  const canOpen = hasPermission(permissions.openCommand) && !readOnly;
  const usesTables = hasFeature("tables");
  const [commands, setCommands] = useState<Command[]>([]);
  const [tables, setTables] = useState<Table[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [opening, setOpening] = useState(false);
  const [selectedTable, setSelectedTable] = useState<string>("");
  const [identifier, setIdentifier] = useState("");
  const context = useRef("");
  context.current = String(currentBranch?.id || "");

  async function load(token: string) {
    if (!currentBranch) { setCommands([]); setLoading(false); return; }
    setLoading(true); setError("");
    try {
      const cmds = await http.getAll<Command>(`commands/?branch=${currentBranch.id}`);
      const tbls = usesTables
        ? await http.getAll<Table>(`tables/?branch=${currentBranch.id}`)
        : [];
      if (context.current === token) { setCommands(cmds); setTables(tbls); }
    } catch (caught) {
      if (context.current === token) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as comandas.");
    } finally {
      if (context.current === token) setLoading(false);
    }
  }

  const loadRef = useRef(load);
  loadRef.current = load;
  useEffect(() => { setCommands([]); void loadRef.current(String(currentBranch?.id || "")); }, [currentBranch?.id, usesTables]);

  async function openCommand() {
    if (!currentBranch) return;
    setOpening(true); setError("");
    try {
      const payload: Record<string, unknown> = { identifier: identifier.trim() };
      if (selectedTable) payload.table = Number(selectedTable);
      await http.post("commands/open/", payload);
      setSelectedTable(""); setIdentifier("");
      await load(String(currentBranch.id));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Não foi possível abrir a comanda.");
    } finally { setOpening(false); }
  }

  if (!currentBranch) return <div className="p-6"><Alert message="Selecione uma filial." /></div>;

  return (
    <>
      <PageHeader title="Comandas" description="Comandas abertas e fechadas da filial." action={
        canOpen ? (
          <div className="flex flex-wrap items-end gap-2">
            <select className="input" value={selectedTable} onChange={(e) => setSelectedTable(e.target.value)} disabled={opening}>
              <option value="">Sem mesa</option>
              {tables.filter((t) => t.status === "active").map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
            <input className="input" value={identifier} onChange={(e) => setIdentifier(e.target.value)} disabled={opening} placeholder="Identificação (ex.: Junior)" />
            <Button loading={opening} onClick={() => void openCommand()}><Plus className="size-4" />Abrir</Button>
          </div>
        ) : undefined
      } />
      <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        {error && <Alert message={error} />}
        {loading ? <Spinner /> : commands.length ? (
            <div className="table-wrap"><table className="data-table"><thead><tr><th>Comanda</th><th>Mesa</th><th>Status</th><th>Aberta em</th><th>Fechada em</th><th>Venda</th></tr></thead><tbody>
            {commands.map((cmd) => (
              <tr key={cmd.id} className="cursor-pointer hover:bg-surface">
                <td><Link href={`/comandas/${cmd.id}`} className="font-bold text-primary hover:underline">{cmd.identifier || cmd.command_number}</Link>{cmd.identifier ? <small className="ml-2 text-muted">{cmd.command_number}</small> : null}</td>
                <td>{cmd.table_name || "—"}</td>
                <td>{cmd.status === "open" ? "Aberta" : "Fechada"}</td>
                <td>{formatDate(cmd.created_at)}</td>
                <td>{cmd.closed_at ? formatDate(cmd.closed_at) : "—"}</td>
                <td>{cmd.sale ? <Link href={`/vendas/${cmd.sale}`} className="text-primary hover:underline">#{cmd.sale}</Link> : "—"}</td>
              </tr>
            ))}
          </tbody></table></div>
        ) : <Alert message="Nenhuma comanda encontrada nesta filial." />}
      </div>
    </>
  );
}

export default function CommandsPageWrapper() {
  return <AdminGuard requiredPermissions={[permissions.viewCommands]} requiredFeatures={["commands"]}><CommandsPage /></AdminGuard>;
}
