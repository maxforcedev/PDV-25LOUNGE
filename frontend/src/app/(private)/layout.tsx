"use client";

import { AppShell } from "@/components/app-shell";
import { Spinner } from "@/components/ui";
import { useAuth } from "@/providers/auth-provider";

export default function PrivateLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading || !user) return <div className="flex min-h-screen items-center justify-center bg-canvas text-primary"><Spinner className="size-7" /><span className="sr-only">Validando sessão</span></div>;
  return <AppShell>{children}</AppShell>;
}
