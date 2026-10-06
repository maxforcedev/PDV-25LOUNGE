"use client";

import Link from "next/link";
import Image from "next/image";
import { useEffect, useState } from "react";
import { useBranding } from "@/providers/branding-provider";

export function BrandWordmark({
  href = "/",
  compact = false,
  dark = false,
  className = "",
  imageClassName = "h-8 max-w-40",
}: {
  href?: string;
  compact?: boolean;
  dark?: boolean;
  className?: string;
  imageClassName?: string;
}) {
  const branding = useBranding();
  const customLogo = compact
    ? (dark ? branding.compact_logo_dark_url : branding.compact_logo_light_url) || branding.compact_logo_url || branding.logo_url
    : (dark ? branding.logo_dark_url : branding.logo_light_url) || branding.logo_url;
  const fallbackLogo = compact
    ? `/branding/core-logo-compact-${dark ? "dark" : "light"}.svg`
    : `/branding/core-logo-${dark ? "dark" : "light"}.svg`;
  const [failedLogo, setFailedLogo] = useState("");
  useEffect(() => { setFailedLogo(""); }, [customLogo]);
  const logo = customLogo && failedLogo !== customLogo ? customLogo : fallbackLogo;
  return (
    <Link
      href={href}
      className={`inline-flex items-center gap-2.5 rounded-md focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/25 ${className}`}
      aria-label={`${branding.platform_name} - página inicial`}
    >
      <Image src={logo} alt={branding.platform_name} width={192} height={40} unoptimized onError={() => customLogo && setFailedLogo(customLogo)} className={`${imageClassName} w-auto object-contain`} />
    </Link>
  );
}
