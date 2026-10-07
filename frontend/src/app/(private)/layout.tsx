"use client";

import { AppShell } from "@/components/app-shell";
import { Spinner } from "@/components/ui";
import { firstAuthorizedRoute } from "@/lib/authorized-routes";
import { isFeaturePathAllowed } from "@/lib/feature-guards";
import { useAuth } from "@/providers/auth-provider";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

export default function PrivateLayout({ children }: { children: React.ReactNode }) {
  const { user, loading, currentCompany, currentBranch, hasFeature } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const restrictedOwner = Boolean(currentCompany?.is_owner && !currentCompany.can_operate);
  const featureBlocked = !isFeaturePathAllowed(pathname, hasFeature);
  const mustRedirect = (restrictedOwner && pathname !== "/assinatura") || featureBlocked;

  useEffect(() => {
    if (!loading && user && mustRedirect) router.replace(restrictedOwner ? "/assinatura" : firstAuthorizedRoute(user, currentCompany, currentBranch));
  }, [currentBranch, currentCompany, loading, mustRedirect, restrictedOwner, router, user]);

  if (loading || !user || mustRedirect) return <div className="flex min-h-screen items-center justify-center bg-canvas text-primary"><Spinner className="size-7" /><span className="sr-only">{mustRedirect ? "Redirecionando" : "Validando sessão"}</span></div>;
  return <AppShell>{children}</AppShell>;
}
