"use client";

import Link from "next/link";
import Image from "next/image";
import { useBranding } from "@/providers/branding-provider";

export function BrandWordmark({
  href = "/",
  compact = false,
  dark = false,
  className = "",
}: {
  href?: string;
  compact?: boolean;
  dark?: boolean;
  className?: string;
}) {
  const branding = useBranding();
  const logo = compact
    ? (dark ? branding.compact_logo_dark_url : branding.compact_logo_light_url) || branding.compact_logo_url || branding.logo_url
    : (dark ? branding.logo_dark_url : branding.logo_light_url) || branding.logo_url;
  return (
    <Link
      href={href}
      className={`inline-flex items-center gap-2.5 rounded-md focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-focus/25 ${className}`}
      aria-label={`${branding.platform_name} - página inicial`}
    >
      {logo ? (
        <Image src={logo} alt={branding.platform_name} width={160} height={32} unoptimized className="h-8 w-auto max-w-40 object-contain" />
      ) : (
        <>
          <span className="text-[15px] font-black tracking-[-0.035em] text-fg sm:text-base">CORE</span>
          <span className="rounded-md bg-primary px-2 py-1 text-[10px] font-black tracking-[0.14em] text-white shadow-sm shadow-primary/20 sm:text-[11px]">PDV</span>
        </>
      )}
      {!compact && (
        <span className="hidden border-l border-subtle pl-2.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted md:inline">
          Gestão operacional
        </span>
      )}
    </Link>
  );
}
