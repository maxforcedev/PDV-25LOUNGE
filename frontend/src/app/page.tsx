"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Spinner } from "@/components/ui";
import { firstAuthorizedRoute } from "@/lib/authorized-routes";
import { useAuth } from "@/providers/auth-provider";

export default function Home() {
  const { user, loading, currentCompany, currentBranch } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!loading && user) router.replace(firstAuthorizedRoute(user, currentCompany, currentBranch));
  }, [loading, user, currentCompany, currentBranch, router]);
  return <div className="flex min-h-screen items-center justify-center text-primary"><Spinner className="size-7" /><span className="sr-only">Redirecionando</span></div>;
}
