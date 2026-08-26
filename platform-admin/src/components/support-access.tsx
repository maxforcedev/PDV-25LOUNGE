"use client";

import { Copy, ExternalLink } from "lucide-react";
import { useState } from "react";
import { dateTime } from "@/lib/format";
import { copySupportAccess, supportSessionUrl } from "@/lib/support";
import type { SupportSession } from "@/lib/types";

export function SupportAccessActions({ sessionId }: { sessionId: number }) {
  const [copied, setCopied] = useState(false);
  const url = supportSessionUrl(sessionId);

  async function copy() {
    try {
      await copySupportAccess(sessionId);
      setCopied(true);
    } catch {
      window.prompt("Copie o acesso de suporte:", url || String(sessionId));
    }
  }

  return <>{url && <a className="btn btn-signal" href={url} target="_blank" rel="noopener noreferrer"><ExternalLink size={14} />Abrir Backoffice</a>}<button className="btn btn-quiet" type="button" onClick={() => void copy()}><Copy size={14} />{copied ? "Acesso copiado" : "Copiar acesso"}</button></>;
}

export function SupportSessionCreated({ session }: { session: SupportSession }) {
  return <div className="border border-cyan/35 bg-cyan-50 p-4"><div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center"><div><p className="eyebrow">Support Session criada</p><p className="mt-1 text-sm font-bold">Sessao #{session.id} pronta ate {dateTime(session.expires_at)}</p></div><div className="flex flex-wrap gap-2"><SupportAccessActions sessionId={session.id} /></div></div></div>;
}
