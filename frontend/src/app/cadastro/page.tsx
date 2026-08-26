import type { Metadata } from "next";
import { Suspense } from "react";
import { PublicFooter } from "@/components/marketing/public-footer";
import { PublicHeader } from "@/components/marketing/public-header";
import { SignupForm } from "@/components/marketing/signup-form";
import { Spinner } from "@/components/ui";

export const metadata: Metadata = {
  title: "Criar conta | CORE PDV",
  description: "Cadastro curto de empresa e conta Owner, sem cartão ou gateway de pagamento.",
};

export default function SignupPage() {
  return (
    <div className="min-h-screen bg-canvas text-fg">
      <PublicHeader active="signup" />
      <main className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
        <Suspense fallback={<div className="flex min-h-96 items-center justify-center text-primary"><Spinner className="size-7" /><span className="sr-only">Preparando cadastro</span></div>}><SignupForm /></Suspense>
      </main>
      <PublicFooter />
    </div>
  );
}
