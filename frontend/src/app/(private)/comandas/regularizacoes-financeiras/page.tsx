"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ShieldCheck } from "lucide-react";
import { AdminGuard } from "@/components/admin-guard";
import { PageHeader } from "@/components/page-header";
import { Alert, Button, Field, Input, Modal, Spinner, Textarea } from "@/components/ui";
import { formatDate } from "@/lib/format";
import { ApiError, http } from "@/lib/http";
import { permissions } from "@/lib/permissions";
import { useAuth } from "@/providers/auth-provider";
import type { LegacyServiceFeeRegularizationCommand } from "@/types";

function FinancialRegularizationsPage() {
  const { currentBranch, hasPermission, supportSession } = useAuth();
  const readOnly = supportSession?.mode === "READ_ONLY";
  const canRegularize = hasPermission(permissions.regularizeCommandServiceFee) && !readOnly;
  const [commands, setCommands] = useState<LegacyServiceFeeRegularizationCommand[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [selected, setSelected] = useState<LegacyServiceFeeRegularizationCommand | null>(null);
  const [rate, setRate] = useState("");
  const [justification, setJustification] = useState("");
  const [evidenceReference, setEvidenceReference] = useState("");
  const [fields, setFields] = useState<Record<string, string[]>>({});
  const context = useRef("");
  context.current = String(currentBranch?.id || "");

  async function load(token: string) {
    if (!currentBranch) { setCommands([]); setLoading(false); return; }
    setLoading(true); setError("");
    try {
      const result = await http.get<LegacyServiceFeeRegularizationCommand[]>(
        "attendance-commands/legacy-service-fee-regularizations/",
      );
      if (context.current === token) setCommands(result);
    } catch (caught) {
      if (context.current === token) setError(caught instanceof ApiError ? caught.message : "Não foi possível carregar as regularizações pendentes.");
    } finally {
      if (context.current === token) setLoading(false);
    }
  }

  const loadRef = useRef(load);
  loadRef.current = load;
  useEffect(() => { setCommands([]); void loadRef.current(String(currentBranch?.id || "")); }, [currentBranch?.id]);

  function openRegularization(command: LegacyServiceFeeRegularizationCommand) {
    setSelected(command); setRate(""); setJustification(""); setEvidenceReference(""); setFields({}); setError("");
  }

  async function regularize() {
    if (!selected) return;
    setSaving(true); setError(""); setFields({});
    try {
      await http.post(`attendance-commands/${selected.id}/service-fee-regularization/`, {
        service_fee_rate: rate.replace(",", "."),
        justification: justification.trim(),
        evidence_reference: evidenceReference.trim(),
        idempotency_key: crypto.randomUUID(),
      });
      setSelected(null);
      setSuccess("Taxa histórica regularizada. A comanda pode seguir pelo fluxo financeiro normal.");
      await load(String(currentBranch?.id || ""));
    } catch (caught) {
      if (caught instanceof ApiError) { setError(caught.message); setFields(caught.fields || {}); }
      else setError("Não foi possível concluir a regularização.");
    } finally { setSaving(false); }
  }

  if (!currentBranch) return <div className="p-6"><Alert message="Selecione uma filial." /></div>;

  return (
    <>
      <PageHeader title="Regularizações financeiras" description="Comandas do CORE POS bloqueadas por taxa de serviço histórica desconhecida." action={<Link href="/comandas" className="btn btn-secondary"><ArrowLeft className="size-4" />Voltar</Link>} />
      <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        <section className="card border-danger/30 p-4 text-sm">
          <strong className="block">Ação excepcional e auditada</strong>
          <p className="mt-1 text-muted">Informe somente uma taxa comprovada por evidência histórica. A operação não altera pagamentos, descontos, comissão, estoque ou custos já registrados. Se as condições históricas dos itens não forem comprováveis, a regularização permanecerá bloqueada.</p>
        </section>
        {error && <Alert message={error} />}
        {success && <Alert message={success} type="success" />}
        {loading ? <Spinner /> : commands.length ? <section className="card overflow-hidden"><div className="table-wrap"><table className="data-table"><thead><tr><th>Comanda</th><th>Aberta em</th><th>Pagamentos históricos</th><th>Ação</th></tr></thead><tbody>{commands.map((command) => <tr key={command.id}><td><strong>{command.identifier || command.number}</strong>{command.identifier ? <small className="ml-2 text-muted">{command.number}</small> : null}</td><td>{formatDate(command.created_at)}</td><td>{command.payment_count}</td><td>{canRegularize ? <Button variant="secondary" onClick={() => openRegularization(command)}><ShieldCheck className="size-4" />Regularizar</Button> : <span className="text-sm text-muted">Taxa histórica precisa de regularização administrativa.</span>}</td></tr>)}</tbody></table></div></section> : <section className="card p-5 text-sm text-muted">Não há comandas bloqueadas por taxa histórica nesta filial.</section>}
      </div>
      <Modal open={!!selected} title="Regularizar taxa histórica" description={selected ? `Comanda ${selected.identifier || selected.number}. Esta confirmação é definitiva.` : undefined} onClose={() => !saving && setSelected(null)}>
        <div className="space-y-4 p-5">
          <Field label="Percentual histórico de serviço" error={fields.service_fee_rate?.[0]}><Input value={rate} onChange={(event) => setRate(event.target.value)} disabled={saving} inputMode="decimal" placeholder="Ex.: 10,00" /></Field>
          <Field label="Justificativa" error={fields.justification?.[0]}><Textarea value={justification} onChange={(event) => setJustification(event.target.value)} disabled={saving} rows={4} placeholder="Explique por que este percentual é o correto." /></Field>
          <Field label="Referência da evidência" error={fields.evidence_reference?.[0]}><Input value={evidenceReference} onChange={(event) => setEvidenceReference(event.target.value)} disabled={saving} placeholder="Ex.: comprovante, relatório ou documento arquivado" /></Field>
          {error && <Alert message={error} />}
          <div className="flex justify-end gap-2 border-t border-subtle pt-4"><Button variant="secondary" onClick={() => setSelected(null)} disabled={saving}>Cancelar</Button><Button loading={saving} onClick={() => void regularize()}>Confirmar regularização</Button></div>
        </div>
      </Modal>
    </>
  );
}

export default function FinancialRegularizationsPageWrapper() {
  return <AdminGuard requiredPermissions={[permissions.viewCommands]} requiredFeatures={["commands"]}><FinancialRegularizationsPage /></AdminGuard>;
}
