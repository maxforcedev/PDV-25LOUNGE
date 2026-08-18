"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Spinner } from "@/components/ui";
import { firstAuthorizedRoute } from "@/lib/authorized-routes";
import { useAuth } from "@/providers/auth-provider";

export function AdminGuard({ requiredPermissions, requireAll = false, children }: { requiredPermissions: readonly string[]; requireAll?: boolean; children: React.ReactNode }) {
  const { user, currentCompany, currentBranch, hasAnyPermission, hasPermission } = useAuth();
  const router = useRouter();
  const allowed = requireAll ? requiredPermissions.every(hasPermission) : hasAnyPermission(requiredPermissions);

  useEffect(() => {
    if (user && !allowed) router.replace(firstAuthorizedRoute(user, currentCompany, currentBranch));
  }, [allowed, currentCompany, currentBranch, router, user]);

  if (!allowed) {
    return <div className="flex min-h-[calc(100vh-4.5rem)] items-center justify-center text-primary"><Spinner className="size-7" /><span className="sr-only">Redirecionando</span></div>;
  }
  return children;
}
