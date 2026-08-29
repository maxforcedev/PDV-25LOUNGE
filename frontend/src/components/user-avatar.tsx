"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { initials } from "@/lib/format";
import { http } from "@/lib/http";

export function UserAvatar({ user, className = "size-9", textClassName = "text-xs" }: {
  user?: { first_name: string; last_name: string; profile_photo_url?: string | null; updated_at?: string } | null;
  className?: string;
  textClassName?: string;
}) {
  const [source, setSource] = useState("");

  useEffect(() => {
    if (!user?.profile_photo_url) { setSource(""); return; }
    let active = true;
    let objectUrl = "";
    http.download(user.profile_photo_url).then(({ blob }) => {
      if (!active) return;
      objectUrl = URL.createObjectURL(blob);
      setSource(objectUrl);
    }).catch(() => active && setSource(""));
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [user?.profile_photo_url, user?.updated_at]);

  return <span className={`flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-primary/10 font-bold text-primary ${textClassName} ${className}`}>
    {source ? <Image src={source} alt="Foto do usuário" width={96} height={96} unoptimized className="size-full object-cover" /> : initials(user?.first_name || "", user?.last_name || "")}
  </span>;
}
