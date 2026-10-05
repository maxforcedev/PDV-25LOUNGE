"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Plus } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, Field, Spinner } from "@/components/ui";
import { CustomerQuickPicker } from "@/components/customer-quick-picker";
import { formatDate } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { Command, Customer } from "@/types";

function CommandsPage() {
  const { currentBranch, hasPermission, hasFeature, supportSession } = useAuth();
  const readOnly = supportSession?.mode === "READ_ONLY";
  const canOpen = hasPermission(permissions.openCommand) && !readOnly;
  const [commands, setCommands] = useState<Command[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [opening, setOpening] = useState(false);
  const [identifier, setIdentifier] = useState("");
  const [customer, setCustomer] = useState<Customer | null>(null);
  const context = useRef("");
  context.current = String(currentBranch?.id || "");

  async function load(token: string) {
    if (!currentBranch) { setCommands([]); setLoading(false); return; }
    setLoading(true); setError("");
    try {
      const cmds = await http.getAll<Command>(`commands/?branch=${currentBranch.id}`);
      if (context.current === token) setCommands(cmds);
    } catch (caught) {
      if (context.current === token) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as comandas.");
    } finally {
      if (context.current === token) setLoading(false);
    }
  }

  const loadRef = useRef(load);
  loadRef.current = load;
  useEffect(() => { setCommands([]); void loadRef.current(String(currentBranch?.id || "")); }, [currentBranch?.id]);

  async function openCommand() {
    if (!currentBranch) return;
    setOpening(true); setError("");
    try {
      const payload: Record<string, unknown> = { identifier: identifier.trim(), ...(customer ? { customer: customer.id } : {}) };
      await http.post("commands/open/", payload);
      setIdentifier(""); setCustomer(null);
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
            <input className="input" value={identifier} onChange={(e) => setIdentifier(e.target.value)} disabled={opening} placeholder="Identificação (ex.: Junior)" />
            <div className="min-w-60"><CustomerQuickPicker value={customer} onChange={setCustomer} disabled={opening} /></div>
            <Button loading={opening} onClick={() => void openCommand()}><Plus className="size-4" />Abrir</Button>
          </div>
        ) : undefined
      } />
      <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        {error && <Alert message={error} />}
        {loading ? <Spinner /> : commands.length ? (
            <div className="table-wrap"><table className="data-table"><thead><tr><th>Comanda</th><th>Status</th><th>Aberta em</th><th>Fechada em</th><th>Venda</th></tr></thead><tbody>
            {commands.map((cmd) => (
              <tr key={cmd.id} className="cursor-pointer hover:bg-surface">
                <td><Link href={`/comandas/${cmd.id}`} className="font-bold text-primary hover:underline">{cmd.identifier || cmd.command_number}</Link>{cmd.identifier ? <small className="ml-2 text-muted">{cmd.command_number}</small> : null}</td>
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
