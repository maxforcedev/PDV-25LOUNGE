"use client";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/providers/auth-provider";

export default function PrivateLayout({ children }: { children: React.ReactNode }) {
  const { loading, user } = useAuth();
  if (loading || !user) return <div className="flex min-h-screen items-center justify-center bg-ink text-white"><div className="text-center"><div className="mx-auto spinner text-signal" /><p className="mt-4 font-mono text-[10px] uppercase tracking-[.18em] text-white/50">Validando credenciais</p></div></div>;
  return <AppShell>{children}</AppShell>;
}
