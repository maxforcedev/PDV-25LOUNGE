import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/providers/auth-provider";
import { BrandingProvider } from "@/providers/branding-provider";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Core PDV",
  description: "Gestão centralizada da sua empresa.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: `(function(){try{var saved=localStorage.getItem('pdv.theme');var theme=saved==='dark'||saved==='light'?saved:(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');document.documentElement.dataset.theme=theme}catch(e){document.documentElement.dataset.theme='light'}})()` }} />
      </head>
      <body className={inter.className}>
        <BrandingProvider>
          <AuthProvider>{children}</AuthProvider>
        </BrandingProvider>
      </body>
    </html>
  );
}
