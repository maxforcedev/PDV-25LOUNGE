"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { GlobalSettings } from "@/lib/types";

type Branding = Pick<GlobalSettings, "platform_name" | "logo_dark_url" | "favicon_url">;

const backofficeUrl = (process.env.NEXT_PUBLIC_BACKOFFICE_URL || "http://localhost:3000").replace(/\/$/, "");
const DEFAULT_BRANDING: Branding = {
  platform_name: "CORE PDV",
  logo_dark_url: `${backofficeUrl}/branding/core-logo-dark.png`,
  favicon_url: `${backofficeUrl}/branding/core-favicon.png`,
};

const BrandingContext = createContext<Branding>(DEFAULT_BRANDING);

export function BrandingProvider({ children }: { children: React.ReactNode }) {
  const [branding, setBranding] = useState(DEFAULT_BRANDING);

  useEffect(() => {
    let active = true;
    api.get<Branding>("public/settings/")
      .then((settings) => {
        if (active) setBranding(settings);
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!branding.favicon_url) return;
    let favicon = document.querySelector<HTMLLinkElement>('link[data-runtime-branding="favicon"]');
    if (!favicon) {
      favicon = document.createElement("link");
      favicon.rel = "icon";
      favicon.dataset.runtimeBranding = "favicon";
      document.head.appendChild(favicon);
    }
    favicon.href = branding.favicon_url;
  }, [branding.favicon_url]);

  return <BrandingContext.Provider value={branding}>{children}</BrandingContext.Provider>;
}

export function useBranding() {
  return useContext(BrandingContext);
}
