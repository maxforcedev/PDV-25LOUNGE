"use client";

import { AppShell } from "@/components/app-shell";
import { Spinner } from "@/components/ui";
import { useAuth } from "@/providers/auth-provider";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

export default function PrivateLayout({ children }: { children: React.ReactNode }) {
  const { user, loading, currentCompany } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const restrictedOwner = Boolean(currentCompany?.is_owner && !currentCompany.can_operate);
  const mustRedirect = restrictedOwner && pathname !== "/assinatura";

  useEffect(() => {
    if (!loading && user && mustRedirect) router.replace("/assinatura");
  }, [loading, mustRedirect, router, user]);

  if (loading || !user || mustRedirect) return <div className="flex min-h-screen items-center justify-center bg-canvas text-primary"><Spinner className="size-7" /><span className="sr-only">{mustRedirect ? "Redirecionando para assinatura" : "Validando sessão"}</span></div>;
  return <AppShell>{children}</AppShell>;
}
