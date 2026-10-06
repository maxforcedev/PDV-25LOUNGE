"use client";

import Link from "next/link";
import { Fragment, type ReactNode } from "react";
import { useBranding } from "@/providers/branding-provider";
import { PublicHeader } from "@/components/marketing/public-header";
import { PublicFooter } from "@/components/marketing/public-footer";
import { resolveLegalTemplate } from "@/lib/legal-documents";

type Document = { title: string; markdown: string };

// Render trusted document text as React elements: no HTML injection or executable markup.
function inline(text: string): ReactNode {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) =>
    part.startsWith("**") ? <strong key={index} className="font-semibold text-fg">{part.slice(2, -2)}</strong> : part,
  );
}

function blocks(markdown: string) {
  return markdown.trim().replace(/\n(?=#{1,6} )/g, "\n\n").split(/\n\s*\n/).map((block) => {
    const heading = /^(#{1,6})\s+(.+)$/.exec(block.trim());
    if (heading) return { type: "heading", text: heading[2], depth: heading[1].length };
    return { type: /^-{3,}$/.test(block.trim()) ? "divider" : block.startsWith("|") ? "table" : block.startsWith("- ") ? "list" : block.startsWith(">") ? "quote" : "paragraph", text: block, depth: 0 };
  });
}

export function LegalDocumentPage({ document }: { document: Document }) {
  const branding = useBranding();
  const { markdown, missing } = resolveLegalTemplate(document.markdown, branding);
  const content = blocks(markdown);
  const headings = content.flatMap((block, index) => block.type === "heading" && index > 0 ? [{ index, text: block.text.replace(/\*\*/g, ""), depth: block.depth }] : []);
  return <div className="min-h-screen bg-canvas text-fg"><PublicHeader /><main className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
    <div className="mb-8"><p className="marketing-eyebrow">Documentos legais</p><nav aria-label="Documentos legais" className="mt-4 flex flex-wrap gap-3 text-sm font-semibold text-primary"><Link href="/termos-de-uso">Termos de Uso</Link><Link href="/privacidade">Privacidade</Link><Link href="/licenca-e-assinatura">Licença e Assinatura</Link><Link href="/tratamento-de-dados">Tratamento de Dados</Link></nav></div>
    {missing.length > 0 && <p role="status" className="mb-8 rounded-xl border border-warning/40 bg-warning-surface p-4 text-sm text-warning-strong">Dados institucionais ainda não informados: {missing.join(", ")}. Os campos pendentes estão identificados no documento.</p>}
    <div className="grid items-start gap-8 lg:grid-cols-[260px_minmax(0,1fr)]"><aside className="rounded-xl border border-subtle bg-surface p-5 lg:sticky lg:top-24"><details open><summary className="cursor-pointer font-bold">Neste documento</summary><nav aria-label="Índice do documento" className="mt-4 max-h-[35vh] lg:max-h-[55vh] space-y-2 overflow-y-auto text-xs leading-5">{headings.map((heading) => <a key={heading.index} className={`block text-muted hover:text-primary ${heading.depth > 1 ? "pl-3" : ""}`} href={`#secao-${heading.index}`}>{heading.text}</a>)}</nav></details></aside>
      <article className="min-w-0 rounded-xl border border-subtle bg-surface p-6 text-sm leading-7 sm:p-10">
        {content.map((block, index) => {
          if (block.type === "heading") return index === 0
            ? <h1 key={index} className="mb-8 text-3xl font-black leading-tight tracking-tight sm:text-4xl">{inline(block.text)}</h1>
            : block.depth === 1 ? <h2 id={`secao-${index}`} key={index} className="mb-4 mt-9 scroll-mt-24 text-xl font-bold leading-7">{inline(block.text)}</h2>
            : <h3 id={`secao-${index}`} key={index} className="mb-3 mt-6 scroll-mt-24 text-base font-bold">{inline(block.text)}</h3>;
          if (block.type === "divider") return <hr key={index} className="my-7 border-subtle" />;
          if (block.type === "list") return <ul key={index} className="mb-5 list-disc space-y-1 pl-6">{block.text.split("\n").map((line, item) => <li key={item}>{inline(line.replace(/^-\s+/, ""))}</li>)}</ul>;
          if (block.type === "table") {
            const rows = block.text.split("\n").filter((line) => !/^\|[\s:|-]+\|$/.test(line)).map((line) => line.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim()));
            return <div key={index} className="mb-6 overflow-x-auto"><table className="w-full border-collapse text-left"><thead><tr>{rows[0].map((cell, i) => <th key={i} className="border border-subtle bg-surface-muted px-3 py-2">{inline(cell)}</th>)}</tr></thead><tbody>{rows.slice(1).map((row, i) => <tr key={i}>{row.map((cell, j) => <td key={j} className="border border-subtle px-3 py-2">{inline(cell)}</td>)}</tr>)}</tbody></table></div>;
          }
          const lines = block.text.split("\n");
          const body = lines.map((line, i) => <Fragment key={i}>{i > 0 && <br />}{inline(line.replace(/^>\s?/, ""))}</Fragment>);
          return block.type === "quote" ? <blockquote key={index} className="mb-5 border-l-2 border-primary pl-4">{body}</blockquote> : <p key={index} className="mb-5 break-words text-muted">{body}</p>;
        })}
      </article>
    </div>
  </main><PublicFooter /></div>;
}
