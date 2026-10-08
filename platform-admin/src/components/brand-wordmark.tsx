"use client";

import Link from "next/link";
import { useBranding } from "@/providers/branding-provider";

export function BrandWordmark({ href, className = "", imageClassName = "h-8 max-w-40" }: {
  href: string;
  className?: string;
  imageClassName?: string;
}) {
  const branding = useBranding();
  if (!branding.logo_dark_url) return null;
  return (
    <Link href={href} className={`inline-flex items-center ${className}`} aria-label={branding.platform_name}>
      <img src={branding.logo_dark_url} alt={branding.platform_name} className={`${imageClassName} w-auto object-contain`} />
    </Link>
  );
}
