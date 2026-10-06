import type { Metadata } from "next";
import { LegalDocumentPage } from "@/components/marketing/legal-document-page";
import document from "@/content/legal/tratamento-de-dados.json";

export const metadata: Metadata = { title: "Tratamento de Dados" };
export default function Page() { return <LegalDocumentPage document={document} />; }
