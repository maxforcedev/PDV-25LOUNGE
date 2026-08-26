"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Spinner } from "@/components/ui";
import { firstAuthorizedRoute } from "@/lib/authorized-routes";
import { useAuth } from "@/providers/auth-provider";
import type { BranchFeature, FeaturePermissionAlternative } from "@/types";

export function AdminGuard({ requiredPermissions, requiredFeatures, alternatives, requireAll = false, requireAnyFeature = false, children }: { requiredPermissions: readonly string[]; requiredFeatures?: readonly BranchFeature[]; alternatives?: readonly FeaturePermissionAlternative[]; requireAll?: boolean; requireAnyFeature?: boolean; children: React.ReactNode }) {
  const { user, currentCompany, currentBranch, hasAnyPermission, hasPermission, hasFeature } = useAuth();
  const router = useRouter();
  const permissionAllowed = requireAll ? requiredPermissions.every(hasPermission) : hasAnyPermission(requiredPermissions);
  const featureAllowed = !requiredFeatures || (requireAnyFeature ? requiredFeatures.some(hasFeature) : requiredFeatures.every(hasFeature));
  const alternativesAllowed = alternatives?.some(({ permission, features }) => hasPermission(permission) && features.every(hasFeature));
  const allowed = alternatives ? alternativesAllowed : permissionAllowed && featureAllowed;

  useEffect(() => {
    if (user && !allowed) router.replace(firstAuthorizedRoute(user, currentCompany, currentBranch));
  }, [allowed, currentCompany, currentBranch, router, user]);

  if (!allowed) {
    return <div className="flex min-h-[calc(100vh-4.5rem)] items-center justify-center text-primary"><Spinner className="size-7" /><span className="sr-only">Redirecionando</span></div>;
  }
  return children;
}
