"use client";

import { createContext, useContext, useEffect, useLayoutEffect, useState } from "react";
import { http } from "@/lib/http";
import type { PublicBranding } from "@/types";

export type BrandTheme = "light" | "dark";

export interface BrandingLogoOptions {
  compact?: boolean;
  theme?: BrandTheme;
  localOnly?: boolean;
}

const LOCAL_ASSETS = {
  logo_url: "/branding/core-logo-light.png",
  compact_logo_url: "/branding/core-logo-compact-light.png",
  favicon_url: "/branding/core-favicon.png",
  logo_light_url: "/branding/core-logo-light.png",
  logo_dark_url: "/branding/core-logo-dark.png",
  compact_logo_light_url: "/branding/core-logo-compact-light.png",
  compact_logo_dark_url: "/branding/core-logo-compact-dark.png",
};

const DEFAULT_BRANDING: PublicBranding = {
  platform_name: "CORE PDV",
  ...LOCAL_ASSETS,
  primary_color: "#3454d1",
  support_email: "",
  support_phone: "",
  institutional_links: {},
  legal_settings: {},
};

type BrandingContextValue = PublicBranding & {
  theme: BrandTheme;
  resolveLogo: (options?: BrandingLogoOptions) => string;
};

const BrandingContext = createContext<BrandingContextValue>({
  ...DEFAULT_BRANDING,
  theme: "light",
  resolveLogo: () => LOCAL_ASSETS.logo_light_url,
});

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
    legal_settings: value.legal_settings && typeof value.legal_settings === "object"
      ? Object.fromEntries(Object.entries(value.legal_settings).filter(([, item]) => typeof item === "string"))
      : {},
  };
}

function currentTheme(): BrandTheme {
  return typeof document !== "undefined" && document.documentElement.dataset.theme === "dark"
    ? "dark"
    : "light";
}

function resolveLogo(
  overrides: Pick<PublicBranding, keyof typeof LOCAL_ASSETS>,
  { compact = false, theme = "light", localOnly = false }: BrandingLogoOptions = {},
) {
  const variant = compact ? "compact_logo" : "logo";
  const specific = `${variant}_${theme}_url` as keyof typeof LOCAL_ASSETS;
  const generic = `${variant}_url` as keyof typeof LOCAL_ASSETS;
  return (!localOnly && (overrides[specific] || overrides[generic])) || LOCAL_ASSETS[specific] || LOCAL_ASSETS[generic];
}

function darkerColor(hex: string) {
  const channels = [1, 3, 5].map((offset) => Math.max(0, Math.round(Number.parseInt(hex.slice(offset, offset + 2), 16) * 0.82)));
  return `#${channels.map((channel) => channel.toString(16).padStart(2, "0")).join("")}`;
}

export function BrandingProvider({ children }: { children: React.ReactNode }) {
  const [branding, setBranding] = useState(DEFAULT_BRANDING);
  const [assetOverrides, setAssetOverrides] = useState<Pick<PublicBranding, keyof typeof LOCAL_ASSETS>>({
    logo_url: "",
    compact_logo_url: "",
    favicon_url: "",
    logo_light_url: "",
    logo_dark_url: "",
    compact_logo_light_url: "",
    compact_logo_dark_url: "",
  });
  const [theme, setTheme] = useState<BrandTheme>("light");

  useLayoutEffect(() => {
    const syncTheme = () => setTheme(currentTheme());
    syncTheme();
    window.addEventListener("themechange", syncTheme);
    return () => window.removeEventListener("themechange", syncTheme);
  }, []);

  useEffect(() => {
    let active = true;
    http.getPublic<Partial<PublicBranding>>("public/settings/")
      .then((settings) => {
        if (!active) return;
        const normalized = normalizeBranding(settings);
        setAssetOverrides({
          logo_url: normalized.logo_url,
          compact_logo_url: normalized.compact_logo_url,
          favicon_url: normalized.favicon_url,
          logo_light_url: normalized.logo_light_url || "",
          logo_dark_url: normalized.logo_dark_url || "",
          compact_logo_light_url: normalized.compact_logo_light_url || "",
          compact_logo_dark_url: normalized.compact_logo_dark_url || "",
        });
        setBranding({ ...normalized, ...LOCAL_ASSETS });
      })
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
    if (!favicon) {
      favicon = document.createElement("link");
      favicon.rel = "icon";
      favicon.dataset.runtimeBranding = "favicon";
      document.head.appendChild(favicon);
    }
    favicon.href = assetOverrides.favicon_url || LOCAL_ASSETS.favicon_url;
    favicon.onerror = () => {
      favicon!.href = LOCAL_ASSETS.favicon_url;
      favicon!.onerror = null;
    };
  }, [assetOverrides.favicon_url, branding]);

  const faviconUrl = assetOverrides.favicon_url || LOCAL_ASSETS.favicon_url;
  const value: BrandingContextValue = {
    ...branding,
    favicon_url: faviconUrl,
    theme,
    resolveLogo: (options) => resolveLogo(assetOverrides, { theme, ...options }),
  };
  return <BrandingContext.Provider value={value}>{children}</BrandingContext.Provider>;
}

export function useBranding() {
  return useContext(BrandingContext);
}
