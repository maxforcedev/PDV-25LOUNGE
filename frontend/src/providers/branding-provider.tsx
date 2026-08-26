"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { http } from "@/lib/http";
import type { PublicBranding } from "@/types";

const DEFAULT_BRANDING: PublicBranding = {
  platform_name: "CORE PDV",
  logo_url: "",
  compact_logo_url: "",
  favicon_url: "",
  primary_color: "#3454d1",
  support_email: "",
  support_phone: "",
  institutional_links: {},
};

const BrandingContext = createContext<PublicBranding>(DEFAULT_BRANDING);

function validUrl(value: unknown) {
  if (typeof value !== "string") return "";
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.toString() : "";
  } catch {
    return "";
  }
}

function normalizeBranding(value: Partial<PublicBranding>): PublicBranding {
  const links = value.institutional_links && typeof value.institutional_links === "object"
    ? Object.fromEntries(Object.entries(value.institutional_links).flatMap(([key, url]) => {
        const safeUrl = validUrl(url);
        return safeUrl && !/whats?app/i.test(key) ? [[key, safeUrl]] : [];
      }))
    : {};
  return {
    platform_name: typeof value.platform_name === "string" && value.platform_name.trim() ? value.platform_name.trim() : DEFAULT_BRANDING.platform_name,
    logo_url: validUrl(value.logo_url),
    compact_logo_url: validUrl(value.compact_logo_url),
    favicon_url: validUrl(value.favicon_url),
    logo_light_url: validUrl(value.logo_light_url),
    logo_dark_url: validUrl(value.logo_dark_url),
    compact_logo_light_url: validUrl(value.compact_logo_light_url),
    compact_logo_dark_url: validUrl(value.compact_logo_dark_url),
    primary_color: typeof value.primary_color === "string" && /^#[0-9a-f]{6}$/i.test(value.primary_color) ? value.primary_color : DEFAULT_BRANDING.primary_color,
    support_email: typeof value.support_email === "string" ? value.support_email.trim() : "",
    support_phone: typeof value.support_phone === "string" ? value.support_phone.trim() : "",
    institutional_links: links,
  };
}

function darkerColor(hex: string) {
  const channels = [1, 3, 5].map((offset) => Math.max(0, Math.round(Number.parseInt(hex.slice(offset, offset + 2), 16) * 0.82)));
  return `#${channels.map((channel) => channel.toString(16).padStart(2, "0")).join("")}`;
}

export function BrandingProvider({ children }: { children: React.ReactNode }) {
  const [branding, setBranding] = useState(DEFAULT_BRANDING);
  const pathname = usePathname();

  useEffect(() => {
    let active = true;
    http.getPublic<Partial<PublicBranding>>("public/settings/")
      .then((settings) => active && setBranding(normalizeBranding(settings)))
      .catch(() => undefined);
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty("--brand-primary", branding.primary_color);
    root.style.setProperty("--brand-primary-dark", darkerColor(branding.primary_color));
    root.style.setProperty("--focus", branding.primary_color);
    root.style.setProperty("--info", branding.primary_color);

    if (document.title) document.title = document.title.replace(/CORE PDV/gi, branding.platform_name);
    else document.title = branding.platform_name;

    let favicon = document.querySelector<HTMLLinkElement>('link[data-runtime-branding="favicon"]');
    if (branding.favicon_url) {
      if (!favicon) {
        favicon = document.createElement("link");
        favicon.rel = "icon";
        favicon.dataset.runtimeBranding = "favicon";
        document.head.appendChild(favicon);
      }
      favicon.href = branding.favicon_url;
    } else {
      favicon?.remove();
    }
  }, [branding, pathname]);

  return <BrandingContext.Provider value={branding}>{children}</BrandingContext.Provider>;
}

export function useBranding() {
  return useContext(BrandingContext);
}
