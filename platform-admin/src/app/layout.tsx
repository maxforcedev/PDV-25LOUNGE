import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/providers/auth-provider";
import { BrandingProvider } from "@/providers/branding-provider";

const fallbackFavicon = `${(process.env.NEXT_PUBLIC_BACKOFFICE_URL || "http://localhost:3000").replace(/\/$/, "")}/branding/core-favicon.png`;

export const metadata: Metadata = {
  title: "CORE Admin",
  description: "Administrativo da plataforma CORE",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR">
      <head><link rel="icon" href={fallbackFavicon} data-runtime-branding="favicon" /></head>
      <body><BrandingProvider><AuthProvider>{children}</AuthProvider></BrandingProvider></body>
    </html>
  );
}
