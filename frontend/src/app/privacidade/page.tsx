import type { Metadata } from "next";
import { LegalDocumentPage } from "@/components/marketing/legal-document-page";
import document from "@/content/legal/privacidade.json";

export const metadata: Metadata = { title: "Política de Privacidade" };
export default function Page() { return <LegalDocumentPage document={document} />; }
