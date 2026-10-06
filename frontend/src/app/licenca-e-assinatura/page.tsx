import type { Metadata } from "next";
import { LegalDocumentPage } from "@/components/marketing/legal-document-page";
import document from "@/content/legal/licenca-e-assinatura.json";

export const metadata: Metadata = { title: "Licença e Assinatura" };
export default function Page() { return <LegalDocumentPage document={document} />; }
