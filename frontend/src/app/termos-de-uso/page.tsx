import type { Metadata } from "next";
import { LegalDocumentPage } from "@/components/marketing/legal-document-page";
import document from "@/content/legal/termos-de-uso.json";

export const metadata: Metadata = { title: "Termos de Uso" };
export default function Page() { return <LegalDocumentPage document={document} />; }
