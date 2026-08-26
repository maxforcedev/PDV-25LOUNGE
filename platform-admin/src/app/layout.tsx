import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/providers/auth-provider";

export const metadata: Metadata = {
  title: "CORE Platform Operations",
  description: "Console administrativo da plataforma CORE",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR">
      <body><AuthProvider>{children}</AuthProvider></body>
    </html>
  );
}
